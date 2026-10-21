"""Sesion de voz nativa: dos transportes, turnos, reproduccion e historial."""

import asyncio
import base64
import json
import os
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
from uuid import uuid4

from agent_instructions import COMMON_AGENT_INSTRUCTIONS
from calendar_domain import Appointment, AppointmentStatus, PatientScope
from calling_service import CallMediaPersistenceError
from fake_calendar_provider import FakeCalendarProvider
from tool_contracts import realtime_tool_definitions
from tool_executor import ToolExecutor
from voice_tools import VoiceTools
from voice_metrics import VoiceMetrics, estimated_cost


VOICE_LAB_MANAGED_BY_VALUE = "whatsapp_voice_lab"
VOICE_CONFIRMATION_TRANSCRIPTION_TIMEOUT_SECONDS = 1.0


def voice_calendar_provider_name(
    environment: Mapping[str, str] | None = None,
) -> str:
    """Devuelve el proveedor de agenda del laboratorio, falso por defecto."""
    values = os.environ if environment is None else environment
    provider_name = values.get("VOICE_CALENDAR_PROVIDER", "fake").strip().lower()
    if provider_name not in {"fake", "google"}:
        raise ValueError("VOICE_CALENDAR_PROVIDER debe ser fake o google")
    return provider_name


def _token_usage(value):
    """Conservar solo contadores del contrato, nunca cuerpos de respuesta."""
    if not isinstance(value, dict):
        return {}
    allowed = {"total_tokens", "input_tokens", "output_tokens", "text_tokens", "audio_tokens", "image_tokens",
               "cached_tokens", "reasoning_tokens", "input_token_details", "output_token_details", "cached_tokens_details"}
    result = {}
    for key in allowed & value.keys():
        item = value[key]
        if isinstance(item, dict):
            result[key] = _token_usage(item)
        elif isinstance(item, int) and not isinstance(item, bool) and item >= 0:
            result[key] = item
    return result


def laboratory_executor(
    repository,
    profile,
    business_hours,
    *,
    environment: Mapping[str, str] | None = None,
    provider_name: str | None = None,
):
    """Compone el alcance ficticio con agenda fake o Google explícita."""
    scope = PatientScope(1, 1, "laboratory:" + profile)
    selected_provider = (
        voice_calendar_provider_name(environment)
        if provider_name is None
        else voice_calendar_provider_name({"VOICE_CALENDAR_PROVIDER": provider_name})
    )
    if selected_provider == "google":
        from google_calendar_provider import create_google_calendar_provider_from_environment

        provider = create_google_calendar_provider_from_environment(
            environment,
            managed_by_value=VOICE_LAB_MANAGED_BY_VALUE,
        )
    else:
        appointments = [Appointment(
            id=item["id"], patient_scope=scope, calendar_id=item["calendar_id"],
            start_at=datetime.fromisoformat(item["start_at"]), end_at=datetime.fromisoformat(item["end_at"]),
            reason=item["reason"], status=AppointmentStatus(item["status"]),
        ) for item in repository.appointments(profile)]
        provider = FakeCalendarProvider(appointments=appointments, appointment_id_prefix="voice-" + uuid4().hex[:12])
    return scope, ToolExecutor(provider=provider, business_hours=business_hours, default_timezone=business_hours.timezone_name)


