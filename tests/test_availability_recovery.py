import os
import tempfile
import unittest
from datetime import datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from calendar_domain import CalendarProviderUnavailable, ToolName
from conversation_service import APPOINTMENT_NAME_REPLY, ConversationService, IncomingTextMessage
from fake_calendar_provider import FakeCalendarProvider
from fakes import FakeLLMProvider
from llm_provider import ToolCall
from persistence import SQLiteDatabase
from tool_executor import ToolExecutor
from tool_validation import BusinessHours, TimeWindow


class AvailabilityRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = SQLiteDatabase(os.path.join(self.directory.name, "replay.sqlite3"))
        self.now = datetime(2026, 10, 28, 10, 46, tzinfo=ZoneInfo("America/Mexico_City"))
        self.provider = FakeCalendarProvider()
        self.executor = ToolExecutor(
            provider=self.provider,
            business_hours=BusinessHours(
                timezone_name="America/Mexico_City",
                windows_by_weekday={
                    day: (TimeWindow(time(9), time(17)),) for day in range(5)
                },
            ),
            default_timezone="America/Mexico_City",
            now=lambda: self.now,
        )
        self.llm = FakeLLMProvider(replies=(
            ToolCall(name="check_availability", arguments={
                "start_at": "2026-10-28T00:00:00-06:00",
                "end_at": "2026-10-29T00:00:00-06:00",
            }),
            "No pude consultar la disponibilidad para hoy.",
        ))
        self.service = self.new_service()
        self.sequence = 0

    def new_service(self):
        return ConversationService(
            self.database, llm_provider=self.llm, tool_executor=self.executor,
            timezone_name="America/Mexico_City", now=lambda: self.now,
        )

    async def turn(self, text):
        self.sequence += 1
        context = self.service.receive_message(IncomingTextMessage(
            sender="test-replay", message_id=f"replay-{self.sequence}",
            message_type="text", text=text,
        ))
        reply = await self.service.build_reply(context)
        self.service.record_reply_sent(context, reply, f"reply-{self.sequence}")
        return context, reply

    async def test_llm_full_day_today_query_offers_future_slots_and_keeps_selection(self):
        context, reply = await self.turn("¿Hay lugar el 28/10/2026?")

        self.assertIn("Horarios disponibles para el 28/10/2026", reply)
        self.assertIn("- 11:00 AM", reply)
        self.assertNotIn("10:46 AM", reply)
        self.assertEqual(self.llm.call_count, 1)
        self.service = self.new_service()
        _, selection = await self.turn("a las 11 am esta bien")
        self.assertEqual(selection, APPOINTMENT_NAME_REPLY)
        self.assertEqual(self.provider.appointments, ())
        self.assertIsNone(self.service._load_pending_appointment_availability(context.conversation_id))

    async def test_retry_after_calendar_failure_preserves_the_requested_day_across_restart(self):
        self.provider.simulate_error(ToolName.CHECK_AVAILABILITY, CalendarProviderUnavailable, once=True)
        context, _ = await self.turn("Quiero agendar una cita para hoy")

        self.service = self.new_service()
        _, retry = await self.turn("Vuelve a intentarlo")

        self.assertIn("Horarios disponibles para el 28/10/2026", retry)
        self.assertIn("- 11:00 AM", retry)
        self.assertEqual(self.llm.call_count, 0)
        self.assertIsNone(self.service._load_pending_appointment_date(context.conversation_id))
        self.assertEqual(self.provider.appointments, ())

    async def test_polite_request_for_today_uses_the_local_availability_flow(self):
        _, reply = await self.turn("Quisiera una cita para hoy")

        self.assertIn("Horarios disponibles para el 28/10/2026", reply)
        self.assertEqual(self.llm.call_count, 0)

    async def test_original_typo_uses_the_local_availability_flow(self):
        _, reply = await self.turn("QUisiera una cita par ahoy")

        self.assertIn("Horarios disponibles para el 28/10/2026", reply)
        self.assertEqual(self.llm.call_count, 0)

    async def test_repeated_retries_consult_again_until_the_calendar_recovers(self):
        self.provider.simulate_error(ToolName.CHECK_AVAILABILITY, CalendarProviderUnavailable)
        context, _ = await self.turn("Quiero agendar una cita para mañana")
        _, failed_retry = await self.turn("Vuelve a intentarlo")
        self.assertNotIn("Horarios disponibles", failed_retry)
        self.assertEqual(
            self.service._load_pending_appointment_date(context.conversation_id).target_date,
            "2026-10-29",
        )

        self.provider.clear_simulated_error(ToolName.CHECK_AVAILABILITY)
        self.service = self.new_service()
        _, reply = await self.turn("Vuelve a intentarlo")
        self.assertIn("Horarios disponibles para el 29/10/2026", reply)
        self.assertEqual(self.llm.call_count, 0)

    async def test_retry_without_a_known_day_does_not_guess_the_date(self):
        await self.turn("Quisiera una cita")
        _, reply = await self.turn("Vuelve a intentarlo")

        self.assertNotIn("Horarios disponibles", reply)
        self.assertIn("qué día", reply)
        self.assertEqual(self.llm.call_count, 0)

    async def test_pausing_and_resuming_a_failed_query_keeps_its_date(self):
        self.provider.simulate_error(ToolName.CHECK_AVAILABILITY, CalendarProviderUnavailable, once=True)
        await self.turn("Quisiera una cita para mañana")
        self.llm.replies = ("Puedes consultar el costo con el consultorio.",)
        await self.turn("¿Cuál es el costo?")
        self.service = self.new_service()
        _, reply = await self.turn("Retomemos la cita")

        self.assertIn("Horarios disponibles para el 29/10/2026", reply)
        self.assertEqual(self.llm.call_count, 1)

    async def test_expired_failed_query_requires_a_new_date(self):
        self.provider.simulate_error(ToolName.CHECK_AVAILABILITY, CalendarProviderUnavailable, once=True)
        await self.turn("Quisiera una cita para hoy")
        self.now += timedelta(minutes=11)
        _, reply = await self.turn("Vuelve a intentarlo")

        self.assertIn("expiró", reply)
        self.assertNotIn("Horarios disponibles", reply)
        self.assertEqual(self.llm.call_count, 0)

    async def test_full_day_query_with_utc_offsets_is_normalized_in_calendar_timezone(self):
        self.llm.replies = (ToolCall(name="check_availability", arguments={
            "start_at": "2026-10-28T06:00:00Z",
            "end_at": "2026-10-29T06:00:00Z",
        }),)
        _, reply = await self.turn("¿Hay lugar el 28/10/2026?")

        self.assertIn("Horarios disponibles para el 28/10/2026", reply)
        self.assertIn("- 11:00 AM", reply)

    async def test_past_day_is_not_shifted_to_today(self):
        self.llm.replies = (ToolCall(name="check_availability", arguments={
            "start_at": "2026-10-27T00:00:00-06:00",
            "end_at": "2026-10-28T00:00:00-06:00",
        }),)
        with patch.object(self.provider, "check_availability", wraps=self.provider.check_availability) as check:
            _, reply = await self.turn("¿Hay lugar el 27/10/2026?")

        self.assertNotIn("Horarios disponibles", reply)
        check.assert_not_awaited()

    async def test_unknown_tool_arguments_are_still_rejected(self):
        call = self.llm.replies[0]
        self.llm.replies = (
            ToolCall(name=call.name, arguments={**call.arguments, "calendar_id": "untrusted"}),
            "No pude consultar la disponibilidad para hoy.",
        )
        with patch.object(self.provider, "check_availability", wraps=self.provider.check_availability) as check:
            context, reply = await self.turn("¿Hay lugar el 28/10/2026?")

        self.assertNotIn("Horarios disponibles", reply)
        self.assertIsNone(self.service._load_pending_appointment_availability(context.conversation_id))
        check.assert_not_awaited()
