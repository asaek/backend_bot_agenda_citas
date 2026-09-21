from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from calendar_domain import (
    Appointment,
    AvailableSlot,
    DomainValidationError,
    PatientScope,
    ToolName,
    ToolRequest,
)


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: ToolName
    description: str
    required_arguments: tuple[str, ...]
    optional_arguments: tuple[str, ...] = ()

    @property
    def allowed_arguments(self) -> frozenset[str]:
        return frozenset(self.required_arguments + self.optional_arguments)


TOOL_DEFINITIONS: Mapping[ToolName, ToolDefinition] = MappingProxyType(
    {
        ToolName.CHECK_AVAILABILITY: ToolDefinition(
            name=ToolName.CHECK_AVAILABILITY,
            description="Consulta espacios disponibles dentro de un rango de fechas.",
            required_arguments=("start_at", "end_at"),
        ),
        ToolName.CREATE_APPOINTMENT: ToolDefinition(
            name=ToolName.CREATE_APPOINTMENT,
            description="Crea una cita en un horario disponible.",
            required_arguments=("start_at", "reason"),
        ),
        ToolName.LIST_APPOINTMENTS: ToolDefinition(
            name=ToolName.LIST_APPOINTMENTS,
            description=(
                "Lista las citas del paciente; acepta un rango completo opcional "
                "con start_at y end_at."
            ),
            required_arguments=(),
            optional_arguments=("start_at", "end_at"),
        ),
        ToolName.RESCHEDULE_APPOINTMENT: ToolDefinition(
            name=ToolName.RESCHEDULE_APPOINTMENT,
            description="Mueve una cita existente a un nuevo horario.",
            required_arguments=("appointment_id", "new_start_at"),
        ),
        ToolName.CANCEL_APPOINTMENT: ToolDefinition(
            name=ToolName.CANCEL_APPOINTMENT,
            description="Cancela una cita existente.",
            required_arguments=("appointment_id",),
        ),
    }
)


def llm_tool_definitions() -> list[dict[str, object]]:
    """Devuelve los esquemas de herramientas para proveedores OpenAI-compatible."""
    date_time = {
        "type": "string",
        "format": "date-time",
        "description": "Fecha y hora ISO 8601; si no incluye zona se usa la del backend.",
    }
    return [
        {
            "type": "function",
            "function": {
                "name": ToolName.CHECK_AVAILABILITY.value,
                "description": (
                    "Consulta espacios disponibles de 30 minutos para un rango. "
                    "Usala cuando el paciente pida horarios y proporcione una fecha."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_at": date_time,
                        "end_at": date_time,
                    },
                    "required": ["start_at", "end_at"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": ToolName.CREATE_APPOINTMENT.value,
                "description": "Crea una cita de 30 minutos en un horario disponible.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_at": date_time,
                        "reason": {
                            "type": "string",
                            "description": "Motivo expresado por el paciente.",
                        },
                    },
                    "required": ["start_at", "reason"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": ToolName.LIST_APPOINTMENTS.value,
                "description": (
                    "Lista las citas del paciente. Usala cuando pregunte por sus "
                    "citas; sin fechas lista todas y con fechas requiere start_at "
                    "y end_at."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_at": date_time,
                        "end_at": date_time,
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": ToolName.RESCHEDULE_APPOINTMENT.value,
                "description": "Mueve una cita del paciente a un nuevo horario.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {
                            "type": "string",
                            "description": "ID interno de la cita devuelto por el backend.",
                        },
                        "new_start_at": date_time,
                    },
                    "required": ["appointment_id", "new_start_at"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": ToolName.CANCEL_APPOINTMENT.value,
                "description": "Cancela una cita del paciente.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appointment_id": {
                            "type": "string",
                            "description": "ID interno de la cita devuelto por el backend.",
                        },
                    },
                    "required": ["appointment_id"],
                    "additionalProperties": False,
                },
            },
        },
    ]


@dataclass(frozen=True, slots=True)
class CheckAvailabilityInput:
    patient_scope: PatientScope
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        _validate_range(self.start_at, self.end_at)


@dataclass(frozen=True, slots=True)
class CreateAppointmentInput:
    patient_scope: PatientScope
    start_at: datetime
    reason: str

    def __post_init__(self) -> None:
        _require_timezone(self.start_at, "start_at")
        _require_text(self.reason, "reason")


@dataclass(frozen=True, slots=True)
class ListAppointmentsInput:
    patient_scope: PatientScope
    start_at: datetime | None = None
    end_at: datetime | None = None

    def __post_init__(self) -> None:
        if (self.start_at is None) != (self.end_at is None):
            raise DomainValidationError(
                "start_at y end_at deben proporcionarse juntos para listar citas"
            )
        if self.start_at is not None and self.end_at is not None:
            _validate_range(self.start_at, self.end_at)


