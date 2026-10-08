from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
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
from conversation_intent import (
    PendingConversationFlow,
    PendingInterruption,
    classify_pending_interruption,
    is_reschedule_request_without_target_time,
    is_pending_slot_selection,
    is_resume_request,
)
from conversation_workflow import (
    PAUSED_CONVERSATION_WORKFLOW_KEY,
    PENDING_WORKFLOW_KEYS,
    PausedConversationWorkflow,
    PendingConversationWorkflow,
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
    format_patient_time,
    parse_time_selection,
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
from tool_contracts import (
    CheckAvailabilityOutput,
    CreateAppointmentOutput,
    ListAppointmentsOutput,
)
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
    "Elige uno de los horarios disponibles indicando la hora, por ejemplo: 10:00 AM."
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
        "Prioriza la intención más reciente del paciente. Si abandona o cambia una "
        "solicitud pendiente, no insistas en completar el flujo anterior.",
        "Las preguntas informativas y saludos pueden pausar una gestión. Usa el estado "
        "del backend como referencia; no reconstruyas ni reactives una reserva o "
        "confirmación por tu cuenta usando el historial.",
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
        "Si solicita cambiar una cita pero todavía no propone una hora nueva, no preguntes "
        "primero una hora libre; identifica la cita y deja que el backend muestre todos "
        "los horarios disponibles de su día.",
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
        "En listas de horarios disponibles o citas usa siempre el formato de 12 horas "
        "con AM o PM en cada hora, por ejemplo: 9:30 AM a 10:00 AM y 1:00 PM a 1:30 PM. "
        "Medianoche es 12:00 AM y mediodia es 12:00 PM.",
        "Nunca uses tablas Markdown. Para cada cita devuelta por list_appointments "
        "usa este formato, con una cita por bloque y sin combinar el horario y el motivo:\n"
        "- *Horario:* h:mm AM/PM a h:mm AM/PM\n"
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


_LISTED_APPOINTMENT_START_TIME_PATTERN = re.compile(
    r"^[ \t]*-[ \t]+\*?Horario:\*?[ \t]*"
    r"(?P<time>\d{1,2}:\d{2}(?:[ \t]*[ap]\.?m\.?)?)"
    r"[ \t]+a\b",
    flags=re.IGNORECASE | re.MULTILINE,
)
_SOURCE_APPOINTMENT_TIME_PATTERN = re.compile(
    r"\b(?:de\s+las?|la\s+de\s+las?)\s+"
    r"(?P<time>\d{1,2}(?::\d{2})?(?:\s*[ap]\.?m\.?)?)\b",
    flags=re.IGNORECASE,
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
        resume_reply = await self._resolve_paused_workflow(context)
        if resume_reply is not None:
            return resume_reply
        if is_resume_request(context.incoming_text):
            active = self._load_pending_conversation_workflow(context.conversation_id)
            if active.flow is not PendingConversationFlow.NONE:
                return await self._resumed_workflow_prompt(context, active)
            return "No hay una gestión pendiente para retomar. ¿Qué deseas hacer?"
        interruption_reply = self._resolve_pending_interruption(context)
        if interruption_reply is not None:
            return interruption_reply
        if self._load_paused_workflow(context.conversation_id) is not None:
            return await self._generate_agent_reply(context, appointment_event_sink)

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
        reschedule_reply = await self._resolve_reschedule_request_without_target_time(
            context,
        )
        if reschedule_reply is not None:
            return reschedule_reply
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
        return await self._generate_agent_reply(context, appointment_event_sink)

    async def _generate_agent_reply(
        self,
        context: ConversationContext,
        appointment_event_sink: AppointmentNotificationEventSink | None,
    ) -> LLMResponse:
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

    def _resolve_pending_interruption(
        self,
        context: ConversationContext,
    ) -> str | None:
        workflow = self._load_pending_conversation_workflow(
            context.conversation_id,
        )
        if workflow.flow is PendingConversationFlow.NONE:
            return None
        if workflow.reason is not None and context.incoming_message_id in {
            workflow.reason.source_message_id,
            workflow.reason.name_message_id,
        }:
            return None

        expected_reply = self._is_expected_pending_reply(context, workflow)
        interruption = classify_pending_interruption(
            context.incoming_text,
            flow=workflow.flow,
            expected_reply=expected_reply,
        )
        if interruption is PendingInterruption.NONE:
            return None
        if interruption is PendingInterruption.ABANDON:
            self._clear_pending_conversation_workflow(context.conversation_id)
            return self._abandoned_workflow_reply(workflow)
        if interruption is PendingInterruption.AMBIGUOUS_CANCEL:
            if workflow.action is not None:
                self._replace_workflow_context(
                    context.conversation_id,
                    paused=PausedConversationWorkflow(workflow, utc_now()),
                )
            return self._ambiguous_cancel_reply(workflow)
        if interruption is PendingInterruption.CLARIFY:
            return self._pending_interruption_clarification(
                workflow,
                expected_reply=expected_reply,
            )
        if interruption is PendingInterruption.PAUSE:
            self._replace_workflow_context(
                context.conversation_id,
                paused=PausedConversationWorkflow(workflow, utc_now()),
            )
            return None

        self._clear_pending_conversation_workflow(context.conversation_id)
        return None

    def _load_pending_conversation_workflow(
        self,
        conversation_id: int,
    ) -> PendingConversationWorkflow:
        with self.database.transaction() as connection:
            conversation = self.conversations.get_by_id(connection, conversation_id)
        if conversation is None:
            return PendingConversationWorkflow(PendingConversationFlow.NONE)
        try:
            stored_context = json.loads(conversation.context_json)
        except json.JSONDecodeError:
            return PendingConversationWorkflow(PendingConversationFlow.NONE)
        if not isinstance(stored_context, dict):
            return PendingConversationWorkflow(PendingConversationFlow.NONE)

        return PendingConversationWorkflow.from_context(stored_context)

    def _load_paused_workflow(self, conversation_id: int) -> PausedConversationWorkflow | None:
        with self.database.transaction() as connection:
            conversation = self.conversations.get_by_id(connection, conversation_id)
        if conversation is None:
            return None
        try:
            stored_context = json.loads(conversation.context_json)
        except json.JSONDecodeError:
            return None
        if not isinstance(stored_context, dict):
            return None
        return PausedConversationWorkflow.from_context(
            stored_context.get(PAUSED_CONVERSATION_WORKFLOW_KEY)
        )

    def _replace_workflow_context(
        self,
        conversation_id: int,
        *,
        active: PendingConversationWorkflow | None = None,
        paused: PausedConversationWorkflow | None = None,
    ) -> None:
        """Mueve o elimina el estado en una sola transaccion, conservando otros datos."""
        with self.database.transaction() as connection:
            conversation = self.conversations.get_by_id(connection, conversation_id)
            if conversation is None:
                return
            try:
                stored_context = json.loads(conversation.context_json)
            except json.JSONDecodeError:
                stored_context = {}
            if not isinstance(stored_context, dict):
                stored_context = {}
            for key in (*PENDING_WORKFLOW_KEYS, PAUSED_CONVERSATION_WORKFLOW_KEY):
                stored_context.pop(key, None)
            if active is not None:
                stored_context.update(active.to_context())
            elif paused is not None:
                stored_context[PAUSED_CONVERSATION_WORKFLOW_KEY] = paused.to_context()
            self.conversations.update_context(
                connection, conversation_id,
                json.dumps(stored_context, ensure_ascii=False, sort_keys=True), utc_now(),
            )

    async def _resolve_paused_workflow(self, context: ConversationContext) -> str | None:
        paused = self._load_paused_workflow(context.conversation_id)
        if paused is None:
            return None
        workflow = paused.workflow
        explicit_resume = is_resume_request(context.incoming_text)
        expected = self._is_expected_pending_reply(context, workflow)
        interruption = classify_pending_interruption(
            context.incoming_text, flow=workflow.flow, expected_reply=expected,
        )
        if interruption is PendingInterruption.ABANDON:
            self._clear_pending_conversation_workflow(context.conversation_id)
            return self._abandoned_workflow_reply(workflow)
        if interruption is PendingInterruption.AMBIGUOUS_CANCEL:
            return self._ambiguous_cancel_reply(workflow)
        can_resume_with_data = (
            expected and interruption is PendingInterruption.NONE
            and workflow.action is None
            and (
                workflow.availability is None
                or is_pending_slot_selection(context.incoming_text, workflow.flow)
            )
        )
        if explicit_resume or can_resume_with_data:
            self._replace_workflow_context(context.conversation_id, active=workflow)
            if explicit_resume:
                return await self._resumed_workflow_prompt(context, workflow)
            if workflow.pending_date is not None and workflow.pending_date.is_expired_at(self._current_local_time()):
                self._save_pending_appointment_date(
                    context.conversation_id,
                    PendingAppointmentDate.start(
                        self._current_local_time(), name_message_id=workflow.pending_date.name_message_id,
                    ),
                )
            if workflow.availability is not None and workflow.availability.is_expired_at(self._current_local_time()):
                return await self._resumed_workflow_prompt(context, workflow)
            return None
        if interruption is PendingInterruption.SWITCH:
            self._clear_pending_conversation_workflow(context.conversation_id)
            return None
        if workflow.action is not None and expected:
            return (
                "La gestión está pausada. Escribe ‘retomemos la cita’ para revisar "
                "los datos y recibir una nueva solicitud de confirmación."
            )
        return None

    async def _resumed_workflow_prompt(
        self, context: ConversationContext, workflow: PendingConversationWorkflow,
    ) -> str:
        if workflow.reason is not None:
            if workflow.reason.is_expired_at(self._current_local_time()):
                start = self._booking_start_at(workflow.reason.start_at)
                return await self._refresh_booking_availability(
                    context, start.date(), name_message_id=workflow.reason.name_message_id,
                )
            return self._booking_details_prompt(context, workflow.reason)
        if workflow.availability is not None:
            availability = workflow.availability
            if availability.is_expired_at(self._current_local_time()):
                if availability.appointment_id is not None:
                    return await self._recover_reschedule_slots(context, workflow)
                return await self._refresh_booking_availability(
                    context, date.fromisoformat(availability.target_date),
                    name_message_id=availability.name_message_id,
                )
            lines = [
                "- " + format_patient_time(datetime.fromisoformat(slot.start_at).astimezone(self._timezone))
                + " a " + format_patient_time(datetime.fromisoformat(slot.end_at).astimezone(self._timezone))
                for slot in availability.slots
            ]
            return (
                f"Horarios disponibles para el {date.fromisoformat(availability.target_date):%d/%m/%Y}:\n"
                + "\n".join(lines) + "\n\n" + APPOINTMENT_SLOT_SELECTION_REPLY
            )
        if workflow.action is not None:
            return await self._renew_paused_confirmation(context, workflow)
        if workflow.pending_date is not None:
            self._replace_workflow_context(
                context.conversation_id,
                active=PendingConversationWorkflow(
                    PendingConversationFlow.BOOKING_DATE,
                    pending_date=PendingAppointmentDate.start(
                        self._current_local_time(), name_message_id=workflow.pending_date.name_message_id,
                    ),
                ),
            )
        return APPOINTMENT_DATE_REPLY

    async def _refresh_booking_availability(
        self, context: ConversationContext, target_date: date, *, name_message_id: int | None,
    ) -> str:
        now = self._current_local_time()
        self._replace_workflow_context(
            context.conversation_id,
            active=PendingConversationWorkflow(
                PendingConversationFlow.BOOKING_DATE,
                pending_date=PendingAppointmentDate.start(now, name_message_id=name_message_id),
            ),
        )
        request = availability_request_for_date(target_date, now=now, timezone=self._timezone)
        if target_date < now.date() or request is None:
            return "El horario anterior ya pasó. " + APPOINTMENT_DATE_REPLY
        return await self._execute_date_only_availability(context, request)

    async def _renew_paused_confirmation(
        self, context: ConversationContext, workflow: PendingConversationWorkflow,
    ) -> str:
        action = workflow.action
        if action is None or self.tool_executor is None:
            return CONTROLLED_FALLBACK_REPLY
        # Mantenerla inactiva incluso si falla una lectura durante la recuperacion.
        self._replace_workflow_context(
            context.conversation_id, paused=PausedConversationWorkflow(workflow, utc_now()),
        )
        try:
            appointment = await self._find_appointment_for_confirmation(
                context.patient_scope, action.arguments["appointment_id"],
            )
        except Exception as error:
            public_error = public_error_from_exception(error)
            return self._calendar_error_reply(
                context, public_error.to_tool_error(), error_type=type(public_error).__name__,
            )
        if appointment is None:
            self._clear_pending_conversation_workflow(context.conversation_id)
            return AppointmentNotFound().message
        tool_call = action.to_tool_call()
        if action.tool_name is ToolName.RESCHEDULE_APPOINTMENT:
            requested_start = self._booking_start_at(action.arguments["new_start_at"])
            result = await self.tool_executor.execute(
                ToolRequest(
                    tool_name=ToolName.CHECK_AVAILABILITY,
                    arguments={
                        "start_at": requested_start.isoformat(),
                        "end_at": (requested_start + timedelta(minutes=30)).isoformat(),
                    },
                    patient_scope=context.patient_scope,
                )
            )
            if not result.ok:
                return result.error.message if result.error is not None else CONTROLLED_FALLBACK_REPLY
            if not isinstance(result.data, CheckAvailabilityOutput):
                return CONTROLLED_FALLBACK_REPLY
            if not any(slot.start_at == requested_start for slot in result.data.slots):
                return await self._recover_reschedule_slots(
                    context, workflow, appointment=appointment,
                )
        fresh_action = PendingAppointmentAction.from_tool_call(
            tool_call, appointment=appointment, now=self._current_local_time(),
        )
        if fresh_action is None:
            return CONTROLLED_FALLBACK_REPLY
        self._replace_workflow_context(
            context.conversation_id,
            active=PendingConversationWorkflow(
                PendingConversationFlow.APPOINTMENT_CONFIRMATION, action=fresh_action,
            ),
        )
        return fresh_action.confirmation_prompt()

    async def _recover_reschedule_slots(
        self, context: ConversationContext, workflow: PendingConversationWorkflow,
        *, appointment: Appointment | None = None,
    ) -> str:
        """No descartar la intencion pausada hasta persistir una lista nueva."""
        self._replace_workflow_context(
            context.conversation_id, paused=PausedConversationWorkflow(workflow, utc_now()),
        )
        if workflow.action is not None:
            tool_call = workflow.action.to_tool_call()
        elif workflow.availability is not None:
            availability = workflow.availability
            tool_call = ToolCall(
                name=ToolName.RESCHEDULE_APPOINTMENT.value,
                arguments={
                    "appointment_id": availability.appointment_id,
                    "new_start_at": availability.slots[0].start_at,
                },
                call_id=availability.call_id,
            )
        else:
            return CONTROLLED_FALLBACK_REPLY
        if appointment is None:
            try:
                appointment = await self._find_appointment_for_confirmation(
                    context.patient_scope, tool_call.arguments["appointment_id"],
                )
            except Exception as error:
                public_error = public_error_from_exception(error)
                return self._calendar_error_reply(
                    context, public_error.to_tool_error(), error_type=type(public_error).__name__,
                )
        if appointment is None:
            self._clear_pending_conversation_workflow(context.conversation_id)
            return AppointmentNotFound().message
        reply = await self._offer_reschedule_availability(context, tool_call, appointment)
        fresh_workflow = self._load_pending_conversation_workflow(context.conversation_id)
        if fresh_workflow.availability is not None:
            self._replace_workflow_context(context.conversation_id, active=fresh_workflow)
        return reply

    def _booking_start_at(self, value: str) -> datetime:
        start = datetime.fromisoformat(value)
        if start.utcoffset() is None:
            start = start.replace(tzinfo=self._timezone)
        return start.astimezone(self._timezone)

    def _booking_details_prompt(
        self, context: ConversationContext, reason: PendingAppointmentReason,
    ) -> str:
        needs_name = reason.name_required
        if needs_name is None:
            needs_name = self._load_patient_name(context.patient_id) is None
        start = self._booking_start_at(reason.start_at)
        return (
            f"Continuamos con tu solicitud para el {start:%d/%m/%Y} "
            f"a las {format_patient_time(start)}. "
            + (APPOINTMENT_NAME_REPLY if needs_name else APPOINTMENT_REASON_REPLY)
        )

    def _is_expected_pending_reply(
        self,
        context: ConversationContext,
        workflow: PendingConversationWorkflow,
    ) -> bool:
        if workflow.action is not None:
            return (
                classify_confirmation(context.incoming_text)
                is not ConfirmationDecision.UNKNOWN
            )
        if workflow.availability is not None:
            return (
                is_pending_slot_selection(context.incoming_text.strip().strip("¿?").strip(), workflow.flow)
                and workflow.availability.matching_slot(
                    context.incoming_text,
                    timezone=self._timezone,
                )
                is not None
            )
        if workflow.pending_date is not None:
            return (
                date_only_availability_follow_up_request(
                    context.incoming_text,
                    now=self._current_local_time(),
                    timezone=self._timezone,
                )
                is not None
            )
        return False

    def _abandoned_workflow_reply(
        self,
        workflow: PendingConversationWorkflow,
    ) -> str:
        if workflow.action is not None:
            return "No se realizó ningún cambio en tu cita."
        if workflow.flow is PendingConversationFlow.RESCHEDULE_AVAILABILITY:
            return "De acuerdo, dejaré tu cita como está. No la he modificado."
        return "De acuerdo, cancelé la solicitud. No se creó ninguna cita nueva."

    @staticmethod
    def _ambiguous_cancel_reply(
        workflow: PendingConversationWorkflow,
    ) -> str:
        if workflow.action is not None:
            return (
                "¿Quieres abandonar la operación pendiente y mantener tu cita, "
                "o solicitar la cancelación de una cita existente? "
                "Indícame qué deseas hacer; todavía no se realizó ningún cambio."
            )
        if workflow.flow is PendingConversationFlow.RESCHEDULE_AVAILABILITY:
            return (
                "¿Quieres abandonar el cambio y dejar tu cita como está, o cancelar "
                "la cita existente? No haré ningún cambio hasta que me indiques."
            )
        return (
            "¿Quieres abandonar esta solicitud para agendar o cancelar una cita que ya "
            "tienes? Todavía no se ha creado una cita nueva."
        )

    @staticmethod
    def _pending_interruption_clarification(
        workflow: PendingConversationWorkflow,
        *,
        expected_reply: bool,
    ) -> str:
        if workflow.action is not None:
            return CONFIRMATION_RESPONSE_INSTRUCTIONS
        if workflow.flow is PendingConversationFlow.RESCHEDULE_AVAILABILITY:
            if expected_reply:
                return (
                    "¿Quieres elegir ese horario? Escribe la hora para seleccionarlo, "
                    "o dime si prefieres dejar tu cita como está."
                )
            return (
                "No identifiqué una hora de la lista. Elige uno de los horarios ofrecidos "
                "o dime si prefieres dejar tu cita como está."
            )
        if workflow.flow is PendingConversationFlow.BOOKING_AVAILABILITY:
            if expected_reply:
                return (
                    "¿Quieres elegir ese horario? Escribe la hora para seleccionarlo, "
                    "o dime si prefieres abandonar la solicitud."
                )
            return (
                "No identifiqué una hora de la lista. Elige uno de los horarios ofrecidos "
                "o dime si prefieres abandonar la solicitud."
            )
        if workflow.flow is PendingConversationFlow.BOOKING_DATE:
            if expected_reply:
                return (
                    "¿Quieres reservar para ese día? Confírmamelo o dime si prefieres "
                    "hacer otra gestión."
                )
            return (
                "Dime qué día quieres reservar o indícame si prefieres hacer otra gestión."
            )
        return (
            "¿Quieres continuar con la solicitud de cita o hacer otra gestión? "
            "Todavía no se ha creado ninguna cita."
        )

    def _clear_pending_conversation_workflow(self, conversation_id: int) -> None:
        self._replace_workflow_context(conversation_id)

    async def _resolve_reschedule_request_without_target_time(
        self,
        context: ConversationContext,
    ) -> str | None:
        if (
            self.tool_executor is None
            or not is_reschedule_request_without_target_time(context.incoming_text)
        ):
            return None

        result = await self.tool_executor.execute(
            ToolRequest(
                tool_name=ToolName.LIST_APPOINTMENTS,
                arguments={},
                patient_scope=context.patient_scope,
            )
        )
        if not result.ok or not isinstance(result.data, ListAppointmentsOutput):
            if result.error is not None:
                return self._calendar_error_reply(
                    context,
                    result.error,
                    error_type="ToolError",
                )
            return "No pude consultar tus citas. Intenta nuevamente."

        appointments = result.data.appointments
        if not appointments:
            return "No encontré citas vigentes para modificar."

        candidates = self._reschedule_target_candidates(context, appointments)
        if len(candidates) != 1:
            return self._format_reschedule_target_selection(candidates)

        appointment = candidates[0]
        requested_date = date_only_availability_follow_up_request(
            context.incoming_text,
            now=self._current_local_time(),
            timezone=self._timezone,
        )
        target_date = (
            requested_date.start_at.astimezone(self._timezone).date()
            if requested_date is not None
            else appointment.start_at.astimezone(self._timezone).date()
        )
        local_start = appointment.start_at.astimezone(self._timezone)
        placeholder_start = local_start.replace(
            year=target_date.year,
            month=target_date.month,
            day=target_date.day,
        )
        tool_call = ToolCall(
            name=ToolName.RESCHEDULE_APPOINTMENT.value,
            arguments={
                "appointment_id": appointment.id,
                "new_start_at": placeholder_start.isoformat(),
            },
            call_id=f"backend-reschedule-availability-{context.incoming_message_id}",
        )
        return await self._offer_reschedule_availability(
            context,
            tool_call,
            appointment,
        )

    def _reschedule_target_candidates(
        self,
        context: ConversationContext,
        appointments: Sequence[Appointment],
    ) -> tuple[Appointment, ...]:
        listed_candidates = self._recently_listed_appointment_candidates(
            context,
            appointments,
        )
        source_time = self._source_appointment_time(context.incoming_text)

        if listed_candidates:
            if source_time is None:
                return listed_candidates
            narrowed = tuple(
                appointment
                for appointment in listed_candidates
                if self._appointment_local_time(appointment) == source_time
            )
            return narrowed or listed_candidates

        if source_time is not None:
            matching_appointments = tuple(
                appointment
                for appointment in appointments
                if self._appointment_local_time(appointment) == source_time
            )
            if matching_appointments:
                return matching_appointments
        return tuple(appointments)

    def _recently_listed_appointment_candidates(
        self,
        context: ConversationContext,
        appointments: Sequence[Appointment],
    ) -> tuple[Appointment, ...] | None:
        history = self.get_history(context.conversation_id)
        for index in range(len(history) - 1, -1, -1):
            message = history[index]
            if message.direction != "outgoing" or message.status != "sent":
                continue
            listed_times = {
                parse_time_selection(match.group("time"))
                for match in _LISTED_APPOINTMENT_START_TIME_PATTERN.finditer(message.text)
            }
            if not listed_times:
                continue

            requested_date = None
            prior_incoming = next(
                (
                    prior
                    for prior in reversed(history[:index])
                    if prior.direction == "incoming"
                ),
                None,
            )
            if prior_incoming is not None:
                date_request = date_only_availability_follow_up_request(
                    prior_incoming.text,
                    now=self._current_local_time(),
                    timezone=self._timezone,
                )
                if date_request is not None:
                    requested_date = date_request.start_at.astimezone(
                        self._timezone
                    ).date()
            if requested_date is None:
                date_match = re.search(
                    r"\b(?P<day>\d{2})/(?P<month>\d{2})/(?P<year>\d{4})\b",
                    message.text,
                )
                if date_match is not None:
                    requested_date = date(
                        int(date_match.group("year")),
                        int(date_match.group("month")),
                        int(date_match.group("day")),
                    )

            return tuple(
                appointment
                for appointment in appointments
                if self._appointment_local_time(appointment) in listed_times
                and (
                    requested_date is None
                    or appointment.start_at.astimezone(self._timezone).date()
                    == requested_date
                )
            )
        return None

    def _source_appointment_time(self, text: str) -> tuple[int, int] | None:
        source_time = _SOURCE_APPOINTMENT_TIME_PATTERN.search(text)
        if source_time is None:
            return None
        return parse_time_selection(source_time.group("time"))

    def _appointment_local_time(
        self,
        appointment: Appointment,
    ) -> tuple[int, int]:
        local_start = appointment.start_at.astimezone(self._timezone)
        return local_start.hour, local_start.minute

    def _format_reschedule_target_selection(
        self,
        appointments: Sequence[Appointment],
    ) -> str:
        if not appointments:
            return "No pude identificar la cita que quieres modificar."
        options = []
        for appointment in appointments:
            start_at = appointment.start_at.astimezone(self._timezone)
            end_at = appointment.end_at.astimezone(self._timezone)
            options.append(
                f"- {start_at:%d/%m/%Y}, "
                f"{format_patient_time(start_at)} a {format_patient_time(end_at)}"
            )
        return (
            "¿Cuál cita quieres modificar? Indica el día y horario de una de estas:\n"
            + "\n".join(options)
        )

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
        previous_date = self._load_pending_appointment_date(context.conversation_id)
        name_message_id = previous_date.name_message_id if previous_date is not None else None
        self._save_pending_appointment_date(
            context.conversation_id,
            PendingAppointmentDate.start(now, name_message_id=name_message_id),
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
                name_message_id=name_message_id,
            )
            if pending_availability is not None:
                self._save_pending_appointment_availability(
                    context.conversation_id,
                    pending_availability,
                )
            elif name_message_id is not None:
                self._save_pending_appointment_date(
                    context.conversation_id,
                    PendingAppointmentDate.start(now, name_message_id=name_message_id),
                )
        else:
            self._save_pending_appointment_date(
                context.conversation_id,
                PendingAppointmentDate.start(self._current_local_time(), name_message_id=name_message_id),
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
            now=self._current_local_time(),
        )
        if pending_availability.name_message_id is not None:
            pending_reason = pending_reason.with_name_message(pending_availability.name_message_id)
        reply = self._start_pending_appointment_reason(context, pending_reason)
        self._clear_pending_appointment_availability(context.conversation_id)
        return reply

    async def _handle_mutation_request(
        self,
        context: ConversationContext,
        tool_call: ToolCall,
        patient_scope: PatientScope,
    ) -> str | None:
        if (
            self._load_paused_workflow(context.conversation_id) is not None
            and tool_call.name in {
                ToolName.CREATE_APPOINTMENT.value,
                ToolName.CANCEL_APPOINTMENT.value,
                ToolName.RESCHEDULE_APPOINTMENT.value,
            }
        ):
            return (
                "Tu gestión sigue pausada. Para continuar, escribe ‘retomemos la cita’, "
                "o indica qué nueva gestión quieres realizar."
            )
        pending_reason = PendingAppointmentReason.from_tool_call(
            tool_call,
            source_message_id=context.incoming_message_id,
            now=self._current_local_time(),
        )
        if pending_reason is not None:
            pending_reason = replace(
                pending_reason, start_at=self._booking_start_at(pending_reason.start_at).isoformat(),
            )
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
        pending_action = PendingAppointmentAction.from_tool_call(
            tool_call, now=self._current_local_time(),
        )
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
            now=self._current_local_time(),
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
            now=self._current_local_time(),
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
        if pending_action.is_expired_at(self._current_local_time()):
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
        if pending_reason.is_expired_at(self._current_local_time()):
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
        return (
            APPOINTMENT_REASON_REPLY if pending_reason.name_required is False
            else APPOINTMENT_NAME_REPLY
        )

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
        paused = self._load_paused_workflow(context.conversation_id)
        if paused is not None:
            workflow = paused.workflow
            detail = "falta indicar el día"
            if workflow.reason is not None:
                reason = workflow.reason
                start = self._booking_start_at(reason.start_at)
                needs_name = reason.name_required
                if needs_name is None:
                    needs_name = self._load_patient_name(context.patient_id) is None
                detail = (
                    f"reserva solicitada para {start:%d/%m/%Y}, {format_patient_time(start)}; "
                    + ("falta nombre" if needs_name else "nombre recibido; falta motivo")
                    + "; el horario elegido no está reservado"
                )
            elif workflow.availability is not None:
                detail = f"falta elegir horario para {workflow.availability.target_date}"
            elif workflow.action is not None:
                detail = "cambio o cancelación pendiente; requiere una confirmación nueva al retomar"
            messages[0] = ChatMessage(
                role="system",
                content=messages[0].content + "\nGestión pausada (datos del backend): " + detail
                + "\nResponde el tema actual. No pidas datos de la cita pausada ni afirmes "
                "que se realizó. El backend controla la recuperación y las confirmaciones.",
            )

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
    return _format_list_times(
        _split_appointment_reason_label(_convert_markdown_tables(reply))
    )


_DISPLAY_TIME_PATTERN = re.compile(
    r"\b\d{1,2}:\d{2}(?:[ \t]*[ap]\.?m\.?)?\b", flags=re.IGNORECASE
)
_DISPLAY_TIME_TEXT = r"\d{1,2}:\d{2}(?:[ \t]*[ap]\.?m\.?)?"
_LIST_TIME_FIELD_PATTERN = re.compile(
    r"(?P<prefix>(?:^|;)[ \t]*(?:\*?(?:Horario|Hora):\*?[ \t]*)?"
    r"(?:\d{2}/\d{2}/\d{4}[, \t]+)?)"
    rf"(?P<value>{_DISPLAY_TIME_TEXT}(?:[ \t]*(?:a|[-–—])[ \t]*{_DISPLAY_TIME_TEXT})?)"
    r"(?=$|[; \t])",
    flags=re.IGNORECASE,
)


def _format_list_times(text: str) -> str:
    """Normaliza las horas de listas del LLM sin reescribir los motivos de consulta."""
    def replace_time(match: re.Match[str]) -> str:
        parsed = parse_time_selection(match.group())
        if parsed is None or not 0 <= parsed[1] < 60:
            return match.group()
        return format_patient_time(time(*parsed))

    def replace_field(match: re.Match[str]) -> str:
        return match.group("prefix") + _DISPLAY_TIME_PATTERN.sub(
            replace_time, match.group("value")
        )

    lines = []
    for line in text.splitlines():
        item = re.match(r"^(?P<bullet>[ \t]*(?:[-*•]|\d+[.)])[ \t]+)(?P<content>.*)$", line)
        if item is not None:
            line = item.group("bullet") + _LIST_TIME_FIELD_PATTERN.sub(
                replace_field, item.group("content")
            )
        lines.append(line)
    return "\n".join(lines)


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
