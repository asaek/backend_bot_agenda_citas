from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from appointment_confirmation import (
    CONFIRMATION_RESPONSE_INSTRUCTIONS,
    ConfirmationDecision,
    PendingAppointmentAction,
    PENDING_APPOINTMENT_ACTION_KEY,
    classify_confirmation,
    confirmation_reply,
)
from appointment_availability import (
    DateOnlyAvailabilityRequest,
    PENDING_APPOINTMENT_DATE_KEY,
    PENDING_APPOINTMENT_AVAILABILITY_KEY,
    PendingAppointmentDate,
    PendingAppointmentAvailability,
    PendingAvailabilitySlot,
    appointment_date_is_required,
    availability_request_for_date,
    date_only_availability_follow_up_request,
    date_only_availability_request,
    format_availability_reply,
)
from appointment_reason_evaluation import (
    AppointmentReasonCategory,
    AppointmentReasonEvaluation,
    AppointmentReasonEvaluator,
    AppointmentReasonQuality,
    failed_appointment_reason_evaluation,
    local_appointment_reason_evaluation,
)
from appointment_reason_validation import validate_appointment_reason
from appointment_scheduling import (
    LAST_APPOINTMENT_REASON_EVALUATION_KEY,
    PENDING_APPOINTMENT_REASON_KEY,
    PendingAppointmentReason,
)
from agent_orchestrator import AgentOrchestrator
from calendar_domain import (
    Appointment,
    AppointmentNotFound,
    CalendarProviderUnavailable,
    PatientScope,
    ToolError,
    ToolName,
    ToolRequest,
    ToolResult,
)
from debug_reporting import format_debug_fallback_reply
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
from tool_contracts import CheckAvailabilityOutput, CreateAppointmentOutput
from tool_executor import ToolExecutor
from tool_results import public_error_from_exception