class VoiceSession:
    def __init__(self, *, session_id, media, provider, repository, settings, business_hours, profile="developer",
                 calendar_provider_name="fake"):
        self.session_id, self.media, self.provider = session_id, media, provider
        self.repository, self.settings, self.business_hours, self.profile = repository, settings, business_hours, profile
        self.calendar_provider_name = voice_calendar_provider_name({
            "VOICE_CALENDAR_PROVIDER": calendar_provider_name,
        })
        self.events = asyncio.Queue(maxsize=16)
        self.tools = None
        self.current_turn = 0
        self._channel_counts = {"voice": 0, "text": 0}
        self._turn_sources = {0: ("voice", 0)}
        self._turn_text = {}
        self._voice_input_turns = {}
        self._turn_transcription_events = {}
        self._input_transcripts = {}
        self._text_waiters = {}
        self._text_outputs = {}
        self._text_publications = {}
        self._generation = 0
        self._closed = False
        self._resources_released = False
        self._finalized = False
        self._media_closed = False
        self._provider_closed = False
        self._began = False
        self._tasks = set()
        self._tool_tasks = set()
        self._receiver_task = None
        self._transcripts_settled = asyncio.Event()
        self._close_lock = asyncio.Lock()
        self._responses = {}
        self._items = {}
        self._inputs = set()
        self._transcribed_inputs = set()
        self._calls = set()
        self._active_response = None
        self._requesting = False
        self._pending_reply = None
        self._speaking = False
        self._state = "preparing"
        self._failure_type = None
        self._failure_code = None
        self._transcripts = {}
        self._usage = {"input_tokens": 0, "output_tokens": 0, "transcription_tokens": 0,
                       "responses": [], "transcriptions": []}
        self._counted_responses = set()
        self._last_activity = asyncio.get_running_loop().time()
        self._reason = "hangup"
        self._input_silence_ms = 0
        self._seen_events = set()
        self._performance = VoiceMetrics()

    @property
    def last_received_at(self):
        return self.media.last_received_at

    @property
    def closed(self):
        return self._closed

    @property
    def metrics(self):
        return {**self.media.metrics, "audio_mode": "realtime", "voice_state": self._state,
                "voice_turn_count": self._channel_counts["voice"], "text_turn_count": self._channel_counts["text"],
                "turn_count": self.current_turn, "voice_tool_calls": len(self._calls),
                "voice_model": self.settings.model, "voice_usage": deepcopy(self._usage),
                "voice_history": list(self._transcripts.values())[-20:], "voice_failure_type": self._failure_type,
                "voice_failure_code": self._failure_code,
                "voice_error_code": getattr(self.provider, "error_code", None),
                 "voice_input_silence_ms": self._input_silence_ms,
                 "voice_performance": self._performance.snapshot(),
                 "voice_cost": estimated_cost(self._usage, missing_records=(
                     len(self._responses.keys() - self._counted_responses)
                     + int(self._requesting)
                     + len(self._inputs - self._transcribed_inputs)
                     + sum(item.get("state") == "transcription_failed" for item in self._transcripts.values()))),
                "confirmation_pending": bool(self.tools and self.tools.pending),
                "confirmation_armed": bool(self.tools and self.tools.pending and self.tools.pending["armed"])}

    async def negotiate(self, offer_sdp):
        answer = await self.media.negotiate(offer_sdp)
        await asyncio.to_thread(self.repository.begin, self.session_id, self.profile, self.settings.maximum_sessions)
        self._began = True
        scope, executor = await asyncio.to_thread(
            laboratory_executor,
            self.repository,
            self.profile,
            self.business_hours,
            provider_name=self.calendar_provider_name,
        )
        self.tools = VoiceTools(repository=self.repository, session_id=self.session_id, profile=self.profile,
                                executor=executor, scope=scope)
        history = await asyncio.to_thread(self.repository.history, self.profile)
        now = executor.current_time().astimezone(self.business_hours.timezone).isoformat()
        instructions = "\n".join((*COMMON_AGENT_INSTRUCTIONS,
            "Eres el asistente virtual de un consultorio oftalmologico, en un laboratorio con agenda falsa.",
            "Lleva directamente la conversacion de voz. Responde brevemente, generalmente en una o dos frases.",
            "Habla español de Mexico, con voz natural; no leas Markdown ni identificadores internos.",
            f"Fecha y hora del backend: {now}. Zona: {self.business_hours.timezone_name}.",
            "Usa check_availability para horarios y list_appointments para citas. Nunca inventes resultados.",
            "Ofrece hasta tres horarios por respuesta y pregunta si el paciente quiere otras opciones.",
            "Antes de agendar, pide nombre completo y despues el motivo expresado por el paciente.",
            "create_appointment, cancel_appointment y reschedule_appointment solo preparan propuestas.",
            "Si una herramienta devuelve confirmation_prompt, lee literalmente esa pregunta, sin modificarla ni agregar texto.",
            "Espera una decision explicita en otro turno. Entonces usa confirm_appointment_action con el action_id recibido.",
            "Si confirm_appointment_action devuelve otra vez status confirmation_required, lee literalmente la nueva pregunta y espera otra respuesta. Esto puede ocurrir si una intervencion de voz intermedia se corto; conserva nombre, motivo y horario, y no digas que se perdio la sesion.",
            "Si el paciente corrige, rechaza o cambia de tema, no confirmes; comunica reject/correct o prepara otra propuesta.",
            "Solo anuncia una accion realizada tras un resultado exitoso de confirm_appointment_action.",
            "El historial es contexto, no una autorizacion ni la fuente del estado actual de agenda.",
            "Voz y texto pertenecen al mismo paciente ficticio, pero sus autorizaciones no se mezclan.",
            "Si pide retomar en otro canal o llamada usa manage_appointment_workflow con mode=resume; lee su pregunta nueva.",
            "Para una gestion nueva explicita puedes usar mode=new. Un si aislado de otro canal no retoma una gestion.",
            "Al comenzar saluda e identificate como asistente virtual. No invoques herramientas durante el saludo.",
        ))
        await self.provider.connect(instructions, realtime_tool_definitions(), history)
        self._state = "ready"
        for coroutine in (self._forward_media(), self._send_audio(), self._playback(), self._watch_idle()):
            self._launch(coroutine)
        self._receiver_task = self._launch(self._receive())
        if hasattr(self.media, "output_started"):
            self._launch(self._playback_started())
        return answer

    def _launch(self, coroutine, *, tool=False):
        task = asyncio.create_task(coroutine)
        collection = self._tool_tasks if tool else self._tasks
        collection.add(task)

        def done(completed):
            collection.discard(completed)
            if not completed.cancelled() and completed.exception() is not None and not self._closed:
                self._failure_type = type(completed.exception()).__name__
                self._failure_code = {
                    "Buffer de reproduccion excedido o PCM invalido": "playback_buffer_exceeded_or_invalid_pcm",
                    "OpenAI no pudo generar la respuesta": "response_failed",
                    "Realtime rechazo un evento": "event_rejected",
                    "Limite de respuestas de la sesion alcanzado": "response_limit",
                    "Limite de turnos alcanzado": "turn_limit",
                    "Solicitud de herramienta excedida": "tool_limit",
                }.get(str(completed.exception()), "voice_task_failed")
                self._state, self._reason = "failed", "voice_failed"
                self._finish_text_waiters("failed", "No se pudo completar la respuesta")
                self._emit("media_failed")

        task.add_done_callback(done)
        return task

    def _emit(self, event):
        if not self._closed and not self.events.full():
            self.events.put_nowait(event)

    async def _forward_media(self):
        while True:
            event = await self.media.events.get()
            self._emit(event)
            if event == "connected" and self.current_turn == 0 and not self._responses and not self._requesting:
                self._pending_reply = (self.current_turn, self._generation)
                await self._maybe_respond()

    async def _send_audio(self):
        while True:
            try:
                pcm = await asyncio.wait_for(self.media.input_audio.get(), timeout=.1)
            except TimeoutError:
                if self.media.last_received_at is None:
                    continue
                # DTX o una fuente WebAudio finalizada puede dejar de producir
                # frames. Realtime necesita conservar el reloj y observar silencio
                # para que VAD consolide el final de la intervencion.
                pcm = bytes(4800)  # PCM16 mono, 24 kHz, 100 ms.
                self._input_silence_ms += 100
            await self.provider.send({"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm).decode("ascii")})

    async def _maybe_respond(self):
        if self._closed or self._speaking or self._active_response or self._requesting or self._tool_tasks or not self._pending_reply:
            return
        turn, generation = self._pending_reply
        self._pending_reply = None
        if generation != self._generation:
            return
        if len(self._responses) >= 64:
            raise ValueError("Limite de respuestas de la sesion alcanzado")
        self._requesting = True
        self._state = "responding"
        channel, sequence = self._turn_sources.get(turn, ("voice", turn))
        response = {"metadata": {"voice_turn": str(turn), "voice_generation": str(generation),
                                 "source_channel": channel, "source_sequence": str(sequence)}}
        if channel == "text":
            response["output_modalities"] = ["text"]
        await self.provider.send({"type": "response.create", "response": response})

    def _finish_text_waiters(self, state, reply):
        for future in self._text_waiters.values():
            if not future.done():
                future.set_result({"state": state, "reply": reply, "session_id": self.session_id})

    async def submit_text(self, text: str):
        """Entrada de texto real, no una transcripcion fingida ni una identidad del cliente."""
        if self._closed:
            raise ValueError("La sesion esta cerrada")
        generation = await self._interrupt()
        if generation != self._generation or self._closed:
            return {"state": "interrupted", "reply": "Otra intervencion reemplazo el mensaje antes de procesarlo.",
                    "session_id": self.session_id, "usage": deepcopy(self._usage)}
        self._speaking = False
        self.current_turn += 1
        self._channel_counts["text"] += 1
        turn = self.current_turn
        self._turn_sources[turn] = ("text", self._channel_counts["text"])
        self._turn_text[turn] = text
        self.tools.current_turn = turn
        item_id = "text_" + uuid4().hex[:24]
        self._inputs.add(item_id)
        self._transcribed_inputs.add(item_id)
        future = asyncio.get_running_loop().create_future()
        self._text_waiters[turn] = future
        self._text_outputs[turn] = []
        self._last_activity = asyncio.get_running_loop().time()
        try:
            await self._transcript(item_id, "user", text, channel="text")
            if generation == self._generation and not future.done():
                await self.provider.send({"type": "conversation.item.create", "item": {
                    "id": item_id, "type": "message", "role": "user", "content": [{"type": "input_text", "text": text}],
                }})
            if generation == self._generation and not future.done():
                self._pending_reply = (turn, generation)
                await self._maybe_respond()
            result = await asyncio.wait_for(asyncio.shield(future), timeout=min(60, self.settings.maximum_seconds))
            return {**result, "usage": deepcopy(self._usage)}
        except (TimeoutError, asyncio.CancelledError):
            if turn == self.current_turn and not self._closed:
                await self._interrupt()
            raise
        finally:
            self._text_waiters.pop(turn, None)
            self._text_outputs.pop(turn, None)

    async def _receive(self):
        while True:
            await self._handle(await self.provider.receive())

    async def _handle(self, event):
        kind = event.get("type")
        if self._closed and kind not in {"conversation.item.input_audio_transcription.completed",
                                       "conversation.item.input_audio_transcription.failed", "response.done"}:
            return
        event_id = event.get("event_id")
        if isinstance(event_id, str):
            if event_id in self._seen_events:
                return
            if len(self._seen_events) >= 65536:
                raise ValueError("Limite de eventos Realtime alcanzado")
            self._seen_events.add(event_id)
        if kind == "error":
            if event.get("error", {}).get("code") != "response_cancel_not_active":
                raise ValueError("Realtime rechazo un evento")
        elif kind == "input_audio_buffer.speech_started":
            self._speaking = True
            self._last_activity = asyncio.get_running_loop().time()
            await self._interrupt()
        elif kind == "input_audio_buffer.speech_stopped":
            self._performance.speech_stopped(event["item_id"])
        elif kind == "input_audio_buffer.committed":
            received_at = self._performance.clock()
            item_id = event["item_id"]
            if item_id in self._inputs:
                return
            if len(self._inputs) >= 128:
                raise ValueError("Limite de turnos alcanzado")
            if not self._speaking:
                generation = await self._interrupt()
                if generation != self._generation:
                    return
            else:
                generation = self._generation
            self._inputs.add(item_id)
            self._transcripts_settled.clear()
            self.current_turn += 1
            turn = self.current_turn
            self._performance.committed(turn, item_id, received_at=received_at)
            self._channel_counts["voice"] += 1
            self._turn_sources[self.current_turn] = ("voice", self._channel_counts["voice"])
            self._voice_input_turns[item_id] = turn
            self._turn_transcription_events[turn] = asyncio.Event()
            if item_id in self._input_transcripts:
                self._turn_text[turn] = self._input_transcripts[item_id]
                self._turn_transcription_events[turn].set()
            elif item_id in self._transcribed_inputs:
                self._turn_transcription_events[turn].set()
            self.tools.current_turn = self.current_turn
            self._speaking = False
            self._last_activity = asyncio.get_running_loop().time()
            self._cache_turn(item_id, "user", "voice", state="received")
            await asyncio.to_thread(self.repository.turn, self.session_id, item_id, "user", None, "received", "voice", self._transcripts[item_id]["sequence"])
            if generation != self._generation:
                return
            self._pending_reply = (turn, generation)
            await self._maybe_respond()
            self._update_state()
        elif kind == "conversation.item.input_audio_transcription.completed":
            if event["item_id"] in self._transcribed_inputs:
                return
            self._transcribed_inputs.add(event["item_id"])
            transcript = event.get("transcript", "")
            self._input_transcripts[event["item_id"]] = transcript
            turn = self._voice_input_turns.get(event["item_id"])
            if turn is not None:
                self._turn_text[turn] = transcript
            await self._transcript(event["item_id"], "user", transcript)
            if turn is not None:
                self._turn_transcription_events[turn].set()
            usage = _token_usage(event.get("usage"))
            self._usage["transcription_tokens"] += usage.get("total_tokens", 0)
            self._usage["transcriptions"].append({"item_id": event["item_id"], "model": self.settings.transcription_model, "usage": usage})
            if self._inputs <= self._transcribed_inputs:
                self._transcripts_settled.set()
        elif kind == "conversation.item.input_audio_transcription.failed":
            if event["item_id"] in self._transcribed_inputs:
                return
            self._transcribed_inputs.add(event["item_id"])
            turn = self._voice_input_turns.get(event["item_id"])
            self._failure_type = "InputTranscriptionFailed"
            self._cache_turn(event["item_id"], "user", "voice", state="transcription_failed")
            await asyncio.to_thread(self.repository.turn, self.session_id, event["item_id"], "user", None, "transcription_failed")
            if turn is not None:
                self._turn_transcription_events[turn].set()
            if self._inputs <= self._transcribed_inputs:
                self._transcripts_settled.set()
        elif kind == "response.created":
            response = event["response"]
            if response["id"] in self._responses:
                return
            metadata = response.get("metadata") or {}
            generation = int(metadata.get("voice_generation", -1))
            turn = int(metadata.get("voice_turn", -1))
            channel, sequence = self._turn_sources.get(turn, ("voice", turn))
            self._responses[response["id"]] = {"generation": generation, "turn": turn,
                                               "channel": channel, "channel_turn": sequence}
            self._requesting = False
            self._active_response = response["id"]
            if generation != self._generation:
                await self.provider.send({"type": "response.cancel", "response_id": response["id"]})
            else:
                self._state = "responding"
        elif kind == "response.done":
            response = event["response"]
            response_id = response["id"]
            if response_id not in self._counted_responses:
                self._counted_responses.add(response_id)
                usage = _token_usage(response.get("usage"))
                for key in ("input_tokens", "output_tokens"):
                    self._usage[key] += usage.get(key, 0)
                self._usage["responses"].append({"response_id": response_id, "model": self.settings.model, "usage": usage})
            generated_state = "completed" if response.get("status") == "completed" else "cancelled" if response.get("status") == "cancelled" else "failed"
            for item_id, item in self._items.items():
                if item["response_id"] == response_id:
                    if item["generation_state"] == "generating":
                        item["generation_state"] = generated_state
                    self._cache_turn(item_id, "assistant", item["channel"], generation_state=item["generation_state"], generated_ms=item["generated_ms"])
                    await asyncio.to_thread(self.repository.progress, self.session_id, item_id,
                                            generated_ms=item["generated_ms"], generation_state=generated_state)
            if self._closed:
                return
            if self._active_response == response_id:
                self._active_response = None
            if response.get("status") == "failed":
                raise ValueError("OpenAI no pudo generar la respuesta")
            if self._valid_response(response_id):
                has_tools = any(item.get("type") == "function_call" for item in response.get("output", []))
                if not has_tools:
                    source = self._responses[response_id]
                    await self.tools.end_turn(source["turn"], channel=source["channel"], channel_turn=source["channel_turn"])
                    future = self._text_waiters.get(source["turn"])
                    if source["channel"] == "text" and future and not future.done():
                        future.set_result({"state": "completed", "reply": "\n".join(self._text_outputs.get(source["turn"], [])),
                                           "session_id": self.session_id, "turn_id": source["turn"]})
            await self._maybe_respond()
            self._update_state()
        elif kind.startswith("response.") and self._valid_response(event.get("response_id")):
            if kind == "response.output_item.added" and event.get("item", {}).get("type") == "message":
                item_id = event["item"]["id"]
                item = self._item(item_id, event["response_id"])
                self._cache_turn(item_id, "assistant", item["channel"], state="generating", generation_state="generating")
                await asyncio.to_thread(self.repository.turn, self.session_id, item_id, "assistant", None, "generating", item["channel"], self._transcripts[item_id]["sequence"])
            elif kind == "response.output_audio.delta":
                item_id = event["item_id"]
                item = self._item(item_id, event["response_id"])
                if not item["interrupted"]:
                    pcm = item["pcm_remainder"] + base64.b64decode(event["delta"], validate=True)
                    complete_length = len(pcm) - len(pcm) % 2
                    item["pcm_remainder"] = pcm[complete_length:]
                    pcm = pcm[:complete_length]
                    if not pcm:
                        return
                    self._performance.audio(self._responses[event["response_id"]]["turn"])
                    item["generated_ms"] += len(pcm) / 48
                    self.media.output_audio(item_id, pcm)
                    self._cache_turn(item_id, "assistant", item["channel"], state="playing", generated_ms=item["generated_ms"], generation_state=item["generation_state"])
                    if not item["started"]:
                        item["started"] = True
                        await asyncio.to_thread(self.repository.turn, self.session_id, item_id, "assistant", None, "playing", item["channel"], self._transcripts[item_id]["sequence"])
            elif kind == "response.output_audio.done":
                item = self._item(event["item_id"], event["response_id"])
                if item["pcm_remainder"]:
                    raise ValueError("PCM de salida incompleto")
                self.media.output_done(event["item_id"])
            elif kind == "response.output_audio_transcript.done":
                item_id = event["item_id"]
                item = self._item(item_id, event["response_id"])
                text = event.get("transcript", "")
                await self._transcript(item_id, "assistant", text, channel=item["channel"])
                self.tools.bind_prompt(item_id, text)
                if item["drained"] and not item["interrupted"]:
                    self.tools.emitted(item_id)
            elif kind == "response.output_text.done":
                source = self._responses[event["response_id"]]
                if source["channel"] != "text":
                    return
                item_id, text = event["item_id"], event.get("text", "")
                item = self._item(item_id, event["response_id"])
                await self._transcript(item_id, "assistant", text, channel="text")
                await asyncio.to_thread(self.repository.turn, self.session_id, item_id, "assistant", None, "prepared", "text")
                self._cache_turn(item_id, "assistant", "text", state="prepared")
                self.tools.bind_prompt(item_id, text)
                publications = self._text_publications.setdefault(source["turn"], [])
                if item_id not in publications:
                    publications.append(item_id)
                outputs = self._text_outputs.get(source["turn"])
                if outputs is not None and not item.get("text_published"):
                    outputs.append(text)
                item["text_published"] = True
            elif kind == "response.function_call_arguments.done":
                call_id = event["call_id"]
                if call_id not in self._calls:
                    if len(self._calls) >= 32 or len(event.get("arguments", "")) > 16384:
                        raise ValueError("Solicitud de herramienta excedida")
                    arguments = json.loads(event["arguments"])
                    if not isinstance(arguments, dict):
                        raise ValueError("Argumentos de herramienta invalidos")
                    self._calls.add(call_id)
                    response = self._responses[event["response_id"]]
                    self._launch(self._execute_tool(call_id, event["name"], arguments, response["turn"], response["generation"]), tool=True)

    def _valid_response(self, response_id):
        response = self._responses.get(response_id)
        return response is not None and response["generation"] == self._generation

    def _playing(self):
        return any(item["started"] and not item["drained"] and not item["interrupted"] for item in self._items.values())

    def _update_state(self):
        if self._closed or self._failure_code:
            return
        if self._playing():
            self._state = "playing"
        elif self._active_response or self._requesting or self._tool_tasks or self._pending_reply:
            self._state = "responding"
        else:
            self._state = "listening"

    def _item(self, item_id, response_id):
        return self._items.setdefault(item_id, {"response_id": response_id, "started": False, "drained": False,
            "interrupted": False, "generation_state": "generating", "generated_ms": 0.0, "pcm_remainder": b"",
            "channel": self._responses.get(response_id, {}).get("channel", "voice")})

    def _cache_turn(self, item_id, role, channel, **updates):
        item = self._transcripts.setdefault(item_id, {"item_id": item_id, "role": role, "channel": channel,
            "sequence": len(self._transcripts) + 1, "text": "", "state": "received"})
        item.update(updates)

    async def _transcript(self, item_id, role, text, channel="voice"):
        self._cache_turn(item_id, role, channel, text=text[:8000], **({"state": "completed"} if role == "user" else {}))
        await asyncio.to_thread(self.repository.turn, self.session_id, item_id, role, text, "completed" if role == "user" else None, channel, self._transcripts[item_id]["sequence"])

    async def publish_text(self, turn: int):
        """Confirmar publicacion solo despues de emitir el cuerpo HTTP completo."""
        if self._closed:
            return
        for item_id in self._text_publications.get(turn, ()):
            item = self._items.get(item_id)
            if item is None or item["interrupted"]:
                continue
            await asyncio.to_thread(self.repository.turn, self.session_id, item_id, "assistant", None, "completed", "text")
            if not item["interrupted"] and not self._closed:
                item["drained"] = True
                self._cache_turn(item_id, "assistant", "text", state="completed")
                self.tools.emitted(item_id)
        self._text_publications.pop(turn, None)

    async def _execute_tool(self, call_id, name, arguments, turn, generation):
        channel, sequence = self._turn_sources.get(turn, ("voice", turn))
        started = self._performance.tool_started(turn)
        try:
            pending = self.tools.pending
            if (
                name == "confirm_appointment_action"
                and channel == "voice"
                and pending
                and sequence > pending["channel_turn"] + 1
            ):
                transcript_ready = self._turn_transcription_events.get(turn)
                if transcript_ready is not None and not transcript_ready.is_set():
                    try:
                        await asyncio.wait_for(
                            transcript_ready.wait(),
                            timeout=VOICE_CONFIRMATION_TRANSCRIPTION_TIMEOUT_SECONDS,
                        )
                    except TimeoutError:
                        pass
            result = await self.tools.execute(call_id, name, arguments, turn, generation=generation,
                                              channel=channel, channel_turn=sequence, source_text=self._turn_text.get(turn))
        finally:
            self._performance.tool_finished(turn, name, started)
        if self._closed:
            return
        await self.provider.send({"type": "conversation.item.create", "item": {
            "type": "function_call_output", "call_id": call_id, "output": json.dumps(result, ensure_ascii=False),
        }})
        if generation == self._generation:
            self._pending_reply = (turn, generation)
        # El propio task aun aparece en _tool_tasks hasta retornar.
        asyncio.get_running_loop().call_soon(self._respond_after_tools)

    def _respond_after_tools(self):
        if not self._closed:
            self._launch(self._maybe_respond())

    async def _interrupt(self):
        started_at = self._performance.clock()
        was_playing = self._playing()
        self._generation += 1
        generation = self._generation
        self.tools.supersede(self._generation)
        self._pending_reply = None
        self._finish_text_waiters("interrupted", "La respuesta se interrumpio; el historial conserva los resultados ya ejecutados.")
        # El audio local se corta antes de esperar una escritura de red.
        emitted = self.media.interrupt_output()
        if was_playing:
            self._performance.interruption(started_at)
        interrupted = tuple((item_id, item) for item_id, item in self._items.items()
                            if not item["drained"] and not item["interrupted"])
        for item_id, item in interrupted:
            item["interrupted"] = True
            item["cancellation_requested"] = True
        if self._active_response:
            await self.provider.send({"type": "response.cancel", "response_id": self._active_response})
        for item_id, item in interrupted:
            if item["started"]:
                await self.provider.send({"type": "conversation.item.truncate", "item_id": item_id,
                                          "content_index": 0, "audio_end_ms": emitted.get(item_id, 0)})
            else:
                await self.provider.send({"type": "conversation.item.delete", "item_id": item_id})
            await asyncio.to_thread(self.repository.turn, self.session_id, item_id, "assistant", None, "interrupted")
            await asyncio.to_thread(self.repository.progress, self.session_id, item_id,
                generated_ms=item["generated_ms"], emitted_ms=emitted.get(item_id, 0), generation_state=item["generation_state"])
            self._cache_turn(item_id, "assistant", item["channel"], state="interrupted", generation_state=item["generation_state"],
                             generated_ms=item["generated_ms"], emitted_ms=emitted.get(item_id, 0))
        await self.tools.interrupt(generation)
        if generation == self._generation:
            self._state = "listening"
        return generation

    async def _playback_started(self):
        while True:
            item_id, started_at = await self.media.output_started.get()
            item = self._items.get(item_id)
            if item:
                response = self._responses[item["response_id"]]
                self._performance.audio(response["turn"], emitted_at=started_at)

    async def _playback(self):
        while True:
            item_id, emitted_ms = await self.media.output_events.get()
            item = self._items.get(item_id)
            if item and item["started"] and emitted_ms > 0 and not item["interrupted"]:
                item["drained"] = True
                self.tools.emitted(item_id)
                await asyncio.to_thread(self.repository.turn, self.session_id, item_id, "assistant", None, "completed")
                await asyncio.to_thread(self.repository.progress, self.session_id, item_id,
                                        generated_ms=item["generated_ms"], emitted_ms=emitted_ms)
                self._cache_turn(item_id, "assistant", item["channel"], state="completed", emitted_ms=emitted_ms)
                self._last_activity = asyncio.get_running_loop().time()
                self._update_state()

    async def _watch_idle(self):
        while True:
            await asyncio.sleep(.25)
            now = asyncio.get_running_loop().time()
            if self._speaking or self._active_response or self._requesting or self._tool_tasks or self._pending_reply or self._playing():
                self._last_activity = now
            elif now - self._last_activity >= self.settings.idle_seconds:
                self._reason = "voice_idle_timeout"
                self._emit("disconnected")
                return

    async def close(self):
        async with self._close_lock:
            if self._finalized:
                return
            self._closed = True
            self._finish_text_waiters("interrupted", "La sesion termino; la respuesta no se emitio completa.")
            if self.tools:
                self.tools.closed = True
                self.tools.pending = None
            if not self._resources_released:
                emitted = self.media.interrupt_output()
                for item_id, item in self._items.items():
                    if not item["drained"]:
                        item["interrupted"] = True
                        self._cache_turn(item_id, "assistant", item["channel"], state="interrupted",
                            generated_ms=item["generated_ms"], emitted_ms=emitted.get(item_id, 0),
                            generation_state=item["generation_state"])
                workers = tuple(task for task in self._tasks if task is not self._receiver_task)
                for task in workers:
                    task.cancel()
                await asyncio.gather(*workers, return_exceptions=True)
                try:
                    if not self._media_closed:
                        await self.media.close()
                        self._media_closed = True
                finally:
                    try:
                        await asyncio.gather(*self._tool_tasks, return_exceptions=True)
                        if self._inputs - self._transcribed_inputs and self._receiver_task and not self._receiver_task.done():
                            try:
                                await asyncio.wait_for(self._transcripts_settled.wait(), timeout=1)
                            except TimeoutError:
                                pass
                    finally:
                        if self._receiver_task:
                            self._receiver_task.cancel()
                            await asyncio.gather(self._receiver_task, return_exceptions=True)
                        if not self._provider_closed:
                            await self.provider.close()
                            self._provider_closed = True
                self._resources_released = self._media_closed and self._provider_closed
            self._state = "closed"
            self._performance.finish()
            if self._began:
                try:
                    for item_id, item in self._items.items():
                        cached = self._transcripts.get(item_id, {})
                        if item["interrupted"]:
                            await asyncio.to_thread(self.repository.turn, self.session_id, item_id, "assistant", None, "interrupted", item["channel"])
                        generation_state = item["generation_state"] if item["generation_state"] != "generating" else "unknown"
                        self._cache_turn(item_id, "assistant", item["channel"], generation_state=generation_state)
                        await asyncio.to_thread(self.repository.progress, self.session_id, item_id,
                            generated_ms=item["generated_ms"], emitted_ms=cached.get("emitted_ms", 0),
                            generation_state=generation_state)
                    await asyncio.to_thread(self.repository.finish, self.session_id, self._reason, self.metrics)
                except Exception:
                    raise CallMediaPersistenceError(resources_released=self._resources_released) from None
            self._finalized = True
