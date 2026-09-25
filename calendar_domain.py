from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import ClassVar, Protocol


APPOINTMENT_DURATION = timedelta(minutes=30)


class DomainValidationError(ValueError):
    """Indica que un valor no cumple una regla del dominio."""


class AppointmentStatus(StrEnum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class ToolName(StrEnum):
    CHECK_AVAILABILITY = "check_availability"
    CREATE_APPOINTMENT = "create_appointment"
    LIST_APPOINTMENTS = "list_appointments"
    RESCHEDULE_APPOINTMENT = "reschedule_appointment"
    CANCEL_APPOINTMENT = "cancel_appointment"


class ToolErrorCode(StrEnum):
    INVALID_ARGUMENTS = "invalid_arguments"
    DATE_IN_PAST = "date_in_past"
    SLOT_UNAVAILABLE = "slot_unavailable"
    OUTSIDE_BUSINESS_HOURS = "outside_business_hours"
    APPOINTMENT_NOT_FOUND = "appointment_not_found"
    APPOINTMENT_ACCESS_DENIED = "appointment_access_denied"
    INVALID_APPOINTMENT_STATE = "invalid_appointment_state"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_ERROR = "provider_error"


class PublicCalendarError(Exception):
    """Base para errores estables que pueden devolverse al agente."""

    code: ClassVar[ToolErrorCode]
    default_message: ClassVar[str]
    retryable: ClassVar[bool] = False

    def __init__(self) -> None:
        super().__init__(self.default_message)

    def to_tool_error(self) -> "ToolError":
        return ToolError(
            code=self.code,
            message=self.default_message,
            retryable=self.retryable,
        )


class InvalidToolArguments(PublicCalendarError):
    code = ToolErrorCode.INVALID_ARGUMENTS
    default_message = "Los argumentos de la herramienta no son validos."


class SlotUnavailable(PublicCalendarError):
    code = ToolErrorCode.SLOT_UNAVAILABLE
    default_message = "El horario solicitado no esta disponible."


class OutsideBusinessHours(PublicCalendarError):
    code = ToolErrorCode.OUTSIDE_BUSINESS_HOURS
    default_message = "El horario solicitado esta fuera del horario laboral."


class AppointmentNotFound(PublicCalendarError):
    code = ToolErrorCode.APPOINTMENT_NOT_FOUND
    default_message = "No se encontro la cita solicitada."


class AppointmentAccessDenied(PublicCalendarError):
    code = ToolErrorCode.APPOINTMENT_ACCESS_DENIED
    default_message = "No tienes permiso para modificar esa cita."


class InvalidAppointmentState(PublicCalendarError):
    code = ToolErrorCode.INVALID_APPOINTMENT_STATE
    default_message = "La cita no puede modificarse en su estado actual."


class CalendarProviderUnavailable(PublicCalendarError):
    code = ToolErrorCode.PROVIDER_UNAVAILABLE
    default_message = (
        "El servicio de agenda no esta disponible en este momento. "
        "Intenta nuevamente mas tarde."
    )
    retryable = True


class CalendarProviderError(PublicCalendarError):
    code = ToolErrorCode.PROVIDER_ERROR
    default_message = (
        "No se pudo completar la operacion de agenda. "
        "Intenta nuevamente mas tarde."
    )


@dataclass(frozen=True, slots=True)
class PatientScope:
    """Identidad establecida por el backend a partir del contexto de WhatsApp."""

    patient_id: int
    conversation_id: int
    whatsapp_number: str

    def __post_init__(self) -> None:
        if self.patient_id <= 0:
            raise DomainValidationError("patient_id debe ser positivo")
        if self.conversation_id <= 0:
            raise DomainValidationError("conversation_id debe ser positivo")
        _require_text(self.whatsapp_number, "whatsapp_number")


@dataclass(frozen=True, slots=True)
class Appointment:
    id: str
    patient_scope: PatientScope
    calendar_id: str
    start_at: datetime
    end_at: datetime
    reason: str
    status: AppointmentStatus = AppointmentStatus.SCHEDULED

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_text(self.calendar_id, "calendar_id")
        _require_text(self.reason, "reason")
        _validate_interval(
            self.start_at,
            self.end_at,
            expected_duration=APPOINTMENT_DURATION,
        )

    @property
    def can_be_rescheduled(self) -> bool:
        return self.status in {
            AppointmentStatus.SCHEDULED,
            AppointmentStatus.CONFIRMED,
        }

    @property
    def can_be_cancelled(self) -> bool:
        return self.status in {
            AppointmentStatus.SCHEDULED,
            AppointmentStatus.CONFIRMED,
        }


@dataclass(frozen=True, slots=True)
class AvailableSlot:
    calendar_id: str
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.calendar_id, "calendar_id")
        _validate_interval(
            self.start_at,
            self.end_at,
            expected_duration=APPOINTMENT_DURATION,
        )


