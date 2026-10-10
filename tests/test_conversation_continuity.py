import asyncio
import os
import tempfile
import unittest
from datetime import datetime, time, timedelta, timezone

from calendar_domain import AppointmentStatus, CalendarProviderUnavailable, ToolName
from conversation_service import (
    APPOINTMENT_NAME_REPLY,
    APPOINTMENT_REASON_REPLY,
    ConversationService,
    IncomingTextMessage,
)
from fake_calendar_provider import FakeCalendarProvider
from fakes import FakeLLMProvider
from llm_provider import ToolCall
from persistence import SQLiteDatabase
from tool_executor import ToolExecutor
from tool_validation import BusinessHours, TimeWindow


class ConversationContinuityTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = SQLiteDatabase(os.path.join(directory.name, "continuity.sqlite3"))
        self.now = datetime.now(timezone.utc)
        self.target_date = (self.now + timedelta(days=1)).date()
        self.provider = FakeCalendarProvider()
        self.llm = FakeLLMProvider(reply="Información del consultorio.")
        self.executor = ToolExecutor(
            provider=self.provider,
            default_timezone="UTC",
            now=lambda: self.now,
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
            now=lambda: self.now,
            max_history_messages=2,
        )

    def send(self, text: str) -> str:
        self.sequence += 1
        context = self.service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id=f"wamid.continuity-{self.sequence}",
                message_type="text",
                text=text,
            )
        )
        reply = asyncio.run(
            self.service.build_reply(context, appointment_event_sink=self.events.append)
        )
        self.service.record_reply_sent(
            context, body=reply, provider_message_id=f"wamid.reply-{self.sequence}"
        )
        return reply

    def offer_slots(self) -> None:
        self.assertIn("Horarios disponibles", self.send("Quiero agendar para mañana"))

    def book(self) -> None:
        self.offer_slots()
        self.send("11 am")
        self.send("Asael Ponce Silva")
        self.assertIn("confirmada", self.send("Revisión general"))
        self.events.clear()

    def request_mutation(self, tool: ToolName, *, text: str | None = None) -> str:
        arguments = {"appointment_id": self.provider.appointments[0].id}
        if tool is ToolName.RESCHEDULE_APPOINTMENT:
            arguments["new_start_at"] = datetime.combine(
                self.target_date, time(15), tzinfo=timezone.utc,
            ).isoformat()
        self.llm.reply = ToolCall(name=tool.value, arguments=arguments, call_id="call-change")
        reply = self.send(text or ("Cancela mi cita" if tool is ToolName.CANCEL_APPOINTMENT else "Quiero cambiar mi cita a las 15"))
        self.llm.reply = "Información del consultorio."
        return reply

    def test_booking_word_in_slot_selection_keeps_the_same_booking(self) -> None:
        self.offer_slots()
        self.assertEqual(self.send("agéndame a las 11 am"), APPOINTMENT_NAME_REPLY)
        self.assertTrue(self.send("Asael Ponce Silva").endswith(APPOINTMENT_REASON_REPLY))
        self.assertIn("confirmada", self.send("Revisión general"))
        self.assertEqual(self.llm.call_count, 0)
        self.assertEqual(len(self.provider.appointments), 1)
        appointment = self.provider.appointments[0]
        self.assertEqual(appointment.start_at.date(), self.target_date)
        self.assertEqual(appointment.start_at.hour, 11)
        self.assertEqual(appointment.reason, "Revisión general")
        self.assertEqual(len(self.events), 1)

    def test_reported_cancellation_uses_one_confirmation_after_listing_monday_appointments(self) -> None:
        self.now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        for selection, reason in (("10 am", "Tengo los ojos rojos"), ("12 pm", "tengo un ojo rojo")):
            self.send("Quiero agendar para el lunes")
            self.send(selection)
            self.send("Asael Ponce Silva")
            self.assertIn("confirmada", self.send(reason))
        first, second = self.provider.appointments
        self.events.clear()
        self.llm.replies = (
            ToolCall(name=ToolName.LIST_APPOINTMENTS.value, arguments={}, call_id="call-monday-list"),
            "- Horario: 10:00 AM a 10:30 AM\n  Motivo de consulta:\n  Tengo los ojos rojos\n\n"
            "- Horario: 12:00 PM a 12:30 PM\n  Motivo de consulta:\n  tengo un ojo rojo",
            "¿Confirmas que deseas cancelar esta cita?\n\nFecha: 12/10/2026\n"
            "Hora: 10:00 AM a 10:30 AM\nMotivo: Tengo los ojos rojos\n\n"
            "Responde Sí para confirmar o No para mantenerla.",
            ToolCall(
                name=ToolName.CANCEL_APPOINTMENT.value,
                arguments={"appointment_id": first.id}, call_id="call-delayed-cancel",
            ),
        )
        self.assertIn("10:00 AM", self.send("Dime las citas que tengo para el lunes"))
        self.assertIn("Confirmas", self.send("quisiera cancelar la de las 10 am"))
        self.assertEqual(self.provider.appointments, (first, second))
        self.assertEqual(self.events, [])
        self.service = self.new_service()

        reply = self.send("si por favor")

        self.assertEqual(reply, "Tu cita ha sido cancelada.")
        self.assertEqual(self.llm.call_count, 2)
        self.assertEqual(self.provider.appointments[0].id, first.id)
        self.assertEqual(self.provider.appointments[0].status, AppointmentStatus.CANCELLED)
        self.assertEqual(self.provider.appointments[1], second)
        self.assertEqual(len(self.events), 1)

    def test_cancellation_does_not_fall_back_to_a_different_date_time_or_multiple_targets(self) -> None:
        self.now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        self.target_date = (self.now + timedelta(days=1)).date()
        self.book()
        original = self.provider.appointments[0]
        for text in (
            "Cancela mi cita del lunes de las 11 am",
            "Cancela mi cita de las 11.30 am",
            "Cancela mi cita de las 11 am y la de las 12 pm",
        ):
            with self.subTest(text=text):
                reply = self.send(text)
                self.assertNotIn("Confirmas", reply)
                self.assertIn("identificar", reply)
                self.assertEqual(self.provider.appointments, (original,))
                self.assertEqual(self.events, [])
        self.assertEqual(self.llm.call_count, 0)

    def test_cancellation_uses_the_explicit_day_and_rejection_preserves_both_appointments(self) -> None:
        self.now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        for day in ("lunes", "martes"):
            self.send(f"Quiero agendar para el {day}")
            self.send("10 am")
            self.send("Asael Ponce Silva")
            self.assertIn("confirmada", self.send("Revisión general"))
        first, second = self.provider.appointments
        self.events.clear()
        ambiguous = self.send("Cancela mi cita de las 10 am")
        self.assertIn("¿Cuál cita quieres cancelar?", ambiguous)
        self.assertNotIn("Confirmas", ambiguous)
        prompt = self.send("Quiero cancelar mi cita del martes a las 10 am")
        self.assertIn("13/10/2026", prompt)
        self.assertIn("Confirmas", prompt)
        self.assertIn("ningún cambio", self.send("No, gracias"))
        self.assertEqual(self.provider.appointments, (first, second))
        self.assertEqual(self.events, [])
        self.service = self.new_service()
        self.assertIn("12/10/2026", self.send("Cancela la de 12/10/2026 a las 10 am"))
        self.assertEqual(self.send("si por favor"), "Tu cita ha sido cancelada.")
        self.assertEqual(self.provider.appointments[0].status, AppointmentStatus.CANCELLED)
        self.assertEqual(self.provider.appointments[1], second)
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.llm.call_count, 0)

    def test_model_cannot_display_a_cancellation_confirmation_without_pending_action(self) -> None:
        self.book()
        original = self.provider.appointments[0]
        self.llm.replies = (
            "¿Confirmas que deseas cancelar esta cita? Responde Sí o No.",
            ToolCall(name=ToolName.CANCEL_APPOINTMENT.value, arguments={"appointment_id": original.id}),
        )
        reply = self.send("Podrías dar de baja mi cita")
        self.assertNotIn("Confirmas", reply)
        self.assertIn("día y horario", reply)
        reply = self.send("si por favor")
        self.assertNotIn("Confirmas", reply)
        self.assertIn("No hay una cancelación pendiente", reply)
        self.assertIn("No hay una gestión pendiente", self.send("Retomemos la cita"))
        self.assertEqual(self.provider.appointments, (original,))
        self.assertEqual(self.events, [])

    def test_reported_monday_booking_collects_the_name_once_and_survives_restart(self) -> None:
        self.now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        self.llm.reply = "¡Hola, buenos días! ¿En qué puedo ayudarte?"
        self.assertIn("Hola", self.send("Hola buenos dias"))
        offered = self.send("quisiera agendar una cita para el dia lunes")
        self.assertIn("12/10/2026", offered)
        self.assertIn("9:00 AM a 9:30 AM", offered)

        self.assertIn("nombre completo", self.send("quisiera una cita a las 9 am"))
        self.assertEqual(self.llm.call_count, 1)
        self.service = self.new_service()
        accepted = self.send("Asael Ponce Silva")
        self.assertIn("Asael Ponce Silva", accepted)
        self.assertIn("motivo", accepted)
        self.assertEqual(self.provider.appointments, ())
        self.assertEqual(self.events, [])

        self.service = self.new_service()
        confirmed = self.send("Tengo los ojos rojos")
        self.assertIn("confirmada", confirmed)
        self.assertNotIn("nombre completo", confirmed)
        self.assertEqual(self.llm.call_count, 1)
        self.assertEqual(len(self.provider.appointments), 1)
        appointment = self.provider.appointments[0]
        self.assertEqual(appointment.start_at, datetime(2026, 10, 12, 9, tzinfo=timezone.utc))
        self.assertEqual(appointment.reason, "Tengo los ojos rojos")
        self.assertEqual(len(self.events), 1)
        with self.database.transaction() as connection:
            patient = self.service.patients.get_by_id(connection, appointment.patient_scope.patient_id)
        self.assertEqual(patient.name, "Asael Ponce Silva")

    def test_reported_ten_am_choices_select_an_available_slot_after_a_nine_am_booking(self) -> None:
        self.now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        self.send("Quiero agendar para el lunes")
        self.send("quisiera a las 9 am")
        self.send("Asael Ponce Silva")
        self.assertIn("confirmada", self.send("tengo un ojo rojo"))
        original = self.provider.appointments[0]
        self.events.clear()

        for expression in ("QUisiera.a las 10 am", "a las 10 am esta bien"):
            with self.subTest(expression=expression):
                offered = self.send("Buenos dias quisiera agendar para el dia lunes")
                self.assertNotIn("- 9:00 AM a 9:30 AM", offered)
                self.assertIn("- 10:00 AM a 10:30 AM", offered)
                self.service = self.new_service()
                self.assertEqual(self.send(expression), APPOINTMENT_NAME_REPLY)
                self.assertEqual(self.provider.appointments, (original,))
                self.assertEqual(self.events, [])

        self.send("Asael Ponce Silva")
        self.assertIn("confirmada", self.send("Revisión general"))
        self.assertEqual(len(self.provider.appointments), 2)
        self.assertIn(original, self.provider.appointments)
        self.assertEqual(self.provider.appointments[1].start_at, datetime(2026, 10, 12, 10, tzinfo=timezone.utc))
        self.assertEqual(self.provider.appointments[1].reason, "Revisión general")
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.llm.call_count, 0)

    def test_booking_explains_an_unavailable_hour_and_keeps_active_or_paused_slots(self) -> None:
        self.now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        self.provider.register_busy_period(
            calendar_id="calendar-1",
            start_at=datetime(2026, 10, 12, 9, tzinfo=timezone.utc),
            end_at=datetime(2026, 10, 12, 9, 30, tzinfo=timezone.utc),
        )
        offered = self.send("Quiero agendar para el lunes")
        self.assertNotIn("- 9:00 AM a 9:30 AM", offered)
        self.assertIn("- 10:00 AM a 10:30 AM", offered)
        for expression in ("9 am", "QUisiera.a las 9 am", "a las 9 am esta bien", "8 am", "5 pm"):
            with self.subTest(expression=expression):
                reply = self.send(expression)
                self.assertIn("no está disponible", reply)
                self.assertNotIn("No identifiqué", reply)
                self.assertNotIn("nombre completo", reply)
                self.assertEqual(self.provider.appointments, ())
                self.assertEqual(self.events, [])
        self.assertEqual(self.llm.call_count, 0)
        self.send("¿Cuánto cuesta la consulta?")
        self.service = self.new_service()
        self.assertIn("no está disponible", self.send("a las 9 am esta bien"))
        self.assertEqual(self.send("a las 10 am está bien, gracias"), APPOINTMENT_NAME_REPLY)
        self.send("Asael Ponce Silva")
        self.assertIn("confirmada", self.send("Revisión general"))
        self.assertEqual(len(self.provider.appointments), 1)
        self.assertEqual(self.provider.appointments[0].start_at, datetime(2026, 10, 12, 10, tzinfo=timezone.utc))
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.llm.call_count, 1)

    def test_booking_distinguishes_invalid_and_ambiguous_times_from_unavailability(self) -> None:
        self.now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        self.executor = ToolExecutor(
            provider=self.provider, default_timezone="UTC", now=lambda: self.now,
            business_hours=BusinessHours(
                timezone_name="UTC",
                windows_by_weekday={day: (TimeWindow(time(0), time(23)),) for day in range(7)},
            ),
        )
        self.service = self.new_service()
        self.send("Quiero agendar para el lunes")
        for text in ("10:99 am", "25 am", "no sé cuál horario", "a las 10 am o a las 11 am esta bien"):
            with self.subTest(text=text):
                reply = self.send(text)
                self.assertNotIn("ocupado", reply)
                self.assertNotIn("no está disponible", reply)
                self.assertNotIn("nombre completo", reply)
                self.assertEqual(self.provider.appointments, ())
                self.assertEqual(self.events, [])
        ambiguous = self.send("a las 12 esta bien")
        self.assertIn("Indica AM o PM", ambiguous)
        self.assertNotIn("ocupado", ambiguous)
        self.assertEqual(self.send("a las 12 pm está bien"), APPOINTMENT_NAME_REPLY)
        self.send("Asael Ponce Silva")
        self.assertIn("confirmada", self.send("Revisión general"))
        self.assertEqual(self.provider.appointments[0].start_at, datetime(2026, 10, 12, 12, tzinfo=timezone.utc))
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.llm.call_count, 0)

    def test_punctuated_night_period_is_not_replaced_by_an_available_morning(self) -> None:
        self.now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        for paused in (False, True):
            with self.subTest(paused=paused):
                offered = self.send("Quiero agendar para el lunes")
                self.assertIn("- 10:00 AM a 10:30 AM", offered)
                if paused:
                    self.send("¿Cuánto cuesta la consulta?")
                self.service = self.new_service()
                reply = self.send("a las 10 de.la.noche está bien")
                self.assertIn("no está disponible", reply)
                self.assertNotIn("nombre completo", reply)
                self.assertEqual(self.provider.appointments, ())
                self.assertEqual(self.events, [])
        self.assertEqual(self.send("a las 10 a.m. está bien"), APPOINTMENT_NAME_REPLY)
        self.send("Asael Ponce Silva")
        self.assertIn("confirmada", self.send("Revisión general"))
        self.assertEqual(self.provider.appointments[0].start_at.hour, 10)
        self.assertEqual(len(self.events), 1)

    def test_punctuated_night_period_selects_night_when_both_periods_are_offered(self) -> None:
        self.now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        self.executor = ToolExecutor(
            provider=self.provider, default_timezone="UTC", now=lambda: self.now,
            business_hours=BusinessHours(
                timezone_name="UTC",
                windows_by_weekday={day: (TimeWindow(time(0), time(23)),) for day in range(7)},
            ),
        )
        self.service = self.new_service()
        offered = self.send("Quiero agendar para el lunes")
        self.assertIn("- 10:00 AM a 10:30 AM", offered)
        self.assertIn("- 10:00 PM a 10:30 PM", offered)
        self.assertEqual(self.send("a las 10 de.la.noche está bien"), APPOINTMENT_NAME_REPLY)
        self.send("Asael Ponce Silva")
        self.assertIn("confirmada", self.send("Revisión general"))
        self.assertEqual(self.provider.appointments[0].start_at, datetime(2026, 10, 12, 22, tzinfo=timezone.utc))
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.llm.call_count, 0)

    def test_new_booking_prefixes_replace_a_paused_list_with_the_requested_day(self) -> None:
        self.now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        for expression in (
            "deseo una cita a las 9 am pasado mañana",
            "me gustaría otra cita a las 9 am pasado mañana",
        ):
            with self.subTest(expression=expression):
                self.llm.reply = "Información del consultorio."
                self.offer_slots()
                self.assertIn("Información", self.send("¿Cuánto cuesta la consulta?"))
                self.service = self.new_service()
                self.llm.reply = ToolCall(
                    name=ToolName.CREATE_APPOINTMENT.value,
                    arguments={"start_at": "2026-10-12T09:00:00+00:00", "reason": "Ignorado"},
                    call_id="call-new-booking-day",
                )
                self.assertIn("nombre completo", self.send(expression))
                resumed = self.send("Retomemos la cita")
                self.assertIn("12/10/2026", resumed)
                self.assertIn("9:00 AM", resumed)
                self.assertNotIn("Horarios disponibles", resumed)
                self.assertEqual(self.provider.appointments, ())
                self.assertEqual(self.events, [])
        self.send("Asael Ponce Silva")
        self.assertIn("confirmada", self.send("Tengo los ojos rojos"))
        self.assertEqual(len(self.provider.appointments), 1)
        self.assertEqual(self.provider.appointments[0].start_at, datetime(2026, 10, 12, 9, tzinfo=timezone.utc))
        self.assertEqual(len(self.events), 1)

    def test_cost_questions_with_booking_words_keep_the_accepted_name_while_paused(self) -> None:
        self.now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        self.offer_slots()
        self.send("11 am")
        self.send("Asael Ponce Silva")
        for text in (
            "¿Cuál es el costo si deseo reservar una cita?",
            "¿Cuánto cuesta si me gustaría agendar una cita?",
        ):
            self.assertIn("Información", self.send(text))
            self.service = self.new_service()
            self.assertEqual(self.provider.appointments, ())
            self.assertEqual(self.events, [])
        resumed = self.send("Retomemos la cita")
        self.assertIn("motivo", resumed)
        self.assertNotIn("nombre completo", resumed)
        self.assertIn("confirmada", self.send("Tengo los ojos rojos"))
        self.assertEqual(len(self.provider.appointments), 1)
        self.assertEqual(self.provider.appointments[0].start_at, datetime(2026, 10, 11, 11, tzinfo=timezone.utc))
        self.assertEqual(len(self.events), 1)

    def test_natural_reschedule_selection_confirms_the_listed_appointment_for_today(self) -> None:
        self.now = datetime(2026, 10, 9, 9, 23, tzinfo=timezone.utc)
        self.target_date = self.now.date()
        self.assertIn("Horarios disponibles", self.send("Quiero agendar para hoy"))
        self.send("10 am")
        self.send("Asael Ponce Silva")
        self.assertIn("confirmada", self.send("Veo oscuro"))
        original = self.provider.appointments[0]
        self.events.clear()
        self.llm.reply = (
            "Hoy tienes esta cita:\n\n- Horario: 10:00 AM a 10:30 AM\n"
            "  Motivo de consulta:\n  Veo oscuro"
        )
        self.assertIn("10:00 AM", self.send("me podrias decir las citas que tengo para hoy"))
        offered = self.send("quisiera modificar la cita de las 10")
        self.assertIn("- 12:00 PM a 12:30 PM", offered)
        self.llm.reply = ToolCall(
            name=ToolName.RESCHEDULE_APPOINTMENT.value,
            arguments={
                "appointment_id": original.id,
                "new_start_at": original.start_at.replace(hour=12).isoformat(),
            },
            call_id="call-repeated-reschedule",
        )
        calls = self.llm.call_count

        reply = self.send("quisiera cambiarla a las 12 pm")

        self.assertIn("Confirmas", reply)
        self.assertIn("10:00 - 10:30", reply)
        self.assertIn("12:00", reply)
        self.assertIn("Veo oscuro", reply)
        self.assertNotIn("Horarios disponibles", reply)
        self.assertEqual(self.llm.call_count, calls)
        self.assertEqual(self.provider.appointments[0], original)
        self.assertEqual(self.events, [])
        self.assertIn("modificada", self.send("Sí, por favor"))
        changed = self.provider.appointments[0]
        self.assertEqual(changed.id, original.id)
        self.assertEqual(changed.start_at, original.start_at.replace(hour=12))
        self.assertEqual(changed.end_at - changed.start_at, timedelta(minutes=30))
        self.assertEqual(changed.reason, original.reason)
        self.assertEqual(len(self.events), 1)

    def test_expired_booking_refreshes_slots_and_keeps_the_received_name(self) -> None:
        self.offer_slots()
        self.send("11 am")
        self.send("Asael Ponce Silva")
        self.send("¿Cuánto cuesta la consulta?")
        self.now += timedelta(minutes=11)
        self.provider.register_busy_period(
            calendar_id="calendar-1",
            start_at=datetime.combine(self.target_date, time(11), tzinfo=timezone.utc),
            end_at=datetime.combine(self.target_date, time(11, 30), tzinfo=timezone.utc),
        )
        reply = self.send("Retomemos la cita")
        self.assertIn("Horarios disponibles", reply)
        self.assertNotIn("- 11:00 AM a 11:30 AM", reply)
        self.assertEqual(self.send("agéndame a las 12 pm"), APPOINTMENT_REASON_REPLY)
        self.assertIn("confirmada", self.send("Revisión general"))
        self.assertEqual(len(self.provider.appointments), 1)
        self.assertEqual(self.provider.appointments[0].start_at.hour, 12)

    def test_natural_reschedule_expressions_choose_a_slot_without_restarting(self) -> None:
        self.book()
        original = self.provider.appointments[0]
        expressions = (
            "Quisiera cambiarla a las 12 pm",
            "Quisiera.cambiarla a las 12 pm",
            "a las 12 pm está bien",
            "Quiero modificarla a las 12 pm",
            "Me gustaría moverla a las 12 pm",
            "Quisiera reprogramar mi cita para las 12 pm",
            "Necesito cambiar la cita a las 12 pm",
            "Deseo reprogramarla a las 12 pm",
            "Prefiero cambiar mi cita a las 12 pm",
            "¿Podrías cambiarla a las 12 pm?",
            "¿Me puedes mover la cita a las 12 pm, por favor?",
            "Cámbiala a las 12 pm",
            "Cámbiame la cita a las 12 pm",
            "Modifícala a las 12 pm",
            "Mueve mi cita a las 12 pm",
            "Reprográmala para las 12 pm",
            "Pásala a las 12 pm",
            "Ponla a las 12 pm",
            "Déjala para las 12 pm",
            "Mejor a las 12 pm",
            "Que sea a las 12 pm",
            "Me sirve a las 12 pm",
            "Me viene bien a las 12 pm",
            "Me quedo con el horario de las 12 pm",
            "Elijo el horario de las 12 pm",
            "Prefiero las 12 pm",
            "Hola, quisiera cambiarla a las 12 pm, por favor.",
            "Hola, ¿podrías cambiarla a las 12 pm?",
            "Por favor, ¿me puedes mover la cita a las 12 pm?",
            "¿Podrías cambiarla a las 12 pm?, por favor.",
            "A las 12 p. m., gracias!",
            "Quisiera moverla a las 12 de la tarde",
            "12:00",
        )

        for expression in expressions:
            with self.subTest(expression=expression):
                self.assertIn("Horarios disponibles", self.send("Quisiera modificar la cita de las 11"))
                calls = self.llm.call_count
                reply = self.send(expression)
                self.assertIn("Confirmas", reply)
                self.assertIn("12:00", reply)
                self.assertNotIn("Horarios disponibles", reply)
                self.assertEqual(self.llm.call_count, calls)
                self.assertEqual(self.provider.appointments[0], original)
                self.assertEqual(self.events, [])
                self.assertIn("ningún cambio", self.send("No"))

    def test_incomplete_reschedule_period_keeps_the_selection_until_corrected(self) -> None:
        self.book()
        original = self.provider.appointments[0]
        self.assertIn("Horarios disponibles", self.send("Quisiera modificar la cita de las 11"))
        calls = self.llm.call_count

        for expression in (
            "quisiera cambiarla a las 12 p,",
            "12 p.",
            "quisiera moverla a las 12 a,",
        ):
            with self.subTest(expression=expression):
                reply = self.send(expression)
                self.assertIn("AM o PM", reply)
                self.assertNotIn("Confirmas", reply)
                self.assertNotIn("ocupado", reply)
                self.assertNotIn("Horarios disponibles", reply)
                self.assertEqual(self.llm.call_count, calls)
                self.assertEqual(self.provider.appointments[0], original)
                self.assertEqual(self.events, [])
                self.service = self.new_service()

        self.assertIn("Confirmas", self.send("quisiera cambiarla a las 12 pm"))
        self.assertEqual(self.provider.appointments[0], original)
        self.service = self.new_service()
        self.assertIn("modificada", self.send("Sí"))
        self.assertEqual(self.provider.appointments[0].id, original.id)
        self.assertEqual(self.provider.appointments[0].start_at.hour, 12)
        self.assertEqual(len(self.events), 1)

    def test_noon_expressions_select_the_available_noon_slot(self) -> None:
        self.book()
        original = self.provider.appointments[0]
        for expression in (
            "Quisiera cambiarla al mediodía",
            "Prefiero el mediodía",
            "Mejor a las 12 del mediodía",
            "Que sea para el mediodía",
            "Me viene bien a las 12 del día",
            "Elijo el horario de las 12 del día",
            "Quisiera cambiarla 12 del día",
        ):
            with self.subTest(expression=expression):
                self.send("Quisiera modificar la cita de las 11")
                calls = self.llm.call_count
                reply = self.send(expression)
                self.assertIn("Confirmas", reply)
                self.assertIn("12:00", reply)
                self.assertEqual(self.llm.call_count, calls)
                self.assertEqual(self.provider.appointments[0], original)
                self.assertEqual(self.events, [])
                self.send("No")

    def test_natural_reschedule_selection_resumes_paused_slots_after_restart(self) -> None:
        self.book()
        original = self.provider.appointments[0]
        self.send("Quisiera modificar la cita de las 11")
        self.assertIn("Información", self.send("¿Cuánto cuesta la consulta?"))
        self.service = self.new_service()
        calls = self.llm.call_count

        reply = self.send("Me gustaría moverla a las 12 pm")

        self.assertIn("Confirmas", reply)
        self.assertIn("12:00", reply)
        self.assertEqual(self.llm.call_count, calls)
        self.assertEqual(self.provider.appointments[0], original)
        self.assertEqual(self.events, [])
        self.assertIn("modificada", self.send("Sí"))
        self.assertEqual(self.provider.appointments[0].id, original.id)
        self.assertEqual(self.provider.appointments[0].start_at.hour, 12)
        self.assertEqual(len(self.events), 1)

    def test_incomplete_period_is_clarified_while_reschedule_slots_are_paused(self) -> None:
        self.book()
        original = self.provider.appointments[0]
        self.send("Quisiera modificar la cita de las 11")
        self.send("¿Cuánto cuesta la consulta?")
        self.service = self.new_service()
        calls = self.llm.call_count

        reply = self.send("quisiera cambiarla a las 12 p,")

        self.assertIn("mediodía", reply)
        self.assertIn("AM o PM", reply)
        self.assertEqual(self.llm.call_count, calls)
        self.assertEqual(self.provider.appointments[0], original)
        self.assertEqual(self.events, [])
        self.service = self.new_service()
        self.assertIn("Confirmas", self.send("12 pm"))
        self.assertIn("modificada", self.send("Sí"))
        self.assertEqual(self.provider.appointments[0].id, original.id)
        self.assertEqual(self.provider.appointments[0].start_at.hour, 12)
        self.assertEqual(len(self.events), 1)

    def test_bare_twelve_clarifies_between_midnight_and_noon(self) -> None:
        self.book()
        original = self.provider.appointments[0]
        self.executor = ToolExecutor(
            provider=self.provider, default_timezone="UTC", now=lambda: self.now,
            business_hours=BusinessHours(
                timezone_name="UTC",
                windows_by_weekday={
                    day: (TimeWindow(time(0), time(23)),) for day in range(7)
                },
            ),
        )
        self.service = self.new_service()
        offered = self.send("Quisiera modificar la cita de las 11")
        self.assertIn("- 12:00 AM a 12:30 AM", offered)
        self.assertIn("- 12:00 PM a 12:30 PM", offered)

        reply = self.send("Quisiera cambiarla a las 12")

        self.assertIn("Indica AM o PM", reply)
        self.assertEqual(self.provider.appointments[0], original)
        self.assertEqual(self.events, [])
        self.assertIn("00:00", self.send("12 am"))
        self.send("No")
        self.send("Quisiera modificar la cita de las 11")
        self.assertIn("12:00", self.send("12 pm"))
        self.assertEqual(self.provider.appointments[0], original)

    def test_leaving_the_appointment_unchanged_abandons_instead_of_reopening(self) -> None:
        self.book()
        original = self.provider.appointments[0]
        for expression in (
            "Quiero dejarla como está",
            "Prefiero dejarla así",
            "Quisiera dejarla igual",
        ):
            with self.subTest(expression=expression):
                self.send("Quisiera modificar la cita de las 11")
                reply = self.send(expression)
                self.assertIn("dejaré tu cita como está", reply)
                self.assertNotIn("Horarios disponibles", reply)
                self.assertIn("No hay una gestión pendiente", self.send("Retomemos la cita"))
                self.assertEqual(self.provider.appointments[0], original)
                self.assertEqual(self.events, [])

    def test_parking_question_pauses_the_reschedule_instead_of_switching_tasks(self) -> None:
        self.book()
        original = self.provider.appointments[0]
        self.send("Quisiera modificar la cita de las 11")

        reply = self.send("¿Dónde puedo dejar el coche durante la cita?")

        self.assertIn("Información", reply)
        self.assertNotIn("Horarios disponibles", reply)
        self.service = self.new_service()
        self.assertIn("Horarios disponibles", self.send("Retomemos la cita"))
        self.assertIn("Confirmas", self.send("12 pm"))
        self.assertEqual(self.provider.appointments[0], original)
        self.assertEqual(self.events, [])

    def test_question_pauses_and_resume_survives_restart_and_short_history(self) -> None:
        self.offer_slots()
        self.assertEqual(self.send("11 am"), APPOINTMENT_NAME_REPLY)
        self.assertTrue(self.send("Asael Ponce Silva").endswith(APPOINTMENT_REASON_REPLY))
        self.assertIn("Información", self.send("¿Cuánto cuesta la consulta?"))
        self.service = self.new_service()
        self.assertIn("Información", self.send("¿Dónde está el consultorio?"))
        prompt = self.llm.received_messages[-1][0].content
        self.assertIn("Gestión pausada", prompt)
        self.assertIn("11:00 AM", prompt)
        self.assertIn("motivo", prompt)
        resume = self.send("Retomemos la cita")
        self.assertIn("motivo", resume)
        self.assertNotIn("nombre completo", resume)
        self.assertIn("confirmada", self.send("Revisión general"))
        self.assertEqual(len(self.provider.appointments), 1)
        self.assertEqual(self.provider.appointments[0].start_at.hour, 11)
        self.assertEqual(len(self.events), 1)

    def test_paused_reschedule_requires_a_fresh_confirmation(self) -> None:
        self.book()
        self.assertIn("Horarios disponibles", self.request_mutation(ToolName.RESCHEDULE_APPOINTMENT))
        self.assertIn("Confirmas", self.send("15:00"))
        self.assertIn("Información", self.send("¿Cuánto cuesta la consulta?"))
        self.service = self.new_service()
        self.send("Sí")
        self.assertEqual(self.provider.appointments[0].start_at.hour, 11)
        self.assertEqual(self.events, [])
        self.assertIn("Confirmas", self.send("Retomemos la cita"))
        self.assertEqual(self.provider.appointments[0].start_at.hour, 11)
        self.assertIn("modificada", self.send("Sí"))
        self.assertEqual(self.provider.appointments[0].start_at.hour, 15)
        self.assertEqual(len(self.events), 1)

    def test_user_can_withdraw_a_paused_cancellation(self) -> None:
        self.book()
        self.assertIn("Confirmas", self.request_mutation(ToolName.CANCEL_APPOINTMENT))
        self.send("¿Dónde está el consultorio?")
        self.assertIn("ningún cambio", self.send("No quiero cancelarla"))
        self.send("Sí")
        self.assertIn("No hay una gestión pendiente", self.send("Retomemos la cita"))
        self.send("Sí")
        self.assertEqual(self.provider.appointments[0].status, AppointmentStatus.SCHEDULED)
        self.assertEqual(self.events, [])

    def test_paused_cancellation_gets_new_confirmation_after_expiry(self) -> None:
        self.book()
        self.request_mutation(ToolName.CANCEL_APPOINTMENT)
        self.send("¿Cuánto cuesta la consulta?")
        self.now += timedelta(minutes=11)
        self.send("Sí")
        self.assertEqual(self.provider.appointments[0].status, AppointmentStatus.SCHEDULED)
        self.assertIn("Confirmas", self.send("Retomemos la cita"))
        self.assertIn("cancelada", self.send("Sí"))
        self.assertEqual(self.provider.appointments[0].status, AppointmentStatus.CANCELLED)
        self.assertEqual(len(self.events), 1)

    def test_user_can_withdraw_a_paused_reschedule(self) -> None:
        self.book()
        self.request_mutation(ToolName.RESCHEDULE_APPOINTMENT)
        self.send("15:00")
        self.send("¿Dónde está el consultorio?")
        self.assertIn("ningún cambio", self.send("No la modifiques"))
        self.assertIn("No hay una gestión pendiente", self.send("Retomemos la cita"))
        self.send("Sí")
        self.assertEqual(self.provider.appointments[0].start_at.hour, 11)
        self.assertEqual(self.events, [])

    def test_abandoning_a_paused_booking_does_not_create_an_appointment(self) -> None:
        self.offer_slots()
        self.send("11 am")
        self.send("¿Cuánto cuesta la consulta?")
        self.assertIn("No se creó ninguna cita", self.send("Ya no quiero agendar"))
        self.assertIn("No hay una gestión pendiente", self.send("Retomemos la cita"))
        self.send("Asael Ponce Silva")
        self.send("Revisión general")
        self.assertEqual(self.provider.appointments, ())
        self.assertEqual(self.events, [])

    def test_clear_slot_answer_resumes_a_paused_selection(self) -> None:
        self.offer_slots()
        self.send("¿Cuánto cuesta una consulta a las 11?")
        self.service = self.new_service()
        self.assertEqual(self.send("agéndame a las 11 am"), APPOINTMENT_NAME_REPLY)
        self.assertTrue(self.send("Asael Ponce Silva").endswith(APPOINTMENT_REASON_REPLY))
        self.assertIn("confirmada", self.send("Revisión general"))
        self.assertEqual(len(self.provider.appointments), 1)

    def test_clear_date_answer_resumes_a_paused_date_request(self) -> None:
        self.assertIn("qué día", self.send("Quiero agendar una cita"))
        self.send("¿Dónde está el consultorio?")
        self.assertIn("Horarios disponibles", self.send("mañana"))
        self.assertEqual(self.send("11 am"), APPOINTMENT_NAME_REPLY)
        self.assertEqual(self.provider.appointments, ())

    def test_model_cannot_mutate_the_calendar_while_answering_a_side_question(self) -> None:
        self.book()
        self.request_mutation(ToolName.CANCEL_APPOINTMENT)
        self.llm.reply = ToolCall(
            name=ToolName.CANCEL_APPOINTMENT.value,
            arguments={"appointment_id": self.provider.appointments[0].id},
            call_id="call-unrequested-cancellation",
        )
        self.assertIn("pausada", self.send("¿Cuánto cuesta la consulta?"))
        self.assertEqual(self.provider.appointments[0].status, AppointmentStatus.SCHEDULED)
        self.assertEqual(self.events, [])

    def test_expired_paused_slots_are_refreshed_before_accepting_an_old_choice(self) -> None:
        self.offer_slots()
        self.send("¿Cuánto cuesta la consulta?")
        self.now += timedelta(minutes=11)
        self.provider.register_busy_period(
            calendar_id="calendar-1",
            start_at=datetime.combine(self.target_date, time(11), tzinfo=timezone.utc),
            end_at=datetime.combine(self.target_date, time(11, 30), tzinfo=timezone.utc),
        )
        refreshed = self.send("11 am")
        self.assertIn("Horarios disponibles", refreshed)
        self.assertNotIn("- 11:00 AM a 11:30 AM", refreshed)
        self.assertEqual(self.send("12 pm"), APPOINTMENT_NAME_REPLY)
        self.assertEqual(self.provider.appointments, ())

    def test_recovery_failure_keeps_the_old_confirmation_inactive(self) -> None:
        self.book()
        self.request_mutation(ToolName.CANCEL_APPOINTMENT)
        self.send("¿Cuánto cuesta la consulta?")
        self.provider.simulate_error(ToolName.LIST_APPOINTMENTS, CalendarProviderUnavailable, once=True)
        self.assertIn("no esta disponible", self.send("Retomemos la cita"))
        self.send("Sí")
        self.assertEqual(self.provider.appointments[0].status, AppointmentStatus.SCHEDULED)
        self.assertIn("Confirmas", self.send("Retomemos la cita"))
        self.assertEqual(self.events, [])

    def test_occupied_reschedule_target_is_offered_again_before_new_confirmation(self) -> None:
        self.book()
        self.request_mutation(ToolName.RESCHEDULE_APPOINTMENT)
        self.send("15:00")
        self.send("¿Cuánto cuesta la consulta?")
        self.provider.register_busy_period(
            calendar_id="calendar-1",
            start_at=datetime.combine(self.target_date, time(15), tzinfo=timezone.utc),
            end_at=datetime.combine(self.target_date, time(15, 30), tzinfo=timezone.utc),
        )
        refreshed = self.send("Retomemos la cita")
        self.assertIn("Horarios disponibles", refreshed)
        self.assertNotIn("- 3:00 PM a 3:30 PM", refreshed)
        self.assertIn("Confirmas", self.send("14:00"))
        self.assertEqual(self.provider.appointments[0].start_at.hour, 11)
        self.assertIn("modificada", self.send("Sí"))
        self.assertEqual(self.provider.appointments[0].start_at.hour, 14)

    def test_explicit_cancel_with_a_listed_hour_is_not_a_slot_selection(self) -> None:
        self.book()
        self.assertIn("11:00 AM", self.send("Quiero agendar para pasado mañana"))
        self.assertIn("Confirmas", self.request_mutation(
            ToolName.CANCEL_APPOINTMENT, text="Cancela mi cita de las 11",
        ))
        self.assertEqual(self.provider.appointments[0].status, AppointmentStatus.SCHEDULED)
        self.assertEqual(self.events, [])

    def test_unlisted_hour_keeps_the_original_availability(self) -> None:
        self.offer_slots()
        self.assertIn("horarios", self.send("agéndame a las 8 am"))
        self.assertEqual(self.send("11 am"), APPOINTMENT_NAME_REPLY)
        self.assertEqual(self.llm.call_count, 0)

    def test_occupied_reschedule_selection_explains_unavailability_and_keeps_the_change(self) -> None:
        self.offer_slots()
        self.send("9 am")
        self.send("Asael Ponce Silva")
        self.assertIn("confirmada", self.send("Revisión general"))
        self.events.clear()
        self.provider.register_busy_period(
            calendar_id="calendar-1",
            start_at=datetime.combine(self.target_date, time(10), tzinfo=timezone.utc),
            end_at=datetime.combine(self.target_date, time(10, 30), tzinfo=timezone.utc),
        )
        offered = self.request_mutation(
            ToolName.RESCHEDULE_APPOINTMENT,
            text="Quisiera modificar la cita de las 9 am",
        )
        self.assertIn("9:30 AM", offered)
        self.assertNotIn("- 10:00 AM a 10:30 AM", offered)
        calls = self.llm.call_count

        for selection in (
            "Cámbiala para las 10 am", "a las 10",
            "Quisiera cambiarla a las 10 am", "Me gustaría moverla a las 10 am",
        ):
            with self.subTest(selection=selection):
                reply = self.send(selection)
                self.assertIn("Ese horario ya está ocupado o no está disponible", reply)
                self.assertIn("Elige uno de los horarios", reply)
                self.assertNotIn("No identifiqué", reply)
                self.assertEqual(self.provider.appointments[0].start_at.hour, 9)
                self.assertEqual(self.events, [])
                self.assertEqual(self.llm.call_count, calls)

        self.assertIn("Confirmas", self.send("9:30 am"))
        self.assertEqual(self.provider.appointments[0].start_at.hour, 9)
        self.assertIn("modificada", self.send("Sí"))
        self.assertEqual(self.provider.appointments[0].start_at.hour, 9)
        self.assertEqual(self.provider.appointments[0].start_at.minute, 30)
        self.assertEqual(len(self.events), 1)

    def test_new_booking_replaces_the_paused_one(self) -> None:
        self.offer_slots()
        self.send("11 am")
        self.send("Asael Ponce Silva")
        self.send("¿Cuánto cuesta la consulta?")
        next_date = self.target_date + timedelta(days=1)
        self.llm.reply = ToolCall(
            name=ToolName.CREATE_APPOINTMENT.value,
            arguments={"start_at": datetime.combine(next_date, time(12), tzinfo=timezone.utc).isoformat()},
            call_id="call-new-booking",
        )
        self.assertEqual(self.send("Quiero agendar otra cita a las 12 para pasado mañana"), APPOINTMENT_NAME_REPLY)
        self.llm.reply = "Información del consultorio."
        self.send("Asael Ponce Silva")
        self.assertIn("confirmada", self.send("Revisión general"))
        self.send("Retomemos la cita")
        self.assertEqual(len(self.provider.appointments), 1)
        self.assertEqual(self.provider.appointments[0].start_at.date(), next_date)
        self.assertEqual(self.provider.appointments[0].start_at.hour, 12)

    def test_reschedule_without_a_valid_hour_is_not_reported_as_occupied(self) -> None:
        self.book()
        self.request_mutation(ToolName.RESCHEDULE_APPOINTMENT)

        for selection in ("a cualquier hora", "a las 10:99", "Quisiera moverla a las 10:99"):
            with self.subTest(selection=selection):
                reply = self.send(selection)
                self.assertIn("No identifiqué una hora", reply)
                self.assertNotIn("ocupado", reply)
                self.assertEqual(self.provider.appointments[0].start_at.hour, 11)
                self.assertEqual(self.events, [])
        self.assertIn("Confirmas", self.send("14:00"))

    def test_ambiguous_reschedule_period_is_not_reported_as_occupied(self) -> None:
        self.book()
        self.executor = ToolExecutor(
            provider=self.provider,
            default_timezone="UTC",
            now=lambda: self.now,
            business_hours=BusinessHours(
                timezone_name="UTC",
                windows_by_weekday={
                    day: (TimeWindow(time(9), time(23)),) for day in range(7)
                },
            ),
        )
        self.service = self.new_service()
        self.request_mutation(ToolName.RESCHEDULE_APPOINTMENT)

        for selection in ("a las 10", "Quisiera cambiarla a las 10"):
            with self.subTest(selection=selection):
                reply = self.send(selection)
                self.assertIn("Indica AM o PM", reply)
                self.assertNotIn("ocupado", reply)
                self.assertEqual(self.provider.appointments[0].start_at.hour, 11)
                self.assertEqual(self.events, [])
        self.assertIn("Confirmas", self.send("10 am"))
        self.assertEqual(self.provider.appointments[0].start_at.hour, 11)

    def test_a_tentative_slot_question_does_not_select_or_pause(self) -> None:
        self.offer_slots()
        self.assertIn("¿Quieres elegir ese horario?", self.send("¿11 am?"))
        self.assertEqual(self.send("11 am"), APPOINTMENT_NAME_REPLY)
        self.assertEqual(self.llm.call_count, 0)

    def test_past_paused_booking_keeps_name_when_a_new_day_is_needed(self) -> None:
        self.offer_slots()
        self.send("11 am")
        self.send("Asael Ponce Silva")
        self.send("¿Cuánto cuesta la consulta?")
        self.now += timedelta(days=2)
        self.assertIn("qué día", self.send("Retomemos la cita"))
        self.assertIn("Horarios disponibles", self.send("mañana"))
        self.assertEqual(self.send("11 am"), APPOINTMENT_REASON_REPLY)
        self.assertIn("confirmada", self.send("Revisión general"))
        self.assertEqual(self.provider.appointments[0].start_at.date(), (self.now + timedelta(days=1)).date())

    def test_question_about_changing_payment_does_not_replace_the_booking(self) -> None:
        self.offer_slots()
        self.send("11 am")
        self.send("Asael Ponce Silva")
        self.send("¿Puedo cambiar el método de pago?")
        self.assertIn("motivo", self.send("Retomemos la cita"))
        self.assertIn("confirmada", self.send("Revisión general"))

    def test_expired_paused_date_consumes_the_new_date(self) -> None:
        self.send("Quiero agendar una cita")
        self.send("¿Cuánto cuesta la consulta?")
        self.now += timedelta(minutes=11)
        self.assertIn("Horarios disponibles", self.send("mañana"))

    def test_short_refusal_discards_a_paused_action(self) -> None:
        self.book()
        self.request_mutation(ToolName.CANCEL_APPOINTMENT)
        self.send("¿Cuánto cuesta la consulta?")
        self.assertIn("ningún cambio", self.send("Prefiero no"))
        self.assertIn("No hay una gestión pendiente", self.send("Retomemos la cita"))
        self.send("Sí")
        self.assertEqual(self.events, [])

    def test_reschedule_fallback_failure_does_not_lose_the_paused_action(self) -> None:
        self.book()
        self.request_mutation(ToolName.RESCHEDULE_APPOINTMENT)
        self.send("15:00")
        self.send("¿Cuánto cuesta la consulta?")
        self.provider.register_busy_period(
            calendar_id="calendar-1",
            start_at=datetime.combine(self.target_date, time(15), tzinfo=timezone.utc),
            end_at=datetime.combine(self.target_date, time(15, 30), tzinfo=timezone.utc),
        )
        original_check = self.provider.check_availability

        async def failing_full_day_check(*, start_at, end_at):
            if end_at - start_at > timedelta(minutes=30):
                raise CalendarProviderUnavailable()
            return await original_check(start_at=start_at, end_at=end_at)

        self.provider.check_availability = failing_full_day_check
        self.assertIn("no esta disponible", self.send("Retomemos la cita"))
        self.provider.check_availability = original_check
        self.send("Sí")
        self.assertEqual(self.events, [])
        self.assertIn("Horarios disponibles", self.send("Retomemos la cita"))

    def test_expired_reschedule_read_failure_preserves_the_paused_selection(self) -> None:
        self.book()
        self.request_mutation(ToolName.RESCHEDULE_APPOINTMENT)
        self.send("¿Cuánto cuesta la consulta?")
        self.now += timedelta(minutes=11)
        self.provider.simulate_error(ToolName.LIST_APPOINTMENTS, CalendarProviderUnavailable, once=True)
        self.assertIn("no esta disponible", self.send("Retomemos la cita"))
        self.assertIn("Horarios disponibles", self.send("Retomemos la cita"))
        self.assertEqual(self.events, [])

    def test_naive_tool_time_uses_the_clinic_timezone_when_paused(self) -> None:
        self.executor = ToolExecutor(
            provider=self.provider, default_timezone="America/Mexico_City",
            now=lambda: self.now,
            business_hours=BusinessHours(
                timezone_name="America/Mexico_City",
                windows_by_weekday={
                    day: (TimeWindow(time(9), time(17)),) for day in range(7)
                },
            ),
        )
        self.service = ConversationService(
            self.database, llm_provider=self.llm, tool_executor=self.executor,
            timezone_name="America/Mexico_City", now=lambda: self.now,
        )
        self.llm.reply = ToolCall(
            name=ToolName.CREATE_APPOINTMENT.value,
            arguments={"start_at": f"{self.target_date}T11:00:00"},
            call_id="call-local-time",
        )
        self.assertEqual(self.send("Agéndame mañana a las 11"), APPOINTMENT_NAME_REPLY)
        self.llm.reply = "Información del consultorio."
        self.send("¿Cuánto cuesta la consulta?")
        self.assertIn("11:00 AM", self.send("Retomemos la cita"))
        self.send("Asael Ponce Silva")
        self.assertIn("confirmada", self.send("Revisión general"))
        self.assertEqual(self.provider.appointments[0].start_at.utcoffset(), timedelta(hours=-6))

    def test_malformed_tool_time_does_not_create_a_broken_pending_booking(self) -> None:
        self.llm.replies = (
            ToolCall(
                name=ToolName.CREATE_APPOINTMENT.value,
                arguments={"start_at": "fecha inválida", "reason": "Revisión general"},
                call_id="call-bad-time",
            ),
            "No pude identificar ese horario.",
        )
        self.assertEqual(self.send("Agéndame mañana a las 11"), "No pude identificar ese horario.")
        self.llm.replies = ()
        self.send("¿Cuánto cuesta la consulta?")
        self.assertIn("No hay una gestión pendiente", self.send("Retomemos la cita"))
        self.assertEqual(self.provider.appointments, ())
