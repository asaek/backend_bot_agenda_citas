"""Mediciones escalares del laboratorio; sin audio, transcripciones ni red."""

import math
import resource
import statistics
import sys
import time
from copy import deepcopy


PRICING_DATE = "2026-10-20"
PRICING_SOURCE = "https://developers.openai.com/api/docs/pricing"


def _response_cost(record):
    if record.get("model") != "gpt-realtime-2.1":
        return None
    usage = record["usage"]
    incoming, outgoing = usage.get("input_token_details", {}), usage.get("output_token_details", {})
    if any(key not in detail for detail in (incoming, outgoing) for key in ("audio_tokens", "text_tokens")):
        return None
    if incoming.get("image_tokens", 0) or outgoing.get("image_tokens", 0):
        return None
    if any(detail["audio_tokens"] + detail["text_tokens"] != usage.get(total)
           for detail, total in ((incoming, "input_tokens"), (outgoing, "output_tokens"))):
        return None
    if "cached_tokens" not in incoming:
        return None
    cached = incoming["cached_tokens"]
    split = incoming.get("cached_tokens_details", {})
    text_cached, audio_cached = split.get("text_tokens", 0), split.get("audio_tokens", 0)
    if text_cached + audio_cached != cached or text_cached > incoming["text_tokens"] or audio_cached > incoming["audio_tokens"]:
        return None
    return ((incoming["text_tokens"] - text_cached) * 4 + (incoming["audio_tokens"] - audio_cached) * 32
            + cached * .4 + outgoing["text_tokens"] * 24 + outgoing["audio_tokens"] * 64) / 1_000_000


def _transcription_cost(record):
    if record.get("model") != "gpt-4o-mini-transcribe":
        return None
    usage = record["usage"]
    if "input_tokens" not in usage or "output_tokens" not in usage:
        return None
    incoming = usage.get("input_token_details", {})
    if any(key not in incoming for key in ("text_tokens", "audio_tokens")):
        return None
    if incoming["text_tokens"] + incoming["audio_tokens"] != usage["input_tokens"]:
        return None
    # La ficha vigente publica $1.25/M de entrada para este modelo. Conservamos
    # la separacion de modalidades para no estimar a partir de totales ambiguos.
    return (incoming["text_tokens"] * 1.25 + incoming["audio_tokens"] * 1.25 + usage["output_tokens"] * 5) / 1_000_000


def estimated_cost(usage, *, missing_records=0):
    """Un total incompleto es null: el subtotal conocido nunca se presenta como factura."""
    response_costs = [_response_cost(record) for record in usage["responses"]]
    transcription_costs = [_transcription_cost(record) for record in usage["transcriptions"]]
    costs = response_costs + transcription_costs
    unpriced = sum(cost is None for cost in costs) + missing_records
    subtotal = sum(cost for cost in costs if cost is not None)
    return {"currency": "USD", "pricing_date": PRICING_DATE, "pricing_source": PRICING_SOURCE,
            "estimated": True, "complete": unpriced == 0,
            "total_usd": round(subtotal, 8) if not unpriced else None,
            "known_subtotal_usd": round(subtotal, 8), "unpriced_records": unpriced,
            "realtime_usd": round(sum(cost for cost in response_costs if cost is not None), 8),
            "transcription_usd": round(sum(cost for cost in transcription_costs if cost is not None), 8)}


def _distribution(values):
    ordered = sorted(values)
    return {"samples": len(ordered), "p50_ms": round(statistics.median(ordered), 3) if ordered else None,
            "p95_ms": round(ordered[math.ceil(len(ordered) * .95) - 1], 3) if ordered else None}


class VoiceMetrics:
    def __init__(self, *, clock=time.monotonic):
        self.clock = clock
        self._started = clock()
        self._cpu_started = time.process_time()
        self._finished = None
        self._cpu_finished = None
        self._turns = {}
        self._ends = {}
        self._interruptions = []
        self._tools = []

    def speech_stopped(self, item_id):
        self._ends.setdefault(item_id, self.clock())

    def committed(self, turn, item_id, *, received_at=None):
        stopped = self._ends.pop(item_id, None)
        self._turns[turn] = {"turn": turn, "reference": "speech_stopped_received" if stopped is not None else "committed_received",
            "ended_at": stopped if stopped is not None else received_at if received_at is not None else self.clock(),
            "first_audio_received_ms": None, "first_audio_emitted_ms": None, "with_tools": False}

    def audio(self, turn, *, emitted_at=None):
        measurement = self._turns.get(turn)
        if measurement is not None:
            key = "first_audio_received_ms" if emitted_at is None else "first_audio_emitted_ms"
            if measurement[key] is None:
                measurement[key] = round(max(0, (self.clock() if emitted_at is None else emitted_at) - measurement["ended_at"]) * 1000, 3)

    def interruption(self, started_at):
        self._interruptions.append(round(max(0, self.clock() - started_at) * 1000, 3))

    def tool_started(self, turn):
        if turn in self._turns:
            self._turns[turn]["with_tools"] = True
        return self.clock()

    def tool_finished(self, turn, name, started_at):
        self._tools.append({"turn": turn, "tool": name, "duration_ms": round((self.clock() - started_at) * 1000, 3)})

    def finish(self):
        if self._finished is None:
            self._finished, self._cpu_finished = self.clock(), time.process_time()

    def snapshot(self):
        elapsed = max(0, (self._finished if self._finished is not None else self.clock()) - self._started)
        cpu = max(0, (self._cpu_finished if self._cpu_finished is not None else time.process_time()) - self._cpu_started)
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        turns = [{key: value for key, value in row.items() if key != "ended_at"} for row in self._turns.values()]
        no_tools = [row for row in turns if not row["with_tools"]]
        return {"reference_note": "Backend VAD event receipt; excludes preceding VAD/network delay. Emission is local, not browser playback.",
            "turns": turns, "tools": deepcopy(self._tools),
            "local_interruptions_ms": list(self._interruptions),
            "without_tools": {key: _distribution([row[key] for row in no_tools if row[key] is not None])
                              for key in ("first_audio_received_ms", "first_audio_emitted_ms")},
            "end_to_end_targets_ms": {"p50": 1500, "p95": 3000},
            "process": {"elapsed_seconds": round(elapsed, 3), "cpu_seconds": round(cpu, 3),
                        "cpu_percent_one_core": round(100 * cpu / elapsed, 2) if elapsed else 0,
                        "peak_rss_mib_process_lifetime": round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024), 3)}}
