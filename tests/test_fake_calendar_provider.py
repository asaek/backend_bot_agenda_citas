import unittest
from datetime import datetime, timedelta, timezone

from calendar_domain import (
    Appointment,
    AppointmentAccessDenied,
    AppointmentNotFound,
    AppointmentStatus,
    CalendarProviderError,
    CalendarProviderUnavailable,
    InvalidAppointmentState,
    PatientScope,
    SlotUnavailable,
    ToolName,
)
from fake_calendar_provider import BusyPeriod, FakeCalendarProvider
from tool_results import execute_with_public_errors


class FakeCalendarProviderTests(unittest.IsolatedAsyncioTestCase):
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
        self.start = datetime(2026, 9, 21, 10, 0, tzinfo=self.utc)

    def appointment(
        self,
        *,
        appointment_id: str = "seed-1",
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

    async def test_registers_busy_periods_and_returns_deterministic_slots(self) -> None:
        provider = FakeCalendarProvider(calendar_ids=("calendar-1", "calendar-2"))
        provider.register_busy_period(
            calendar_id="calendar-1",
            start_at=self.start,
            end_at=self.start + timedelta(minutes=30),
        )

        slots = await provider.check_availability(
            start_at=self.start,
            end_at=self.start + timedelta(hours=1),
        )

        self.assertEqual(
            provider.busy_periods,
            (
                BusyPeriod(
                    calendar_id="calendar-1",
                    start_at=self.start,
                    end_at=self.start + timedelta(minutes=30),
                ),
            ),
        )
        self.assertEqual(
            [(slot.calendar_id, slot.start_at) for slot in slots],
            [
                ("calendar-2", self.start),
                ("calendar-1", self.start + timedelta(minutes=30)),
                ("calendar-2", self.start + timedelta(minutes=30)),
            ],
        )

    async def test_creates_lists_reschedules_and_cancels_appointments(self) -> None:
        provider = FakeCalendarProvider()

        created = await provider.create_appointment(
            patient_scope=self.patient,
            start_at=self.start,
            reason=" Revision ",
        )
        listed = await provider.list_appointments(patient_scope=self.patient)
        moved = await provider.reschedule_appointment(
            patient_scope=self.patient,
            appointment_id=created.id,
            new_start_at=self.start + timedelta(hours=1),
        )
        cancelled = await provider.cancel_appointment(
            patient_scope=self.patient,
            appointment_id=created.id,
        )

        self.assertEqual(created.id, "appointment-1")
        self.assertEqual(created.reason, "Revision")
        self.assertEqual(listed, (created,))
        self.assertEqual(moved.start_at, self.start + timedelta(hours=1))
        self.assertEqual(cancelled.status, AppointmentStatus.CANCELLED)
        self.assertEqual((await provider.list_appointments(patient_scope=self.patient)), (cancelled,))

    async def test_conflicts_block_creation_and_rescheduling(self) -> None:
        provider = FakeCalendarProvider(
            appointments=(self.appointment(),),
        )

        with self.assertRaises(SlotUnavailable):
            await provider.create_appointment(
                patient_scope=self.other_patient,
                start_at=self.start,
                reason="Conflicto",
            )

        second = await provider.create_appointment(
            patient_scope=self.other_patient,
            start_at=self.start + timedelta(minutes=30),
            reason="Otra cita",
        )
        with self.assertRaises(SlotUnavailable):
            await provider.reschedule_appointment(
                patient_scope=self.patient,
                appointment_id="seed-1",
                new_start_at=second.start_at,
            )

    async def test_access_and_state_rules_are_enforced(self) -> None:
        provider = FakeCalendarProvider(
            appointments=(
                self.appointment(patient_scope=self.other_patient),
                self.appointment(
                    appointment_id="cancelled-1",
                    start_at=self.start + timedelta(hours=1),
                    status=AppointmentStatus.CANCELLED,
                ),
            )
        )

        with self.assertRaises(AppointmentAccessDenied):
            await provider.cancel_appointment(
                patient_scope=self.patient,
                appointment_id="seed-1",
            )

        with self.assertRaises(InvalidAppointmentState):
            await provider.cancel_appointment(
                patient_scope=self.patient,
                appointment_id="cancelled-1",
            )

        with self.assertRaises(AppointmentNotFound):
            await provider.cancel_appointment(
                patient_scope=self.patient,
                appointment_id="missing-1",
            )

    async def test_simulates_persistent_and_one_shot_provider_errors(self) -> None:
        provider = FakeCalendarProvider()
        provider.simulate_error(
            ToolName.CHECK_AVAILABILITY,
            CalendarProviderUnavailable,
            once=True,
        )
        provider.simulate_error(
            ToolName.CREATE_APPOINTMENT,
            CalendarProviderError,
        )

        first = await execute_with_public_errors(
            lambda: provider.check_availability(
                start_at=self.start,
                end_at=self.start + timedelta(minutes=30),
            )
        )
        second = await execute_with_public_errors(
            lambda: provider.check_availability(
                start_at=self.start,
                end_at=self.start + timedelta(minutes=30),
            )
        )
        third = await execute_with_public_errors(
            lambda: provider.create_appointment(
                patient_scope=self.patient,
                start_at=self.start,
                reason="Error",
            )
        )

        self.assertFalse(first.ok)
        self.assertEqual(first.error.code.value, "provider_unavailable")
        self.assertTrue(second.ok)
        self.assertFalse(third.ok)
        self.assertEqual(third.error.code.value, "provider_error")
