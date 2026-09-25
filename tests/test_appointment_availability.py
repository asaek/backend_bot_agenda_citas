import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from appointment_availability import (
    date_only_availability_request,
    format_availability_reply,
)
from calendar_domain import AvailableSlot, ToolResult
from tool_contracts import CheckAvailabilityOutput


class AppointmentAvailabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.timezone = ZoneInfo("UTC")
        self.now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)

    def test_resolves_relative_date_without_an_exact_time(self) -> None:
        request = date_only_availability_request(
            "Agendame una cita para ma;ana",
            now=self.now,
            timezone=self.timezone,
        )

        self.assertIsNotNone(request)
        self.assertEqual(request.start_at, datetime(2026, 9, 21, tzinfo=timezone.utc))
        self.assertEqual(request.end_at, datetime(2026, 9, 22, tzinfo=timezone.utc))

    def test_leaves_exact_time_requests_for_the_normal_booking_flow(self) -> None:
        request = date_only_availability_request(
            "Agendame una cita para mañana a las 11:30",
            now=self.now,
            timezone=self.timezone,
        )

        self.assertIsNone(request)

    def test_recognizes_the_patient_phrase_sacar_cita(self) -> None:
        request = date_only_availability_request(
            "y para hoy quisiera sacar cita que tienes para hoy",
            now=self.now,
            timezone=self.timezone,
        )

        self.assertIsNotNone(request)
        self.assertEqual(request.start_at.date(), self.now.date())

    def test_formats_slots_without_duplicate_calendar_times(self) -> None:
        start_at = datetime(2026, 9, 21, 11, tzinfo=timezone.utc)
        result = ToolResult.success(
            CheckAvailabilityOutput(
                slots=(
                    AvailableSlot(
                        calendar_id="calendar-1",
                        start_at=start_at,
                        end_at=start_at.replace(hour=11, minute=30),
                    ),
                    AvailableSlot(
                        calendar_id="calendar-2",
                        start_at=start_at,
                        end_at=start_at.replace(hour=11, minute=30),
                    ),
                )
            )
        )
        request = date_only_availability_request(
            "Agendame una cita para mañana",
            now=self.now,
            timezone=self.timezone,
        )

        reply = format_availability_reply(result, request, timezone=self.timezone)

        self.assertEqual(reply.count("- 11:00 a 11:30"), 1)
        self.assertIn("Elige uno", reply)
