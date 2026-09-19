import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from conversation_service import ConversationService, IncomingTextMessage
from llm_provider import ChatMessage, LLMProviderError
from main import app, normalize_recipient_number
from persistence import SQLiteDatabase
from whatsapp_client import GRAPH_API_VERSION, WhatsAppClient


@contextmanager
def open_database(path: str) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path)
    try:
        yield connection
    finally:
        connection.close()


class FakeWhatsAppClient:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, str]] = []

    async def send_text(self, to: str, body: str) -> dict[str, Any]:
        self.sent_messages.append((to, body))
        return {"messages": [{"id": f"wamid.reply.{len(self.sent_messages)}"}]}


class FailOnceWhatsAppClient(FakeWhatsAppClient):
    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    async def send_text(self, to: str, body: str) -> dict[str, Any]:
        self.attempts += 1
        if self.attempts == 1:
            raise httpx.ConnectError("fallo de prueba")
        return await super().send_text(to, body)


GENERATED_REPLY = "Respuesta generada por el proveedor."


class FakeLLMProvider:
    def __init__(self, reply: str = GENERATED_REPLY) -> None:
        self.reply = reply
        self.received_messages: list[list[ChatMessage]] = []

    async def generate(self, messages: list[ChatMessage]) -> str:
        self.received_messages.append(messages)
        return self.reply


class FailingLLMProvider(FakeLLMProvider):
    async def generate(self, messages: list[ChatMessage]) -> str:
        self.received_messages.append(messages)
        raise LLMProviderError("fallo de generacion de prueba")


class WebhookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_directory = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(
            self.database_directory.name,
            "chatbot.sqlite3",
        )
        self.addCleanup(self.database_directory.cleanup)

    @contextmanager
    def configured_runtime(
        self,
        whatsapp_client: FakeWhatsAppClient,
        llm_provider: FakeLLMProvider | None = None,
    ) -> Iterator[FakeLLMProvider]:
        provider = llm_provider or FakeLLMProvider()
        with patch.dict(
            os.environ,
            {
                "DATABASE_PATH": self.database_path,
                "LLM_API_KEY": "test-key",
                "LLM_MODEL": "test-model",
            },
        ):
            with patch("main.WhatsAppClient", return_value=whatsapp_client):
                with patch("main.create_llm_provider", return_value=provider):
                    yield provider

    def text_payload(
        self,
        sender: str = "5491100000000",
        message_id: str = "wamid.test",
        text: str = "Hola",
    ) -> dict[str, object]:
        return {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": sender,
                                        "id": message_id,
                                        "type": "text",
                                        "text": {"body": text},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ],
        }

    def post_messages(
        self,
        client: TestClient,
        *payloads: dict[str, object],
    ) -> list[httpx.Response]:
        responses = []
        for payload in payloads:
            responses.append(client.post("/webhook/whatsapp", json=payload))
        return responses

    def test_normalizes_mexico_recipient_number_for_sending(self) -> None:
        self.assertEqual(
            normalize_recipient_number("5217531363338"),
            "527531363338",
        )

    def test_keeps_other_country_formats_unchanged(self) -> None:
        self.assertEqual(
            normalize_recipient_number("5491100000000"),
            "5491100000000",
        )

    def test_verification_uses_whatsapp_path(self) -> None:
        with patch.dict(os.environ, {"WHATSAPP_VERIFY_TOKEN": "test-token"}):
            with TestClient(app) as client:
                response = client.get(
                    "/webhook/whatsapp",
                    params={
                        "hub.mode": "subscribe",
                        "hub.verify_token": "test-token",
                        "hub.challenge": "challenge-123",
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "challenge-123")

    def test_text_message_is_parsed_and_answered(self) -> None:
        payload = self.text_payload()
        fake_client = FakeWhatsAppClient()

        with self.configured_runtime(fake_client):
            with TestClient(app) as client:
                response = client.post("/webhook/whatsapp", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(fake_client.sent_messages, [("5491100000000", GENERATED_REPLY)])

    def test_first_message_creates_patient_conversation_and_history(self) -> None:
        fake_client = FakeWhatsAppClient()

        with self.configured_runtime(fake_client):
            with TestClient(app) as client:
                response = client.post(
                    "/webhook/whatsapp",
                    json=self.text_payload(),
                )

        self.assertEqual(response.status_code, 200)
        with open_database(self.database_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM patients").fetchone()[0], 1)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0],
                1,
            )
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 2)
            conversation_id = connection.execute(
                "SELECT id FROM conversations"
            ).fetchone()[0]
            statuses = connection.execute(
                "SELECT direction, status FROM messages ORDER BY id"
            ).fetchall()

        self.assertEqual(statuses, [("incoming", "received"), ("outgoing", "sent")])
        service = ConversationService(SQLiteDatabase(self.database_path))
        history = service.get_history(conversation_id)
        self.assertEqual([message.text for message in history], ["Hola", GENERATED_REPLY])

    def test_second_message_reuses_patient_and_conversation(self) -> None:
        fake_client = FakeWhatsAppClient()
        first_payload = self.text_payload()
        second_payload = self.text_payload(
            message_id="wamid.test.2",
            text="Quiero continuar",
        )

        with self.configured_runtime(fake_client):
            with TestClient(app) as client:
                responses = self.post_messages(
                    client,
                    first_payload,
                    second_payload,
                )

        self.assertEqual([response.status_code for response in responses], [200, 200])
        with open_database(self.database_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM patients").fetchone()[0], 1)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0],
                1,
            )
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 4)
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(DISTINCT conversation_id) FROM messages"
                ).fetchone()[0],
                1,
            )

    def test_different_numbers_create_independent_patients(self) -> None:
        fake_client = FakeWhatsAppClient()

        with self.configured_runtime(fake_client):
            with TestClient(app) as client:
                responses = self.post_messages(
                    client,
                    self.text_payload(),
                    self.text_payload(
                        sender="5491100000001",
                        message_id="wamid.test.2",
                    ),
                )

        self.assertEqual([response.status_code for response in responses], [200, 200])
        with open_database(self.database_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM patients").fetchone()[0], 2)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0],
                2,
            )

    def test_repeated_webhook_does_not_send_a_second_reply(self) -> None:
        fake_client = FakeWhatsAppClient()
        payload = self.text_payload()

        with self.configured_runtime(fake_client):
            with TestClient(app) as client:
                responses = self.post_messages(
                    client,
                    payload,
                    payload,
                )

        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(len(fake_client.sent_messages), 1)
        with open_database(self.database_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 2)

    def test_failed_reply_can_be_retried(self) -> None:
        fake_client = FailOnceWhatsAppClient()
        payload = self.text_payload()

        with self.configured_runtime(fake_client):
            with TestClient(app) as client:
                first_response = client.post("/webhook/whatsapp", json=payload)
                second_response = client.post("/webhook/whatsapp", json=payload)

        self.assertEqual(first_response.status_code, 502)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(fake_client.attempts, 2)
        with open_database(self.database_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 2)
            self.assertEqual(
                connection.execute(
                    "SELECT status FROM messages WHERE direction = 'outgoing'"
                ).fetchone()[0],
                "sent",
            )

    def test_llm_failure_is_recorded_without_sending_a_message(self) -> None:
        fake_client = FakeWhatsAppClient()
        failing_provider = FailingLLMProvider()

        with self.configured_runtime(fake_client, failing_provider):
            with TestClient(app) as client:
                response = client.post(
                    "/webhook/whatsapp",
                    json=self.text_payload(),
                )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(fake_client.sent_messages, [])
        with open_database(self.database_path) as connection:
            messages = connection.execute(
                "SELECT direction, status, text FROM messages ORDER BY id"
            ).fetchall()

        self.assertEqual(messages, [("incoming", "received", "Hola"), ("outgoing", "failed", "")])

    def test_history_survives_new_conversation_service(self) -> None:
        service = ConversationService(SQLiteDatabase(self.database_path))
        context = service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.restart",
                message_type="text",
                text="Hola",
            )
        )
        service.record_reply_sent(context, GENERATED_REPLY, "wamid.reply.restart")

        restarted_service = ConversationService(SQLiteDatabase(self.database_path))
        history = restarted_service.get_history(context.conversation_id)

        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].text, "Hola")
        self.assertEqual(history[1].text, GENERATED_REPLY)

    def test_non_text_event_is_ignored_without_cloud_api_credentials(self) -> None:
        payload = {
            "entry": [{"changes": [{"value": {"statuses": [{"status": "read"}]}}]}]
        }

        with patch.dict(os.environ, {}, clear=True):
            with TestClient(app) as client:
                response = client.post("/webhook/whatsapp", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertFalse(os.path.exists(self.database_path))


class WhatsAppClientTests(unittest.TestCase):
    def test_builds_cloud_api_text_request(self) -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"messages": [{"id": "wamid.reply"}]})

        async def run_test() -> None:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http_client:
                client = WhatsAppClient(
                    access_token="access-token",
                    phone_number_id="phone-id",
                    http_client=http_client,
                )
                result = await client.send_text("5491100000000", GENERATED_REPLY)

            self.assertEqual(result, {"messages": [{"id": "wamid.reply"}]})

        asyncio.run(run_test())

        self.assertEqual(
            str(requests[0].url),
            f"https://graph.facebook.com/{GRAPH_API_VERSION}/phone-id/messages",
        )
        self.assertEqual(requests[0].headers["Authorization"], "Bearer access-token")
        self.assertEqual(
            json.loads(requests[0].content),
            {
                "messaging_product": "whatsapp",
                "to": "5491100000000",
                "type": "text",
                "text": {"body": GENERATED_REPLY},
            },
        )
