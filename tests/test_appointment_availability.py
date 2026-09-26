import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from appointment_availability import (
    PendingAppointmentAvailability,
    date_only_availability_request,
    format_availability_reply,
    parse_time_selection,
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

    def test_parses_common_patient_time_selections(self) -> None:
        cases = (
            ("damela a las 10 am", (10, 0)),
            ("a las 10:30", (10, 30)),
            ("a las 1 pm", (13, 0)),
            ("13:30", (13, 30)),
        )

        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(parse_time_selection(text), expected)

    def test_pending_availability_round_trips_and_matches_a_slot(self) -> None:
        request = date_only_availability_request(
            "Agendame una cita para mañana",
            now=self.now,
            timezone=self.timezone,
        )
        self.assertIsNotNone(request)
        start_at = datetime(2026, 9, 21, 10, tzinfo=timezone.utc)
        pending = PendingAppointmentAvailability.from_slots(
            request,
            (
                AvailableSlot(
                    calendar_id="calendar-1",
                    start_at=start_at,
                    end_at=start_at.replace(minute=30),
                ),
                AvailableSlot(
                    calendar_id="calendar-1",
                    start_at=start_at.replace(hour=13),
                    end_at=start_at.replace(hour=13, minute=30),
                ),
            ),
            timezone=self.timezone,
            now=self.now,
        )
        self.assertIsNotNone(pending)

        restored = PendingAppointmentAvailability.from_context(pending.to_context())

        self.assertIsNotNone(restored)
        self.assertEqual(restored.target_date, "2026-09-21")
        self.assertIsNotNone(
            restored.matching_slot("damela a las 10 am", timezone=self.timezone)
        )
        self.assertIsNotNone(restored.matching_slot("a la 1", timezone=self.timezone))
        self.assertIsNone(restored.matching_slot("a las 11 am", timezone=self.timezone))
