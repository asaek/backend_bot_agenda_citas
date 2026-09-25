"""Bucle del agente entre el proveedor LLM y las herramientas del backend."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
import json
from calendar_domain import (
    DomainValidationError,
    PatientScope,
    ToolName,
    ToolRequest,
    ToolResult,
)
from llm_provider import (
    ChatMessage,
    LLMProvider,
    LLMProviderError,
    ToolCall,
)
from notification_domain import (
    AppointmentNotificationEventSink,
    appointment_notification_event_from_result,
)
from tool_executor import ToolExecutor
from tool_results import tool_result_from_exception


DEFAULT_AGENT_MAX_ITERATIONS = 3


class AgentOrchestrationError(LLMProviderError):
    """Indica que el agente no pudo completar su ciclo controlado."""


class AgentIterationLimitError(AgentOrchestrationError):
    """Indica que el LLM solicito demasiadas herramientas consecutivas."""


MutationRequestHandler = Callable[[ToolCall, PatientScope], Awaitable[str | None]]


class AgentOrchestrator:
    """Coordina respuestas LLM, herramientas y la redaccion final."""

    def __init__(
        self,
        *,
        llm_provider: LLMProvider,
        tool_executor: ToolExecutor,
        max_iterations: int = DEFAULT_AGENT_MAX_ITERATIONS,
    ) -> None:
        if max_iterations <= 0:
            raise ValueError("max_iterations debe ser positivo")
        self.llm_provider = llm_provider
        self.tool_executor = tool_executor
        self.max_iterations = max_iterations

    async def run(
        self,
        *,
        messages: Sequence[ChatMessage],
        patient_scope: PatientScope,
        incoming_message_id: int | None = None,
        on_appointment_event: AppointmentNotificationEventSink | None = None,
        on_mutation_requested: MutationRequestHandler | None = None,
    ) -> str:
        if on_appointment_event is not None and (
            incoming_message_id is None or incoming_message_id <= 0
        ):
            raise ValueError(
                "incoming_message_id es obligatorio para observar eventos de citas"
            )

        conversation = list(messages)

        for iteration in range(self.max_iterations + 1):
            response = await self.llm_provider.generate(conversation)
            if isinstance(response, str):
                return response
            if not isinstance(response, ToolCall):
                raise AgentOrchestrationError("El LLM devolvio una respuesta no soportada")
            if iteration == self.max_iterations:
                raise AgentIterationLimitError(
                    "El agente alcanzo el limite de iteraciones de herramientas"
                )

            tool_call = _with_call_id(response, iteration)
            if on_mutation_requested is not None:
                confirmation_reply = await on_mutation_requested(tool_call, patient_scope)
                if confirmation_reply is not None:
                    return confirmation_reply
            result = await self._execute_tool_call(tool_call, patient_scope)
            if on_appointment_event is not None and incoming_message_id is not None:
                self._emit_appointment_event(
                    tool_call=tool_call,
                    incoming_message_id=incoming_message_id,
                    patient_scope=patient_scope,
                    result=result,
                    event_sink=on_appointment_event,
                )
            conversation.append(
                ChatMessage(
                    role="assistant",
                    content=None,
                    tool_calls=(tool_call,),
                )
            )
            conversation.append(
                ChatMessage(
                    role="tool",
                    content=serialize_tool_result(result),
                    tool_call_id=tool_call.call_id,
                )
            )

        raise AgentIterationLimitError(
            "El agente alcanzo el limite de iteraciones de herramientas"
        )

    async def execute_confirmed_tool(
        self,
        *,
        tool_call: ToolCall,
        patient_scope: PatientScope,
        incoming_message_id: int | None = None,
        on_appointment_event: AppointmentNotificationEventSink | None = None,
    ) -> ToolResult:
        """Ejecuta una mutacion ya autorizada por el flujo de confirmacion."""
        result = await self._execute_tool_call(tool_call, patient_scope)
        if on_appointment_event is not None and incoming_message_id is not None:
            self._emit_appointment_event(
                tool_call=tool_call,
                incoming_message_id=incoming_message_id,
                patient_scope=patient_scope,
                result=result,
                event_sink=on_appointment_event,
            )
        return result

    @staticmethod
    def _emit_appointment_event(
        *,
        tool_call: ToolCall,
        incoming_message_id: int,
        patient_scope: PatientScope,
        result: ToolResult,
        event_sink: AppointmentNotificationEventSink,
    ) -> None:
        try:
            tool_name = ToolName(tool_call.name)
        except (TypeError, ValueError):
            return

        event = appointment_notification_event_from_result(
            tool_name=tool_name,
            tool_call_id=tool_call.call_id or "",
            incoming_message_id=incoming_message_id,
            patient_scope=patient_scope,
            result=result,
        )
        if event is not None:
            event_sink(event)

    async def _execute_tool_call(
        self,
        tool_call: ToolCall,
        patient_scope: PatientScope,
    ) -> ToolResult:
        try:
            tool_name = ToolName(tool_call.name)
            request = ToolRequest(
                tool_name=tool_name,
                arguments=tool_call.arguments,
                patient_scope=patient_scope,
            )
        except (TypeError, ValueError):
            return tool_result_from_exception(
                DomainValidationError("La herramienta solicitada no esta soportada")
            )
        except Exception as error:
            return tool_result_from_exception(error)
        return await self.tool_executor.execute(request)


def serialize_tool_result(result: ToolResult) -> str:
    """Convierte un resultado tipado en el mensaje estructurado del siguiente LLM."""
    payload: dict[str, object] = {"ok": result.ok}
    if result.ok:
        payload["data"] = _public_tool_value(result.data)
    elif result.error is not None:
        payload["error"] = {
            "code": result.error.code.value,
            "message": result.error.message,
            "retryable": result.error.retryable,
        }
    return json.dumps(payload, ensure_ascii=False, default=_json_default)


def _with_call_id(tool_call: ToolCall, iteration: int) -> ToolCall:
    if tool_call.call_id is not None:
        return tool_call
    return ToolCall(
        name=tool_call.name,
        arguments=tool_call.arguments,
        call_id=f"agent-tool-call-{iteration + 1}",
    )


def _json_default(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if is_dataclass(value):
        return _public_tool_value(value)
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"Tipo no serializable: {type(value).__name__}")


_BACKEND_ONLY_FIELDS = frozenset(
    {
        "patient_id",
        "patient_scope",
        "conversation_id",
        "whatsapp_number",
        "calendar_id",
        "calendar_ids",
    }
)


def _public_tool_value(value: object) -> object:
    if is_dataclass(value):
        return {
            field.name: _public_tool_value(getattr(value, field.name))
            for field in fields(value)
            if field.name not in _BACKEND_ONLY_FIELDS
        }
    if isinstance(value, Mapping):
        return {
            key: _public_tool_value(item)
            for key, item in value.items()
            if key not in _BACKEND_ONLY_FIELDS
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_public_tool_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
