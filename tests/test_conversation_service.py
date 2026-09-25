import asyncio
import os
import tempfile
import unittest
from datetime import datetime, time, timezone

from calendar_domain import PatientScope
from calendar_domain import AppointmentStatus, ToolName
from conversation_service import (
    SYSTEM_PROMPT,
    ConversationService,
    IncomingTextMessage,
)
from fake_calendar_provider import FakeCalendarProvider
from fakes import FakeLLMProvider
from llm_provider import ToolCall
from notification_domain import AppointmentNotificationType
from persistence import SQLiteDatabase
from tool_executor import ToolExecutor
from tool_validation import BusinessHours, TimeWindow


class ConversationContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_directory = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(
            self.database_directory.name,
            "chatbot.sqlite3",
        )
        self.addCleanup(self.database_directory.cleanup)
        self.llm_provider = FakeLLMProvider(reply="Respuesta del LLM")
        self.service = ConversationService(
            SQLiteDatabase(self.database_path),
            llm_provider=self.llm_provider,
        )

    def test_build_reply_generates_from_the_conversation_context(self) -> None:
        first_context = self.service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.first",
                message_type="text",
                text="Necesito una cita",
            )
        )
        self.service.record_reply_sent(
            first_context,
            body="¿Qué día prefieres?",
            provider_message_id="wamid.reply.first",
        )
        current_context = self.service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.second",
                message_type="text",
                text="El viernes",
            )
        )

        reply = asyncio.run(self.service.build_reply(current_context))

        self.assertEqual(reply, "Respuesta del LLM")
        self.assertEqual(
            current_context.patient_scope,
            PatientScope(
                patient_id=current_context.patient_id,
                conversation_id=current_context.conversation_id,
                whatsapp_number="5491100000000",
            ),
        )
        received_messages = self.llm_provider.received_messages[0]
        self.assertEqual(
            [(message.role, message.content) for message in received_messages[1:]],
            [
                ("user", "Necesito una cita"),
                ("assistant", "¿Qué día prefieres?"),
                ("user", "El viernes"),
            ],
        )
        self.assertEqual(received_messages[0].role, "system")
        self.assertTrue(received_messages[0].content.startswith(SYSTEM_PROMPT))

    def test_build_chat_messages_include_the_current_calendar_date_and_range(self) -> None:
        service = ConversationService(
            self.service.database,
            llm_provider=self.llm_provider,
            timezone_name="UTC",
            now=datetime(2026, 9, 24, 5, 30, tzinfo=timezone.utc),
        )
        context = service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.today",
                message_type="text",
                text="Que citas tengo hoy?",
            )
        )

        prompt = service.build_chat_messages(context)[0].content

        self.assertIn(
            "Fecha y hora actual de la agenda: 2026-09-24T05:30:00+00:00",
            prompt,
        )
        self.assertIn(
            '"hoy" corresponde a [2026-09-24T00:00:00+00:00, '
            '2026-09-25T00:00:00+00:00).',
            prompt,
        )
        self.assertIn(
            "No pidas la fecha exacta cuando el paciente use una expresión relativa",
            prompt,
        )
        self.assertIn(
            "devuelven solo citas vigentes",
            prompt,
        )

    def test_date_only_appointment_request_returns_available_slots_before_reason(self) -> None:
        provider = FakeCalendarProvider()
        llm_provider = FakeLLMProvider(reply="El LLM no deberia responder este turno")
        service = ConversationService(
            SQLiteDatabase(self.database_path),
            llm_provider=llm_provider,
            now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
            tool_executor=ToolExecutor(
                provider=provider,
                business_hours=BusinessHours(
                    timezone_name="UTC",
                    windows_by_weekday={
                        weekday: (TimeWindow(time(9), time(17)),)
                        for weekday in range(5)
                    },
                ),
                default_timezone="UTC",
                now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
            ),
        )
        context = service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.date-only-appointment",
                message_type="text",
                text="Agendame una cita para mañana",
            )
        )

        reply = asyncio.run(service.build_reply(context))

        self.assertIn("horarios disponibles", reply.lower())
        self.assertIn("09:00", reply)
        self.assertIn("16:30", reply)
        self.assertIn("elige", reply.lower())
        self.assertNotIn("Antes de agendar tu cita", reply)
        self.assertEqual(llm_provider.call_count, 0)
        self.assertEqual(provider.appointments, ())

    def test_sacar_cita_phrase_uses_date_only_availability_before_the_llm(self) -> None:
        provider = FakeCalendarProvider()
        llm_provider = FakeLLMProvider(reply="El LLM no deberia responder este turno")
        service = ConversationService(
            SQLiteDatabase(self.database_path),
            llm_provider=llm_provider,
            now=datetime(2026, 9, 21, 8, 0, tzinfo=timezone.utc),
            tool_executor=ToolExecutor(
                provider=provider,
                business_hours=BusinessHours(
                    timezone_name="UTC",
                    windows_by_weekday={
                        weekday: (TimeWindow(time(9), time(17)),)
                        for weekday in range(5)
                    },
                ),
                default_timezone="UTC",
                now=datetime(2026, 9, 21, 8, 0, tzinfo=timezone.utc),
            ),
        )
        context = service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.sacar-cita-date-only",
                message_type="text",
                text="y para hoy quisiera sacar cita que tienes para hoy",
            )
        )

        reply = asyncio.run(service.build_reply(context))

        self.assertIn("horarios disponibles", reply.lower())
        self.assertIn("09:00", reply)
        self.assertIn("16:30", reply)
        self.assertEqual(llm_provider.call_count, 0)
        self.assertEqual(provider.appointments, ())

    def test_build_reply_converts_markdown_appointment_table_to_a_list(self) -> None:
        self.llm_provider.reply = (
            "Para manana tienes dos citas confirmadas:\n\n"
            "| ID | Hora | Motivo |\n"
            "| --- | --- | --- |\n"
            "| 2 | 11:00 - 11:30 | Revision del ojo rojo |\n"
            "| 1 | 11:30 - 12:00 | Revision de queratocono |\n"
            "| | | |\n"
        )
        context = self.service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.table",
                message_type="text",
                text="Que citas tengo manana?",
            )
        )

        reply = asyncio.run(self.service.build_reply(context))

        self.assertEqual(
            reply,
            "Para manana tienes dos citas confirmadas:\n\n"
            "- Hora: 11:00 - 11:30; Motivo: Revision del ojo rojo\n"
            "- Hora: 11:30 - 12:00; Motivo: Revision de queratocono",
        )
        self.assertNotIn("|", reply)
        self.assertNotIn("ID", reply)

    def test_build_reply_uses_the_injected_tool_executor(self) -> None:
        calendar_provider = FakeCalendarProvider()
        llm_provider = FakeLLMProvider(
            replies=(
                ToolCall(name="list_appointments", arguments={}),
                "Respuesta final despues de la herramienta",
            )
        )
        service = ConversationService(
            SQLiteDatabase(self.database_path),
            llm_provider=llm_provider,
            tool_executor=ToolExecutor(
                provider=calendar_provider,
                business_hours=BusinessHours(
                    timezone_name="UTC",
                    windows_by_weekday={
                        weekday: (TimeWindow(time(9), time(17)),)
                        for weekday in range(5)
                    },
                ),
                default_timezone="UTC",
                now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
            ),
        )
        context = service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.tool",
                message_type="text",
                text="Que citas tengo?",
            )
        )

        reply = asyncio.run(service.build_reply(context))

        self.assertEqual(reply, "Respuesta final despues de la herramienta")
        self.assertIsNotNone(service.agent_orchestrator)
        self.assertEqual(llm_provider.call_count, 2)
        self.assertEqual(
            [message.role for message in llm_provider.received_messages[1]],
            ["system", "user", "assistant", "tool"],
        )

    def test_build_reply_passes_the_incoming_message_to_appointment_events(self) -> None:
        calendar_provider = FakeCalendarProvider()
        llm_provider = FakeLLMProvider(
            replies=(
                ToolCall(
                    name="create_appointment",
                    arguments={
                        "start_at": "2026-09-21T10:00:00",
                        "reason": "Revision",
                    },
                    call_id="call-create",
                ),
            )
        )
        service = ConversationService(
            SQLiteDatabase(self.database_path),
            llm_provider=llm_provider,
            tool_executor=ToolExecutor(
                provider=calendar_provider,
                business_hours=BusinessHours(
                    timezone_name="UTC",
                    windows_by_weekday={
                        weekday: (TimeWindow(time(9), time(17)),)
                        for weekday in range(5)
                    },
                ),
                default_timezone="UTC",
                now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
            ),
        )
        context = service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.event",
                message_type="text",
                text="Necesito una cita",
            )
        )
        events = []

        reply = asyncio.run(
            service.build_reply(context, appointment_event_sink=events.append)
        )

        self.assertIn("motivo", reply.lower())
        self.assertEqual(calendar_provider.appointments, ())
        self.assertEqual(events, [])

        reason_context = service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.event.reason",
                message_type="text",
                text="Revision",
            )
        )
        reply = asyncio.run(
            service.build_reply(reason_context, appointment_event_sink=events.append)
        )

        self.assertIn("confirmada", reply)
        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0].notification_type,
            AppointmentNotificationType.SCHEDULED,
        )
        self.assertEqual(events[0].incoming_message_id, reason_context.incoming_message_id)
        self.assertEqual(events[0].tool_call_id, "call-create")
        self.assertEqual(calendar_provider.appointments[0].reason, "Revision")
        self.assertEqual(llm_provider.call_count, 1)

    def test_patient_scope_is_resolved_from_whatsapp_and_persisted_context(self) -> None:
        first_context = self.service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.first",
                message_type="text",
                text="Hola",
            )
        )
        repeated_context = self.service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.first",
                message_type="text",
                text="Texto ignorado por idempotencia",
            )
        )

        self.assertEqual(
            first_context.patient_scope,
            PatientScope(
                patient_id=first_context.patient_id,
                conversation_id=first_context.conversation_id,
                whatsapp_number="5491100000000",
            ),
        )
        self.assertEqual(repeated_context.patient_scope, first_context.patient_scope)

    def test_patient_scope_is_not_added_to_messages_sent_to_the_llm(self) -> None:
        context = self.service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.first",
                message_type="text",
                text="Hola",
            )
        )

        messages = self.service.build_chat_messages(context)

        self.assertEqual(
            [(message.role, message.content) for message in messages[1:]],
            [("user", "Hola")],
        )
        self.assertNotIn("patient_id", messages[0].content)
        self.assertNotIn("conversation_id", messages[0].content)
        self.assertNotIn(context.patient_scope.whatsapp_number, messages[0].content)

    def test_builds_system_prompt_and_chat_history_in_order(self) -> None:
        first_context = self.service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.first",
                message_type="text",
                text="Necesito una cita",
            )
        )
        self.service.record_reply_sent(
            first_context,
            body="¿Qué día prefieres?",
            provider_message_id="wamid.reply.first",
        )
        current_context = self.service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.second",
                message_type="text",
                text="El viernes",
            )
        )

        messages = self.service.build_chat_messages(current_context)

        self.assertEqual(messages[0].role, "system")
        self.assertTrue(messages[0].content.startswith(SYSTEM_PROMPT))
        self.assertIn("list_appointments", messages[0].content)
        self.assertIn(
            "Cuando muestres detalles de una cita, incluye fecha, hora y motivo, "
            "pero nunca muestres su ID interno al paciente.",
            messages[0].content,
        )
        self.assertIn("Nunca uses tablas Markdown", messages[0].content)
        self.assertIn("lista simple con guiones", messages[0].content)
        self.assertEqual(
            [(message.role, message.content) for message in messages[1:]],
            [
                ("user", "Necesito una cita"),
                ("assistant", "¿Qué día prefieres?"),
                ("user", "El viernes"),
            ],
        )

    def test_keeps_only_the_most_recent_history_messages(self) -> None:
        context = self.service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.first",
                message_type="text",
                text="Mensaje antiguo",
            )
        )
        self.service.record_reply_sent(
            context,
            body="Respuesta antigua",
            provider_message_id="wamid.reply.first",
        )
        current_context = self.service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.second",
                message_type="text",
                text="Mensaje actual",
            )
        )

        messages = self.service.build_chat_messages(
            current_context,
            max_history_messages=2,
        )

        self.assertEqual(
            [(message.role, message.content) for message in messages[1:]],
            [("assistant", "Respuesta antigua"), ("user", "Mensaje actual")],
        )

    def test_does_not_include_failed_replies_in_context(self) -> None:
        context = self.service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.first",
                message_type="text",
                text="Necesito ayuda",
            )
        )
        self.service.record_reply_failed(context, body="Respuesta no entregada")

        messages = self.service.build_chat_messages(context)

        self.assertEqual(
            [(message.role, message.content) for message in messages[1:]],
            [("user", "Necesito ayuda")],
        )

    def test_rejects_non_positive_history_limit(self) -> None:
        context = self.service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.first",
                message_type="text",
                text="Hola",
            )
        )

        with self.assertRaises(ValueError):
            self.service.build_chat_messages(context, max_history_messages=0)


class AppointmentConfirmationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.database_directory.cleanup)
        database_path = os.path.join(
            self.database_directory.name,
            "chatbot.sqlite3",
        )
        self.provider = FakeCalendarProvider()
        self.scope_sender = "5491100000000"
        self.service = ConversationService(
            SQLiteDatabase(database_path),
            llm_provider=FakeLLMProvider(),
            tool_executor=ToolExecutor(
                provider=self.provider,
                business_hours=BusinessHours(
                    timezone_name="UTC",
                    windows_by_weekday={
                        weekday: (TimeWindow(time(9), time(17)),)
                        for weekday in range(5)
                    },
                ),
                default_timezone="UTC",
                now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
            ),
        )
        self.scope = PatientScope(
            patient_id=1,
            conversation_id=1,
            whatsapp_number=self.scope_sender,
        )
        self.appointment = asyncio.run(
            self.provider.create_appointment(
                patient_scope=self.scope,
                start_at=datetime(2026, 9, 21, 11, tzinfo=timezone.utc),
                reason="Revision de cornea",
            )
        )

    def test_create_asks_for_reason_before_provider_execution(self) -> None:
        self.service.llm_provider.replies = (
            ToolCall(
                name=ToolName.CREATE_APPOINTMENT.value,
                arguments={
                    "start_at": "2026-09-21T15:00:00",
                    "reason": "Consulta general",
                },
                call_id="call-create",
            ),
            "La cita fue agendada.",
        )
        first_context = self.service.receive_message(
            IncomingTextMessage(
                sender=self.scope_sender,
                message_id="wamid.create-request",
                message_type="text",
                text="Agendame otra cita a las 15:00",
            )
        )

        first_reply = asyncio.run(self.service.build_reply(first_context))

        self.assertIn("motivo", first_reply.lower())
        self.assertEqual(self.provider.appointments, (self.appointment,))

        repeated_context = self.service.receive_message(
            IncomingTextMessage(
                sender=self.scope_sender,
                message_id="wamid.create-request",
                message_type="text",
                text="Texto ignorado por idempotencia",
            )
        )
        repeated_reply = asyncio.run(self.service.build_reply(repeated_context))

        self.assertIn("motivo", repeated_reply.lower())
        self.assertEqual(self.provider.appointments, (self.appointment,))

        reason_context = self.service.receive_message(
            IncomingTextMessage(
                sender=self.scope_sender,
                message_id="wamid.create-reason",
                message_type="text",
                text="Revision de cornea",
            )
        )

        asyncio.run(self.service.build_reply(reason_context))

        self.assertEqual(len(self.provider.appointments), 2)
        self.assertEqual(self.provider.appointments[-1].reason, "Revision de cornea")

    def test_pending_reason_survives_a_service_restart(self) -> None:
        self.service.llm_provider.replies = (
            ToolCall(
                name=ToolName.CREATE_APPOINTMENT.value,
                arguments={
                    "start_at": "2026-09-21T15:00:00",
                    "reason": "Consulta general",
                },
            ),
        )
        first_context = self.service.receive_message(
            IncomingTextMessage(
                sender=self.scope_sender,
                message_id="wamid.restart-create",
                message_type="text",
                text="Agendame otra cita a las 15:00",
            )
        )

        first_reply = asyncio.run(self.service.build_reply(first_context))

        restarted_service = ConversationService(
            self.service.database,
            llm_provider=FakeLLMProvider(),
            tool_executor=self.service.tool_executor,
        )
        reason_context = restarted_service.receive_message(
            IncomingTextMessage(
                sender=self.scope_sender,
                message_id="wamid.restart-reason",
                message_type="text",
                text="Seguimiento de queratocono",
            )
        )

        second_reply = asyncio.run(restarted_service.build_reply(reason_context))

        self.assertIn("motivo", first_reply.lower())
        self.assertIn("confirmada", second_reply)
        self.assertEqual(len(self.provider.appointments), 2)
        self.assertEqual(
            self.provider.appointments[-1].reason,
            "Seguimiento de queratocono",
        )

    def test_cancel_requires_confirmation_before_provider_and_notification(self) -> None:
        self.service.llm_provider.replies = (
            ToolCall(
                name=ToolName.CANCEL_APPOINTMENT.value,
                arguments={"appointment_id": self.appointment.id},
                call_id="call-cancel",
            ),
        )
        events = []
        first_context = self.service.receive_message(
            IncomingTextMessage(
                sender=self.scope_sender,
                message_id="wamid.cancel-request",
                message_type="text",
                text="Deseo cancelarla",
            )
        )

        first_reply = asyncio.run(
            self.service.build_reply(first_context, appointment_event_sink=events.append)
        )

        self.assertIn("confirmas", first_reply.lower())
        self.assertIn("21/09/2026", first_reply)
        self.assertIn("11:00 - 11:30", first_reply)
        self.assertIn("Revision de cornea", first_reply)
        self.assertNotIn(self.appointment.id, first_reply)
        self.assertEqual(self.provider.appointments[0].status, AppointmentStatus.SCHEDULED)
        self.assertEqual(events, [])

        confirmation_context = self.service.receive_message(
            IncomingTextMessage(
                sender=self.scope_sender,
                message_id="wamid.cancel-confirm",
                message_type="text",
                text="Si",
            )
        )

        confirmed_reply = asyncio.run(
            self.service.build_reply(
                confirmation_context,
                appointment_event_sink=events.append,
            )
        )

        self.assertIn("cancelada", confirmed_reply.lower())
        self.assertEqual(self.provider.appointments[0].status, AppointmentStatus.CANCELLED)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].tool_name, ToolName.CANCEL_APPOINTMENT)

    def test_negative_confirmation_keeps_appointment_and_clears_pending_action(self) -> None:
        self.service.llm_provider.replies = (
            ToolCall(
                name=ToolName.CANCEL_APPOINTMENT.value,
                arguments={"appointment_id": self.appointment.id},
            ),
        )
        first_context = self.service.receive_message(
            IncomingTextMessage(
                sender=self.scope_sender,
                message_id="wamid.cancel-request",
                message_type="text",
                text="Quiero cancelarla",
            )
        )
        asyncio.run(self.service.build_reply(first_context))

        rejection_context = self.service.receive_message(
            IncomingTextMessage(
                sender=self.scope_sender,
                message_id="wamid.cancel-reject",
                message_type="text",
                text="No",
            )
        )

        rejection_reply = asyncio.run(self.service.build_reply(rejection_context))

        self.assertIn("no se realizó", rejection_reply.lower())
        self.assertEqual(self.provider.appointments[0].status, AppointmentStatus.SCHEDULED)

    def test_reschedule_requires_confirmation_for_the_requested_new_time(self) -> None:
        self.service.llm_provider.replies = (
            ToolCall(
                name=ToolName.RESCHEDULE_APPOINTMENT.value,
                arguments={
                    "appointment_id": self.appointment.id,
                    "new_start_at": "2026-09-21T15:00:00",
                },
                call_id="call-reschedule",
            ),
        )
        first_context = self.service.receive_message(
            IncomingTextMessage(
                sender=self.scope_sender,
                message_id="wamid.reschedule-request",
                message_type="text",
                text="Quiero cambiarla para las 3",
            )
        )

        first_reply = asyncio.run(self.service.build_reply(first_context))

        self.assertIn("reprogramar", first_reply.lower())
        self.assertEqual(self.provider.appointments[0].start_at.hour, 11)

        confirmation_context = self.service.receive_message(
            IncomingTextMessage(
                sender=self.scope_sender,
                message_id="wamid.reschedule-confirm",
                message_type="text",
                text="Confirmo",
            )
        )
        confirmed_reply = asyncio.run(self.service.build_reply(confirmation_context))

        self.assertIn("modificada", confirmed_reply.lower())
        self.assertEqual(self.provider.appointments[0].start_at.hour, 15)
