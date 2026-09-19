import unittest
from datetime import datetime, timedelta, timezone

from calendar_domain import (
    APPOINTMENT_DURATION,
    Appointment,
    AppointmentStatus,
    AvailableSlot,
    DomainValidationError,
    PatientScope,
    ToolError,
    ToolErrorCode,
    ToolName,
    ToolRequest,
    ToolResult,
)


class CalendarDomainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.patient_scope = PatientScope(
            patient_id=1,
            conversation_id=2,
            whatsapp_number="5491100000000",
        )
        self.start_at = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)

    def test_appointment_has_the_fixed_duration(self) -> None:
        appointment = Appointment(
            id="appointment-1",
            patient_scope=self.patient_scope,
            calendar_id="calendar-1",
            start_at=self.start_at,
            end_at=self.start_at + APPOINTMENT_DURATION,
            reason="Revision",
        )

        self.assertEqual(appointment.status, AppointmentStatus.SCHEDULED)
        self.assertEqual(appointment.end_at - appointment.start_at, timedelta(minutes=30))

    def test_appointment_rejects_a_different_duration(self) -> None:
        with self.assertRaises(DomainValidationError):
            Appointment(
                id="appointment-1",
                patient_scope=self.patient_scope,
                calendar_id="calendar-1",
                start_at=self.start_at,
                end_at=self.start_at + timedelta(minutes=60),
                reason="Revision",
            )

    def test_appointment_and_slot_require_timezone_aware_dates(self) -> None:
        naive_start = datetime(2026, 9, 21, 10, 0)

        with self.assertRaises(DomainValidationError):
            AvailableSlot(
                calendar_id="calendar-1",
                start_at=naive_start,
                end_at=naive_start + APPOINTMENT_DURATION,
            )

    def test_cancelled_appointment_cannot_be_rescheduled(self) -> None:
        appointment = Appointment(
            id="appointment-1",
            patient_scope=self.patient_scope,
            calendar_id="calendar-1",
            start_at=self.start_at,
            end_at=self.start_at + APPOINTMENT_DURATION,
            reason="Revision",
            status=AppointmentStatus.CANCELLED,
        )

        self.assertFalse(appointment.can_be_rescheduled)

    def test_tool_request_requires_backend_scope(self) -> None:
        request = ToolRequest(
            tool_name=ToolName.CHECK_AVAILABILITY,
            arguments={"start_at": self.start_at.isoformat()},
            patient_scope=self.patient_scope,
        )

        self.assertEqual(request.patient_scope, self.patient_scope)
        self.assertNotIn("patient_id", request.arguments)
        self.assertNotIn("calendar_id", request.arguments)

    def test_tool_request_rejects_scope_arguments_from_the_llm(self) -> None:
        with self.assertRaises(DomainValidationError):
            ToolRequest(
                tool_name=ToolName.CREATE_APPOINTMENT,
                arguments={"patient_id": 999, "start_at": self.start_at.isoformat()},
                patient_scope=self.patient_scope,
            )

        with self.assertRaises(DomainValidationError):
            ToolRequest(
                tool_name=ToolName.CHECK_AVAILABILITY,
                arguments={"calendar_ids": ["private-calendar"]},
                patient_scope=self.patient_scope,
            )

        with self.assertRaises(DomainValidationError):
            ToolRequest(
                tool_name=ToolName.CREATE_APPOINTMENT,
                arguments={"duration_minutes": 90},
                patient_scope=self.patient_scope,
            )

        with self.assertRaises(DomainValidationError):
            ToolRequest(
                tool_name=ToolName.CREATE_APPOINTMENT,
                arguments={"timezone": "UTC"},
                patient_scope=self.patient_scope,
            )

    def test_tool_result_is_either_success_or_failure(self) -> None:
        success = ToolResult.success({"available": True})
        failure = ToolResult.failure(
            ToolError(
                code=ToolErrorCode.SLOT_UNAVAILABLE,
                message="El horario no esta disponible.",
            )
        )

        self.assertTrue(success.ok)
        self.assertEqual(success.data, {"available": True})
        self.assertFalse(failure.ok)
        self.assertEqual(failure.error.code, ToolErrorCode.SLOT_UNAVAILABLE)

        with self.assertRaises(DomainValidationError):
            ToolResult(ok=True, error=failure.error)
