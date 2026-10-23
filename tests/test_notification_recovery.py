import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from chat_notifications import ChatDoctorNotifications
from fakes import FakeLLMProvider
from llm_provider import ToolCall
from main import app
from notification_delivery import DoctorNotificationSettings
from notification_trigger import DoctorNotificationTrigger
from persistence import SQLiteDatabase
from test_notification_retry import Clock
import test_main as webhook_fixtures


class ChatRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.scenario = webhook_fixtures.WebhookTests()
        self.scenario.setUp()
        self.addCleanup(self.scenario.doCleanups)
        self.scenario.set_fixed_calendar_runtime()
        self.clock = Clock()
        self.client = webhook_fixtures.FakeWhatsAppClient()
        self.provider = FakeLLMProvider(replies=(
            ToolCall(name="create_appointment", arguments={"start_at": "2026-09-21T10:00:00", "reason": "Revision"}, call_id="recovery-create"),
            '{"summary":"Solicita una revision general.","priority_signals":[]}',
        ))
        self.settings = DoctorNotificationSettings(True, ("5491100000001",), "template")

    def create_registered_event_before_notification_capture(self):
        with self.scenario.configured_runtime(self.client, self.provider):
            with patch("main.deliver_doctor_notifications", new=AsyncMock(return_value=False)):
                with TestClient(app) as client:
                    responses = self.scenario.post_messages(client,
                        self.scenario.text_payload(message_id="recovery-request", text="Agendar para el lunes a las 10"),
                        self.scenario.text_payload(message_id="recovery-name", text="Ana Prueba"),
                        self.scenario.text_payload(message_id="recovery-reason", text="Revision"))
        self.assertTrue(all(response.status_code == 200 for response in responses))
        self.assertEqual(len(self.client.sent_messages), 3)
        with SQLiteDatabase(self.scenario.database_path).transaction() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM doctor_notifications").fetchone()[0], 0)

    def configure_template(self):
        components = json.dumps([{"type": "body", "parameters": [{"type": "text", "text": "{notification_body}"}]}])
        self.settings = DoctorNotificationSettings(True, ("5491100000001",), "template", "fixture_cita", "es_MX", components)

    def worker(self):
        def factory(database):
            trigger = DoctorNotificationTrigger(database, self.provider, whatsapp_client=self.client, settings=self.settings)
            trigger.delivery.now = self.clock.now
            return trigger
        return ChatDoctorNotifications(self.scenario.database_path, factory, retry_seconds=0.01)

    async def test_chat_recovers_its_registered_event_and_frozen_context_after_reopening(self):
        self.create_registered_event_before_notification_capture()
        worker = self.worker()
        await worker.flush()
        await worker.close()
        with SQLiteDatabase(self.scenario.database_path).transaction() as db:
            notice = db.execute("SELECT status,event_json,context_json FROM doctor_notifications").fetchone()
            self.assertEqual(notice["status"], "pending")
            self.assertTrue(notice["event_json"])
            self.assertEqual(json.loads(notice["context_json"])["patient_name"], "Ana Prueba")
            db.execute("UPDATE patients SET name='Nombre posterior'")
            # La bandeja por destinatario es recuperable aun si la fuente ya se cerro.
            db.execute("UPDATE reply_outbox SET notifications_completed=1")
        self.configure_template()
        reopened = self.worker()
        await reopened.flush()
        await reopened.flush()
        await reopened.close()
        self.assertEqual(len(self.client.sent_templates), 1)
        payload = self.client.sent_templates[0]
        self.assertEqual(payload[:3], ("5491100000001", "fixture_cita", "es_MX"))
        self.assertIn("Nombre: Ana Prueba", payload[3][0]["parameters"][0]["text"])
        self.assertNotIn("Nombre posterior", payload[3][0]["parameters"][0]["text"])
        self.assertEqual(len(self.client.sent_messages), 3)
        self.assertEqual(len(app.state.calendar_provider.appointments), 1)
        self.assertEqual(self.provider.call_count, 2)

    async def test_startup_loop_delivers_without_another_patient_message(self):
        self.create_registered_event_before_notification_capture()
        self.configure_template()
        worker = self.worker()
        worker.start()
        try:
            async with asyncio.timeout(3):
                while not self.client.sent_templates:
                    await asyncio.sleep(0.01)
            await asyncio.sleep(0.03)
        finally:
            await worker.close()
        self.assertEqual(len(self.client.sent_templates), 1)
        self.assertEqual(len(self.client.sent_messages), 3)
        self.assertEqual(len(app.state.calendar_provider.appointments), 1)

    async def test_fastapi_lifespan_starts_and_stops_chat_recovery(self):
        self.create_registered_event_before_notification_capture()
        self.configure_template()
        worker = self.worker()
        with patch("main.create_chat_notification_worker", return_value=worker):
            with TestClient(app):
                async with asyncio.timeout(3):
                    while not self.client.sent_templates:
                        await asyncio.sleep(0.01)
        self.assertIsNone(worker._task)
        self.assertEqual(len(self.client.sent_templates), 1)
        self.assertEqual(len(self.client.sent_messages), 3)

    async def test_concurrent_recovery_does_not_duplicate_a_claimed_dispatch(self):
        entered, release = asyncio.Event(), asyncio.Event()
        class BlockingClient(webhook_fixtures.FakeWhatsAppClient):
            async def send_template(client, *args, **kwargs):
                entered.set()
                await release.wait()
                return await super().send_template(*args, **kwargs)
        self.client = BlockingClient()
        self.create_registered_event_before_notification_capture()
        self.configure_template()
        first = self.worker()
        second = self.worker()
        task = asyncio.create_task(first.flush())
        try:
            await asyncio.wait_for(entered.wait(), 2)
            await asyncio.wait_for(second.flush(), 2)
        finally:
            release.set()
            await task
            await first.close()
            await second.close()
        self.assertEqual(len(self.client.sent_templates), 1)
        self.assertEqual(self.provider.call_count, 2)
