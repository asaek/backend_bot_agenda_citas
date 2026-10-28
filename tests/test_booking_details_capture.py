import asyncio
from datetime import datetime, time, timezone
import os
import tempfile
import unittest
from unittest.mock import patch

from appointment_reason_evaluation import StructuredAppointmentReasonEvaluator
from conversation_service import ConversationService, IncomingTextMessage
from fake_calendar_provider import FakeCalendarProvider
from fakes import FakeLLMProvider
from llm_provider import ToolCall
from persistence import SQLiteDatabase
from tool_executor import ToolExecutor
from tool_validation import BusinessHours, TimeWindow


class BookingDetailsCaptureTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = SQLiteDatabase(os.path.join(directory.name, "capture.sqlite3"))
        self.now = datetime(2026, 10, 28, 5, tzinfo=timezone.utc)
        self.provider = FakeCalendarProvider()
        self.executor = ToolExecutor(
            provider=self.provider, default_timezone="UTC", now=self.now,
            business_hours=BusinessHours(
                timezone_name="UTC",
                windows_by_weekday={day: (TimeWindow(time(9), time(17)),) for day in range(7)},
            ),
        )
        self.events = []
        self.sequence = 0

    def configure(self, *replies):
        self.llm = FakeLLMProvider(replies=replies)
        self.restart()

    def restart(self):
        self.service = ConversationService(
            self.database, llm_provider=self.llm, tool_executor=self.executor,
            timezone_name="UTC", now=self.now, max_history_messages=2,
        )

    def create_request(self, hour):
        return ToolCall(
            name="create_appointment",
            arguments={"start_at": f"2026-10-28T{hour:02}:00:00+00:00", "reason": "Inventado"},
            call_id="capture-booking",
        )

    def send(self, text, *, message_id=None):
        self.sequence += 1
        self.context = self.service.receive_message(IncomingTextMessage(
            sender="5491100000000", message_id=message_id or f"capture-{self.sequence}",
            message_type="text", text=text,
        ))
        reply = asyncio.run(self.service.build_reply(self.context, self.events.append))
        self.service.record_reply_sent(
            self.context, body=reply, provider_message_id=f"capture-reply-{self.sequence}",
        )
        return reply

    def assert_booking(self, reply, *, name, reason, hour):
        self.assertIn("Tipo de evento: Cita agendada", reply)
        with self.database.transaction() as connection:
            patient = self.service.patients.get_by_id(connection, self.context.patient_id)
        self.assertEqual(patient.name, name)
        self.assertEqual(len(self.provider.appointments), 1)
        self.assertEqual(self.provider.appointments[0].reason, reason)
        self.assertEqual(self.provider.appointments[0].start_at.hour, hour)
        self.assertEqual(len(self.events), 1)

    def test_name_and_reason_in_one_message_are_not_saved_as_a_single_name(self):
        self.configure(self.create_request(10))
        self.assertIn("nombre completo", self.send("a las 10 am"))

        reply = self.send("Asael Ponce Silva y el motivo es por problemas de la vista")

        self.assert_booking(reply, name="Asael Ponce Silva", reason="problemas de la vista", hour=10)

    def test_reason_given_before_backend_requests_name_survives_restart(self):
        reason = "Me hice unos estudios y deseo que el medico los revise es sobre problemas de la vista"
        self.configure(
            "Claro. ¿Cuál es el motivo de la consulta para la cita de hoy a las 4:00 PM?",
            self.create_request(16),
        )
        self.send("quisiera agendar una cita para le dia de hoy a las 4 pm")
        self.assertIn("nombre completo", self.send(reason))
        self.restart()

        reply = self.send("Asael ponce Silva")

        self.assert_booking(reply, name="Asael ponce Silva", reason=reason, hour=16)

    def test_name_acknowledged_by_agent_is_not_requested_again_after_reason(self):
        self.configure(
            "¿Cuál es tu nombre completo?",
            "Gracias, Asael Ponce Silva. ¿Cuál es el motivo de la consulta?",
            self.create_request(11),
        )
        self.send("a ;as 11 am esta bien por favor")
        self.send("Asael Ponce Silva")
        self.restart()

        reply = self.send("Tengo problemas en la vista")

        self.assert_booking(reply, name="Asael Ponce Silva", reason="Tengo problemas en la vista", hour=11)

    def test_combined_data_also_works_when_backend_is_waiting_for_reason(self):
        self.configure(self.create_request(10))
        self.send("a las 10 am")
        self.send("Ana Prueba")

        reply = self.send("Mi nombre es Asael Ponce Silva y el motivo es problemas de la vista")

        self.assert_booking(reply, name="Asael Ponce Silva", reason="problemas de la vista", hour=10)

    def test_reason_first_with_explicit_name_is_separated(self):
        self.configure(self.create_request(10))
        self.send("a las 10 am")

        reply = self.send("El motivo es problemas de la vista; mi nombre es Asael Ponce Silva")

        self.assert_booking(reply, name="Asael Ponce Silva", reason="problemas de la vista", hour=10)

    def test_conversational_name_prefix_and_symptom_clause_are_separated(self):
        self.configure(self.create_request(10))
        self.send("a las 10 am")

        reply = self.send("Me llamo Asael Ponce Silva, tengo problemas en la vista")

        self.assert_booking(reply, name="Asael Ponce Silva", reason="tengo problemas en la vista", hour=10)

    def test_suspicious_combined_name_keeps_reason_until_explicit_confirmation(self):
        self.configure(self.create_request(10))
        self.send("a las 10 am")
        reply = self.send("Jan Chrząszcz y el motivo es problemas de la vista")
        self.assertIn("Jan Chrząszcz", reply)
        self.assertEqual(self.provider.appointments, ())
        self.restart()

        reply = self.send("Sí, es correcto")

        self.assert_booking(reply, name="Jan Chrząszcz", reason="problemas de la vista", hour=10)

    def test_combined_reason_still_uses_structured_evaluator_before_booking(self):
        self.configure(self.create_request(10))
        self.send("a las 10 am")
        evaluator = FakeLLMProvider(replies=(
            '{"quality":"out_of_scope","category":"out_of_scope","priority_signals":[],"confidence":0.95}',
            '{"quality":"valid","category":"routine_exam","priority_signals":[],"confidence":0.95}',
        ))
        self.service.reason_evaluator = StructuredAppointmentReasonEvaluator(evaluator)

        reply = self.send("Asael Ponce Silva y el motivo es dolor en el pie")

        self.assertIn("no estar relacionado", reply)
        self.assertEqual(self.provider.appointments, ())
        self.assertEqual(self.events, [])
        reply = self.send("Revisión general")
        self.assert_booking(reply, name="Asael Ponce Silva", reason="Revisión general", hour=10)
        self.assertEqual(evaluator.call_count, 2)

    def test_multi_clause_reason_is_preserved_without_becoming_a_name(self):
        self.configure(self.create_request(10))
        self.send("a las 10 am")
        self.send("Asael Ponce Silva")
        reason = "Me hice unos estudios y tengo problemas en la vista, tengo dolor al leer"

        reply = self.send(reason)

        self.assert_booking(reply, name="Asael Ponce Silva", reason=reason, hour=10)

    def test_first_person_medical_reason_does_not_replace_the_name(self):
        self.configure(self.create_request(10))
        self.send("a las 10 am")
        self.send("Asael Ponce Silva")
        reason = "Soy diabético y tengo problemas en la vista"

        reply = self.send(reason)

        self.assert_booking(reply, name="Asael Ponce Silva", reason=reason, hour=10)

    def test_name_starting_with_soy_is_preserved_in_full(self):
        self.configure(self.create_request(10))
        self.send("a las 10 am")
        self.assertIn("Soyoung Kim", self.send("Soyoung Kim"))

        reply = self.send("Revisión general")

        self.assert_booking(reply, name="Soyoung Kim", reason="Revisión general", hour=10)

    def test_blank_reply_does_not_retry_a_previously_rejected_reason(self):
        self.configure(self.create_request(10))
        self.send("a las 10 am")
        evaluator = FakeLLMProvider(replies=(
            '{"quality":"out_of_scope","category":"out_of_scope","priority_signals":[],"confidence":0.95}',
            '{"quality":"valid","category":"routine_exam","priority_signals":[],"confidence":0.95}',
        ))
        self.service.reason_evaluator = StructuredAppointmentReasonEvaluator(evaluator)
        self.send("Asael Ponce Silva y el motivo es dolor en el pie")

        reply = self.send("")

        self.assertIn("¿Quieres una revisión general", reply)
        self.assertEqual(self.provider.appointments, ())
        self.assertEqual(evaluator.call_count, 1)

    def test_agent_invented_name_is_not_evidence_of_patient_name(self):
        self.configure(
            "Gracias, Nombre Inventado. ¿Cuál es el motivo de la consulta?",
            self.create_request(10),
        )
        self.send("a las 10 am")

        reply = self.send("Tengo problemas en la vista")

        self.assertIn("nombre completo", reply)
        self.assertEqual(self.provider.appointments, ())
        reply = self.send("Asael Ponce Silva")
        self.assert_booking(reply, name="Asael Ponce Silva", reason="Tengo problemas en la vista", hour=10)

    def test_new_booking_does_not_reuse_data_from_a_completed_booking(self):
        self.configure(self.create_request(10), self.create_request(11))
        self.send("a las 10 am")
        self.send("Asael Ponce Silva y el motivo es problemas de la vista")

        reply = self.send("Quiero otra cita hoy a las 11 am")

        self.assertIn("nombre completo", reply)
        self.assertEqual(len(self.provider.appointments), 1)
        self.assertEqual(len(self.events), 1)
        reply = self.send("Ana Prueba")
        self.assertIn("motivo", reply)
        self.assertEqual(len(self.provider.appointments), 1)

    def test_abandoned_capture_does_not_supply_data_to_the_next_booking(self):
        self.configure(
            "¿Cuál es tu nombre completo?",
            "Gracias. ¿Cuál es el motivo de la consulta?",
            "De acuerdo, dejamos la solicitud.",
            self.create_request(10),
        )
        self.send("a las 10 am")
        self.send("Asael Ponce Silva")
        self.send("Mejor no")

        reply = self.send("Quiero una cita hoy a las 10 am")

        self.assertIn("nombre completo", reply)
        self.assertEqual(self.provider.appointments, ())

    def test_expired_prompted_data_is_not_recovered(self):
        self.configure(
            "¿Cuál es tu nombre completo?",
            "Gracias. ¿Cuál es el motivo de la consulta?",
            self.create_request(10),
        )
        with patch("conversation_service.utc_now", return_value="2026-10-28T05:00:00+00:00"):
            self.send("a las 10 am")
            self.send("Asael Ponce Silva")

        with patch("conversation_service.utc_now", return_value="2026-10-28T05:11:00+00:00"):
            reply = self.send("Tengo problemas en la vista")

        self.assertIn("nombre completo", reply)
        self.assertEqual(self.provider.appointments, ())
