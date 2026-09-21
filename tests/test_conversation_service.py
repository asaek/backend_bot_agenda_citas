import asyncio
import os
import tempfile
import unittest
from datetime import datetime, time, timezone

from calendar_domain import PatientScope
from conversation_service import (
    SYSTEM_PROMPT,
    ConversationService,
    IncomingTextMessage,
)
from fake_calendar_provider import FakeCalendarProvider
from fakes import FakeLLMProvider
from llm_provider import ToolCall
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
        self.assertEqual(
            [
                (message.role, message.content)
                for message in self.llm_provider.received_messages[0]
            ],
            [
                ("system", SYSTEM_PROMPT),
                ("user", "Necesito una cita"),
                ("assistant", "¿Qué día prefieres?"),
                ("user", "El viernes"),
            ],
        )

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
        self.assertNotIn(str(context.patient_scope.patient_id), messages[0].content)
        self.assertNotIn(str(context.patient_scope.conversation_id), messages[0].content)
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
        self.assertEqual(messages[0].content, SYSTEM_PROMPT)
        self.assertIn("list_appointments", messages[0].content)
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
