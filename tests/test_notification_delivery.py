import asyncio
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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
        self.sent_templates = []

    async def send_template(self, to, name, language_code, components):
        self.sent_templates.append((to, name, language_code, copy.deepcopy(components)))
        return {"messages": [{"id": "wamid.template"}]}

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
        return (datetime(2026, 9, 20, 12, tzinfo=timezone.utc) + timedelta(seconds=self.now_value)).isoformat()

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

    def test_incomplete_template_keeps_notification_capture_enabled(self) -> None:
        settings = load_doctor_notification_settings({
            "DOCTOR_NOTIFICATIONS_ENABLED": "true",
            "DOCTOR_WHATSAPP_NUMBERS": "+5491100000001",
            "DOCTOR_NOTIFICATION_TRANSPORT": "template",
            "DOCTOR_WHATSAPP_TEMPLATE_NAME": "",
            "DOCTOR_WHATSAPP_TEMPLATE_LANGUAGE": "",
        })

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.recipient_numbers, ("5491100000001",))
        self.assertEqual(settings.transport, "template")
        self.assertEqual(settings.template_name, "")
        self.assertEqual(settings.template_language, "")
        self.assertEqual(settings.configuration_error, "Configuración de plantilla incompleta.")

    def test_template_delivery_freezes_fields_and_components_for_retries_after_reopening(self) -> None:
        class FailOnceTemplateClient(FakeDoctorWhatsAppClient):
            async def send_template(client, to, name, language_code, components):
                result = await super().send_template(to, name, language_code, components)
                if len(client.sent_templates) == 1:
                    raise httpx.ConnectError("connection unavailable")
                return result

        fields = {
            "event_type": "Cita agendada", "status": "confirmada", "date": "2026-09-21",
            "time": "10:00-10:30", "reason": "Revision", "patient_name": "Ana Prueba",
            "patient_phone": "1100000000", "summary": "Solicita una revision general.",
            "priority_signals": "Ninguna detectada.",
        }
        mapping = [
            {"type": "header", "parameters": [{"type": "text", "text": "{event_type}: {status}"}]},
            {"type": "body", "parameters": [
                {"type": "text", "parameter_name": "cita", "text": "{date} {time}; {reason}"},
                {"type": "text", "parameter_name": "paciente", "text": "{patient_name}: {patient_phone}"},
                {"type": "text", "parameter_name": "resumen", "text": "{summary} {priority_signals}"},
            ]},
        ]
        settings = load_doctor_notification_settings({
            "DOCTOR_NOTIFICATIONS_ENABLED": "true", "DOCTOR_WHATSAPP_NUMBERS": "5491100000001",
            "DOCTOR_NOTIFICATION_TRANSPORT": "template", "DOCTOR_WHATSAPP_TEMPLATE_NAME": "fixture_cita",
            "DOCTOR_WHATSAPP_TEMPLATE_LANGUAGE": "es_MX",
            "DOCTOR_WHATSAPP_TEMPLATE_COMPONENTS": json.dumps(mapping),
        })
        client = FailOnceTemplateClient()
        service = DoctorNotificationDeliveryService(self.database, client, settings, now=self.now)
        first = asyncio.run(service.deliver(self.event, self.body, template_data=fields))
        self.assertEqual(first.deliveries[0].status, "failed")
        self.now_value += 60

        reopened = SQLiteDatabase(self.database.path)
        changed = load_doctor_notification_settings({
            "DOCTOR_NOTIFICATIONS_ENABLED": "true", "DOCTOR_WHATSAPP_NUMBERS": "5491100000001",
            "DOCTOR_NOTIFICATION_TRANSPORT": "template", "DOCTOR_WHATSAPP_TEMPLATE_NAME": "otra_fixture",
            "DOCTOR_WHATSAPP_TEMPLATE_LANGUAGE": "en_US",
            "DOCTOR_WHATSAPP_TEMPLATE_COMPONENTS": json.dumps(mapping),
        })
        service = DoctorNotificationDeliveryService(reopened, client, changed, now=self.now)
        second = asyncio.run(service.deliver(self.event, "Otro cuerpo", template_data={"summary": "Otro resumen"}))
        asyncio.run(service.deliver(self.event, "Otro intento"))
        self.assertEqual(second.deliveries[0].status, "sent")
        self.assertEqual(second.deliveries[0].attempt_count, 2)
        self.assertEqual(client.sent_messages, [])
        self.assertEqual(len(client.sent_templates), 2)
        self.assertEqual(client.sent_templates[0], client.sent_templates[1])
        self.assertEqual(client.sent_templates[1], ("5491100000001", "fixture_cita", "es_MX", [
            {"type": "header", "parameters": [{"type": "text", "text": "Cita agendada: confirmada"}]},
            {"type": "body", "parameters": [
                {"type": "text", "parameter_name": "cita", "text": "2026-09-21 10:00-10:30; Revision"},
                {"type": "text", "parameter_name": "paciente", "text": "Ana Prueba: 1100000000"},
                {"type": "text", "parameter_name": "resumen", "text": "Solicita una revision general. Ninguna detectada."},
            ]},
        ]))

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

    def test_template_gate_retains_notices_for_each_doctor_without_text_fallback(self) -> None:
        cases = (
            ({}, "Configuración de plantilla incompleta."),
            ({"DOCTOR_WHATSAPP_TEMPLATE_NAME": "cita"}, "Configuración de plantilla incompleta."),
            ({"DOCTOR_WHATSAPP_TEMPLATE_LANGUAGE": "es_MX"}, "Configuración de plantilla incompleta."),
            ({"DOCTOR_WHATSAPP_TEMPLATE_NAME": "Nombre Invalido", "DOCTOR_WHATSAPP_TEMPLATE_LANGUAGE": "es_MX"}, "Nombre de plantilla no válido."),
            ({"DOCTOR_WHATSAPP_TEMPLATE_NAME": "cita", "DOCTOR_WHATSAPP_TEMPLATE_LANGUAGE": "spanish"}, "Idioma de plantilla no válido."),
            ({"DOCTOR_NOTIFICATION_TRANSPORT": "unsupported"}, "Transporte de notificaciones no válido."),
            ({"DOCTOR_WHATSAPP_TEMPLATE_NAME": " cita ", "DOCTOR_WHATSAPP_TEMPLATE_LANGUAGE": " es_MX "}, "Mapeo de plantilla pendiente."),
        )
        client = FakeDoctorWhatsAppClient()
        for changes, reason in cases:
            with self.subTest(changes=changes):
                settings = load_doctor_notification_settings({
                    "DOCTOR_NOTIFICATIONS_ENABLED": "true",
                    "DOCTOR_WHATSAPP_NUMBERS": "5491100000001,5491100000002",
                    "DOCTOR_NOTIFICATION_TRANSPORT": "template",
                    **changes,
                })
                service = DoctorNotificationDeliveryService(self.database, client, settings, now=self.now)
                batch = asyncio.run(service.deliver(self.event, self.body))
                self.assertTrue(batch.enabled)
                self.assertEqual([r.recipient_number for r in batch.deliveries], ["5491100000001", "5491100000002"])
                self.assertEqual([r.status for r in batch.deliveries], ["pending", "pending"])
                self.assertEqual([r.last_error for r in batch.deliveries], [reason, reason])
                self.assertEqual([r.attempt_count for r in batch.deliveries], [0, 0])
                self.assertTrue(all(r.body == self.body and r.provider_message_id is None for r in batch.deliveries))
        self.assertEqual(client.sent_messages, [])

    def test_template_with_unavailable_fields_is_pending_without_a_dispatch_attempt(self) -> None:
        client = FakeDoctorWhatsAppClient()
        mapping = [{"type": "body", "parameters": [{"type": "text", "text":
            "{event_type} {status} {date} {time} {reason} {patient_name} {patient_phone} {summary} {priority_signals}"}]}]
        settings = DoctorNotificationSettings(True, ("5491100000001",), "template", "fixture_cita", "es_MX", json.dumps(mapping))
        batch = asyncio.run(DoctorNotificationDeliveryService(self.database, client, settings).deliver(self.event, self.body))
        self.assertEqual(batch.deliveries[0].status, "pending")
        self.assertEqual(batch.deliveries[0].last_error, "Datos de plantilla no disponibles para este aviso.")
        self.assertEqual(batch.deliveries[0].attempt_count, 0)
        self.assertEqual(client.sent_templates, [])
        self.assertEqual(client.sent_messages, [])

    def test_template_response_lost_does_not_resend_after_reopening(self) -> None:
        class LostResponseClient(FakeDoctorWhatsAppClient):
            async def send_template(client, to, name, language_code, components):
                await super().send_template(to, name, language_code, components)
                raise httpx.ReadTimeout("response lost")
        client = LostResponseClient()
        mapping = json.dumps([{"type": "body", "parameters": [{"type": "text", "text": "{notification_body}"}]}])
        settings = DoctorNotificationSettings(True, ("5491100000001",), "template", "fixture_cita", "es_MX", mapping)
        service = DoctorNotificationDeliveryService(self.database, client, settings)
        first = asyncio.run(service.deliver(self.event, self.body))
        reopened = DoctorNotificationDeliveryService(SQLiteDatabase(self.database.path), client, settings)
        second = asyncio.run(reopened.deliver(self.event, "No reemplazar"))
        self.assertEqual(first.deliveries[0].status, "sending")
        self.assertEqual(second.deliveries[0].status, "sending")
        self.assertEqual(second.deliveries[0].attempt_count, 1)
        self.assertEqual(len(client.sent_templates), 1)

    def test_template_acceptance_without_message_id_is_uncertain_and_not_resent(self) -> None:
        class MissingIdClient(FakeDoctorWhatsAppClient):
            async def send_template(client, to, name, language_code, components):
                await super().send_template(to, name, language_code, components)
                return {}
        client = MissingIdClient()
        mapping = json.dumps([{"type": "body", "parameters": [{"type": "text", "text": "{notification_body}"}]}])
        settings = DoctorNotificationSettings(True, ("5491100000001",), "template", "fixture_cita", "es_MX", mapping)
        service = DoctorNotificationDeliveryService(self.database, client, settings)
        first = asyncio.run(service.deliver(self.event, self.body))
        second = asyncio.run(service.deliver(self.event, self.body))
        self.assertEqual(first.deliveries[0].status, "sending")
        self.assertEqual(second.deliveries[0].attempt_count, 1)
        self.assertEqual(len(client.sent_templates), 1)

    def test_configuration_hold_preserves_sent_and_uncertain_deliveries(self) -> None:
        client = FakeDoctorWhatsAppClient(failures={"5491100000002": httpx.ReadTimeout("response lost")})
        service = self.service(client, recipients=("5491100000001", "5491100000002"))
        original = asyncio.run(service.deliver(self.event, self.body))
        blocked = DoctorNotificationDeliveryService(self.database, client, DoctorNotificationSettings(
            enabled=True, recipient_numbers=("5491100000001", "5491100000002"), transport="template",
        ), now=self.now)

        held = asyncio.run(blocked.deliver(self.event, "Otro cuerpo que no debe reemplazar al original."))

        self.assertEqual(held.deliveries, original.deliveries)
        self.assertEqual([r.status for r in held.deliveries], ["sent", "sending"])
        self.assertEqual(client.sent_messages, [("5491100000001", self.body)])

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
        self.now_value += 60
        second = asyncio.run(service.deliver(self.event, self.body))
        third = asyncio.run(service.deliver(self.event, self.body))

        self.assertEqual(first.deliveries[0].status, "failed")
        self.assertEqual(second.deliveries[0].status, "sent")
        self.assertEqual(second.deliveries[0].attempt_count, 2)
        self.assertEqual(third.deliveries[0].status, "sent")
        self.assertEqual(third.deliveries[0].attempt_count, 2)
        self.assertEqual(client.attempts, 2)
        self.assertEqual(client.sent_messages, [(recipient, self.body)])

    def test_concurrent_delivery_freezes_one_body_for_all_doctors_without_duplicate_sends(self) -> None:
        async def scenario():
            entered, release = asyncio.Event(), asyncio.Event()

            class SlowClient(FakeDoctorWhatsAppClient):
                attempts = 0

                async def send_text(client, to, body):
                    client.attempts += 1
                    if client.attempts == 1:
                        entered.set()
                        await release.wait()
                    return await super().send_text(to, body)

            client = SlowClient()
            service = self.service(client, recipients=("5491100000001", "5491100000002"))
            first = asyncio.create_task(service.deliver(self.event, self.body))
            await asyncio.wait_for(entered.wait(), 1)
            try:
                await asyncio.wait_for(service.deliver(self.event, "Otro resumen concurrente."), 1)
            finally:
                release.set()
                await first
            self.assertEqual(sorted(client.sent_messages), [
                ("5491100000001", self.body), ("5491100000002", self.body),
            ])

        asyncio.run(scenario())

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
