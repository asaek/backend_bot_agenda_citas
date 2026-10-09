import asyncio
import os
import tempfile
import unittest
from datetime import datetime, time, timezone

from conversation_service import ConversationService, IncomingTextMessage
from fake_calendar_provider import FakeCalendarProvider
from fakes import FakeLLMProvider
from persistence import SQLiteDatabase
from tool_executor import ToolExecutor
from tool_validation import BusinessHours, TimeWindow


class PatientNameCollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = SQLiteDatabase(os.path.join(directory.name, "names.sqlite3"))
        self.now = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)
        self.provider = FakeCalendarProvider()
        self.llm = FakeLLMProvider(reply="El LLM no debe interpretar el nombre")
        self.executor = ToolExecutor(
            provider=self.provider,
            default_timezone="UTC",
            now=self.now,
            business_hours=BusinessHours(
                timezone_name="UTC",
                windows_by_weekday={
                    day: (TimeWindow(time(9), time(17)),) for day in range(7)
                },
            ),
        )
        self.service = self.new_service()
        self.sequence = 0
        self.events = []

    def new_service(self) -> ConversationService:
        return ConversationService(
            self.database,
            llm_provider=self.llm,
            tool_executor=self.executor,
            timezone_name="UTC",
            now=self.now,
            max_history_messages=2,
        )

    def send(self, text: str, *, message_id: str | None = None) -> str:
        self.sequence += 1
        self.context = self.service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id=message_id or f"wamid.name-{self.sequence}",
                message_type="text",
                text=text,
            )
        )
        reply = asyncio.run(
            self.service.build_reply(self.context, appointment_event_sink=self.events.append)
        )
        self.service.record_reply_sent(
            self.context, body=reply, provider_message_id=f"wamid.reply-{self.sequence}"
        )
        return reply

    def start_booking(self) -> None:
        self.assertIn("Horarios disponibles", self.send("Quiero agendar para mañana"))
        self.assertIn("nombre completo", self.send("11 am"))

    def stored_name(self) -> str | None:
        with self.database.transaction() as connection:
            patient = self.service.patients.get_by_id(connection, self.context.patient_id)
        return patient.name

    def test_suspicious_parts_request_clarification_without_saving_or_trimming(self) -> None:
        self.start_booking()
        for name in ("Asael Ponce jhbashkda", "Asael Ponce junajusndqwd"):
            with self.subTest(name=name):
                reply = self.send(name)
                self.assertIn("¿Me confirmas tus apellidos?", reply)
                self.assertIn(f"Recibí ‘{name}’", reply)
                self.assertIsNone(self.stored_name())
                self.assertEqual(self.provider.appointments, ())
                self.assertEqual(self.events, [])
                pending = self.service._load_pending_appointment_reason(self.context.conversation_id)
                self.assertTrue(pending.name_required)
                self.assertEqual(pending.to_context()["name_candidate"], name)
        self.assertEqual(self.llm.call_count, 0)

    def test_received_full_name_is_echoed_and_preserved(self) -> None:
        self.start_booking()
        reply = self.send("  Asael  Ponce  Silva  ")
        self.assertIn("Asael Ponce Silva", reply)
        self.assertIn("motivo", reply)
        self.assertEqual(self.stored_name(), "Asael Ponce Silva")
        self.assertEqual(self.provider.appointments, ())
        self.assertIn("confirmada", self.send("Revisión general"))
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.provider.appointments[0].start_at.hour, 11)

    def test_corrected_name_replaces_candidate_and_keeps_the_selected_slot(self) -> None:
        self.start_booking()
        self.send("Asael Ponce jhbashkda")
        reply = self.send("Asael Ponce Silva")
        self.assertIn("Asael Ponce Silva", reply)
        self.assertEqual(self.stored_name(), "Asael Ponce Silva")
        self.assertIn("confirmada", self.send("Revisión general"))
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.provider.appointments[0].start_at.hour, 11)

    def test_explicit_confirmation_preserves_an_unusual_name_after_restart(self) -> None:
        self.start_booking()
        name = "Jan Chrząszcz"
        self.assertIn(name, self.send(name, message_id="wamid.candidate"))
        self.assertIsNone(self.stored_name())
        self.service = self.new_service()
        reply = self.send("Sí, es correcto", message_id="wamid.confirm-name")
        self.assertIn(name, reply)
        self.assertIn("motivo", reply)
        self.assertEqual(self.stored_name(), name)
        retry = self.send("Texto ignorado por idempotencia", message_id="wamid.confirm-name")
        self.assertEqual(retry, reply)
        self.assertEqual(self.provider.appointments, ())
        self.assertEqual(self.events, [])
        self.assertIn("confirmada", self.send("Revisión general"))
        self.assertEqual(len(self.events), 1)

    def test_repeating_candidate_is_not_an_explicit_confirmation(self) -> None:
        self.start_booking()
        name = "Asael Ponce junajusndqwd"
        first_reply = self.send(name)
        self.assertEqual(self.send(name), first_reply)
        self.assertIsNone(self.stored_name())
        self.assertEqual(self.provider.appointments, ())
        self.assertEqual(self.llm.call_count, 0)

    def test_invalid_reply_keeps_candidate_and_cannot_confirm_it(self) -> None:
        self.start_booking()
        name = "Asael Ponce jhbashkda"
        self.send(name)
        for text in ("12345", "", "???", "Sí, 123"):
            with self.subTest(text=text):
                self.assertIn(name, self.send(text))
                self.assertIsNone(self.stored_name())
        self.assertIn(name, self.send("Sí"))
        self.assertEqual(self.stored_name(), name)
        self.assertEqual(self.provider.appointments, ())

    def test_negative_confirmation_requests_full_name_without_abandoning_booking(self) -> None:
        self.start_booking()
        self.send("Asael Ponce jhbashkda")
        reply = self.send("No", message_id="wamid.reject-name")
        self.assertIn("nombre completo", reply)
        self.assertIsNone(self.stored_name())
        self.assertIsNotNone(self.service._load_pending_appointment_reason(self.context.conversation_id))
        self.assertIn("nombre completo", self.send("No", message_id="wamid.reject-name"))
        self.send("Sí")
        self.assertIsNone(self.stored_name())
        self.assertIn("Asael Ponce Silva", self.send("Asael Ponce Silva"))
        self.assertIn("confirmada", self.send("Revisión general"))

    def test_old_candidate_retry_does_not_replace_new_candidate_or_become_reason(self) -> None:
        self.start_booking()
        first_name = "Asael Ponce jhbashkda"
        second_name = "Asael Ponce junajusndqwd"
        self.send(first_name, message_id="wamid.old-candidate")
        self.send(second_name)
        self.assertIn(second_name, self.send(first_name, message_id="wamid.old-candidate"))
        self.assertIn("motivo", self.send("Asael Ponce Silva"))
        self.assertIn("motivo", self.send(first_name, message_id="wamid.old-candidate"))
        self.assertEqual(self.stored_name(), "Asael Ponce Silva")
        self.assertEqual(self.events, [])
        self.assertEqual(self.provider.appointments, ())

    def test_uncommon_names_and_scripts_are_not_silently_changed(self) -> None:
        for name in (
            "María José D’Ávila",
            "Jean-Luc O'Neill",
            "Jan Krzysztof Brzęczyszczykiewicz",
            "Ana Schwarzenegger",
            "Li Ng",
            "李 小龙",
            "محمد العتيبي",
        ):
            with self.subTest(name=name):
                self.start_booking()
                reply = self.send(name)
                self.assertIn(name, reply)
                self.assertIn("motivo", reply)
                self.assertEqual(self.stored_name(), name)
                self.assertEqual(self.provider.appointments, ())
        self.assertEqual(self.llm.call_count, 0)

    def test_pending_name_survives_a_side_question_and_explicit_resume(self) -> None:
        self.start_booking()
        name = "Asael Ponce jhbashkda"
        self.send(name)
        self.send("¿Dónde está el consultorio?")
        self.service = self.new_service()
        self.assertIn(name, self.send("Retomemos la cita"))
        self.assertIn(name, self.send("Sí"))
        self.assertEqual(self.stored_name(), name)

    def test_suspicious_name_does_not_replace_a_previously_saved_name(self) -> None:
        self.start_booking()
        with self.database.transaction() as connection:
            self.service.patients.update_name(connection, self.context.patient_id, "Ana Prueba", self.now.isoformat())
        self.send("Asael Ponce jhbashkda")
        self.assertEqual(self.stored_name(), "Ana Prueba")
        self.assertEqual(self.provider.appointments, ())
        self.assertEqual(self.events, [])

    def test_confirmation_while_paused_does_not_accept_the_name(self) -> None:
        self.start_booking()
        name = "Asael Ponce jhbashkda"
        self.send(name)
        self.send("¿Dónde está el consultorio?")
        self.send("Sí")
        self.assertIsNone(self.stored_name())
        self.assertEqual(self.provider.appointments, ())
        self.assertIn(name, self.send("Retomemos la cita"))
        self.assertIn(name, self.send("Sí"))
        self.assertEqual(self.stored_name(), name)

    def test_invalid_name_retry_cannot_be_used_as_reason(self) -> None:
        self.start_booking()
        self.send("Asael 123", message_id="wamid.invalid-name")
        self.assertIsNone(self.stored_name())
        self.send("Asael Ponce Silva")
        self.assertIn("motivo", self.send("Asael 123", message_id="wamid.invalid-name"))
        self.assertEqual(self.provider.appointments, ())
        self.assertEqual(self.events, [])


if __name__ == "__main__":
    unittest.main()
