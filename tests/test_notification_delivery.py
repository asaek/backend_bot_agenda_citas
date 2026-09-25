import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timezone
from typing import Any

import httpx

from calendar_domain import Appointment, AppointmentStatus, PatientScope, ToolName
from notification_delivery import (
    DoctorNotificationConfigurationError,
    DoctorNotificationDeliveryService,
    DoctorNotificationSettings,
    create_doctor_notification_delivery,
    load_doctor_notification_settings,
)
from notification_domain import AppointmentNotificationEvent, AppointmentNotificationType
from persistence import SQLiteDatabase
from whatsapp_client import WhatsAppConfigurationError


class FakeDoctorWhatsAppClient:
    def __init__(self, failures: dict[str, Exception] | None = None) -> None:
        self.failures = failures or {}
        self.sent_messages: list[tuple[str, str]] = []

    async def send_text(self, to: str, body: str) -> dict[str, Any]:
        failure = self.failures.get(to)
        if failure is not None:
            raise failure
        self.sent_messages.append((to, body))
        return {"messages": [{"id": f"wamid.doctor.{len(self.sent_messages)}"}]}


class FailOnceDoctorWhatsAppClient(FakeDoctorWhatsAppClient):
    def __init__(self, recipient: str) -> None:
        super().__init__()
        self.recipient = recipient
        self.attempts = 0

    async def send_text(self, to: str, body: str) -> dict[str, Any]:
        self.attempts += 1
        if to == self.recipient and self.attempts == 1:
            raise httpx.ConnectError("token=secret-no-persistir")
        return await super().send_text(to, body)


class NotificationDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = SQLiteDatabase(
            os.path.join(self.directory.name, "notifications.sqlite3")
        )
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO patients (id, whatsapp_number, created_at, last_seen_at)
                VALUES (1, ?, ?, ?)
                """,
                (
                    "5491100000000",
                    "2026-09-20T12:00:00+00:00",
                    "2026-09-20T12:00:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO conversations (
                    id, patient_id, status, state, context_json, created_at, updated_at
                ) VALUES (1, 1, 'active', 'active', '{}', ?, ?)
                """,
                (
                    "2026-09-20T12:00:00+00:00",
                    "2026-09-20T12:00:00+00:00",
                ),
            )
        self.scope = PatientScope(
            patient_id=1,
            conversation_id=1,
            whatsapp_number="5491100000000",
        )
        self.event = AppointmentNotificationEvent(
            notification_type=AppointmentNotificationType.SCHEDULED,
            tool_name=ToolName.CREATE_APPOINTMENT,
            appointment=Appointment(
                id="appointment-1",
                patient_scope=self.scope,
                calendar_id="calendar-1",
                start_at=datetime(2026, 9, 21, 10, tzinfo=timezone.utc),
                end_at=datetime(2026, 9, 21, 10, 30, tzinfo=timezone.utc),
                reason="Revision",
                status=AppointmentStatus.CONFIRMED,
            ),
            patient_scope=self.scope,
            incoming_message_id=10,
            tool_call_id="call-1",
        )
        self.body = "Notificacion interna de prueba."
        self.now_value = 0

    def now(self) -> str:
        self.now_value += 1
        return f"2026-09-20T12:00:{self.now_value:02d}+00:00"

    def service(
        self,
        client: FakeDoctorWhatsAppClient,
        recipients: tuple[str, ...] = ("5491100000001",),
        enabled: bool = True,
    ) -> DoctorNotificationDeliveryService:
        return DoctorNotificationDeliveryService(
            self.database,
            client,
            DoctorNotificationSettings(
                enabled=enabled,
                recipient_numbers=recipients,
            ),
            now=self.now,
        )

    def test_loads_enabled_doctors_trimming_normalizing_and_deduplicating(self) -> None:
        settings = load_doctor_notification_settings(
            {
                "DOCTOR_NOTIFICATIONS_ENABLED": "true",
                "DOCTOR_WHATSAPP_NUMBERS": " +5491100000001, 5491100000001, 5217531363338 ",
            }
        )

        self.assertTrue(settings.enabled)
        self.assertEqual(
            settings.recipient_numbers,
            ("5491100000001", "527531363338"),
        )

    def test_disabled_configuration_does_not_require_recipients(self) -> None:
        settings = load_doctor_notification_settings(
            {
                "DOCTOR_NOTIFICATIONS_ENABLED": "false",
                "DOCTOR_WHATSAPP_NUMBERS": "not-a-number",
            }
        )

        self.assertEqual(
            settings,
            DoctorNotificationSettings(enabled=False, recipient_numbers=()),
        )

    def test_enabled_configuration_requires_valid_unique_recipients(self) -> None:
        invalid_values = ("", "5491100000001,", "not-a-number")
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(DoctorNotificationConfigurationError):
                    load_doctor_notification_settings(
                        {
                            "DOCTOR_NOTIFICATIONS_ENABLED": "1",
                            "DOCTOR_WHATSAPP_NUMBERS": value,
                        }
                    )

    def test_sends_same_body_to_each_doctor_and_persists_provider_ids(self) -> None:
        client = FakeDoctorWhatsAppClient()
        service = self.service(
            client,
            recipients=("5491100000001", "5491100000002"),
        )

        batch = asyncio.run(service.deliver(self.event, self.body))

        self.assertTrue(batch.enabled)
        self.assertEqual(
            client.sent_messages,
            [
                ("5491100000001", self.body),
                ("5491100000002", self.body),
            ],
        )
        self.assertEqual(
            [(record.recipient_number, record.status) for record in batch.deliveries],
            [("5491100000001", "sent"), ("5491100000002", "sent")],
        )
        self.assertEqual(
            [record.provider_message_id for record in batch.deliveries],
            ["wamid.doctor.1", "wamid.doctor.2"],
        )
        self.assertEqual([record.attempt_count for record in batch.deliveries], [1, 1])

    def test_failure_for_one_doctor_does_not_block_the_other(self) -> None:
        failing_recipient = "5491100000001"
        client = FakeDoctorWhatsAppClient(
            failures={
                failing_recipient: httpx.ConnectError("token=secret-no-persistir"),
            }
        )
        service = self.service(
            client,
            recipients=(failing_recipient, "5491100000002"),
        )

        batch = asyncio.run(service.deliver(self.event, self.body))

        self.assertEqual(client.sent_messages, [("5491100000002", self.body)])
        self.assertEqual(
            [record.status for record in batch.deliveries],
            ["failed", "sent"],
        )
        self.assertEqual(
            batch.deliveries[0].last_error,
            "No se pudo conectar con WhatsApp.",
        )
        self.assertNotIn("secret-no-persistir", batch.deliveries[0].last_error or "")

    def test_failed_delivery_is_retried_and_sent_delivery_is_idempotent(self) -> None:
        recipient = "5491100000001"
        client = FailOnceDoctorWhatsAppClient(recipient)
        service = self.service(client, recipients=(recipient,))

        first = asyncio.run(service.deliver(self.event, self.body))
        second = asyncio.run(service.deliver(self.event, self.body))
        third = asyncio.run(service.deliver(self.event, self.body))

        self.assertEqual(first.deliveries[0].status, "failed")
        self.assertEqual(second.deliveries[0].status, "sent")
        self.assertEqual(second.deliveries[0].attempt_count, 2)
        self.assertEqual(third.deliveries[0].status, "sent")
        self.assertEqual(third.deliveries[0].attempt_count, 2)
        self.assertEqual(client.attempts, 2)
        self.assertEqual(client.sent_messages, [(recipient, self.body)])

    def test_disabled_service_does_not_persist_or_send(self) -> None:
        client = FakeDoctorWhatsAppClient()
        service = self.service(client, enabled=False)

        batch = asyncio.run(service.deliver(self.event, self.body))

        self.assertFalse(batch.enabled)
        self.assertEqual(batch.deliveries, ())
        self.assertEqual(client.sent_messages, [])
        with self.database.transaction() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM doctor_notifications"
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_factory_uses_injected_whatsapp_client_and_environment_settings(self) -> None:
        client = FakeDoctorWhatsAppClient()
        service = create_doctor_notification_delivery(
            self.database,
            environment={
                "DOCTOR_NOTIFICATIONS_ENABLED": "true",
                "DOCTOR_WHATSAPP_NUMBERS": "5491100000001",
            },
            whatsapp_client=client,
        )

        self.assertIs(service.whatsapp_client, client)
        self.assertEqual(service.settings.recipient_numbers, ("5491100000001",))

    def test_configuration_error_is_normalized_without_credentials(self) -> None:
        client = FakeDoctorWhatsAppClient(
            failures={
                "5491100000001": WhatsAppConfigurationError(
                    "WHATSAPP_ACCESS_TOKEN=secret"
                )
            }
        )
        service = self.service(client)

        batch = asyncio.run(service.deliver(self.event, self.body))

        self.assertEqual(
            batch.deliveries[0].last_error,
            "Configuracion de WhatsApp incompleta.",
        )
        self.assertNotIn("secret", batch.deliveries[0].last_error or "")

    def test_records_composition_failure_without_sending_placeholder(self) -> None:
        client = FakeDoctorWhatsAppClient()
        service = self.service(client, recipients=("5491100000001", "5491100000002"))

        batch = service.record_failed(
            self.event,
            error="No se pudo construir la notificacion al doctor.",
        )

        self.assertEqual(client.sent_messages, [])
        self.assertEqual(
            [record.status for record in batch.deliveries],
            ["failed", "failed"],
        )
        self.assertEqual(
            [record.body for record in batch.deliveries],
            [
                "No se pudo construir la notificacion al doctor.",
                "No se pudo construir la notificacion al doctor.",
            ],
        )
