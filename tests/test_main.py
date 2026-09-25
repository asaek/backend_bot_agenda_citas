import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, time, timezone
from typing import Any
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from conversation_service import (
    CONTROLLED_FALLBACK_REPLY,
    ConversationService,
    IncomingTextMessage,
)
from fake_calendar_provider import FakeCalendarProvider
from fakes import GENERATED_REPLY, FakeLLMProvider
from llm_provider import LLMProviderError, ToolCall
from main import (
    app,
    create_availability_provider,
    create_business_hours,
    create_calendar_provider,
    create_conversation_service,
    create_tool_executor,
    normalize_recipient_number,
)
from persistence import SQLiteDatabase
from persistent_calendar_provider import PersistentCalendarProvider
from tool_executor import ToolExecutor
from tool_validation import BusinessHours, TimeWindow
from whatsapp_client import (
    GRAPH_API_VERSION,
    WhatsAppClient,
    WhatsAppConfigurationError,
)


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


class MissingWhatsAppConfigurationClient(FakeWhatsAppClient):
    async def send_text(self, to: str, body: str) -> dict[str, Any]:
        raise WhatsAppConfigurationError("configuracion de prueba ausente")


class FailingRecipientWhatsAppClient(FakeWhatsAppClient):
    def __init__(self, failing_recipients: set[str]) -> None:
        super().__init__()
        self.failing_recipients = failing_recipients

    async def send_text(self, to: str, body: str) -> dict[str, Any]:
        if to in self.failing_recipients:
            raise httpx.ConnectError("fallo de doctor de prueba")
        return await super().send_text(to, body)


class WebhookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_directory = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(
            self.database_directory.name,
            "chatbot.sqlite3",
        )
        self.addCleanup(self.database_directory.cleanup)
        self.reset_calendar_runtime()
        self.addCleanup(self.reset_calendar_runtime)

    def reset_calendar_runtime(self) -> None:
        environment = {
            "CALENDAR_PROVIDER": "fake",
            "CALENDAR_AVAILABILITY_PROVIDER": "fake",
            "GOOGLE_CALENDAR_TIMEZONE": "UTC",
        }
        provider = create_calendar_provider(environment)
        app.state.calendar_provider = provider
        app.state.availability_provider = provider
        app.state.tool_executor = create_tool_executor(provider, environment)

    def set_fixed_calendar_runtime(self) -> None:
        provider = FakeCalendarProvider()
        business_hours = BusinessHours(
            timezone_name="UTC",
            windows_by_weekday={
                weekday: (TimeWindow(time(9), time(17)),)
                for weekday in range(5)
            },
        )
        app.state.calendar_provider = provider
        app.state.availability_provider = provider
        app.state.tool_executor = ToolExecutor(
            provider=provider,
            business_hours=business_hours,
            default_timezone="UTC",
            now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
        )

    def test_google_calendar_provider_requires_explicit_runtime_selection(self) -> None:
        expected_provider = object()
        environment = {
            "CALENDAR_PROVIDER": "google",
            "DATABASE_PATH": self.database_path,
        }
        with patch(
            "main.create_google_calendar_provider_from_environment",
            return_value=expected_provider,
        ) as factory:
            provider = create_calendar_provider(environment)

        self.assertIsInstance(provider, PersistentCalendarProvider)
        self.assertIs(provider.provider, expected_provider)
        factory.assert_called_once_with(environment)

    def test_availability_provider_can_use_google_independently(self) -> None:
        primary_provider = FakeCalendarProvider()
        expected_provider = object()
        environment = {"CALENDAR_AVAILABILITY_PROVIDER": "google"}

        with patch(
            "main.create_google_calendar_provider_from_environment",
            return_value=expected_provider,
        ) as factory:
            availability_provider = create_availability_provider(
                primary_provider,
                environment,
            )

        self.assertIs(availability_provider, expected_provider)
        self.assertIsNot(availability_provider, primary_provider)
        factory.assert_called_once_with(environment)

    def test_business_hours_are_configurable_from_environment(self) -> None:
        business_hours = create_business_hours(
            {
                "GOOGLE_CALENDAR_TIMEZONE": "UTC",
                "BUSINESS_WORKDAYS": "1,3,5",
                "BUSINESS_HOURS_START": "08:30",
                "BUSINESS_HOURS_END": "16:15",
            }
        )

        self.assertEqual(
            set(business_hours.windows_by_weekday),
            {1, 3, 5},
        )
        self.assertEqual(
            business_hours.windows_by_weekday[1][0],
            TimeWindow(time(8, 30), time(16, 15)),
        )

    def test_conversation_service_uses_calendar_timezone_for_relative_dates(self) -> None:
        business_hours = BusinessHours(
            timezone_name="America/Mexico_City",
            windows_by_weekday={
                weekday: (TimeWindow(time(9), time(17)),)
                for weekday in range(5)
            },
        )
        executor = ToolExecutor(
            provider=FakeCalendarProvider(),
            business_hours=business_hours,
            default_timezone="America/Mexico_City",
            now=datetime(2026, 9, 24, 5, 30, tzinfo=timezone.utc),
        )

        with patch.dict(
            os.environ,
            {
                "DATABASE_PATH": self.database_path,
                "LLM_API_KEY": "test-key",
                "LLM_MODEL": "test-model",
            },
        ):
            with patch("main.create_llm_provider", return_value=FakeLLMProvider()):
                service = create_conversation_service(executor)

        context = service.receive_message(
            IncomingTextMessage(
                sender="5491100000000",
                message_id="wamid.relative-date",
                message_type="text",
                text="Que citas tengo hoy?",
            )
        )
        prompt = service.build_chat_messages(context)[0].content

        self.assertIn("Zona horaria de la agenda: America/Mexico_City", prompt)
        self.assertIn(
            '"hoy" corresponde a [2026-09-23T00:00:00-06:00, '
            '2026-09-24T00:00:00-06:00).',
            prompt,
        )

    @contextmanager
    def configured_runtime(
        self,
        whatsapp_client: FakeWhatsAppClient,
        llm_provider: FakeLLMProvider | None = None,
        environment: dict[str, str] | None = None,
    ) -> Iterator[FakeLLMProvider]:
        provider = llm_provider or FakeLLMProvider()
        runtime_environment = {
            "DATABASE_PATH": self.database_path,
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        }
        if environment is not None:
            runtime_environment.update(environment)
        with patch.dict(
            os.environ,
            runtime_environment,
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

        with self.configured_runtime(fake_client) as provider:
            with TestClient(app) as client:
                response = client.post("/webhook/whatsapp", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(fake_client.sent_messages, [("5491100000000", GENERATED_REPLY)])
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(provider.received_messages[0][-1].role, "user")
        self.assertEqual(provider.received_messages[0][-1].content, "Hola")

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

        with self.configured_runtime(fake_client) as provider:
            with TestClient(app) as client:
                responses = self.post_messages(
                    client,
                    payload,
                    payload,
                )

        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(len(fake_client.sent_messages), 1)
        self.assertEqual(provider.call_count, 1)
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

    def test_whatsapp_configuration_failure_records_controlled_reply_as_failed(self) -> None:
        fake_client = MissingWhatsAppConfigurationClient()

        with self.configured_runtime(fake_client):
            with TestClient(app) as client:
                response = client.post(
                    "/webhook/whatsapp",
                    json=self.text_payload(),
                )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(fake_client.sent_messages, [])
        with open_database(self.database_path) as connection:
            status_and_text = connection.execute(
                "SELECT status, text FROM messages WHERE direction = 'outgoing'"
            ).fetchone()

        self.assertEqual(status_and_text, ("failed", GENERATED_REPLY))

    def test_llm_failure_sends_controlled_fallback_and_records_failure(self) -> None:
        fake_client = FakeWhatsAppClient()
        failing_provider = FakeLLMProvider(
            error=LLMProviderError("fallo de generacion de prueba")
        )

        with self.configured_runtime(fake_client, failing_provider):
            with TestClient(app) as client:
                response = client.post(
                    "/webhook/whatsapp",
                    json=self.text_payload(),
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            fake_client.sent_messages,
            [("5491100000000", CONTROLLED_FALLBACK_REPLY)],
        )
        self.assertEqual(failing_provider.call_count, 1)
        with open_database(self.database_path) as connection:
            messages = connection.execute(
                "SELECT direction, status, text FROM messages ORDER BY id"
            ).fetchall()
            failures = connection.execute(
                "SELECT error_type FROM llm_failures"
            ).fetchall()

        self.assertEqual(
            messages,
            [
                ("incoming", "received", "Hola"),
                ("outgoing", "sent", CONTROLLED_FALLBACK_REPLY),
            ],
        )
        self.assertEqual(failures, [("LLMProviderError",)])

    def test_default_fake_calendar_provider_executes_tool_cycle(self) -> None:
        fake_client = FakeWhatsAppClient()
        tool_provider = FakeLLMProvider(
            replies=(
                ToolCall(
                    name="list_appointments",
                    arguments={},
                ),
                GENERATED_REPLY,
            )
        )

        with self.configured_runtime(fake_client, tool_provider):
            with TestClient(app) as client:
                response = client.post(
                    "/webhook/whatsapp",
                    json=self.text_payload(),
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake_client.sent_messages, [("5491100000000", GENERATED_REPLY)])
        self.assertEqual(tool_provider.call_count, 2)
        self.assertIsInstance(app.state.calendar_provider, FakeCalendarProvider)
        self.assertIs(app.state.tool_executor.provider, app.state.calendar_provider)
        self.assertEqual(
            app.state.tool_executor.business_hours.timezone_name,
            "UTC",
        )
        self.assertEqual(
            app.state.tool_executor.business_hours.windows_by_weekday[0],
            (TimeWindow(time(9), time(17)),),
        )

    def test_configured_tool_executor_completes_the_whatsapp_tool_cycle(self) -> None:
        fake_client = FakeWhatsAppClient()
        tool_provider = FakeLLMProvider(
            replies=(
                ToolCall(
                    name="check_availability",
                    arguments={
                        "start_at": "2026-09-21T10:00:00",
                        "end_at": "2026-09-21T17:00:00",
                    },
                ),
                GENERATED_REPLY,
            )
        )
        calendar_provider = FakeCalendarProvider()
        executor = ToolExecutor(
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
        )
        app.state.tool_executor = executor
        app.state.calendar_provider = calendar_provider
        try:
            with self.configured_runtime(fake_client, tool_provider):
                with TestClient(app) as client:
                    response = client.post(
                        "/webhook/whatsapp",
                        json=self.text_payload(),
                    )
        finally:
            self.reset_calendar_runtime()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake_client.sent_messages, [("5491100000000", GENERATED_REPLY)])
        self.assertEqual(tool_provider.call_count, 2)
        self.assertEqual(
            [message.role for message in tool_provider.received_messages[1]],
            ["system", "user", "assistant", "tool"],
        )

    def test_webhook_completes_the_three_doctor_notification_flows(self) -> None:
        self.set_fixed_calendar_runtime()
        fake_client = FakeWhatsAppClient()
        tool_provider = FakeLLMProvider(
            replies=(
                ToolCall(
                    name="create_appointment",
                    arguments={
                        "start_at": "2026-09-21T10:00:00",
                        "reason": "Revision",
                    },
                    call_id="call-create",
                ),
                '{"summary":"El paciente solicito una cita.","priority_signals":[]}',
                ToolCall(
                    name="reschedule_appointment",
                    arguments={
                        "appointment_id": "appointment-1",
                        "new_start_at": "2026-09-21T11:00:00",
                    },
                    call_id="call-reschedule",
                ),
                '{"summary":"El paciente confirmo un nuevo horario.","priority_signals":[]}',
                ToolCall(
                    name="cancel_appointment",
                    arguments={"appointment_id": "appointment-1"},
                    call_id="call-cancel",
                ),
                '{"summary":"El paciente solicito cancelar la cita.","priority_signals":[]}',
            )
        )
        environment = {
            "DOCTOR_NOTIFICATIONS_ENABLED": "true",
            "DOCTOR_WHATSAPP_NUMBERS": "5491100000001",
        }

        with self.configured_runtime(fake_client, tool_provider, environment):
            with TestClient(app) as client:
                responses = self.post_messages(
                    client,
                    self.text_payload(message_id="wamid.create", text="Agendar"),
                    self.text_payload(
                        message_id="wamid.create-reason",
                        text="Revision",
                    ),
                    self.text_payload(message_id="wamid.reschedule", text="Cambiar"),
                    self.text_payload(
                        message_id="wamid.reschedule-confirm",
                        text="Si",
                    ),
                    self.text_payload(message_id="wamid.cancel", text="Cancelar"),
                    self.text_payload(
                        message_id="wamid.cancel-confirm",
                        text="Si",
                    ),
                )

        self.assertEqual(
            [response.status_code for response in responses],
            [200, 200, 200, 200, 200, 200],
        )
        self.assertEqual(
            [recipient for recipient, _ in fake_client.sent_messages],
            [
                "5491100000000",
                "5491100000000",
                "5491100000001",
                "5491100000000",
                "5491100000000",
                "5491100000001",
                "5491100000000",
                "5491100000000",
                "5491100000001",
            ],
        )
        doctor_bodies = [body for recipient, body in fake_client.sent_messages if recipient == "5491100000001"]
        self.assertIn("Tipo de evento: Cita agendada", doctor_bodies[0])
        self.assertIn("Tipo de evento: Cita modificada", doctor_bodies[1])
        self.assertIn("Hora: 11:00-11:30", doctor_bodies[1])
        self.assertIn("Tipo de evento: Cita cancelada", doctor_bodies[2])
        self.assertIn("confirmas", fake_client.sent_messages[3][1].lower())
        self.assertIn("confirmas", fake_client.sent_messages[6][1].lower())
        self.assertIn("Fecha: 21/09/2026", fake_client.sent_messages[6][1])
        self.assertIn("Hora: 11:00 - 11:30", fake_client.sent_messages[6][1])
        self.assertIn("Motivo: Revision", fake_client.sent_messages[6][1])
        self.assertNotIn("appointment-1", fake_client.sent_messages[6][1])
        with open_database(self.database_path) as connection:
            notification_rows = connection.execute(
                """
                SELECT notification_type, status, attempt_count
                FROM doctor_notifications
                ORDER BY id
                """
            ).fetchall()

        self.assertEqual(
            notification_rows,
            [
                ("appointment_scheduled", "sent", 1),
                ("appointment_modified", "sent", 1),
                ("appointment_cancelled", "sent", 1),
            ],
        )

    def test_doctor_failure_does_not_change_successful_patient_reply(self) -> None:
        self.set_fixed_calendar_runtime()
        fake_client = FailingRecipientWhatsAppClient({"5491100000001"})
        tool_provider = FakeLLMProvider(
            replies=(
                ToolCall(
                    name="create_appointment",
                    arguments={
                        "start_at": "2026-09-21T10:00:00",
                        "reason": "Revision",
                    },
                    call_id="call-create",
                ),
                '{"summary":"Solicitud de cita.","priority_signals":[]}',
            )
        )

        with self.configured_runtime(
            fake_client,
            tool_provider,
            {
                "DOCTOR_NOTIFICATIONS_ENABLED": "true",
                "DOCTOR_WHATSAPP_NUMBERS": "5491100000001,5491100000002",
            },
        ):
            with TestClient(app) as client:
                response = client.post(
                    "/webhook/whatsapp",
                    json=self.text_payload(message_id="wamid.doctor-failure"),
                )
                reason_response = client.post(
                    "/webhook/whatsapp",
                    json=self.text_payload(
                        message_id="wamid.doctor-failure-reason",
                        text="Revision",
                    ),
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(reason_response.status_code, 200)
        self.assertEqual(
            [recipient for recipient, _ in fake_client.sent_messages],
            ["5491100000000", "5491100000000", "5491100000002"],
        )
        with open_database(self.database_path) as connection:
            patient_reply = connection.execute(
                """
                SELECT status, text
                FROM messages
                WHERE direction = 'outgoing'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            notification_rows = connection.execute(
                """
                SELECT recipient_number, status, last_error
                FROM doctor_notifications
                ORDER BY id
                """
            ).fetchall()

        self.assertEqual(patient_reply[0], "sent")
        self.assertIn("confirmada", patient_reply[1])
        self.assertEqual(notification_rows[0][0:2], ("5491100000001", "failed"))
        self.assertEqual(notification_rows[0][2], "No se pudo conectar con WhatsApp.")
        self.assertEqual(notification_rows[1][0:2], ("5491100000002", "sent"))

    def test_summary_failure_is_recorded_without_affecting_patient_reply(self) -> None:
        self.set_fixed_calendar_runtime()
        fake_client = FakeWhatsAppClient()
        tool_provider = FakeLLMProvider(
            replies=(
                ToolCall(
                    name="create_appointment",
                    arguments={
                        "start_at": "2026-09-21T10:00:00",
                        "reason": "Revision",
                    },
                    call_id="call-create",
                ),
                ToolCall(name="create_appointment", arguments={}),
            )
        )

        with self.configured_runtime(
            fake_client,
            tool_provider,
            {
                "DOCTOR_NOTIFICATIONS_ENABLED": "true",
                "DOCTOR_WHATSAPP_NUMBERS": "5491100000001",
            },
        ):
            with TestClient(app) as client:
                response = client.post(
                    "/webhook/whatsapp",
                    json=self.text_payload(message_id="wamid.summary-failure"),
                )
                reason_response = client.post(
                    "/webhook/whatsapp",
                    json=self.text_payload(
                        message_id="wamid.summary-failure-reason",
                        text="Revision",
                    ),
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(reason_response.status_code, 200)
        self.assertEqual(
            [recipient for recipient, _ in fake_client.sent_messages],
            ["5491100000000", "5491100000000"],
        )
        with open_database(self.database_path) as connection:
            patient_reply = connection.execute(
                "SELECT status FROM messages WHERE direction = 'outgoing'"
            ).fetchone()
            notification = connection.execute(
                "SELECT status, last_error FROM doctor_notifications"
            ).fetchone()

        self.assertEqual(patient_reply, ("sent",))
        self.assertEqual(
            notification,
            ("failed", "No se pudo construir la notificacion al doctor."),
        )

    def test_duplicate_webhook_does_not_send_duplicate_doctor_notification(self) -> None:
        self.set_fixed_calendar_runtime()
        fake_client = FakeWhatsAppClient()
        tool_provider = FakeLLMProvider(
            replies=(
                ToolCall(
                    name="create_appointment",
                    arguments={
                        "start_at": "2026-09-21T10:00:00",
                        "reason": "Revision",
                    },
                    call_id="call-create",
                ),
                '{"summary":"Solicitud de cita.","priority_signals":[]}',
            )
        )
        payload = self.text_payload(message_id="wamid.duplicate")
        reason_payload = self.text_payload(
            message_id="wamid.duplicate-reason",
            text="Revision",
        )

        with self.configured_runtime(
            fake_client,
            tool_provider,
            {
                "DOCTOR_NOTIFICATIONS_ENABLED": "true",
                "DOCTOR_WHATSAPP_NUMBERS": "5491100000001",
            },
        ):
            with TestClient(app) as client:
                responses = self.post_messages(client, payload, payload)
                responses.extend(self.post_messages(client, reason_payload))

        self.assertEqual([response.status_code for response in responses], [200, 200, 200])
        self.assertEqual(
            [recipient for recipient, _ in fake_client.sent_messages],
            ["5491100000000", "5491100000000", "5491100000001"],
        )
        self.assertEqual(tool_provider.call_count, 2)
        with open_database(self.database_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM doctor_notifications"
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_missing_api_key_sends_controlled_fallback_and_records_failure(self) -> None:
        fake_client = FakeWhatsAppClient()

        with patch.dict(
            os.environ,
            {"DATABASE_PATH": self.database_path},
            clear=True,
        ):
            with patch("main.WhatsAppClient", return_value=fake_client):
                with TestClient(app) as client:
                    response = client.post(
                        "/webhook/whatsapp",
                        json=self.text_payload(),
                    )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            fake_client.sent_messages,
            [("5491100000000", CONTROLLED_FALLBACK_REPLY)],
        )
        with open_database(self.database_path) as connection:
            failure_type = connection.execute(
                "SELECT error_type FROM llm_failures"
            ).fetchone()[0]

        self.assertEqual(failure_type, "LLMConfigurationError")

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
