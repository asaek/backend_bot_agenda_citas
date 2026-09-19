"""Frontera interna para ejecutar solicitudes de herramientas de agenda."""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from calendar_domain import (
    Appointment,
    CalendarProvider,
    DomainValidationError,
    ToolRequest,
    ToolResult,
)
from tool_contracts import (
    CancelAppointmentInput,
    CancelAppointmentOutput,
    CheckAvailabilityInput,
    CheckAvailabilityOutput,
    CreateAppointmentInput,
    CreateAppointmentOutput,
    ListAppointmentsInput,
    ListAppointmentsOutput,
    RescheduleAppointmentInput,
    RescheduleAppointmentOutput,
    ToolInput,
    parse_tool_request,
)
from tool_results import tool_result_from_exception
from tool_validation import BusinessHours, validate_tool_input


NowSource = Callable[[], datetime]


class ToolExecutor:
    """Valida y ejecuta una solicitud con el alcance resuelto por el backend."""

    def __init__(
        self,
        *,
        provider: CalendarProvider,
        business_hours: BusinessHours,
        default_timezone: str = "UTC",
        now: datetime | NowSource | None = None,
    ) -> None:
        self.provider = provider
        self.business_hours = business_hours
        self.default_timezone = default_timezone
        self._now = now

    async def execute(self, request: ToolRequest) -> ToolResult:
        """Devuelve siempre un `ToolResult`, incluso si falla el proveedor."""
        try:
            if not isinstance(request, ToolRequest):
                raise DomainValidationError("La solicitud debe ser un ToolRequest")

            tool_input = parse_tool_request(
                request,
                default_timezone=self.default_timezone,
            )
            self._validate(tool_input, ())
            if self._requires_snapshot(tool_input):
                existing_appointments = await self._load_snapshot(tool_input)
                self._validate(tool_input, existing_appointments)
            output = await self._execute_provider(tool_input)
            return ToolResult.success(output)
        except Exception as error:
            return tool_result_from_exception(error)

    async def _load_snapshot(self, tool_input: ToolInput) -> Sequence[Appointment]:
        return await self.provider.list_appointments(
            patient_scope=tool_input.patient_scope,
        )

    @staticmethod
    def _requires_snapshot(tool_input: ToolInput) -> bool:
        return isinstance(
            tool_input,
            (CreateAppointmentInput, RescheduleAppointmentInput, CancelAppointmentInput),
        )

    def _validate(
        self,
        tool_input: ToolInput,
        existing_appointments: Sequence[Appointment],
    ) -> None:
        if isinstance(tool_input, (RescheduleAppointmentInput, CancelAppointmentInput)):
            appointment_is_known = any(
                appointment.id == tool_input.appointment_id
                for appointment in existing_appointments
            )
            if not appointment_is_known:
                # El proveedor conserva la autoridad sobre citas no visibles para
                # este paciente y devuelve not-found o access-denied sin filtrarlas.
                return

        validate_tool_input(
            tool_input,
            business_hours=self.business_hours,
            now=self._current_time(),
            existing_appointments=existing_appointments,
        )

    async def _execute_provider(self, tool_input: ToolInput) -> object:
        if isinstance(tool_input, CheckAvailabilityInput):
            slots = await self.provider.check_availability(
                start_at=tool_input.start_at,
                end_at=tool_input.end_at,
            )
            return CheckAvailabilityOutput(slots=slots)

        if isinstance(tool_input, CreateAppointmentInput):
            appointment = await self.provider.create_appointment(
                patient_scope=tool_input.patient_scope,
                start_at=tool_input.start_at,
                reason=tool_input.reason,
            )
            return CreateAppointmentOutput(appointment=appointment)

        if isinstance(tool_input, ListAppointmentsInput):
            appointments = await self.provider.list_appointments(
                patient_scope=tool_input.patient_scope,
                start_at=tool_input.start_at,
                end_at=tool_input.end_at,
            )
            return ListAppointmentsOutput(appointments=appointments)

        if isinstance(tool_input, RescheduleAppointmentInput):
            appointment = await self.provider.reschedule_appointment(
                patient_scope=tool_input.patient_scope,
                appointment_id=tool_input.appointment_id,
                new_start_at=tool_input.new_start_at,
            )
            return RescheduleAppointmentOutput(appointment=appointment)

        appointment = await self.provider.cancel_appointment(
            patient_scope=tool_input.patient_scope,
            appointment_id=tool_input.appointment_id,
        )
        return CancelAppointmentOutput(appointment=appointment)

    def _current_time(self) -> datetime:
        current_time = self._now() if callable(self._now) else self._now
        return current_time or datetime.now(timezone.utc)
