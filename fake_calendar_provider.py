"""Proveedor de calendario en memoria para pruebas deterministas."""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from calendar_domain import (
    APPOINTMENT_DURATION,
    Appointment,
    AppointmentAccessDenied,
    AppointmentNotFound,
    AppointmentStatus,
    AvailableSlot,
    CalendarProvider,
    DomainValidationError,
    InvalidAppointmentState,
    InvalidToolArguments,
    PatientScope,
    PublicCalendarError,
    SlotUnavailable,
    ToolName,
)


@dataclass(frozen=True, slots=True)
class BusyPeriod:
    """Periodo ocupado externo que impide ofrecer un espacio."""

    calendar_id: str
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.calendar_id, "calendar_id")
        _require_aware(self.start_at, "start_at")
        _require_aware(self.end_at, "end_at")
        if self.end_at <= self.start_at:
            raise DomainValidationError("end_at debe ser posterior a start_at")


FailureFactory = Callable[[], Exception]


class FakeCalendarProvider(CalendarProvider):
    """Implementacion en memoria del contrato que usara Google Calendar."""

    def __init__(
        self,
        *,
        calendar_ids: Sequence[str] = ("calendar-1",),
        busy_periods: Sequence[BusyPeriod] = (),
        appointments: Sequence[Appointment] = (),
        appointment_id_prefix: str = "appointment",
        simulated_errors: Mapping[
            ToolName | str,
            PublicCalendarError | type[PublicCalendarError],
        ] | None = None,
    ) -> None:
        normalized_calendar_ids = tuple(calendar_ids)
        if not normalized_calendar_ids:
            raise DomainValidationError("Debe existir al menos un calendario")
        for calendar_id in normalized_calendar_ids:
            _require_text(calendar_id, "calendar_id")
        if len(set(normalized_calendar_ids)) != len(normalized_calendar_ids):
            raise DomainValidationError("Los calendarios no pueden repetirse")
        _require_text(appointment_id_prefix, "appointment_id_prefix")

        self.calendar_ids = normalized_calendar_ids
        self._calendar_order = {
            calendar_id: index
            for index, calendar_id in enumerate(normalized_calendar_ids)
        }
        self._appointment_id_prefix = appointment_id_prefix.strip()
        self._next_appointment_number = 1
        self._busy_periods: list[BusyPeriod] = []
        self._appointments: dict[str, Appointment] = {}
        self._simulated_errors: dict[ToolName, FailureFactory] = {}
        self._next_simulated_errors: dict[ToolName, FailureFactory] = {}

        for busy_period in busy_periods:
            self.register_busy_period(
                calendar_id=busy_period.calendar_id,
                start_at=busy_period.start_at,
                end_at=busy_period.end_at,
            )
        for appointment in appointments:
            self._register_initial_appointment(appointment)
        for operation, error in (simulated_errors or {}).items():
            self.simulate_error(operation, error)

    @property
    def busy_periods(self) -> tuple[BusyPeriod, ...]:
        return tuple(self._busy_periods)

    @property
    def appointments(self) -> tuple[Appointment, ...]:
        return tuple(self._sorted_appointments(self._appointments.values()))

    def register_busy_period(
        self,
        *,
        calendar_id: str,
        start_at: datetime,
        end_at: datetime,
    ) -> BusyPeriod:
        self._require_calendar(calendar_id)
        busy_period = BusyPeriod(
            calendar_id=calendar_id,
            start_at=start_at,
            end_at=end_at,
        )
        self._busy_periods.append(busy_period)
        self._busy_periods.sort(key=self._busy_period_sort_key)
        return busy_period

    def simulate_error(
        self,
        operation: ToolName | str,
        error: PublicCalendarError | type[PublicCalendarError],
        *,
        once: bool = False,
    ) -> None:
        """Configura un error persistente o de una sola ejecucion."""
        operation_name = _coerce_operation(operation)
        factory = _error_factory(error)
        target = self._next_simulated_errors if once else self._simulated_errors
        target[operation_name] = factory

    def clear_simulated_error(self, operation: ToolName | str) -> None:
        operation_name = _coerce_operation(operation)
        self._simulated_errors.pop(operation_name, None)
        self._next_simulated_errors.pop(operation_name, None)

    async def check_availability(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> Sequence[AvailableSlot]:
        self._raise_simulated_error(ToolName.CHECK_AVAILABILITY)
        _validate_range(start_at, end_at)

        slots = []
        candidate_start = start_at
        while candidate_start + APPOINTMENT_DURATION <= end_at:
            candidate_end = candidate_start + APPOINTMENT_DURATION
            for calendar_id in self.calendar_ids:
                if not self._is_occupied(calendar_id, candidate_start, candidate_end):
                    slots.append(
                        AvailableSlot(
                            calendar_id=calendar_id,
                            start_at=candidate_start,
                            end_at=candidate_end,
                        )
                    )
            candidate_start = candidate_end

        return tuple(
            sorted(
                slots,
                key=lambda slot: (
                    slot.start_at,
                    self._calendar_order[slot.calendar_id],
                ),
            )
        )

    async def create_appointment(
        self,
        *,
        patient_scope: PatientScope,
        start_at: datetime,
        reason: str,
    ) -> Appointment:
        self._raise_simulated_error(ToolName.CREATE_APPOINTMENT)
        _require_aware(start_at, "start_at")
        _require_text(reason, "reason")

        end_at = start_at + APPOINTMENT_DURATION
        calendar_id = next(
            (
                candidate
                for candidate in self.calendar_ids
                if not self._is_occupied(candidate, start_at, end_at)
            ),
            None,
        )
        if calendar_id is None:
            raise SlotUnavailable()

        appointment = Appointment(
            id=self._next_appointment_id(),
            patient_scope=patient_scope,
            calendar_id=calendar_id,
            start_at=start_at,
            end_at=end_at,
            reason=reason.strip(),
        )
        self._appointments[appointment.id] = appointment
        return appointment

    async def list_appointments(
        self,
        *,
        patient_scope: PatientScope,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> Sequence[Appointment]:
        self._raise_simulated_error(ToolName.LIST_APPOINTMENTS)
        if (start_at is None) != (end_at is None):
            raise InvalidToolArguments()
        if start_at is not None and end_at is not None:
            _validate_range(start_at, end_at)

        active_statuses = {
            AppointmentStatus.SCHEDULED,
            AppointmentStatus.CONFIRMED,
        }
        appointments = [
            appointment
            for appointment in self._appointments.values()
            if appointment.patient_scope.patient_id == patient_scope.patient_id
            and appointment.status in active_statuses
            and _matches_range(appointment, start_at, end_at)
        ]
        return tuple(self._sorted_appointments(appointments))

    async def reschedule_appointment(
        self,
        *,
        patient_scope: PatientScope,
        appointment_id: str,
        new_start_at: datetime,
    ) -> Appointment:
        self._raise_simulated_error(ToolName.RESCHEDULE_APPOINTMENT)
        _require_text(appointment_id, "appointment_id")
        _require_aware(new_start_at, "new_start_at")
        appointment = self._find_appointment(appointment_id)
        self._require_access(appointment, patient_scope)
        if not appointment.can_be_rescheduled:
            raise InvalidAppointmentState()

        new_end_at = new_start_at + APPOINTMENT_DURATION
        if self._is_occupied(
            appointment.calendar_id,
            new_start_at,
            new_end_at,
            excluded_appointment_id=appointment.id,
        ):
            raise SlotUnavailable()

        updated = replace(
            appointment,
            start_at=new_start_at,
            end_at=new_end_at,
        )
        self._appointments[appointment.id] = updated
        return updated

    async def cancel_appointment(
        self,
        *,
        patient_scope: PatientScope,
        appointment_id: str,
    ) -> Appointment:
        self._raise_simulated_error(ToolName.CANCEL_APPOINTMENT)
        _require_text(appointment_id, "appointment_id")
        appointment = self._find_appointment(appointment_id)
        self._require_access(appointment, patient_scope)
        if not appointment.can_be_cancelled:
            raise InvalidAppointmentState()

        cancelled = replace(appointment, status=AppointmentStatus.CANCELLED)
        self._appointments[appointment.id] = cancelled
        return cancelled

    def _register_initial_appointment(self, appointment: Appointment) -> None:
        self._require_calendar(appointment.calendar_id)
        if appointment.id in self._appointments:
            raise DomainValidationError("Los identificadores de citas no pueden repetirse")
        self._appointments[appointment.id] = appointment

    def _next_appointment_id(self) -> str:
        while True:
            appointment_id = f"{self._appointment_id_prefix}-{self._next_appointment_number}"
            self._next_appointment_number += 1
            if appointment_id not in self._appointments:
                return appointment_id

    def _is_occupied(
        self,
        calendar_id: str,
        start_at: datetime,
        end_at: datetime,
        *,
        excluded_appointment_id: str | None = None,
    ) -> bool:
        if any(
            busy_period.calendar_id == calendar_id
            and _overlaps(start_at, end_at, busy_period.start_at, busy_period.end_at)
            for busy_period in self._busy_periods
        ):
            return True

        active_statuses = {
            AppointmentStatus.SCHEDULED,
            AppointmentStatus.CONFIRMED,
        }
        return any(
            appointment.id != excluded_appointment_id
            and appointment.calendar_id == calendar_id
            and appointment.status in active_statuses
            and _overlaps(
                start_at,
                end_at,
                appointment.start_at,
                appointment.end_at,
            )
            for appointment in self._appointments.values()
        )

    def _find_appointment(self, appointment_id: str) -> Appointment:
        try:
            return self._appointments[appointment_id]
        except KeyError:
            raise AppointmentNotFound() from None

    @staticmethod
    def _require_access(appointment: Appointment, patient_scope: PatientScope) -> None:
        if appointment.patient_scope.patient_id != patient_scope.patient_id:
            raise AppointmentAccessDenied()

    def _require_calendar(self, calendar_id: str) -> None:
        if calendar_id not in self._calendar_order:
            raise DomainValidationError(f"Calendario no configurado: {calendar_id}")

    def _raise_simulated_error(self, operation: ToolName) -> None:
        factory = self._next_simulated_errors.pop(operation, None)
        if factory is None:
            factory = self._simulated_errors.get(operation)
        if factory is not None:
            raise factory()

    def _busy_period_sort_key(self, busy_period: BusyPeriod) -> tuple:
        return (
            busy_period.start_at,
            self._calendar_order[busy_period.calendar_id],
            busy_period.end_at,
        )

    @staticmethod
    def _sorted_appointments(appointments: Iterable[Appointment]) -> list[Appointment]:
        return sorted(
            appointments,
            key=lambda appointment: (appointment.start_at, appointment.id),
        )


def _error_factory(
    error: PublicCalendarError | type[PublicCalendarError],
) -> FailureFactory:
    if isinstance(error, type) and issubclass(error, PublicCalendarError):
        return error
    if isinstance(error, PublicCalendarError):
        return type(error)
    raise DomainValidationError(
        "Los errores simulados deben ser errores publicos de calendario"
    )


def _coerce_operation(operation: ToolName | str) -> ToolName:
    try:
        return ToolName(operation)
    except (TypeError, ValueError) as error:
        raise DomainValidationError(f"Operacion no soportada: {operation}") from error


def _validate_range(start_at: datetime, end_at: datetime) -> None:
    _require_aware(start_at, "start_at")
    _require_aware(end_at, "end_at")
    if end_at <= start_at:
        raise InvalidToolArguments()


def _matches_range(
    appointment: Appointment,
    start_at: datetime | None,
    end_at: datetime | None,
) -> bool:
    if start_at is None or end_at is None:
        return True
    return _overlaps(appointment.start_at, appointment.end_at, start_at, end_at)


def _overlaps(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> bool:
    return first_start < second_end and first_end > second_start


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidToolArguments()


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidToolArguments()
