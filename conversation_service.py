from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from appointment_confirmation import (
    ConfirmationDecision,
    PendingAppointmentAction,
    PENDING_APPOINTMENT_ACTION_KEY,
    classify_confirmation,
    confirmation_reply,
)
from appointment_availability import (
    date_only_availability_request,
    format_availability_reply,
)
from appointment_scheduling import (
    PENDING_APPOINTMENT_REASON_KEY,
    PendingAppointmentReason,
)
from agent_orchestrator import AgentOrchestrator
from calendar_domain import Appointment, PatientScope, ToolName, ToolRequest, ToolResult
from llm_provider import (
    ChatMessage,
    DEFAULT_LLM_MAX_HISTORY_MESSAGES,
    DEFAULT_LLM_MAX_TOOL_ITERATIONS,
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    ToolCall,
)
from notification_domain import AppointmentNotificationEventSink
from persistence import SQLiteDatabase
from repositories import (
    ConversationRepository,
    LLMFailureRecord,
    LLMFailureRepository,
    MessageRecord,
    MessageRepository,
    PatientRepository,
)
from tool_contracts import CreateAppointmentOutput
from tool_executor import ToolExecutor


CONTROLLED_FALLBACK_REPLY = (
    "En este momento no pude procesar tu mensaje. "
    "Intenta nuevamente en unos minutos."
)
SYSTEM_PROMPT = "\n".join(
    (
        "Responder en español.",
        "Ser breve y claro.",
        "No inventar citas, horarios o datos.",
        "No afirmar que realizó acciones externas.",
        "No proporcionar diagnósticos médicos.",
        "Pedir aclaración cuando falte información.",
        "Si el paciente solicita agendar para un dia pero no indica una hora exacta, "
        "consultar primero check_availability para todo ese dia; no pedir aun la hora "
        "ni el motivo.",
        "Despues de mostrar los horarios libres, esperar a que el paciente elija uno; "
        "solo entonces solicitar create_appointment. El backend preguntara el motivo "
        "antes de ejecutarla.",
        "Nunca inventar un motivo ni usar un motivo predeterminado.",
        "Nunca cancelar ni reprogramar una cita sin confirmación explícita del paciente.",
        "Cuando el paciente pida horarios y dé una fecha o rango, usar check_availability.",
        "Cuando el paciente pregunte por sus citas, usar list_appointments.",
        "Para listar todas las citas no enviar argumentos; para un rango enviar start_at y end_at.",
        "Si el paciente usa hoy, mañana, ayer u otra expresión relativa, resolverla con el contexto temporal del backend; no pedir la fecha exacta.",
        "Para consultar un día concreto, usar list_appointments con el inicio de ese día y el inicio del día siguiente.",
        "Las consultas de citas devuelven solo citas vigentes; no presentes tombstones cancelados como citas del paciente.",
        "Una cita solo debe describirse como cancelada despues de ejecutar con exito cancel_appointment.",
        "Si se consulta un día, no mezclar citas de otros días en la respuesta.",
        "Usar el id devuelto por list_appointments si luego debe reprogramar o cancelar.",
        "WhatsApp no admite tablas Markdown ni separadores con barras verticales.",
        "Nunca uses tablas Markdown; para varias citas usa una lista simple con guiones, "
        "una cita por linea, con hora y motivo.",
        "Cuando muestres detalles de una cita, incluye fecha, hora y motivo, "
        "pero nunca muestres su ID interno al paciente.",
        "No pedir clínica, consultorio, calendario, duración ni preferencia de turno.",
        "Responder únicamente con texto normal.",
    )
)


NowSource = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class IncomingTextMessage:
    sender: str
    message_id: str
    message_type: str
    text: str