@dataclass(frozen=True, slots=True)
class ToolRequest:
    """Solicitud enriquecida con el alcance que el LLM no puede elegir."""

    tool_name: ToolName
    arguments: Mapping[str, object]
    patient_scope: PatientScope

    def __post_init__(self) -> None:
        forbidden_arguments = {
            "patient_id",
            "patient_scope",
            "calendar_id",
            "calendar_ids",
            "conversation_id",
            "duration_minutes",
            "timezone",
            "user_id",
            "whatsapp_number",
        }
        received_forbidden = forbidden_arguments.intersection(self.arguments)
        if received_forbidden:
            names = ", ".join(sorted(received_forbidden))
            raise DomainValidationError(
                f"La solicitud no puede incluir datos controlados por el backend: {names}"
            )
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))


@dataclass(frozen=True, slots=True)
class ToolError:
    code: ToolErrorCode
    message: str
    retryable: bool = False

    def __post_init__(self) -> None:
        _require_text(self.message, "message")


@dataclass(frozen=True, slots=True)
class ToolResult:
    ok: bool
    data: object | None = None
    error: ToolError | None = None

    def __post_init__(self) -> None:
        if self.ok and self.error is not None:
            raise DomainValidationError("Un resultado exitoso no puede contener error")
        if not self.ok and self.error is None:
            raise DomainValidationError("Un resultado fallido debe contener error")
        if not self.ok and self.data is not None:
            raise DomainValidationError("Un resultado fallido no puede contener datos")

    @classmethod
    def success(cls, data: object | None = None) -> "ToolResult":
        return cls(ok=True, data=data)

    @classmethod
    def failure(cls, error: ToolError) -> "ToolResult":
        return cls(ok=False, error=error)


class CalendarProvider(Protocol):
    """Contrato asíncrono para un proveedor configurado por el backend."""

    async def check_availability(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> Sequence[AvailableSlot]:
        """Devuelve slots libres dentro del rango solicitado."""

    async def create_appointment(
        self,
        *,
        patient_scope: PatientScope,
        start_at: datetime,
        reason: str,
    ) -> Appointment:
        """Crea una cita en los calendarios configurados por el backend."""

    async def list_appointments(
        self,
        *,
        patient_scope: PatientScope,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> Sequence[Appointment]:
        """Devuelve las citas vigentes del paciente dentro del rango opcional."""

    async def reschedule_appointment(
        self,
        *,
        patient_scope: PatientScope,
        appointment_id: str,
        new_start_at: datetime,
    ) -> Appointment:
        """Mueve una cita existente a un nuevo inicio."""

    async def cancel_appointment(
        self,
        *,
        patient_scope: PatientScope,
        appointment_id: str,
    ) -> Appointment:
        """Cancela una cita existente."""


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{name} no puede estar vacio")


def _validate_interval(
    start_at: datetime,
    end_at: datetime,
    expected_duration: timedelta,
) -> None:
    _require_timezone(start_at, "start_at")
    _require_timezone(end_at, "end_at")
    if end_at <= start_at:
        raise DomainValidationError("end_at debe ser posterior a start_at")
    if end_at - start_at != expected_duration:
        raise DomainValidationError("Las citas y slots deben durar 30 minutos")


def _require_timezone(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError(f"{name} debe incluir una zona horaria")
