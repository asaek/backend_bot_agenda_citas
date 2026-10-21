"""Herramientas de voz: identidad del servidor y confirmacion ligada a emision/turno."""

import asyncio
import json
import re
import unicodedata
from datetime import timedelta

from agent_orchestrator import execute_agent_tool, serialize_tool_result
from calendar_domain import PatientScope, ToolName, ToolRequest
from llm_provider import ToolCall
from booking_details import BookingDetails
from tool_contracts import parse_tool_request
from tool_validation import validate_tool_input
from voice_authorization import VoiceAuthorization
from appointment_confirmation import (
    ConfirmationDecision,
    classify_action_confirmation,
)
from conversation_intent import PendingConversationFlow, PendingInterruption, classify_pending_interruption, is_resume_request


MUTATIONS = {"create_appointment", "cancel_appointment", "reschedule_appointment"}


def prompt_fingerprint(text: str) -> str:
    text = unicodedata.normalize("NFD", text.casefold())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in text if not unicodedata.combining(c)))


def appointment_payload(appointment):
    return {"id": appointment.id, "calendar_id": appointment.calendar_id,
            "start_at": appointment.start_at.isoformat(), "end_at": appointment.end_at.isoformat(),
            "reason": appointment.reason, "status": appointment.status.value}


class VoiceTools:
    def __init__(self, *, repository, session_id: str, profile: str, executor, scope: PatientScope):
        self.repository, self.session_id, self.profile = repository, session_id, profile
        self.executor, self.scope = executor, scope
        self.pending = None
        self._interrupted_proposal = None
        self.authorization = VoiceAuthorization()
        self._closed = False
        self._lock = asyncio.Lock()
        self.calls = 0
        self.current_turn = None
        self._workflow_channel = None

    @property
    def closed(self):
        return self._closed

    @closed.setter
    def closed(self, value):
        self._closed = value
        if value:
            self.authorization.close()
            self._interrupted_proposal = None

    def supersede(self, generation: int):
        self.authorization.supersede(generation)

    def _current(self, turn, generation):
        return self.authorization.valid(generation) and self.current_turn in (None, turn)

    async def execute(self, call_id: str, name: str, arguments: dict, turn: int, generation: int | None = None,
                      *, channel: str = "voice", channel_turn: int | None = None, source_text: str | None = None) -> dict:
        generation = self.authorization.generation if generation is None else generation
        channel_turn = turn if channel_turn is None else channel_turn
        if channel not in {"voice", "text"}:
            return {"ok": False, "error": "Canal invalido"}
        async with self._lock:
            if turn <= 0 or not self._current(turn, generation):
                return {"ok": False, "error": "Se requiere un turno de audio activo"}
            request = {"name": name, "arguments": arguments}
            fresh, previous = await asyncio.to_thread(self.repository.claim_tool, self.session_id, call_id, request)
            if not fresh:
                return previous
            self.calls += 1
            try:
                if self.calls > 32:
                    raise ValueError("Limite de herramientas de la sesion alcanzado")
                if not self._current(turn, generation):
                    raise ValueError("El turno fue reemplazado")
                if name == "manage_appointment_workflow":
                    if channel == "text" and (
                        source_text is None or
                        (arguments.get("mode") == "resume" and not is_resume_request(source_text)) or
                        (arguments.get("mode") == "new" and classify_pending_interruption(
                            source_text, flow=PendingConversationFlow.APPOINTMENT_CONFIRMATION,
                        ) is not PendingInterruption.SWITCH)
                    ):
                        raise ValueError("El texto debe pedir explicitamente retomar o iniciar otra gestion")
                    result = await self._manage(arguments, turn, generation, channel, channel_turn)
                    await asyncio.to_thread(self.repository.tool_result, self.session_id, call_id, result)
                    return result
                if name == "confirm_appointment_action":
                    return await self._confirm(call_id, arguments, turn, generation, channel, channel_turn, source_text)
                if name in MUTATIONS:
                    last = self.pending or await asyncio.to_thread(self.repository.latest_action, self.profile)
                    if last and last.get("channel", "voice") != channel and self._workflow_channel != channel:
                        raise ValueError("La gestion pertenece al otro canal. Usa manage_appointment_workflow para retomarla o iniciar una nueva.")
                if self.pending is None or self.pending.get("channel", "voice") == channel:
                    await self.invalidate()
                if name in MUTATIONS:
                    result = await self._propose(name, arguments, turn, generation, channel, channel_turn)
                else:
                    if name not in {"check_availability", "list_appointments"}:
                        raise ValueError("Herramienta no permitida")
                    if name == "check_availability":
                        parsed = parse_tool_request(ToolRequest(ToolName(name), arguments, self.scope), default_timezone=self.executor.default_timezone)
                        if parsed.end_at - parsed.start_at > timedelta(days=7):
                            raise ValueError("Consulta un rango de hasta siete dias")
                    result = json.loads(serialize_tool_result(await execute_agent_tool(self.executor, ToolCall(name, arguments, call_id), self.scope)))
                    if result.get("ok"):
                        for key in ("slots", "appointments"):
                            values = result.get("data", {}).get(key)
                            if isinstance(values, list) and len(values) > 20:
                                result["data"][key] = values[:20]
                                result["has_more"] = True
                await asyncio.to_thread(self.repository.tool_result, self.session_id, call_id, result)
                return result
            except (ValueError, TypeError, KeyError) as error:
                # Solo errores de validacion propios; no cuerpos de red ni SQL.
                result = {"ok": False, "error": str(error)[:300]}
                await asyncio.to_thread(self.repository.tool_result, self.session_id, call_id, result)
                return result

    async def _propose(self, name, arguments, turn, generation, channel="voice", channel_turn=None):
        channel_turn = turn if channel_turn is None else channel_turn
        arguments = dict(arguments)
        patient_name = None
        if name == "create_appointment":
            details = BookingDetails.from_patient_texts(arguments.pop("patient_name", ""), arguments.get("reason", ""))
            if len(details.reason) > 1000:
                raise ValueError("Solicita un motivo comprensible expresado por el paciente")
            patient_name = details.patient_name
            arguments["reason"] = details.reason
        parsed = parse_tool_request(ToolRequest(ToolName(name), arguments, self.scope), default_timezone=self.executor.default_timezone)
        existing = await self.executor.provider.list_appointments(patient_scope=self.scope)
        validate_tool_input(parsed, business_hours=self.executor.business_hours, now=self.executor.current_time(), existing_appointments=existing)
        appointment = None
        if name != "create_appointment":
            appointment = next((item for item in existing if item.id == parsed.appointment_id), None)
            if appointment is None:
                raise ValueError("Primero identifica una cita del paciente mediante list_appointments")
        start_at = parsed.start_at if name == "create_appointment" else parsed.new_start_at if name == "reschedule_appointment" else appointment.start_at
        if name != "cancel_appointment":
            slots = await self.executor.availability_provider.check_availability(start_at=start_at, end_at=start_at + timedelta(minutes=30))
            if not any(slot.start_at == start_at for slot in slots):
                raise ValueError("El horario ya no esta disponible; consulta otra opcion")
        if not self._current(turn, generation):
            raise ValueError("El turno fue reemplazado; solicita una propuesta nueva")
        local = start_at.astimezone(self.executor.business_hours.timezone)
        when = local.strftime("%Y-%m-%d a las %I:%M %p")
        if name == "create_appointment":
            prompt = f"¿Confirmas agendar la cita para el {when}, a nombre de {patient_name}, por {arguments['reason']}?"
        elif name == "reschedule_appointment":
            old = appointment.start_at.astimezone(self.executor.business_hours.timezone).strftime("%Y-%m-%d a las %I:%M %p")
            prompt = f"¿Confirmas cambiar la cita del {old}, por {appointment.reason}, al {when}?"
        else:
            prompt = f"¿Confirmas cancelar la cita del {when}, por {appointment.reason}?"
        action_id = await asyncio.to_thread(self.repository.propose, self.session_id, str(turn), {
            "name": name, "arguments": arguments, "patient_name": patient_name,
            "channel": channel, "channel_turn": channel_turn,
        }, prompt)
        if not self._current(turn, generation):
            await asyncio.to_thread(self.repository.invalidate_action, self.session_id, action_id)
            raise ValueError("El turno fue reemplazado; solicita una propuesta nueva")
        self.pending = {"id": action_id, "name": name, "arguments": arguments, "patient_name": patient_name,
                         "turn": turn, "prompt": prompt, "armed": False, "item_id": None,
                         "channel": channel, "channel_turn": channel_turn,
                        "expires": asyncio.get_running_loop().time() + 600}
        return {"ok": True, "status": "confirmation_required", "action_id": action_id,
                "confirmation_prompt": prompt, "instruction": "Lee literalmente esta pregunta; espera la respuesta del paciente en otro turno. No anuncies exito."}

    async def _confirm(self, call_id, arguments, turn, generation, channel, channel_turn, source_text):
        pending = self.pending
        if set(arguments) != {"action_id", "decision"} or arguments["decision"] not in {"confirm", "reject", "correct"}:
            raise ValueError("Decision de confirmacion invalida")
        interrupted = pending is None and self._interrupted_proposal is not None
        if interrupted:
            pending = self._interrupted_proposal
        if not pending or arguments["action_id"] != pending["id"]:
            raise ValueError("No hay una propuesta vigente en esta llamada")
        if pending.get("channel", "voice") != channel:
            raise ValueError("La pregunta pertenece al otro canal. Retoma la gestion para recibir una pregunta nueva aqui.")
        if channel == "text" and arguments["decision"] == "confirm":
            if source_text is None or _classify_pending_confirmation(source_text, pending) is not ConfirmationDecision.CONFIRMED:
                raise ValueError("El texto recibido no es una afirmacion completa de la accion pendiente")
        if arguments["decision"] != "confirm":
            await self.invalidate()
            result = {"ok": True, "status": "not_executed", "instruction": "La operacion no se realizo; solicita los datos corregidos si corresponde."}
            await asyncio.to_thread(self.repository.tool_result, self.session_id, call_id, result)
            return result
        if interrupted:
            result = await self._renew_confirmation(pending, turn, generation, channel, channel_turn)
            await asyncio.to_thread(self.repository.tool_result, self.session_id, call_id, result)
            return result
        if not pending["armed"] or asyncio.get_running_loop().time() >= pending["expires"]:
            # Una pregunta incompleta o vencida nunca autoriza la accion, aunque
            # una transcripcion posterior contenga una afirmacion.
            result = await self._renew_confirmation(pending, turn, generation, channel, channel_turn)
            await asyncio.to_thread(self.repository.tool_result, self.session_id, call_id, result)
            return result
        if channel_turn != pending["channel_turn"] + 1:
            explicit_voice_confirmation = (
                channel == "voice"
                and channel_turn > pending["channel_turn"] + 1
                and source_text is not None
                and _classify_pending_confirmation(source_text, pending) is ConfirmationDecision.CONFIRMED
            )
            if not explicit_voice_confirmation:
                # Si VAD cancelo una respuesta intermedia, solo una afirmacion
                # transcrita de la intervencion actual puede confirmar el cambio.
                result = await self._renew_confirmation(pending, turn, generation, channel, channel_turn)
                await asyncio.to_thread(self.repository.tool_result, self.session_id, call_id, result)
                return result
        if not self._current(turn, generation) or not await asyncio.to_thread(
            self.repository.execute_action, self.session_id, pending["id"], self.authorization, generation,
        ):
            raise ValueError("La accion ya no puede ejecutarse")
        self.pending = None
        result = json.loads(serialize_tool_result(await execute_agent_tool(
            self.executor, ToolCall(pending["name"], pending["arguments"], call_id), self.scope)))
        provider_appointments = getattr(self.executor.provider, "appointments", None)
        snapshot = (
            None
            if provider_appointments is None
            else [appointment_payload(item) for item in provider_appointments]
        )
        await asyncio.to_thread(self.repository.save_action_result, self.session_id, pending["id"], call_id, result,
                                self.profile, snapshot, pending["patient_name"] if result.get("ok") else None)
        return result

    async def _renew_confirmation(self, pending, turn, generation, channel, channel_turn):
        """Revalida datos y agenda para emitir una autorizacion nueva, sin mutar."""
        supplied = dict(pending["arguments"])
        if pending["name"] == "create_appointment":
            supplied["patient_name"] = pending["patient_name"]
        await self.invalidate()
        return await self._propose(pending["name"], supplied, turn, generation, channel, channel_turn)

    async def _manage(self, arguments, turn, generation, channel, channel_turn):
        if set(arguments) != {"mode"} or arguments["mode"] not in {"resume", "new"}:
            raise ValueError("Indica si quieres retomar o iniciar una gestion nueva")
        previous = self.pending or await asyncio.to_thread(self.repository.latest_action, self.profile)
        await self.invalidate()
        self._workflow_channel = channel
        if arguments["mode"] == "new":
            await asyncio.to_thread(self.repository.replace_workflow, self.profile)
            return {"ok": True, "status": "new_workflow", "instruction": "Solicita los datos de la nueva gestion; no reutilices autorizaciones."}
        if not previous:
            raise ValueError("No hay una propuesta de cita para retomar")
        supplied = dict(previous["arguments"])
        if previous["name"] == "create_appointment":
            supplied["patient_name"] = previous["patient_name"]
        return await self._propose(previous["name"], supplied, turn, generation, channel, channel_turn)

    def bind_prompt(self, item_id: str, transcript: str):
        if self.pending and prompt_fingerprint(transcript) == prompt_fingerprint(self.pending["prompt"]):
            self.pending["item_id"] = item_id

    def emitted(self, item_id: str):
        if self.pending and self.pending["item_id"] == item_id:
            self.pending["armed"] = True

    async def invalidate(self):
        self.pending = None
        self._interrupted_proposal = None
        await asyncio.to_thread(self.repository.invalidate, self.session_id)

    async def interrupt(self, generation=None):
        if generation is not None and not self.authorization.valid(generation):
            return
        if self.pending and not self.pending["armed"]:
            self._interrupted_proposal = self.pending
            action_id = self._interrupted_proposal["id"]
            self.pending = None
            await asyncio.to_thread(self.repository.invalidate_action, self.session_id, action_id)

    async def end_turn(self, turn: int, *, channel="voice", channel_turn=None):
        channel_turn = turn if channel_turn is None else channel_turn
        if self.pending and self.pending.get("channel", "voice") == channel and channel_turn > self.pending["channel_turn"]:
            await self.invalidate()

    async def close(self):
        self.closed = True
        async with self._lock:
            await self.invalidate()


def _classify_pending_confirmation(source_text, pending):
    tool_name = ToolName.CANCEL_APPOINTMENT if pending["name"] == "cancel_appointment" else ToolName.RESCHEDULE_APPOINTMENT
    return classify_action_confirmation(source_text, tool_name=tool_name)