@dataclass(frozen=True, slots=True)
class ConversationContext:
    patient_scope: PatientScope
    incoming_message_id: int
    incoming_text: str
    reply_status: str | None

    @property
    def patient_id(self) -> int:
        return self.patient_scope.patient_id

    @property
    def conversation_id(self) -> int:
        return self.patient_scope.conversation_id


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationService:
    def __init__(
        self,
        database: SQLiteDatabase,
        llm_provider: LLMProvider | None = None,
        max_history_messages: int = DEFAULT_LLM_MAX_HISTORY_MESSAGES,
        llm_configuration_error: LLMProviderError | None = None,
        max_tool_iterations: int = DEFAULT_LLM_MAX_TOOL_ITERATIONS,
        tool_executor: ToolExecutor | None = None,
        timezone_name: str = "UTC",
        now: datetime | NowSource | None = None,
    ) -> None:
        self.database = database
        self.llm_provider = llm_provider
        self.max_history_messages = max_history_messages
        self.llm_configuration_error = llm_configuration_error
        self.tool_executor = tool_executor
        try:
            self._timezone = ZoneInfo(timezone_name)
        except (TypeError, ZoneInfoNotFoundError) as error:
            raise ValueError(f"Zona horaria invalida: {timezone_name}") from error
        self.timezone_name = timezone_name
        self._now = now
        self.agent_orchestrator = (
            AgentOrchestrator(
                llm_provider=llm_provider,
                tool_executor=tool_executor,
                max_iterations=max_tool_iterations,
            )
            if llm_provider is not None and tool_executor is not None
            else None
        )
        self.patients = PatientRepository()
        self.conversations = ConversationRepository()
        self.messages = MessageRepository()
        self.llm_failures = LLMFailureRepository()

    def receive_message(self, message: IncomingTextMessage) -> ConversationContext:
        now = utc_now()
        with self.database.transaction() as connection:
            existing = self.messages.get_by_provider_id(
                connection,
                direction="incoming",
                provider_message_id=message.message_id,
            )
            if existing is not None:
                conversation = self.conversations.get_by_id(
                    connection,
                    existing.conversation_id,
                )
                if conversation is None:
                    raise RuntimeError("El mensaje existente no tiene conversacion")
                patient = self.patients.get_by_id(connection, conversation.patient_id)
                if patient is None:
                    raise RuntimeError("La conversacion existente no tiene paciente")
                reply = self.messages.get_reply(connection, existing.id)
                return ConversationContext(
                    patient_scope=PatientScope(
                        patient_id=patient.id,
                        conversation_id=conversation.id,
                        whatsapp_number=patient.whatsapp_number,
                    ),
                    incoming_message_id=existing.id,
                    incoming_text=existing.text,
                    reply_status=reply.status if reply else None,
                )

            patient = self.patients.get_or_create(connection, message.sender, now)
            conversation = self.conversations.get_or_create_active(
                connection,
                patient_id=patient.id,
                now=now,
            )
            incoming = self.messages.create_incoming(
                connection,
                conversation_id=conversation.id,
                provider_message_id=message.message_id,
                text=message.text,
                message_type=message.message_type,
                now=now,
            )
            self.conversations.mark_active(connection, conversation.id, now)

            return ConversationContext(
                patient_scope=PatientScope(
                    patient_id=patient.id,
                    conversation_id=conversation.id,
                    whatsapp_number=patient.whatsapp_number,
                ),
                incoming_message_id=incoming.id,
                incoming_text=message.text,
                reply_status=None,
            )

    async def build_reply(
        self,
        context: ConversationContext,
        appointment_event_sink: AppointmentNotificationEventSink | None = None,
    ) -> LLMResponse:
        if self.llm_configuration_error is not None:
            raise self.llm_configuration_error
        if self.llm_provider is None:
            raise LLMProviderError("ConversationService requiere un proveedor LLM")
        pending_reply = await self._resolve_pending_appointment_action(
            context,
            appointment_event_sink,
        )
        if pending_reply is not None:
            return pending_reply
        pending_reply = await self._resolve_pending_appointment_reason(
            context,
            appointment_event_sink,
        )
        if pending_reply is not None:
            return pending_reply
        availability_reply = await self._resolve_date_only_availability(context)
        if availability_reply is not None:
            return availability_reply
        messages = self.build_chat_messages(context)
        if self.agent_orchestrator is not None:
            reply = await self.agent_orchestrator.run(
                messages=messages,
                patient_scope=context.patient_scope,
                incoming_message_id=context.incoming_message_id,
                on_appointment_event=appointment_event_sink,
                on_mutation_requested=lambda tool_call, patient_scope: (
                    self._handle_mutation_request(
                        context,
                        tool_call,
                        patient_scope,
                    )
                ),
            )
        else:
            reply = await self.llm_provider.generate(messages)
        return format_whatsapp_reply(reply)

    async def _resolve_date_only_availability(
        self,
        context: ConversationContext,
    ) -> str | None:
        if self.tool_executor is None:
            return None
        request = date_only_availability_request(
            context.incoming_text,
            now=self._current_local_time(),
            timezone=self._timezone,
        )
        if request is None:
            return None

        result = await self.tool_executor.execute(
            ToolRequest(
                tool_name=ToolName.CHECK_AVAILABILITY,
                arguments={
                    "start_at": request.start_at.isoformat(),
                    "end_at": request.end_at.isoformat(),
                },
                patient_scope=context.patient_scope,
            )
        )
        return format_availability_reply(
            result,
            request,
            timezone=self._timezone,
        )

    async def _handle_mutation_request(
        self,
        context: ConversationContext,
        tool_call: ToolCall,
        patient_scope: PatientScope,
    ) -> str | None:
        pending_reason = PendingAppointmentReason.from_tool_call(
            tool_call,
            source_message_id=context.incoming_message_id,
        )
        if pending_reason is not None:
            self._save_pending_appointment_reason(
                context.conversation_id,
                pending_reason,
            )
            return "Antes de agendar tu cita, ¿cuál es el motivo de la consulta?"
        return await self._request_appointment_confirmation(
            context,
            tool_call,
            patient_scope,
        )

    async def _request_appointment_confirmation(
        self,
        context: ConversationContext,
        tool_call: ToolCall,
        patient_scope: PatientScope,
    ) -> str | None:
        appointment = await self._find_appointment_for_confirmation(
            patient_scope,
            tool_call,
        )
        pending_action = PendingAppointmentAction.from_tool_call(
            tool_call,
            appointment=appointment,
        )
        if pending_action is None:
            return None
        self._save_pending_appointment_action(context.conversation_id, pending_action)
        return pending_action.confirmation_prompt()

    async def _find_appointment_for_confirmation(
        self,
        patient_scope: PatientScope,
        tool_call: ToolCall,
    ) -> Appointment | None:
        if self.tool_executor is None:
            return None
        appointment_id = tool_call.arguments.get("appointment_id")
        if not isinstance(appointment_id, str) or not appointment_id.strip():
            return None
        try:
            return await self.tool_executor.find_appointment(
                patient_scope=patient_scope,
                appointment_id=appointment_id,
            )
        except Exception:
            return None

    async def _resolve_pending_appointment_action(
        self,
        context: ConversationContext,
        appointment_event_sink: AppointmentNotificationEventSink | None,
    ) -> str | None:
        pending_action = self._load_pending_appointment_action(context.conversation_id)
        if pending_action is None:
            return None
        if pending_action.is_expired:
            self._clear_pending_appointment_action(context.conversation_id)
            return (
                "La confirmación expiró. Si aún deseas realizar el cambio, "
                "solicítalo nuevamente."
            )

        decision = classify_confirmation(context.incoming_text)
        if decision is ConfirmationDecision.UNKNOWN:
            return "Responde Sí para confirmar la operación o No para mantener la cita."

        self._clear_pending_appointment_action(context.conversation_id)
        if decision is ConfirmationDecision.REJECTED:
            return "No se realizó ningún cambio en tu cita."
        if self.agent_orchestrator is None:
            return CONTROLLED_FALLBACK_REPLY

        result = await self.agent_orchestrator.execute_confirmed_tool(
            tool_call=pending_action.to_tool_call(),
            patient_scope=context.patient_scope,
            incoming_message_id=context.incoming_message_id,
            on_appointment_event=appointment_event_sink,
        )
        if result.ok:
            return confirmation_reply(pending_action.tool_name)
        if result.error is not None:
            return result.error.message
        return CONTROLLED_FALLBACK_REPLY

    async def _resolve_pending_appointment_reason(
        self,
        context: ConversationContext,
        appointment_event_sink: AppointmentNotificationEventSink | None,
    ) -> str | None:
        pending_reason = self._load_pending_appointment_reason(
            context.conversation_id,
        )
        if pending_reason is None:
            return None
        if pending_reason.is_expired:
            self._clear_pending_appointment_reason(context.conversation_id)
            return (
                "La solicitud para agendar esa cita expiró. "
                "Solicítala nuevamente indicando el horario."
            )
        if pending_reason.source_message_id == context.incoming_message_id:
            return "Antes de agendar tu cita, ¿cuál es el motivo de la consulta?"

        reason = " ".join(context.incoming_text.split())
        if not reason:
            return "Antes de agendar tu cita, ¿cuál es el motivo de la consulta?"

        self._clear_pending_appointment_reason(context.conversation_id)
        if self.agent_orchestrator is None:
            return CONTROLLED_FALLBACK_REPLY

        result = await self.agent_orchestrator.execute_confirmed_tool(
            tool_call=pending_reason.to_tool_call(reason),
            patient_scope=context.patient_scope,
            incoming_message_id=context.incoming_message_id,
            on_appointment_event=appointment_event_sink,
        )
        if result.ok:
            return self._create_appointment_reply(result)
        if result.error is not None:
            return result.error.message
        return CONTROLLED_FALLBACK_REPLY

    @staticmethod
    def _create_appointment_reply(result: ToolResult) -> str:
        if not isinstance(result.data, CreateAppointmentOutput):
            return "Tu cita fue agendada correctamente."
        appointment = result.data.appointment
        return (
            f"Tu cita está confirmada para el {appointment.start_at:%d/%m/%Y} "
            f"a las {appointment.start_at:%H:%M}. Motivo: {appointment.reason}."
        )

    def _load_pending_appointment_action(
        self,
        conversation_id: int,
    ) -> PendingAppointmentAction | None:
        with self.database.transaction() as connection:
            conversation = self.conversations.get_by_id(connection, conversation_id)
        if conversation is None:
            return None
        try:
            context = json.loads(conversation.context_json)
        except json.JSONDecodeError:
            return None
        if not isinstance(context, dict):
            return None
        return PendingAppointmentAction.from_context(
            context.get(PENDING_APPOINTMENT_ACTION_KEY)
        )

    def _load_pending_appointment_reason(
        self,
        conversation_id: int,
    ) -> PendingAppointmentReason | None:
        with self.database.transaction() as connection:
            conversation = self.conversations.get_by_id(connection, conversation_id)
        if conversation is None:
            return None
        try:
            context = json.loads(conversation.context_json)
        except json.JSONDecodeError:
            return None
        if not isinstance(context, dict):
            return None
        return PendingAppointmentReason.from_context(
            context.get(PENDING_APPOINTMENT_REASON_KEY)
        )

    def _save_pending_appointment_action(
        self,
        conversation_id: int,
        action: PendingAppointmentAction,
    ) -> None:
        self._update_appointment_action_context(conversation_id, action)

    def _clear_pending_appointment_action(self, conversation_id: int) -> None:
        self._update_appointment_action_context(conversation_id, None)

    def _save_pending_appointment_reason(
        self,
        conversation_id: int,
        reason: PendingAppointmentReason,
    ) -> None:
        self._update_appointment_reason_context(conversation_id, reason)

    def _clear_pending_appointment_reason(self, conversation_id: int) -> None:
        self._update_appointment_reason_context(conversation_id, None)

    def _update_appointment_action_context(
        self,
        conversation_id: int,
        action: PendingAppointmentAction | None,
    ) -> None:
        self._update_conversation_context_value(
            conversation_id,
            PENDING_APPOINTMENT_ACTION_KEY,
            action.to_context() if action is not None else None,
        )

    def _update_appointment_reason_context(
        self,
        conversation_id: int,
        reason: PendingAppointmentReason | None,
    ) -> None:
        self._update_conversation_context_value(
            conversation_id,
            PENDING_APPOINTMENT_REASON_KEY,
            reason.to_context() if reason is not None else None,
        )

    def _update_conversation_context_value(
        self,
        conversation_id: int,
        key: str,
        value: object | None,
    ) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            conversation = self.conversations.get_by_id(connection, conversation_id)
            if conversation is None:
                raise RuntimeError("No se encontro la conversacion activa")
            try:
                context = json.loads(conversation.context_json)
            except json.JSONDecodeError:
                context = {}
            if not isinstance(context, dict):
                context = {}
            if value is None:
                context.pop(key, None)
            else:
                context[key] = value
            self.conversations.update_context(
                connection,
                conversation_id,
                json.dumps(context, ensure_ascii=False, sort_keys=True),
                now,
            )

    def build_chat_messages(
        self,
        context: ConversationContext,
        max_history_messages: int | None = None,
    ) -> list[ChatMessage]:
        """Construye el contexto del LLM con el historial más reciente."""
        history_limit = (
            self.max_history_messages
            if max_history_messages is None
            else max_history_messages
        )
        if history_limit <= 0:
            raise ValueError("max_history_messages debe ser positivo")

        history = self.get_history(context.conversation_id)
        recent_history = history[-history_limit:]
        messages = [
            ChatMessage(
                role="system",
                content=self._build_system_prompt(),
            )
        ]

        for message in recent_history:
            if message.direction == "incoming":
                role = "user"
            elif message.direction == "outgoing" and message.status == "sent":
                role = "assistant"
            else:
                continue
            messages.append(ChatMessage(role=role, content=message.text))

        return messages

    def _build_system_prompt(self) -> str:
        """Agrega al prompt las fechas relativas resueltas por el backend."""
        current = self._current_local_time()
        today_start = datetime.combine(
            current.date(),
            time.min,
            tzinfo=self._timezone,
        )
        tomorrow_start = datetime.combine(
            current.date() + timedelta(days=1),
            time.min,
            tzinfo=self._timezone,
        )
        yesterday_start = datetime.combine(
            current.date() - timedelta(days=1),
            time.min,
            tzinfo=self._timezone,
        )
        return "\n".join(
            (
                SYSTEM_PROMPT,
                "Contexto temporal confiable de la agenda:",
                f"- Fecha y hora actual de la agenda: {current.isoformat()}.",
                f"- Zona horaria de la agenda: {self.timezone_name}.",
                f'- "hoy" corresponde a [{today_start.isoformat()}, {tomorrow_start.isoformat()}).',
                f'- "mañana" corresponde a [{tomorrow_start.isoformat()}, '
                f'{datetime.combine(current.date() + timedelta(days=2), time.min, tzinfo=self._timezone).isoformat()}).',
                f'- "ayer" corresponde a [{yesterday_start.isoformat()}, {today_start.isoformat()}).',
                "No pidas la fecha exacta cuando el paciente use una expresión relativa.",
            )
        )

    def _current_local_time(self) -> datetime:
        current = self._now() if callable(self._now) else self._now
        if current is None:
            return datetime.now(self._timezone)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("now debe incluir una zona horaria")
        return current.astimezone(self._timezone)

    def record_reply_sent(
        self,
        context: ConversationContext,
        body: str,
        provider_message_id: str | None,
    ) -> MessageRecord:
        return self._record_reply(
            context=context,
            body=body,
            status="sent",
            provider_message_id=provider_message_id,
        )

    def record_reply_failed(
        self,
        context: ConversationContext,
        body: str,
    ) -> MessageRecord:
        return self._record_reply(
            context=context,
            body=body,
            status="failed",
            provider_message_id=None,
        )

    def record_llm_failure(
        self,
        context: ConversationContext,
        error_type: str,
    ) -> LLMFailureRecord:
        with self.database.transaction() as connection:
            return self.llm_failures.create(
                connection,
                conversation_id=context.conversation_id,
                incoming_message_id=context.incoming_message_id,
                error_type=error_type,
                now=utc_now(),
            )

    def _record_reply(
        self,
        context: ConversationContext,
        body: str,
        status: str,
        provider_message_id: str | None,
    ) -> MessageRecord:
        with self.database.transaction() as connection:
            return self.messages.save_reply(
                connection,
                incoming_message_id=context.incoming_message_id,
                conversation_id=context.conversation_id,
                text=body,
                status=status,
                provider_message_id=provider_message_id,
                now=utc_now(),
            )

    def get_history(self, conversation_id: int) -> list[MessageRecord]:
        with self.database.transaction() as connection:
            return self.messages.list_for_conversation(connection, conversation_id)


