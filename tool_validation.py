from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from types import MappingProxyType
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from calendar_domain import (
    APPOINTMENT_DURATION,
    Appointment,
    AppointmentStatus,
    DomainValidationError,
    ToolErrorCode,
)
from tool_contracts import (
    CancelAppointmentInput,
    CheckAvailabilityInput,
    CreateAppointmentInput,
    ListAppointmentsInput,
    RescheduleAppointmentInput,
    ToolInput,
)


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start_at: time
    end_at: time

    def __post_init__(self) -> None:
        if self.start_at.tzinfo is not None or self.end_at.tzinfo is not None:
            raise DomainValidationError("El horario laboral no debe incluir zona horaria")
        if self.end_at <= self.start_at:
            raise DomainValidationError("end_at debe ser posterior a start_at")

    def contains(self, start_at: datetime, end_at: datetime) -> bool:
        return (
            start_at.date() == end_at.date()
            and start_at.time() >= self.start_at
            and end_at.time() <= self.end_at
        )


@dataclass(frozen=True, slots=True)
class BusinessHours:
    """Horario semanal configurado por el backend, sin festivos incluidos."""

    timezone_name: str
    windows_by_weekday: Mapping[int, Sequence[TimeWindow]]
    _timezone: ZoneInfo = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        timezone = _load_timezone(self.timezone_name)
        normalized: dict[int, tuple[TimeWindow, ...]] = {}
        for weekday, windows in self.windows_by_weekday.items():
            if weekday not in range(7):
                raise DomainValidationError("weekday debe estar entre 0 y 6")
            day_windows = tuple(windows)
            if not day_windows:
                raise DomainValidationError("Cada dia configurado debe tener un horario")
            for previous, current in zip(day_windows, day_windows[1:]):
                if current.start_at < previous.end_at:
                    raise DomainValidationError("Los horarios laborales no pueden solaparse")
            normalized[weekday] = day_windows
        object.__setattr__(self, "windows_by_weekday", MappingProxyType(normalized))
        object.__setattr__(self, "_timezone", timezone)

    @property
    def timezone(self) -> ZoneInfo:
        return self._timezone

    def contains(self, start_at: datetime, end_at: datetime) -> bool:
        local_start = start_at.astimezone(self.timezone)
        local_end = end_at.astimezone(self.timezone)
        windows = self.windows_by_weekday.get(local_start.weekday(), ())
        return any(window.contains(local_start, local_end) for window in windows)

    def intersects(self, start_at: datetime, end_at: datetime) -> bool:
        local_start = start_at.astimezone(self.timezone)
        local_end = end_at.astimezone(self.timezone)
        current_day = local_start.date()
        last_day = local_end.date()
        while current_day <= last_day:
            if self.windows_by_weekday.get(current_day.weekday()):
                return True
            current_day += timedelta(days=1)
        return False


class ToolValidationError(DomainValidationError):
    """Error tipificado que el ejecutor convertira en `ToolResult.failure()`."""

    def __init__(
        self,
        code: ToolErrorCode,
        message: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def validate_tool_input(
    tool_input: ToolInput,
    *,
    business_hours: BusinessHours,
    now: datetime,
    existing_appointments: Sequence[Appointment] = (),
) -> None:
    """Valida reglas locales antes de delegar en cualquier proveedor."""
    _require_aware(now, "now")

    if isinstance(tool_input, CheckAvailabilityInput):
        _validate_not_past(tool_input.start_at, now)
        if not business_hours.intersects(tool_input.start_at, tool_input.end_at):
            _raise(
                ToolErrorCode.OUTSIDE_BUSINESS_HOURS,
                "El rango no contiene horario laboral configurado.",
            )
        return

    if isinstance(tool_input, CreateAppointmentInput):
        end_at = tool_input.start_at + APPOINTMENT_DURATION
        _validate_appointment_window(tool_input.start_at, end_at, business_hours, now)
        _validate_no_overlap(
            tool_input.start_at,
            end_at,
            existing_appointments,
        )
        return

    if isinstance(tool_input, ListAppointmentsInput):
        # Consultar el historial no modifica la agenda y puede incluir fechas pasadas.
        return

    appointment = _find_appointment(
        existing_appointments,
        tool_input.appointment_id,
    )
    if appointment.patient_scope.patient_id != tool_input.patient_scope.patient_id:
        _raise(
            ToolErrorCode.APPOINTMENT_ACCESS_DENIED,
            "La cita no pertenece al paciente actual.",
        )

    if isinstance(tool_input, RescheduleAppointmentInput):
        if not appointment.can_be_rescheduled:
            _raise(
                ToolErrorCode.INVALID_APPOINTMENT_STATE,
                "La cita no puede reprogramarse en su estado actual.",
            )
        end_at = tool_input.new_start_at + APPOINTMENT_DURATION
        _validate_appointment_window(
            tool_input.new_start_at,
            end_at,
            business_hours,
            now,
        )
        _validate_no_overlap(
            tool_input.new_start_at,
            end_at,
            existing_appointments,
            excluded_appointment_id=appointment.id,
        )
        return

    if not appointment.can_be_cancelled:
        _raise(
            ToolErrorCode.INVALID_APPOINTMENT_STATE,
            "La cita no puede cancelarse en su estado actual.",
        )


def _validate_appointment_window(
    start_at: datetime,
    end_at: datetime,
    business_hours: BusinessHours,
    now: datetime,
) -> None:
    _validate_not_past(start_at, now)
    if not business_hours.contains(start_at, end_at):
        _raise(
            ToolErrorCode.OUTSIDE_BUSINESS_HOURS,
            "El horario solicitado esta fuera del horario laboral.",
        )


def _validate_not_past(value: datetime, now: datetime) -> None:
    if value < now:
        _raise(ToolErrorCode.DATE_IN_PAST, "No se aceptan fechas pasadas.")


def _validate_no_overlap(
    start_at: datetime,
    end_at: datetime,
    appointments: Sequence[Appointment],
    excluded_appointment_id: str | None = None,
) -> None:
    active_statuses = {
        AppointmentStatus.SCHEDULED,
        AppointmentStatus.CONFIRMED,
    }
    for appointment in appointments:
        if appointment.id == excluded_appointment_id:
            continue
        if appointment.status not in active_statuses:
            continue
        if start_at < appointment.end_at and end_at > appointment.start_at:
            _raise(
                ToolErrorCode.SLOT_UNAVAILABLE,
                "El horario se superpone con una cita existente.",
            )


def _find_appointment(
    appointments: Sequence[Appointment],
    appointment_id: str,
) -> Appointment:
    for appointment in appointments:
        if appointment.id == appointment_id:
            return appointment
    _raise(ToolErrorCode.APPOINTMENT_NOT_FOUND, "La cita no existe.")
    raise AssertionError("_raise siempre lanza una excepcion")


def _load_timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except (TypeError, ZoneInfoNotFoundError) as error:
        raise DomainValidationError(f"Zona horaria invalida: {value}") from error


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError(f"{name} debe incluir una zona horaria")


def _raise(code: ToolErrorCode, message: str) -> None:
    raise ToolValidationError(code, message)
