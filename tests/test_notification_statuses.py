import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from notification_delivery import DoctorNotificationDeliveryService, DoctorNotificationSettings
from repositories import DoctorNotificationRepository
from test_notification_retry import Clock
from voice_repository import VoiceRepository
import test_notification_delivery as delivery_fixtures


def status_payload(message_id, status, timestamp=1792670400, recipient="5491100000001", codes=()):
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": "fixture-phone-id"},
        "statuses": [{"id": message_id, "recipient_id": recipient, "status": status,
                      "timestamp": str(timestamp), "errors": [{"code": code} for code in codes]}],
    }}]}]}


class NotificationStatusTests(unittest.TestCase):
    def setUp(self):
        delivery_fixtures.NotificationDeliveryTests.setUp(self)
        self.clock = Clock()
        self.client = delivery_fixtures.FakeDoctorWhatsAppClient()
        self.settings = DoctorNotificationSettings(True, ("5491100000001",))
        self.delivery = DoctorNotificationDeliveryService(self.database, self.client, self.settings, now=self.clock.now)

    def current(self, notification_id):
        with self.database.transaction() as db:
            return DoctorNotificationRepository().get_by_id(db, notification_id)

    def status_service(self, **targets):
        from notification_statuses import MetaDeliveryStatusService
        return MetaDeliveryStatusService(self.database.path, {"chat": self.database.path, **targets}, now=self.clock.now)

    def test_api_acceptance_is_not_meta_sent_or_delivered(self):
        accepted = asyncio.run(self.delivery.deliver(self.event, self.body)).deliveries[0]
        self.assertEqual(accepted.delivery_status, "accepted")
        self.assertEqual(accepted.api_accepted_at, self.clock.now())
        self.assertIsNone(accepted.delivery_status_at)

    def test_callbacks_are_durable_idempotent_and_cannot_regress_delivery(self):
        from notification_statuses import MetaDeliveryStatusService
        accepted = asyncio.run(self.delivery.deliver(self.event, self.body)).deliveries[0]
        service = MetaDeliveryStatusService(self.database.path, {"chat": self.database.path}, now=self.clock.now)
        provider_id = accepted.provider_message_id
        service.receive(status_payload(provider_id, "read", 1792670403))
        service.receive(status_payload(provider_id, "delivered", 1792670402))
        service.receive(status_payload(provider_id, "sent", 1792670401))
        service.receive(status_payload(provider_id, "read", 1792670403))
        self.assertEqual(self.current(accepted.id).delivery_status, "read")
        with self.database.transaction() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM whatsapp_delivery_receipts").fetchone()[0], 3)
        service = MetaDeliveryStatusService(self.database.path, {"chat": self.database.path}, now=self.clock.now)
        service.flush()
        self.assertEqual(self.current(accepted.id).delivery_status, "read")

    def test_accepted_notice_becomes_failed_without_hiding_acceptance_or_retrying_configuration(self):
        accepted = asyncio.run(self.delivery.deliver(self.event, self.body)).deliveries[0]
        service = self.status_service()
        failed = status_payload(accepted.provider_message_id, "failed", codes=(131047,))
        service.receive(failed)
        service.receive(failed)
        service.receive(status_payload(accepted.provider_message_id, "sent", 1792670399))
        current = self.current(accepted.id)
        self.assertEqual((current.status, current.delivery_status, current.retry_kind), ("failed", "failed", "configuration"))
        self.assertEqual(current.api_accepted_at, accepted.api_accepted_at)
        self.assertEqual(current.provider_message_id, accepted.provider_message_id)
        self.assertEqual(json.loads(current.delivery_error_codes_json), [131047])
        self.assertEqual(current.failure_count, 1)
        asyncio.run(self.delivery.deliver(self.event, self.body))
        self.assertEqual(len(self.client.sent_messages), 1)
        service.receive(status_payload(accepted.provider_message_id, "delivered", 1792670405))
        self.assertEqual((self.current(accepted.id).status, self.current(accepted.id).delivery_status), ("sent", "delivered"))

    def test_early_callback_survives_reopening_until_the_api_id_is_saved(self):
        service = self.status_service()
        outer = self
        class EarlyCallback(delivery_fixtures.FakeDoctorWhatsAppClient):
            async def send_text(client, to, body):
                service.receive(status_payload("wamid.early", "delivered"))
                with outer.database.transaction() as db:
                    outer.assertIsNone(db.execute("SELECT applied_at FROM whatsapp_delivery_receipts").fetchone()[0])
                await super().send_text(to, body)
                return {"messages": [{"id": "wamid.early"}]}
        self.delivery.whatsapp_client = EarlyCallback()
        accepted = asyncio.run(self.delivery.deliver(self.event, self.body)).deliveries[0]
        self.assertEqual(accepted.delivery_status, "accepted")
        self.status_service().flush()
        self.assertEqual(self.current(accepted.id).delivery_status, "delivered")

    def test_recipient_is_required_and_unknown_id_is_not_guessed_from_the_phone(self):
        self.client.failures["5491100000001"] = httpx.ReadTimeout("response lost")
        uncertain = asyncio.run(self.delivery.deliver(self.event, self.body)).deliveries[0]
        service = self.status_service()
        service.receive(status_payload("wamid.recovered", "read"))
        self.assertEqual(self.current(uncertain.id).status, "sending")
        self.delivery.reconcile(uncertain.id, attempt_number=1, outcome="accepted", reason="Fixture provider trace", provider_message_id="wamid.recovered")
        service.receive(status_payload("wamid.recovered", "failed", recipient="5491100000099", codes=(131047,)))
        self.assertEqual(self.current(uncertain.id).delivery_status, "read")
        self.assertEqual(self.current(uncertain.id).status, "sent")

    def test_old_attempt_failure_cannot_change_a_newer_attempt(self):
        first = asyncio.run(self.delivery.deliver(self.event, self.body)).deliveries[0]
        service = self.status_service()
        service.receive(status_payload(first.provider_message_id, "failed", codes=(130429,)))
        self.clock.advance(60)
        second = asyncio.run(self.delivery.deliver(self.event, self.body)).deliveries[0]
        self.assertEqual((second.attempt_count, second.delivery_status), (2, "accepted"))
        service.receive(status_payload(first.provider_message_id, "failed", 1792670500, codes=(131047,)))
        self.assertEqual((self.current(second.id).status, self.current(second.id).delivery_status), ("sent", "accepted"))
        service.receive(status_payload(second.provider_message_id, "read", 1792670501))
        self.assertEqual(self.current(second.id).delivery_status, "read")

    def test_repeated_async_failures_keep_exponential_wait_across_api_acceptances(self):
        first = asyncio.run(self.delivery.deliver(self.event, self.body)).deliveries[0]
        service = self.status_service()
        service.receive(status_payload(first.provider_message_id, "failed", codes=(130429,)))
        self.clock.advance(60)
        second = asyncio.run(self.delivery.deliver(self.event, self.body)).deliveries[0]
        service.receive(status_payload(second.provider_message_id, "failed", 1792670500, codes=(130429,)))
        self.assertEqual(self.current(second.id).next_attempt_at, "2026-10-22T12:03:00+00:00")
        service.receive(status_payload(second.provider_message_id, "delivered", 1792670600))
        self.assertEqual(self.current(second.id).failure_count, 0)
        self.assertIsNone(self.current(second.id).next_attempt_at)

    def test_a_callback_arriving_during_projection_is_not_marked_applied_prematurely(self):
        accepted = asyncio.run(self.delivery.deliver(self.event, self.body)).deliveries[0]
        service = self.status_service()
        project = service._project
        def inject(*args):
            result = project(*args)
            service.receive(status_payload(accepted.provider_message_id, "read", 1792670410), reconcile=False)
            return result
        with patch.object(service, "_project", side_effect=inject):
            service.receive(status_payload(accepted.provider_message_id, "sent"))
        with self.database.transaction() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM whatsapp_delivery_receipts WHERE applied_at IS NULL").fetchone()[0], 1)
        service.flush()
        self.assertEqual(self.current(accepted.id).delivery_status, "read")

    def test_webhook_correlates_voice_without_conversation_or_outbound_calls(self):
        from main import app
        voice_path = os.path.join(os.path.dirname(self.database.path), "voice.sqlite3")
        repository = VoiceRepository(voice_path)
        repository.start()
        self.addCleanup(repository.close)
        class VoiceClient(delivery_fixtures.FakeDoctorWhatsAppClient):
            async def send_text(client, to, body):
                return {"messages": [{"id": "wamid.voice-status"}]}
        delivered = asyncio.run(DoctorNotificationDeliveryService(repository, VoiceClient(), self.settings).deliver(self.event, self.body)).deliveries[0]
        with patch.dict(os.environ, {"DATABASE_PATH": self.database.path, "VOICE_DATABASE_PATH": voice_path, "CALENDAR_PROVIDER": "fake", "CALENDAR_AVAILABILITY_PROVIDER": "fake"}):
            with patch("main.create_chat_notification_worker", return_value=None), patch("main.create_meta_status_worker", return_value=None):
                with patch("main.create_conversation_service") as conversation, patch("main.WhatsAppClient") as outgoing:
                    with TestClient(app) as client:
                        response = client.post("/webhook/whatsapp", json=status_payload("wamid.voice-status", "delivered"))
                    self.assertEqual(response.status_code, 200)
                    conversation.assert_not_called()
                    outgoing.assert_not_called()
        with repository.connection() as db:
            record = DoctorNotificationRepository().get_by_id(db, delivered.id)
        self.assertEqual(record.delivery_status, "delivered")
        with self.database.transaction() as db:
            receipt = db.execute("SELECT target_channel,notification_id FROM whatsapp_delivery_receipts").fetchone()
            self.assertEqual(tuple(receipt), ("voice", delivered.id))
            self.assertEqual(db.execute("SELECT count(*) FROM doctor_notifications").fetchone()[0], 0)

    def test_webhook_does_not_acknowledge_a_callback_that_could_not_be_persisted(self):
        from main import app
        with patch.dict(os.environ, {"DATABASE_PATH": self.database.path, "CALENDAR_PROVIDER": "fake", "CALENDAR_AVAILABILITY_PROVIDER": "fake"}):
            with patch("main.create_chat_notification_worker", return_value=None), patch("main.create_meta_status_worker", return_value=None):
                with patch("main.create_meta_status_service") as factory:
                    factory.return_value.receive.side_effect = sqlite3.OperationalError("fixture write failure")
                    with TestClient(app) as client:
                        response = client.post("/webhook/whatsapp", json=status_payload("wamid.pending", "sent"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "No se pudo registrar el estado de entrega")

    def test_callback_waits_durably_when_the_voice_target_is_temporarily_unavailable(self):
        voice_path = os.path.join(os.path.dirname(self.database.path), "voice.sqlite3")
        repository = VoiceRepository(voice_path)
        repository.start()
        self.addCleanup(repository.close)
        accepted = asyncio.run(DoctorNotificationDeliveryService(repository, self.client, self.settings).deliver(self.event, self.body)).deliveries[0]
        service = self.status_service(voice=voice_path)
        with patch.object(service, "_find_target", side_effect=sqlite3.OperationalError("fixture locked target")):
            service.receive(status_payload(accepted.provider_message_id, "delivered"))
        with self.database.transaction() as db:
            self.assertIsNone(db.execute("SELECT applied_at FROM whatsapp_delivery_receipts").fetchone()[0])
        self.status_service(voice=voice_path).flush()
        with repository.connection() as db:
            self.assertEqual(DoctorNotificationRepository().get_by_id(db, accepted.id).delivery_status, "delivered")

    def test_persisted_callback_survives_a_projection_failure_after_storage(self):
        accepted = asyncio.run(self.delivery.deliver(self.event, self.body)).deliveries[0]
        service = self.status_service()
        with patch.object(service, "_flush_pending", side_effect=sqlite3.OperationalError("fixture inbox temporarily locked")):
            service.receive(status_payload(accepted.provider_message_id, "delivered"))
        with self.database.transaction() as db:
            self.assertIsNone(db.execute("SELECT applied_at FROM whatsapp_delivery_receipts").fetchone()[0])
        service.flush()
        self.assertEqual(self.current(accepted.id).delivery_status, "delivered")

    def test_equal_status_timestamp_does_not_regress_under_concurrent_projection(self):
        accepted = asyncio.run(self.delivery.deliver(self.event, self.body)).deliveries[0]
        service = self.status_service()
        project = service._project
        def overtake(*args):
            self.status_service().receive(status_payload(accepted.provider_message_id, "sent", 1792670500))
            return project(*args)
        with patch.object(service, "_project", side_effect=overtake):
            service.receive(status_payload(accepted.provider_message_id, "sent", 1792670400))
        self.assertEqual(self.current(accepted.id).delivery_status_at, "2026-10-22T12:01:40+00:00")

    def test_mexican_recipient_alias_is_normalized_for_correlation(self):
        settings = DoctorNotificationSettings(True, ("525500000001",))
        accepted = asyncio.run(DoctorNotificationDeliveryService(self.database, self.client, settings).deliver(self.event, self.body)).deliveries[0]
        self.status_service().receive(status_payload(accepted.provider_message_id, "read", recipient="+5215500000001"))
        self.assertEqual(self.current(accepted.id).delivery_status, "read")

    def test_reconciliation_utility_preserves_voice_isolation_and_callbacks_resolve_its_id(self):
        voice_path = os.path.join(os.path.dirname(self.database.path), "voice.sqlite3")
        repository = VoiceRepository(voice_path)
        repository.start()
        self.addCleanup(repository.close)
        self.client.failures["5491100000001"] = httpx.ReadTimeout("fixture response lost")
        uncertain = asyncio.run(DoctorNotificationDeliveryService(repository, self.client, self.settings).deliver(self.event, self.body)).deliveries[0]
        script = Path(__file__).resolve().parents[1] / "scripts/reconcile_doctor_notification.py"
        result = subprocess.run([sys.executable, "-B", str(script), "--database", voice_path,
            "--notification-id", str(uncertain.id), "--attempt", "1", "--outcome", "accepted",
            "--reason", "Fixture recovered provider trace", "--provider-message-id", "wamid.voice-reconciled"],
            capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["delivery_status"], "accepted")
        repository.close()
        repository.start()
        self.status_service(voice=voice_path).receive(status_payload("wamid.voice-reconciled", "read"))
        with repository.connection() as db:
            self.assertEqual(DoctorNotificationRepository().get_by_id(db, uncertain.id).delivery_status, "read")
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='patients'").fetchone())

    def test_malformed_statuses_do_not_create_a_database_or_invent_recipients(self):
        from notification_statuses import MetaDeliveryStatusService
        path = os.path.join(os.path.dirname(self.database.path), "uncreated.sqlite3")
        service = MetaDeliveryStatusService(path, {"chat": path})
        payloads = [None, [], {}, {"entry": "invalid"}, {"entry": [{"changes": [None]}]}]
        for changes in ({"recipient_id": None}, {"timestamp": "invalid"}, {"timestamp": True},
                        {"status": "accepted"}, {"id": ""}):
            payload = status_payload("wamid.invalid", "sent")
            payload["entry"][0]["changes"][0]["value"]["statuses"][0].update(changes)
            payloads.append(payload)
        for payload in payloads:
            self.assertEqual(service.receive(payload), 0)
        self.assertFalse(os.path.exists(path))

    def test_error_history_stores_only_numeric_codes_not_raw_provider_content(self):
        accepted = asyncio.run(self.delivery.deliver(self.event, self.body)).deliveries[0]
        payload = status_payload(accepted.provider_message_id, "failed", codes=(131047,))
        payload["entry"][0]["changes"][0]["value"]["statuses"][0]["errors"][0]["message"] = "fixture-secret-provider-text"
        self.status_service().receive(payload)
        with self.database.transaction() as db:
            row = db.execute("SELECT * FROM whatsapp_delivery_receipts").fetchone()
        self.assertNotIn("fixture-secret-provider-text", repr(tuple(row)))
        self.assertEqual(row["error_codes_json"], "[131047]")

    def test_ambiguous_channel_match_is_retained_instead_of_guessing(self):
        chat = asyncio.run(self.delivery.deliver(self.event, self.body)).deliveries[0]
        voice_path = os.path.join(os.path.dirname(self.database.path), "voice.sqlite3")
        repository = VoiceRepository(voice_path)
        repository.start()
        self.addCleanup(repository.close)
        asyncio.run(DoctorNotificationDeliveryService(repository, delivery_fixtures.FakeDoctorWhatsAppClient(), self.settings).deliver(self.event, self.body))
        self.status_service(voice=voice_path).receive(status_payload(chat.provider_message_id, "read"))
        self.assertEqual(self.current(chat.id).delivery_status, "accepted")
        with self.database.transaction() as db:
            self.assertIsNone(db.execute("SELECT applied_at FROM whatsapp_delivery_receipts").fetchone()[0])

    def test_legacy_message_without_attempt_history_is_correlated_without_fabricating_attempts(self):
        accepted = asyncio.run(self.delivery.deliver(self.event, self.body)).deliveries[0]
        with self.database.transaction() as db:
            db.execute("DELETE FROM doctor_notification_attempts")
        self.status_service().receive(status_payload(accepted.provider_message_id, "delivered"))
        self.assertEqual(self.current(accepted.id).delivery_status, "delivered")
        with self.database.transaction() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM doctor_notification_attempts").fetchone()[0], 0)


class NotificationStatusWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_lifespan_replays_an_early_callback_after_the_api_id_is_registered(self):
        from main import app
        from notification_statuses import MetaDeliveryStatusWorker
        fixture = NotificationStatusTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        service = fixture.status_service()
        service.receive(status_payload("wamid.doctor.1", "read"))
        worker = MetaDeliveryStatusWorker(service, interval_seconds=0.01)
        with patch.dict(os.environ, {"DATABASE_PATH": fixture.database.path, "CALENDAR_PROVIDER": "fake", "CALENDAR_AVAILABILITY_PROVIDER": "fake"}):
            with patch("main.create_chat_notification_worker", return_value=None), patch("main.create_meta_status_worker", return_value=worker):
                with TestClient(app):
                    accepted = await fixture.delivery.deliver(fixture.event, fixture.body)
                    async with asyncio.timeout(3):
                        while fixture.current(accepted.deliveries[0].id).delivery_status != "read":
                            await asyncio.sleep(0.01)
        self.assertIsNone(worker._task)
        self.assertEqual(len(fixture.client.sent_messages), 1)