def format_whatsapp_reply(reply: LLMResponse) -> LLMResponse:
    """Convierte tablas Markdown del LLM en listas legibles en WhatsApp."""
    if not isinstance(reply, str):
        return reply
    return _convert_markdown_tables(reply)


def _convert_markdown_tables(text: str) -> str:
    lines = text.splitlines()
    formatted_lines: list[str] = []
    index = 0

    while index < len(lines):
        headers = _markdown_table_cells(lines[index])
        separator = (
            _markdown_table_cells(lines[index + 1])
            if index + 1 < len(lines)
            else None
        )
        if (
            headers is not None
            and separator is not None
            and _is_markdown_table_separator(separator)
        ):
            rows: list[list[str]] = []
            row_index = index + 2
            while row_index < len(lines):
                row = _markdown_table_cells(lines[row_index])
                if row is None:
                    break
                if any(row):
                    rows.append(row)
                row_index += 1

            formatted_lines.extend(_format_table_rows(headers, rows))
            index = row_index
            continue

        formatted_lines.append(lines[index])
        index += 1

    return "\n".join(formatted_lines)


def _markdown_table_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _is_markdown_table_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _format_table_rows(headers: list[str], rows: list[list[str]]) -> list[str]:
    visible_columns = [
        index
        for index, header in enumerate(headers)
        if header and not _is_internal_id_header(header)
    ]
    formatted_rows: list[str] = []

    for row in rows:
        values: list[str] = []
        for column_index in visible_columns:
            if column_index >= len(row) or not row[column_index]:
                continue
            values.append(f"{headers[column_index]}: {row[column_index]}")
        if values:
            formatted_rows.append(f"- {'; '.join(values)}")

    return formatted_rows


def _is_internal_id_header(header: str) -> bool:
    normalized = " ".join(header.casefold().split())
    return normalized in {
        "id",
        "id de cita",
        "id interno",
        "identificador",
        "identificador interno",
    }