CONTROLLED_FALLBACK_REPLY = (
    "En este momento no pude procesar tu mensaje. "
    "Intenta nuevamente en unos minutos."
)
APPOINTMENT_NAME_REPLY = (
    "Antes de agendar tu cita, ¿cuál es tu nombre completo?"
)
APPOINTMENT_NAME_CLARIFICATION_REPLY = (
    "Necesito tu nombre completo para continuar. ¿Cómo te llamas?"
)
APPOINTMENT_REASON_REPLY = "Gracias. Ahora, ¿cuál es el motivo de la consulta?"
APPOINTMENT_REASON_CLARIFICATION_REPLY = (
    "No pude identificar el motivo de la consulta. "
    "¿Qué problema de la vista deseas revisar? Puedes escribirlo con tus palabras, "
    "por ejemplo: visión borrosa, dolor ocular, ojo rojo, seguimiento de córnea "
    "o revisión general."
)
APPOINTMENT_REASON_OUT_OF_SCOPE_REPLY = (
    "El motivo parece no estar relacionado con una consulta de la vista. "
    "Si deseas una cita oftalmológica, indícame qué problema deseas revisar."
)
APPOINTMENT_SLOT_SELECTION_REPLY = (
    "Elige uno de los horarios disponibles indicando la hora, por ejemplo: 10:00."
)
APPOINTMENT_DATE_REPLY = "Para agendar una cita, ¿qué día te gustaría reservar?"
APPOINTMENT_DATE_EXPIRED_REPLY = (
    "La solicitud de reserva expiró. Si aún quieres agendar, dime qué día te gustaría reservar."
)
APPOINTMENT_AVAILABILITY_EXPIRED_REPLY = (
    "La lista de horarios expiró. Solicita nuevamente la disponibilidad para ese día."
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
        "solo entonces solicitar create_appointment. Despues de que el paciente elija "
        "un horario, el backend siempre preguntara su nombre completo y luego solicitara "
        "el motivo antes de ejecutarla.",
        "Cuando el backend muestre horarios disponibles, no pidas directamente el nombre "
        "ni el motivo y no vuelvas a consultar disponibilidad; espera la seleccion del "
        "paciente.",
        "Nunca inventar un motivo ni usar un motivo predeterminado.",
        "Nunca cancelar ni reprogramar una cita sin confirmación explícita del paciente.",
        "Cuando el paciente proponga una fecha y hora para reprogramar, solicita "
        "reschedule_appointment con la cita y el horario preferido; el backend consultara "
        "la disponibilidad del dia y mostrara las opciones antes de pedir confirmacion. "
        "No afirmes que el cambio esta disponible ni solicites confirmacion antes de que "
        "el paciente elija un horario ofrecido.",
        "Si el paciente solo quiere cambiar la hora, conservar la fecha de la cita "
        "seleccionada como destino, salvo que indique otro día.",
        "Cuando el paciente pida horarios y dé una fecha o rango, usar check_availability.",
        "Cuando el paciente pregunte por sus citas, usar list_appointments.",
        "Para listar todas las citas no enviar argumentos; para un rango enviar start_at y end_at.",
        "Si el paciente usa hoy, mañana, ayer u otra expresión relativa, resolverla con el contexto temporal del backend; no pedir la fecha exacta.",
        "Para consultar un día concreto, usar list_appointments con el inicio de ese día y el inicio del día siguiente.",
        "Las consultas de citas devuelven solo citas vigentes; no presentes tombstones cancelados como citas del paciente.",
        "Una cita solo debe describirse como cancelada despues de ejecutar con exito cancel_appointment.",
        "Si se consulta un día, no mezclar citas de otros días en la respuesta.",
        "Usar el id devuelto por list_appointments si luego debe reprogramar o cancelar.",
        "WhatsApp admite formato limitado con asteriscos simples para negrita, "
        "pero no admite tablas Markdown ni HTML.",
        "Nunca uses tablas Markdown. Para cada cita devuelta por list_appointments "
        "usa este formato, con una cita por bloque y sin combinar el horario y el motivo:\n"
        "- *Horario:* HH:MM a HH:MM\n"
        "  *Motivo de consulta:*\n"
        "  <motivo de la cita>.",
        "Cada bloque debe ocupar exactamente tres lineas: deja *Motivo de consulta:* "
        "sola en la segunda linea y escribe el motivo en la tercera. Nunca pongas el "
        "motivo en la misma linea que su etiqueta.",
        "Repite el bloque por cada cita y conserva el texto del motivo. Si el listado "
        "abarca varios dias, indica la fecha en cada bloque; si corresponde a un solo "
        "dia, no es necesario repetirla.",
        "Cuando muestres el detalle de una sola cita, incluye fecha, hora y motivo, "
        "pero nunca muestres su ID interno al paciente.",
        "No pedir clínica, consultorio, calendario, duración ni preferencia de turno.",
        "Responder únicamente con texto plano y formato compatible con WhatsApp; no usar HTML.",
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
        reason_evaluator: AppointmentReasonEvaluator | None = None,
    ) -> None:
        self.database = database
        self.llm_provider = llm_provider
        self.max_history_messages = max_history_messages
        self.llm_configuration_error = llm_configuration_error
        self.tool_executor = tool_executor
        self.reason_evaluator = reason_evaluator
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
        pending_reply = await self._resolve_pending_appointment_date(context)
        if pending_reply is not None:
            return pending_reply
        date_question = self._begin_pending_appointment_date(context)
        if date_question is not None:
            return date_question
        pending_reply = await self._resolve_pending_appointment_availability(context)
        if pending_reply is not None:
            return pending_reply
        if self.llm_configuration_error is not None:
            raise self.llm_configuration_error
        if self.llm_provider is None:
            raise LLMProviderError("ConversationService requiere un proveedor LLM")
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

        return await self._execute_date_only_availability(context, request)

    async def _resolve_pending_appointment_date(
        self,
        context: ConversationContext,
    ) -> str | None:
        if self.tool_executor is None:
            return None
        pending_date = self._load_pending_appointment_date(context.conversation_id)
        if pending_date is None:
            return None

        now = self._current_local_time()
        if pending_date.is_expired_at(now):
            self._clear_pending_appointment_date(context.conversation_id)
            return APPOINTMENT_DATE_EXPIRED_REPLY

        request = date_only_availability_follow_up_request(
            context.incoming_text,
            now=now,
            timezone=self._timezone,
        )
        if request is None:
            return APPOINTMENT_DATE_REPLY
        return await self._execute_date_only_availability(context, request)

    def _begin_pending_appointment_date(
        self,
        context: ConversationContext,
    ) -> str | None:
        if self.tool_executor is None:
            return None
        now = self._current_local_time()
        if not appointment_date_is_required(
            context.incoming_text,
            now=now,
            timezone=self._timezone,
        ):
            return None
        self._save_pending_appointment_date(
            context.conversation_id,
            PendingAppointmentDate.start(now),
        )
        self._clear_pending_appointment_availability(context.conversation_id)
        return APPOINTMENT_DATE_REPLY

    async def _execute_date_only_availability(
        self,
        context: ConversationContext,
        request: DateOnlyAvailabilityRequest,
    ) -> str:
        if self.tool_executor is None:
            raise RuntimeError("La disponibilidad requiere un ToolExecutor")

        now = self._current_local_time()
        self._save_pending_appointment_date(
            context.conversation_id,
            PendingAppointmentDate.start(now),
        )

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
        self._clear_pending_appointment_availability(context.conversation_id)
        if result.ok and isinstance(result.data, CheckAvailabilityOutput):
            self._clear_pending_appointment_date(context.conversation_id)
            pending_availability = PendingAppointmentAvailability.from_slots(
                request,
                result.data.slots,
                timezone=self._timezone,
                now=self._current_local_time(),
            )
            if pending_availability is not None:
                self._save_pending_appointment_availability(
                    context.conversation_id,
                    pending_availability,
                )
        else:
            self._save_pending_appointment_date(
                context.conversation_id,
                PendingAppointmentDate.start(self._current_local_time()),
            )
        return format_availability_reply(
            result,
            request,
            timezone=self._timezone,
        )

    async def _resolve_pending_appointment_availability(
        self,
        context: ConversationContext,
    ) -> str | None:
        pending_availability = self._load_pending_appointment_availability(
            context.conversation_id,
        )
        if pending_availability is None:
            return None
        if pending_availability.is_expired_at(self._current_local_time()):
            self._clear_pending_appointment_availability(context.conversation_id)
            return APPOINTMENT_AVAILABILITY_EXPIRED_REPLY

        selected_slot = pending_availability.matching_slot(
            context.incoming_text,
            timezone=self._timezone,
        )
        if selected_slot is None:
            if pending_availability.appointment_id is not None:
                return (
                    "Elige uno de los horarios disponibles para reprogramar tu cita, "
                    "por ejemplo: 10:00."
                )
            return APPOINTMENT_SLOT_SELECTION_REPLY

        if pending_availability.appointment_id is not None:
            return await self._confirm_reschedule_from_available_slot(
                context,
                pending_availability,
                selected_slot,
            )

        pending_reason = PendingAppointmentReason.from_start_at(
            selected_slot.start_at,
            call_id=f"backend-availability-{context.incoming_message_id}",
            source_message_id=context.incoming_message_id,
        )
        reply = self._start_pending_appointment_reason(context, pending_reason)
        self._clear_pending_appointment_availability(context.conversation_id)
        return reply

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
            return self._start_pending_appointment_reason(context, pending_reason)
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
        pending_action = PendingAppointmentAction.from_tool_call(tool_call)
        if pending_action is None:
            return None
        if self.tool_executor is None:
            return self._calendar_error_reply(
                context,
                CalendarProviderUnavailable().to_tool_error(),
                error_type="CalendarProviderUnavailable",
            )

        try:
            appointment = await self._find_appointment_for_confirmation(
                patient_scope,
                pending_action.arguments["appointment_id"],
            )
        except Exception as error:
            public_error = public_error_from_exception(error)
            return self._calendar_error_reply(
                context,
                public_error.to_tool_error(),
                error_type=type(public_error).__name__,
            )
        if appointment is None:
            not_found = AppointmentNotFound()
            return self._calendar_error_reply(
                context,
                not_found.to_tool_error(),
                error_type=type(not_found).__name__,
            )

        if pending_action.tool_name is ToolName.RESCHEDULE_APPOINTMENT:
            return await self._offer_reschedule_availability(
                context,
                tool_call,
                appointment,
            )

        pending_action = PendingAppointmentAction.from_tool_call(
            tool_call,
            appointment=appointment,
        )
        if pending_action is None:
            return None
        self._save_pending_appointment_action(context.conversation_id, pending_action)
        return pending_action.confirmation_prompt()

    async def _offer_reschedule_availability(
        self,
        context: ConversationContext,
        tool_call: ToolCall,
        appointment: Appointment,
    ) -> str:
        if self.tool_executor is None:
            return CONTROLLED_FALLBACK_REPLY
        self._clear_pending_appointment_action(context.conversation_id)
        self._clear_pending_appointment_date(context.conversation_id)
        self._clear_pending_appointment_availability(context.conversation_id)
        try:
            requested_start = datetime.fromisoformat(
                tool_call.arguments["new_start_at"]
            )
        except (KeyError, TypeError, ValueError):
            return "No pude identificar el día para consultar los horarios disponibles."
        if requested_start.tzinfo is None or requested_start.utcoffset() is None:
            requested_start = requested_start.replace(tzinfo=self._timezone)
        else:
            requested_start = requested_start.astimezone(self._timezone)

        request = availability_request_for_date(
            requested_start.date(),
            now=self._current_local_time(),
            timezone=self._timezone,
        )
        if request is None:
            return (
                f"No quedan horarios disponibles para el "
                f"{requested_start:%d/%m/%Y}. Si quieres, reviso otro día."
            )

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
        if not result.ok or not isinstance(result.data, CheckAvailabilityOutput):
            if result.error is not None:
                return self._calendar_error_reply(
                    context,
                    result.error,
                    error_type="ToolError",
                )
            return "No pude consultar los horarios disponibles. Intenta nuevamente."

        pending_availability = PendingAppointmentAvailability.from_slots(
            request,
            result.data.slots,
            timezone=self._timezone,
            now=self._current_local_time(),
            appointment_id=appointment.id,
            call_id=tool_call.call_id,
        )
        if pending_availability is not None:
            self._save_pending_appointment_availability(
                context.conversation_id,
                pending_availability,
            )
        return format_availability_reply(
            result,
            request,
            timezone=self._timezone,
            selection_prompt=(
                "Elige uno de estos horarios para cambiar tu cita. "
                "La modificación se realizará solo después de que la confirmes."
            ),
        )

    async def _confirm_reschedule_from_available_slot(
        self,
        context: ConversationContext,
        pending_availability: PendingAppointmentAvailability,
        selected_slot: PendingAvailabilitySlot,
    ) -> str:
        self._clear_pending_appointment_availability(context.conversation_id)
        try:
            appointment = await self._find_appointment_for_confirmation(
                context.patient_scope,
                pending_availability.appointment_id or "",
            )
        except Exception as error:
            public_error = public_error_from_exception(error)
            return self._calendar_error_reply(
                context,
                public_error.to_tool_error(),
                error_type=type(public_error).__name__,
            )
        if appointment is None:
            not_found = AppointmentNotFound()
            return self._calendar_error_reply(
                context,
                not_found.to_tool_error(),
                error_type=type(not_found).__name__,
            )

        tool_call = ToolCall(
            name=ToolName.RESCHEDULE_APPOINTMENT.value,
            arguments={
                "appointment_id": appointment.id,
                "new_start_at": selected_slot.start_at,
            },
            call_id=pending_availability.call_id,
        )
        pending_action = PendingAppointmentAction.from_tool_call(
            tool_call,
            appointment=appointment,
        )
        if pending_action is None:
            return CONTROLLED_FALLBACK_REPLY
        self._save_pending_appointment_action(context.conversation_id, pending_action)
        return pending_action.confirmation_prompt()

    async def _find_appointment_for_confirmation(
        self,
        patient_scope: PatientScope,
        appointment_id: str,
    ) -> Appointment | None:
        if self.tool_executor is None:
            return None
        return await self.tool_executor.find_appointment(
            patient_scope=patient_scope,
            appointment_id=appointment_id,
        )

    @staticmethod
    def _calendar_error_reply(
        context: ConversationContext,
        error: ToolError,
        *,
        error_type: str,
    ) -> str:
        diagnostic_reply = format_debug_fallback_reply(
            context.patient_scope.whatsapp_number,
            error_type=error_type,
            provider_name="calendar",
            diagnostic_code=error.code.value,
        )
        return diagnostic_reply or error.message

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
            return CONFIRMATION_RESPONSE_INSTRUCTIONS

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
            return self._calendar_error_reply(
                context,
                result.error,
                error_type="ToolError",
            )
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
            if (
                pending_reason.name_required is None
                and self._load_patient_name(context.patient_id) is not None
            ):
                return APPOINTMENT_REASON_REPLY
            return APPOINTMENT_NAME_REPLY

        if pending_reason.name_message_id == context.incoming_message_id:
            return APPOINTMENT_REASON_REPLY

        name_required = pending_reason.name_required
        if name_required is None:
            name_required = self._load_patient_name(context.patient_id) is None

        if name_required:
            normalized_name = _normalize_patient_name(context.incoming_text)
            if normalized_name is None:
                return APPOINTMENT_NAME_CLARIFICATION_REPLY
            named_pending_reason = pending_reason.with_name_message(
                context.incoming_message_id
            )
            self._save_patient_name_and_pending_reason(
                context,
                normalized_name,
                named_pending_reason,
            )
            return APPOINTMENT_REASON_REPLY

        evaluated_at = utc_now()
        validation = validate_appointment_reason(context.incoming_text)
        if not validation.accepted:
            evaluation = local_appointment_reason_evaluation(
                validation,
                evaluated_at=evaluated_at,
            )
        elif self.reason_evaluator is None:
            evaluation = local_appointment_reason_evaluation(
                validation,
                evaluated_at=evaluated_at,
            )
        else:
            try:
                evaluation = await self.reason_evaluator.evaluate(
                    validation.normalized_text,
                    evaluated_at=evaluated_at,
                )
                if not isinstance(evaluation, AppointmentReasonEvaluation):
                    raise TypeError("El evaluador devolvio un resultado invalido")
            except Exception as error:
                self.record_llm_failure(
                    context,
                    error_type=type(error).__name__,
                )
                evaluation = failed_appointment_reason_evaluation(
                    validation,
                    evaluated_at=evaluated_at,
                )

        evaluated_pending_reason = pending_reason.with_evaluation(evaluation)
        self._save_pending_appointment_reason(
            context.conversation_id,
            evaluated_pending_reason,
        )
        if (
            evaluation.quality is AppointmentReasonQuality.OUT_OF_SCOPE
            or evaluation.category is AppointmentReasonCategory.OUT_OF_SCOPE
        ):
            return APPOINTMENT_REASON_OUT_OF_SCOPE_REPLY
        if not evaluation.accepted:
            return APPOINTMENT_REASON_CLARIFICATION_REPLY

        self._save_last_appointment_reason_evaluation(
            context.conversation_id,
            attempt_count=evaluated_pending_reason.attempt_count,
            evaluation=evaluation,
        )
        self._clear_pending_appointment_reason(context.conversation_id)
        if self.agent_orchestrator is None:
            return CONTROLLED_FALLBACK_REPLY

        result = await self.agent_orchestrator.execute_confirmed_tool(
            tool_call=pending_reason.to_tool_call(validation.normalized_text),
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

    def _load_pending_appointment_availability(
        self,
        conversation_id: int,
    ) -> PendingAppointmentAvailability | None:
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
        return PendingAppointmentAvailability.from_context(
            context.get(PENDING_APPOINTMENT_AVAILABILITY_KEY)
        )

    def _load_pending_appointment_date(
        self,
        conversation_id: int,
    ) -> PendingAppointmentDate | None:
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
        return PendingAppointmentDate.from_context(
            context.get(PENDING_APPOINTMENT_DATE_KEY)
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

    def _load_patient_name(self, patient_id: int) -> str | None:
        with self.database.transaction() as connection:
            patient = self.patients.get_by_id(connection, patient_id)
        if patient is None or not isinstance(patient.name, str):
            return None
        normalized_name = " ".join(patient.name.split())
        return normalized_name or None

    def _start_pending_appointment_reason(
        self,
        context: ConversationContext,
        pending_reason: PendingAppointmentReason,
    ) -> str:
        self._clear_last_appointment_reason_evaluation(context.conversation_id)
        self._save_pending_appointment_reason(
            context.conversation_id,
            pending_reason,
        )
        return APPOINTMENT_NAME_REPLY

    def _save_pending_appointment_availability(
        self,
        conversation_id: int,
        availability: PendingAppointmentAvailability,
    ) -> None:
        self._update_conversation_context_value(
            conversation_id,
            PENDING_APPOINTMENT_AVAILABILITY_KEY,
            availability.to_context(),
        )

    def _save_pending_appointment_date(
        self,
        conversation_id: int,
        pending_date: PendingAppointmentDate,
    ) -> None:
        self._update_conversation_context_value(
            conversation_id,
            PENDING_APPOINTMENT_DATE_KEY,
            pending_date.to_context(),
        )

    def _clear_pending_appointment_date(self, conversation_id: int) -> None:
        self._update_conversation_context_value(
            conversation_id,
            PENDING_APPOINTMENT_DATE_KEY,
            None,
        )

    def _clear_pending_appointment_availability(self, conversation_id: int) -> None:
        self._update_conversation_context_value(
            conversation_id,
            PENDING_APPOINTMENT_AVAILABILITY_KEY,
            None,
        )

    def _save_patient_name_and_pending_reason(
        self,
        context: ConversationContext,
        name: str,
        pending_reason: PendingAppointmentReason,
    ) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            patient = self.patients.get_by_id(
                connection,
                context.patient_id,
            )
            if patient is None:
                raise RuntimeError("No se encontro el paciente activo")
            self.patients.update_name(
                connection,
                context.patient_id,
                name,
                now,
            )
            conversation = self.conversations.get_by_id(
                connection,
                context.conversation_id,
            )
            if conversation is None:
                raise RuntimeError("No se encontro la conversacion activa")
            try:
                conversation_context = json.loads(conversation.context_json)
            except json.JSONDecodeError:
                conversation_context = {}
            if not isinstance(conversation_context, dict):
                conversation_context = {}
            conversation_context[PENDING_APPOINTMENT_REASON_KEY] = (
                pending_reason.to_context()
            )
            self.conversations.update_context(
                connection,
                context.conversation_id,
                json.dumps(conversation_context, ensure_ascii=False, sort_keys=True),
                now,
            )

    def _save_last_appointment_reason_evaluation(
        self,
        conversation_id: int,
        *,
        attempt_count: int,
        evaluation: AppointmentReasonEvaluation,
    ) -> None:
        self._update_conversation_context_value(
            conversation_id,
            LAST_APPOINTMENT_REASON_EVALUATION_KEY,
            {
                "attempt_count": attempt_count,
                "evaluation": evaluation.to_context(),
            },
        )

    def _clear_last_appointment_reason_evaluation(self, conversation_id: int) -> None:
        self._update_conversation_context_value(
            conversation_id,
            LAST_APPOINTMENT_REASON_EVALUATION_KEY,
            None,
        )

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
        http_status_code: int | None = None,
    ) -> LLMFailureRecord:
        with self.database.transaction() as connection:
            return self.llm_failures.create(
                connection,
                conversation_id=context.conversation_id,
                incoming_message_id=context.incoming_message_id,
                error_type=error_type,
                now=utc_now(),
                http_status_code=http_status_code,
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
    """Adapta listas de citas y tablas Markdown a texto legible en WhatsApp."""
    if not isinstance(reply, str):
        return reply
    return _split_appointment_reason_label(_convert_markdown_tables(reply))


_INLINE_APPOINTMENT_REASON_LABEL = re.compile(
    r"^(?P<indent>[ \t]*)\*?Motivo de consulta:\*?[ \t]+(?P<reason>\S(?:.*\S)?)\s*$",
    flags=re.IGNORECASE,
)
_APPOINTMENT_REASON_LABEL = re.compile(
    r"^(?P<indent>[ \t]*)\*?Motivo de consulta:\*?[ \t]*$",
    flags=re.IGNORECASE,
)
_APPOINTMENT_LIST_ITEM = re.compile(
    r"^[ \t]*-[ \t]+(?:\*?Horario:|\*?Fecha:)",
    flags=re.IGNORECASE,
)


def _split_appointment_reason_label(text: str) -> str:
    """Deja la etiqueta del motivo sola y mueve su valor a la linea siguiente."""
    lines = text.splitlines()
    formatted_lines: list[str] = []
    index = 0

    while index < len(lines):
        inline_match = _INLINE_APPOINTMENT_REASON_LABEL.match(lines[index])
        if inline_match is not None:
            indent = inline_match.group("indent")
            reason = inline_match.group("reason").strip()
            formatted_lines.extend(
                (
                    f"{indent}*Motivo de consulta:*",
                    f"{indent}{reason}",
                )
            )
            index += 1
            continue

        label_match = _APPOINTMENT_REASON_LABEL.match(lines[index])
        if label_match is None:
            formatted_lines.append(lines[index])
            index += 1
            continue

        indent = label_match.group("indent")
        formatted_lines.append(f"{indent}*Motivo de consulta:*")
        index += 1
        while index < len(lines) and not lines[index].strip():
            index += 1
        if index < len(lines) and not _APPOINTMENT_LIST_ITEM.match(lines[index]):
            formatted_lines.append(f"{indent}{lines[index].strip()}")
            index += 1

    return "\n".join(formatted_lines)


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


def _normalize_patient_name(value: str) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    if not 2 <= len(normalized) <= 120:
        return None
    if not re.search(r"[^\W\d_]", normalized, flags=re.UNICODE):
        return None
    return normalized
