import unittest
from datetime import datetime, time, timedelta, timezone

from calendar_domain import (
    APPOINTMENT_DURATION,
    Appointment,
    AppointmentStatus,
    PatientScope,
    ToolErrorCode,
)
from tool_contracts import (
    CancelAppointmentInput,
    CreateAppointmentInput,
    RescheduleAppointmentInput,
)
from tool_validation import (
    BusinessHours,
    TimeWindow,
    ToolValidationError,
    validate_tool_input,
)


class ToolValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.patient_scope = PatientScope(
            patient_id=1,
            conversation_id=2,
            whatsapp_number="5491100000000",
        )
        self.other_patient_scope = PatientScope(
            patient_id=2,
            conversation_id=3,
            whatsapp_number="5491100000001",
        )
        self.timezone = timezone.utc
        self.now = datetime(2026, 9, 20, 12, 0, tzinfo=self.timezone)
        self.business_hours = BusinessHours(
            timezone_name="UTC",
            windows_by_weekday={
                weekday: (TimeWindow(time(9), time(17)),)
                for weekday in range(5)
            },
        )

    def appointment(
        self,
        *,
        start_at: datetime,
        patient_scope: PatientScope | None = None,
        status: AppointmentStatus = AppointmentStatus.SCHEDULED,
        appointment_id: str = "appointment-1",
    ) -> Appointment:
        return Appointment(
            id=appointment_id,
            patient_scope=patient_scope or self.patient_scope,
            calendar_id="calendar-1",
            start_at=start_at,
            end_at=start_at + APPOINTMENT_DURATION,
            reason="Revision",
            status=status,
        )

    def test_accepts_a_future_start_inside_business_hours(self) -> None:
        request = CreateAppointmentInput(
            patient_scope=self.patient_scope,
            start_at=datetime(2026, 9, 21, 10, 0, tzinfo=self.timezone),
            reason="Revision",
        )

        validate_tool_input(
            request,
            business_hours=self.business_hours,
            now=self.now,
        )

    def test_rejects_a_start_outside_business_hours(self) -> None:
        request = CreateAppointmentInput(
            patient_scope=self.patient_scope,
            start_at=datetime(2026, 9, 21, 16, 45, tzinfo=self.timezone),
            reason="Revision",
        )

        with self.assertRaises(ToolValidationError) as raised:
            validate_tool_input(
                request,
                business_hours=self.business_hours,
                now=self.now,
            )

        self.assertEqual(raised.exception.code, ToolErrorCode.OUTSIDE_BUSINESS_HOURS)

    def test_rejects_past_create_and_reschedule_dates(self) -> None:
        create_request = CreateAppointmentInput(
            patient_scope=self.patient_scope,
            start_at=datetime(2026, 9, 19, 10, 0, tzinfo=self.timezone),
            reason="Revision",
        )
        reschedule_request = RescheduleAppointmentInput(
            patient_scope=self.patient_scope,
            appointment_id="appointment-1",
            new_start_at=datetime(2026, 9, 19, 10, 0, tzinfo=self.timezone),
        )

        for request in (create_request, reschedule_request):
            with self.assertRaises(ToolValidationError) as raised:
                validate_tool_input(
                    request,
                    business_hours=self.business_hours,
                    now=self.now,
                    existing_appointments=(
                        self.appointment(
                            start_at=datetime(2026, 9, 21, 10, 0, tzinfo=self.timezone)
                        ),
                    )
                    if isinstance(request, RescheduleAppointmentInput)
                    else (),
                )
            self.assertEqual(raised.exception.code, ToolErrorCode.DATE_IN_PAST)

    def test_rejects_an_overlapping_active_appointment(self) -> None:
        start_at = datetime(2026, 9, 21, 10, 0, tzinfo=self.timezone)
        request = CreateAppointmentInput(
            patient_scope=self.patient_scope,
            start_at=start_at,
            reason="Revision",
        )

        with self.assertRaises(ToolValidationError) as raised:
            validate_tool_input(
                request,
                business_hours=self.business_hours,
                now=self.now,
                existing_appointments=(self.appointment(start_at=start_at),),
            )

        self.assertEqual(raised.exception.code, ToolErrorCode.SLOT_UNAVAILABLE)

    def test_cancelled_appointments_do_not_block_a_new_slot(self) -> None:
        start_at = datetime(2026, 9, 21, 10, 0, tzinfo=self.timezone)
        request = CreateAppointmentInput(
            patient_scope=self.patient_scope,
            start_at=start_at,
            reason="Revision",
        )

        validate_tool_input(
            request,
            business_hours=self.business_hours,
            now=self.now,
            existing_appointments=(
                self.appointment(
                    start_at=start_at,
                    status=AppointmentStatus.CANCELLED,
                ),
            ),
        )

    def test_reschedule_requires_ownership_and_reschedulable_state(self) -> None:
        request = RescheduleAppointmentInput(
            patient_scope=self.patient_scope,
            appointment_id="appointment-1",
            new_start_at=datetime(2026, 9, 21, 11, 0, tzinfo=self.timezone),
        )
        other_patient_appointment = self.appointment(
            start_at=datetime(2026, 9, 21, 10, 0, tzinfo=self.timezone),
            patient_scope=self.other_patient_scope,
        )

        with self.assertRaises(ToolValidationError) as raised:
            validate_tool_input(
                request,
                business_hours=self.business_hours,
                now=self.now,
                existing_appointments=(other_patient_appointment,),
            )

        self.assertEqual(raised.exception.code, ToolErrorCode.APPOINTMENT_ACCESS_DENIED)

        cancelled = self.appointment(
            start_at=datetime(2026, 9, 21, 10, 0, tzinfo=self.timezone),
            status=AppointmentStatus.CANCELLED,
        )
        with self.assertRaises(ToolValidationError) as raised:
            validate_tool_input(
                request,
                business_hours=self.business_hours,
                now=self.now,
                existing_appointments=(cancelled,),
            )

        self.assertEqual(raised.exception.code, ToolErrorCode.INVALID_APPOINTMENT_STATE)

    def test_cancel_requires_ownership_and_valid_state(self) -> None:
        request = CancelAppointmentInput(
            patient_scope=self.patient_scope,
            appointment_id="appointment-1",
        )
        completed = self.appointment(
            start_at=datetime(2026, 9, 21, 10, 0, tzinfo=self.timezone),
            status=AppointmentStatus.COMPLETED,
        )

        with self.assertRaises(ToolValidationError) as raised:
            validate_tool_input(
                request,
                business_hours=self.business_hours,
                now=self.now,
                existing_appointments=(completed,),
            )

        self.assertEqual(raised.exception.code, ToolErrorCode.INVALID_APPOINTMENT_STATE)