@dataclass(frozen=True, slots=True)
class RescheduleAppointmentInput:
    patient_scope: PatientScope
    appointment_id: str
    new_start_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.appointment_id, "appointment_id")
        _require_timezone(self.new_start_at, "new_start_at")


@dataclass(frozen=True, slots=True)
class CancelAppointmentInput:
    patient_scope: PatientScope
    appointment_id: str

    def __post_init__(self) -> None:
        _require_text(self.appointment_id, "appointment_id")


@dataclass(frozen=True, slots=True)
class CheckAvailabilityOutput:
    slots: Sequence[AvailableSlot]

    def __post_init__(self) -> None:
        object.__setattr__(self, "slots", tuple(self.slots))


@dataclass(frozen=True, slots=True)
class CreateAppointmentOutput:
    appointment: Appointment


@dataclass(frozen=True, slots=True)
class ListAppointmentsOutput:
    appointments: Sequence[Appointment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "appointments", tuple(self.appointments))


@dataclass(frozen=True, slots=True)
class RescheduleAppointmentOutput:
    appointment: Appointment


@dataclass(frozen=True, slots=True)
class CancelAppointmentOutput:
    appointment: Appointment


ToolInput = (
    CheckAvailabilityInput
    | CreateAppointmentInput
    | ListAppointmentsInput
    | RescheduleAppointmentInput
    | CancelAppointmentInput
)


def parse_tool_request(
    request: ToolRequest,
    *,
    default_timezone: str,
) -> ToolInput:
    """Valida y normaliza argumentos del LLM usando la zona del backend."""
    timezone = _load_timezone(default_timezone)
    definition = TOOL_DEFINITIONS.get(request.tool_name)
    if definition is None:
        raise DomainValidationError(f"Herramienta no soportada: {request.tool_name}")
    _validate_argument_names(request.arguments, definition)

    if request.tool_name is ToolName.CHECK_AVAILABILITY:
        return CheckAvailabilityInput(
            patient_scope=request.patient_scope,
            start_at=_parse_datetime(request.arguments["start_at"], "start_at", timezone),
            end_at=_parse_datetime(request.arguments["end_at"], "end_at", timezone),
        )

    if request.tool_name is ToolName.CREATE_APPOINTMENT:
        return CreateAppointmentInput(
            patient_scope=request.patient_scope,
            start_at=_parse_datetime(request.arguments["start_at"], "start_at", timezone),
            reason=_parse_text(request.arguments["reason"], "reason"),
        )

    if request.tool_name is ToolName.LIST_APPOINTMENTS:
        return ListAppointmentsInput(
            patient_scope=request.patient_scope,
            start_at=_parse_optional_datetime(
                request.arguments.get("start_at"), "start_at", timezone
            ),
            end_at=_parse_optional_datetime(
                request.arguments.get("end_at"), "end_at", timezone
            ),
        )

    if request.tool_name is ToolName.RESCHEDULE_APPOINTMENT:
        return RescheduleAppointmentInput(
            patient_scope=request.patient_scope,
            appointment_id=_parse_text(
                request.arguments["appointment_id"], "appointment_id"
            ),
            new_start_at=_parse_datetime(
                request.arguments["new_start_at"], "new_start_at", timezone
            ),
        )

    return CancelAppointmentInput(
        patient_scope=request.patient_scope,
        appointment_id=_parse_text(
            request.arguments["appointment_id"], "appointment_id"
        ),
    )


def _validate_argument_names(
    arguments: Mapping[str, object],
    definition: ToolDefinition,
) -> None:
    missing = set(definition.required_arguments).difference(arguments)
    if missing:
        names = ", ".join(sorted(missing))
        raise DomainValidationError(f"Faltan argumentos requeridos: {names}")

    unknown = set(arguments).difference(definition.allowed_arguments)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise DomainValidationError(f"Argumentos no soportados: {names}")


def _load_timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except (TypeError, ZoneInfoNotFoundError) as error:
        raise DomainValidationError(f"Zona horaria invalida: {value}") from error


def _parse_datetime(value: object, name: str, timezone: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise DomainValidationError(f"{name} debe ser una fecha ISO valida") from error
    else:
        raise DomainValidationError(f"{name} debe ser una fecha ISO valida")

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


def _parse_optional_datetime(
    value: object | None,
    name: str,
    timezone: ZoneInfo,
) -> datetime | None:
    if value is None:
        return None
    return _parse_datetime(value, name, timezone)


def _parse_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise DomainValidationError(f"{name} debe ser texto")
    _require_text(value, name)
    return value.strip()


def _require_text(value: str, name: str) -> None:
    if not value.strip():
        raise DomainValidationError(f"{name} no puede estar vacio")


def _require_timezone(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError(f"{name} debe incluir una zona horaria")


def _validate_range(start_at: datetime, end_at: datetime) -> None:
    _require_timezone(start_at, "start_at")
    _require_timezone(end_at, "end_at")
    if end_at <= start_at:
        raise DomainValidationError("end_at debe ser posterior a start_at")
