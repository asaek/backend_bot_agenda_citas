"""Prueba acotada en la Pi: WebRTC real, OpenAI real y voz de entrada conocida.

No reproduce audio en dispositivos; informa metricas, nunca transcripciones ni claves.
"""

import asyncio
import json
import os
import sys
import tempfile
import time
import wave
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import av
import httpx
import numpy as np
from aiortc import AudioStreamTrack, RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamError

from calling_repository import CallingRepository
from main import create_lab_app
from openai_realtime_provider import RealtimeSettings


class SampleTrack(AudioStreamTrack):
    def __init__(self):
        super().__init__()
        self.source = wave.open(str(ROOT / "assets/voice-user-sample.wav"), "rb")
        self.enabled = False
        self.position = 0
        self.started_at = None
        self.complete_at = None

    async def recv(self):
        loop = asyncio.get_running_loop()
        if self.started_at is None:
            self.started_at = loop.time()
        await asyncio.sleep(max(0, self.started_at + self.position / 16000 - loop.time()))
        data = self.source.readframes(320) if self.enabled else b""
        if self.enabled and not data and self.complete_at is None:
            self.complete_at = loop.time()
        raw = data + bytes(640 - len(data))
        frame = av.AudioFrame.from_ndarray(np.frombuffer(raw, dtype="<i2").reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate, frame.pts, frame.time_base = 16000, self.position, Fraction(1, 16000)
        self.position += 320
        return frame

    def stop(self):
        self.source.close()
        super().stop()


class ProbeFailure(RuntimeError):
    def __init__(self, row):
        metrics = row.get("metrics", {})
        self.result = {"passed": False, "stage": "conversation", "state": row.get("state"),
                       "failure_type": metrics.get("voice_failure_type"), "error_code": metrics.get("voice_error_code"),
                       "failure_code": metrics.get("voice_failure_code"),
                       "usage": metrics.get("voice_usage")}


async def probe():
    settings = replace(RealtimeSettings.from_environment(), maximum_seconds=60, idle_seconds=30)
    with tempfile.TemporaryDirectory(prefix="realtime-probe-") as directory:
        os.environ["VOICE_DATABASE_PATH"] = str(Path(directory) / "voice.sqlite3")
        os.environ["VOICE_CALENDAR_PROVIDER"] = "fake"
        lab = create_lab_app(enabled=True, audio_mode="realtime", voice_settings=settings,
                             voice_database_path=Path(directory) / "voice.sqlite3",
                             repository=CallingRepository(Path(directory) / "calls.sqlite3"))
        peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        sample = SampleTrack()
        peer.addTrack(sample)
        received = {"non_silent_frames": 0, "seconds": 0.0, "first_followup_at": None}
        tasks = []

        async def receive(track):
            try:
                while True:
                    frame = await track.recv()
                    peak = float(np.max(np.abs(frame.to_ndarray().astype(np.float64))))
                    received["seconds"] += frame.samples / frame.sample_rate
                    if peak > 500:
                        received["non_silent_frames"] += 1
                        if sample.complete_at and received["first_followup_at"] is None:
                            received["first_followup_at"] = asyncio.get_running_loop().time()
            except MediaStreamError:
                pass

        @peer.on("track")
        def incoming(track):
            tasks.append(asyncio.create_task(receive(track)))

        started = time.monotonic()
        try:
            async with lab.router.lifespan_context(lab):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=lab), base_url="http://lab", timeout=25) as client:
                    await peer.setLocalDescription(await peer.createOffer())
                    created = await client.post("/lab/calls", json={"type": "offer", "sdp": peer.localDescription.sdp})
                    if created.status_code != 201:
                        with lab.state.calling_service.repository._connect() as db:
                            metrics = json.loads(db.execute("SELECT metrics_json FROM lab_call_sessions ORDER BY created_at DESC LIMIT 1").fetchone()[0])
                        return {"passed": False, "http_status": created.status_code, "voice_error_code": metrics.get("voice_error_code")}
                    answer = created.json()
                    session_id = answer["session_id"]
                    await peer.setRemoteDescription(RTCSessionDescription(type="answer", sdp=answer["sdp"]))

                    async def state():
                        value = (await client.get(f"/lab/calls/{session_id}")).json()
                        if value["state"] in {"failed", "ended"}:
                            raise ProbeFailure(value)
                        return value

                    async with asyncio.timeout(25):
                        while True:
                            row = await state()
                            history = row["metrics"]["voice_history"]
                            if row["metrics"]["voice_state"] == "listening" and any(item["role"] == "assistant" for item in history):
                                break
                            await asyncio.sleep(.1)
                    initial_frames = received["non_silent_frames"]
                    sample.enabled = True
                    async with asyncio.timeout(30):
                        while True:
                            row = await state()
                            metrics = row["metrics"]
                            assistant = [item for item in metrics["voice_history"] if item["role"] == "assistant"]
                            user = [item for item in metrics["voice_history"] if item["role"] == "user"]
                            if metrics["voice_turn_count"] >= 1 and len(assistant) >= 2 and user and metrics["voice_state"] == "listening":
                                break
                            await asyncio.sleep(.1)
                    final = (await client.delete(f"/lab/calls/{session_id}")).json()
                    latency = received["first_followup_at"] - sample.complete_at if received["first_followup_at"] and sample.complete_at else None
                    assert received["non_silent_frames"] > initial_frames + 20
                    assert final["resources_released"]
                    return {"passed": True, "mode": "real_openai_real_webrtc_same_pi", "model": settings.model,
                            "audio_turns": metrics["voice_turn_count"], "assistant_transcripts": len(assistant),
                            "input_transcripts": len(user), "received_non_silent_frames": received["non_silent_frames"],
                            "sample_end_to_followup_audio_ms": round(latency * 1000) if latency is not None else None,
                            "usage": metrics["voice_usage"], "wall_seconds": round(time.monotonic() - started, 3),
                             "playback_peak_queued_ms": metrics.get("playback_peak_queued_ms"),
                             "performance": final["metrics"].get("voice_performance"),
                             "estimated_cost": final["metrics"].get("voice_cost"),
                            "resources_released": final["resources_released"], "physical_listening": "not_performed"}
        finally:
            sample.stop()
            await peer.close()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    try:
        result = asyncio.run(probe())
    except ProbeFailure as error:
        result = error.result
    except Exception as error:
        result = {"passed": False, "error_type": type(error).__name__}
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
