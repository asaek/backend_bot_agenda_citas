import unittest
from datetime import datetime, time, timedelta, timezone

from calendar_domain import (
    Appointment,
    AppointmentStatus,
    CalendarProviderUnavailable,
    DomainValidationError,
    PatientScope,
    ToolErrorCode,
    ToolName,
    ToolRequest,
)
from fake_calendar_provider import BusyPeriod, FakeCalendarProvider
from tool_contracts import (
    CancelAppointmentOutput,
    CheckAvailabilityOutput,
    CreateAppointmentOutput,
    ListAppointmentsOutput,
    RescheduleAppointmentOutput,
)
from tool_executor import ToolExecutor
from tool_validation import BusinessHours, TimeWindow


class ToolExecutorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.utc = timezone.utc
        self.patient = PatientScope(
            patient_id=1,
            conversation_id=10,
            whatsapp_number="5491100000000",
        )
        self.other_patient = PatientScope(
            patient_id=2,
            conversation_id=20,
            whatsapp_number="5491100000001",
        )
        self.now = datetime(2026, 9, 20, 12, 0, tzinfo=self.utc)
        self.start = datetime(2026, 9, 21, 10, 0, tzinfo=self.utc)
        self.business_hours = BusinessHours(
            timezone_name="UTC",
            windows_by_weekday={
                weekday: (TimeWindow(time(9), time(17)),)
                for weekday in range(5)
            },
        )

    def executor(
        self,
        provider: FakeCalendarProvider,
        availability_provider: FakeCalendarProvider | None = None,
    ) -> ToolExecutor:
        return ToolExecutor(
            provider=provider,
            business_hours=self.business_hours,
            default_timezone="UTC",
            now=self.now,
            availability_provider=availability_provider,
        )

    def test_exposes_the_configured_clock_for_conversation_context(self) -> None:
        executor = self.executor(FakeCalendarProvider())

        self.assertEqual(executor.current_time(), self.now)

    def request(self, tool_name: ToolName, arguments: dict[str, object]) -> ToolRequest:
        return ToolRequest(
            tool_name=tool_name,
            arguments=arguments,
            patient_scope=self.patient,
        )

    def appointment(
        self,
        *,
        appointment_id: str = "appointment-1",
        patient_scope: PatientScope | None = None,
        start_at: datetime | None = None,
        status: AppointmentStatus = AppointmentStatus.SCHEDULED,
    ) -> Appointment:
        appointment_start = start_at or self.start
        return Appointment(
            id=appointment_id,
            patient_scope=patient_scope or self.patient,
            calendar_id="calendar-1",
            start_at=appointment_start,
            end_at=appointment_start + timedelta(minutes=30),
            reason="Revision",
            status=status,
        )

    async def test_parses_validates_and_executes_create_request(self) -> None:
        provider = FakeCalendarProvider()

        result = await self.executor(provider).execute(
            self.request(
                ToolName.CREATE_APPOINTMENT,
                {
                    "start_at": "2026-09-21T10:00:00",
                    "reason": "Revision",
                },
            )
        )

        self.assertTrue(result.ok)
        self.assertIsInstance(result.data, CreateAppointmentOutput)
        self.assertEqual(result.data.appointment.patient_scope, self.patient)
        self.assertEqual(result.data.appointment.calendar_id, "calendar-1")

    async def test_rejects_invalid_arguments_before_provider_execution(self) -> None:
        provider = FakeCalendarProvider()

        result = await self.executor(provider).execute(
            self.request(ToolName.CREATE_APPOINTMENT, {"reason": "Revision"})
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, ToolErrorCode.INVALID_ARGUMENTS)
        self.assertEqual(provider.appointments, ())

    async def test_applies_business_hours_before_provider_execution(self) -> None:
        provider = FakeCalendarProvider()

        result = await self.executor(provider).execute(
            self.request(
                ToolName.CREATE_APPOINTMENT,
                {
                    "start_at": "2026-09-21T16:45:00",
                    "reason": "Fuera de horario",
                },
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, ToolErrorCode.OUTSIDE_BUSINESS_HOURS)
        self.assertEqual(provider.appointments, ())

    async def test_filters_availability_to_business_hours(self) -> None:
        provider = FakeCalendarProvider()

        result = await self.executor(provider).execute(
            self.request(
                ToolName.CHECK_AVAILABILITY,
                {
                    "start_at": "2026-09-21T08:00:00",
                    "end_at": "2026-09-21T18:00:00",
                },
            )
        )

        self.assertTrue(result.ok)
        self.assertIsInstance(result.data, CheckAvailabilityOutput)
        self.assertEqual(len(result.data.slots), 16)
        self.assertEqual(result.data.slots[0].start_at.hour, 9)
        self.assertEqual(result.data.slots[-1].end_at.hour, 17)
        self.assertTrue(
            all(
                self.business_hours.contains(slot.start_at, slot.end_at)
                for slot in result.data.slots
            )
        )

    async def test_routes_only_availability_to_the_dedicated_provider(self) -> None:
        primary_provider = FakeCalendarProvider()
        availability_provider = FakeCalendarProvider(
            busy_periods=(
                BusyPeriod(
                    calendar_id="calendar-1",
                    start_at=self.start,
                    end_at=self.start + timedelta(minutes=30),
                ),
            )
        )
        executor = self.executor(primary_provider, availability_provider)

        available = await executor.execute(
            self.request(
                ToolName.CHECK_AVAILABILITY,
                {
                    "start_at": self.start.isoformat(),
                    "end_at": (self.start + timedelta(hours=1)).isoformat(),
                },
            )
        )
        created = await executor.execute(
            self.request(
                ToolName.CREATE_APPOINTMENT,
                {"start_at": self.start.isoformat(), "reason": "Revision"},
            )
        )

        self.assertTrue(available.ok)
        self.assertEqual(len(available.data.slots), 1)
        self.assertEqual(available.data.slots[0].start_at, self.start + timedelta(minutes=30))
        self.assertTrue(created.ok)
        self.assertEqual(len(primary_provider.appointments), 1)
        self.assertEqual(availability_provider.appointments, ())

    async def test_executes_all_read_and_write_operations_with_patient_scope(self) -> None:
        provider = FakeCalendarProvider()
        executor = self.executor(provider)
        created = await executor.execute(
            self.request(
                ToolName.CREATE_APPOINTMENT,
                {"start_at": self.start.isoformat(), "reason": "Revision"},
            )
        )
        appointment_id = created.data.appointment.id

        listed = await executor.execute(
            self.request(ToolName.LIST_APPOINTMENTS, {})
        )
        available = await executor.execute(
            self.request(
                ToolName.CHECK_AVAILABILITY,
                {
                    "start_at": "2026-09-21T10:00:00",
                    "end_at": "2026-09-21T11:00:00",
                },
            )
        )
        moved = await executor.execute(
            self.request(
                ToolName.RESCHEDULE_APPOINTMENT,
                {
                    "appointment_id": appointment_id,
                    "new_start_at": "2026-09-21T11:00:00",
                },
            )
        )
        cancelled = await executor.execute(
            self.request(
                ToolName.CANCEL_APPOINTMENT,
                {"appointment_id": appointment_id},
            )
        )

        self.assertIsInstance(listed.data, ListAppointmentsOutput)
        self.assertEqual(listed.data.appointments, (created.data.appointment,))
        self.assertIsInstance(available.data, CheckAvailabilityOutput)
        self.assertEqual(len(available.data.slots), 1)
        self.assertIsInstance(moved.data, RescheduleAppointmentOutput)
        self.assertEqual(moved.data.appointment.patient_scope, self.patient)
        self.assertIsInstance(cancelled.data, CancelAppointmentOutput)
        self.assertEqual(cancelled.data.appointment.status, AppointmentStatus.CANCELLED)

    async def test_lists_only_appointments_for_the_current_patient(self) -> None:
        provider = FakeCalendarProvider(
            appointments=(
                self.appointment(appointment_id="current-patient-1"),
                self.appointment(
                    appointment_id="other-patient-1",
                    patient_scope=self.other_patient,
                ),
            )
        )

        result = await self.executor(provider).execute(
            self.request(ToolName.LIST_APPOINTMENTS, {})
        )

        self.assertTrue(result.ok)
        self.assertIsInstance(result.data, ListAppointmentsOutput)
        self.assertEqual(
            [appointment.id for appointment in result.data.appointments],
            ["current-patient-1"],
        )

    async def test_lists_appointments_overlapping_the_optional_range(self) -> None:
        provider = FakeCalendarProvider(
            appointments=(
                self.appointment(appointment_id="inside", start_at=self.start),
                self.appointment(
                    appointment_id="outside",
                    start_at=self.start + timedelta(hours=2),
                ),
            )
        )

        result = await self.executor(provider).execute(
            self.request(
                ToolName.LIST_APPOINTMENTS,
                {
                    "start_at": (self.start + timedelta(minutes=15)).isoformat(),
                    "end_at": (self.start + timedelta(minutes=45)).isoformat(),
                },
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(
            [appointment.id for appointment in result.data.appointments],
            ["inside"],
        )

    async def test_rejects_an_invalid_reschedule_before_provider_execution(self) -> None:
        appointment = self.appointment()
        provider = FakeCalendarProvider(appointments=(appointment,))

        result = await self.executor(provider).execute(
            self.request(
                ToolName.RESCHEDULE_APPOINTMENT,
                {
                    "appointment_id": appointment.id,
                    "new_start_at": "2026-09-21T16:45:00",
                },
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, ToolErrorCode.OUTSIDE_BUSINESS_HOURS)
        self.assertEqual(provider.appointments, (appointment,))

    async def test_rejects_cancelling_an_unknown_appointment(self) -> None:
        provider = FakeCalendarProvider()

        result = await self.executor(provider).execute(
            self.request(
                ToolName.CANCEL_APPOINTMENT,
                {"appointment_id": "missing-appointment"},
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, ToolErrorCode.APPOINTMENT_NOT_FOUND)

    async def test_provider_conflicts_are_returned_as_safe_results(self) -> None:
        provider = FakeCalendarProvider(
            appointments=(self.appointment(patient_scope=self.other_patient),)
        )

        result = await self.executor(provider).execute(
            self.request(
                ToolName.CREATE_APPOINTMENT,
                {"start_at": self.start.isoformat(), "reason": "Conflicto"},
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, ToolErrorCode.SLOT_UNAVAILABLE)

    async def test_provider_errors_are_returned_as_public_results(self) -> None:
        provider = FakeCalendarProvider()
        provider.simulate_error(
            ToolName.CREATE_APPOINTMENT,
            CalendarProviderUnavailable,
        )

        result = await self.executor(provider).execute(
            self.request(
                ToolName.CREATE_APPOINTMENT,
                {"start_at": self.start.isoformat(), "reason": "Fallo"},
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, ToolErrorCode.PROVIDER_UNAVAILABLE)
        self.assertTrue(result.error.retryable)

    async def test_preserves_provider_access_errors_for_another_patient(self) -> None:
        provider = FakeCalendarProvider(
            appointments=(self.appointment(patient_scope=self.other_patient),)
        )

        result = await self.executor(provider).execute(
            self.request(
                ToolName.CANCEL_APPOINTMENT,
                {"appointment_id": "appointment-1"},
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, ToolErrorCode.APPOINTMENT_ACCESS_DENIED)

    async def test_does_not_allow_the_request_to_choose_a_calendar(self) -> None:
        with self.assertRaises(DomainValidationError):
            self.request(
                ToolName.CREATE_APPOINTMENT,
                {
                    "start_at": self.start.isoformat(),
                    "reason": "Revision",
                    "calendar_id": "private-calendar",
                },
            )
