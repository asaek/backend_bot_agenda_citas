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
        self.assertEqual(self.send("Asael Ponce Silva"), APPOINTMENT_REASON_REPLY)
        self.assertIn("confirmada", self.send("Revisión general"))
        self.assertEqual(self.llm.call_count, 0)
        self.assertEqual(len(self.provider.appointments), 1)
        appointment = self.provider.appointments[0]
        self.assertEqual(appointment.start_at.date(), self.target_date)
        self.assertEqual(appointment.start_at.hour, 11)
        self.assertEqual(appointment.reason, "Revisión general")
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

    def test_question_pauses_and_resume_survives_restart_and_short_history(self) -> None:
        self.offer_slots()
        self.assertEqual(self.send("11 am"), APPOINTMENT_NAME_REPLY)
        self.assertEqual(self.send("Asael Ponce Silva"), APPOINTMENT_REASON_REPLY)
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
        self.assertEqual(self.send("Asael Ponce Silva"), APPOINTMENT_REASON_REPLY)
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
