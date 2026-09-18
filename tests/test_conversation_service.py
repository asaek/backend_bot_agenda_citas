import os
import tempfile
import unittest

from conversation_service import (
    SYSTEM_PROMPT,
    ConversationService,
    IncomingTextMessage,
)
from persistence import SQLiteDatabase


class ConversationContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_directory = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(
            self.database_directory.name,
            "chatbot.sqlite3",
        )
        self.addCleanup(self.database_directory.cleanup)
        self.service = ConversationService(SQLiteDatabase(self.database_path))

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
