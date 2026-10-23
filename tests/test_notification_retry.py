import unittest
from datetime import datetime, timedelta, timezone

import asyncio
import json
import httpx

from notification_delivery import DoctorNotificationDeliveryService, DoctorNotificationSettings
from persistence import SQLiteDatabase
import test_notification_delivery as delivery_fixtures


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)

    def now(self):
        return self.value.isoformat()

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


class NotificationRetryTests(unittest.TestCase):
    def setUp(self):
        delivery_fixtures.NotificationDeliveryTests.setUp(self)
        self.clock = Clock()
        self.client = delivery_fixtures.FakeDoctorWhatsAppClient()
        self.settings = DoctorNotificationSettings(True, ("5491100000001",))

    def service(self):
        return DoctorNotificationDeliveryService(
            SQLiteDatabase(self.database.path), self.client, self.settings, now=self.clock.now,
        )

    def test_transient_failure_waits_until_its_persisted_due_time_after_reopening(self):
        self.client.failures["5491100000001"] = httpx.ConnectError("unavailable")
        first = asyncio.run(self.service().deliver(self.event, self.body)).deliveries[0]
        self.assertEqual(first.status, "failed")
        self.assertEqual(first.next_attempt_at, "2026-10-22T12:01:00+00:00")
        self.client.failures.clear()
        early = asyncio.run(self.service().deliver(self.event, "No reemplazar"))
        self.assertEqual(early.deliveries[0].attempt_count, 1)
        self.assertEqual(self.client.sent_messages, [])
        self.clock.advance(60)
        completed = asyncio.run(self.service().deliver(self.event, "No reemplazar")).deliveries[0]
        self.assertEqual((completed.status, completed.attempt_count), ("sent", 2))
        self.assertEqual(self.client.sent_messages, [("5491100000001", self.body)])

    def test_rate_limit_honors_retry_after_and_exponential_backoff(self):
        response = httpx.Response(429, headers={"Retry-After": "300"}, request=httpx.Request("POST", "https://example.test/messages"))
        self.client.failures["5491100000001"] = httpx.HTTPStatusError("rate limit", request=response.request, response=response)
        first = asyncio.run(self.service().deliver(self.event, self.body)).deliveries[0]
        self.assertEqual(first.next_attempt_at, "2026-10-22T12:05:00+00:00")
        self.clock.advance(299)
        self.assertEqual(asyncio.run(self.service().deliver(self.event, self.body)).deliveries[0].attempt_count, 1)
        self.clock.advance(1)
        self.client.failures["5491100000001"] = httpx.ConnectError("unavailable")
        second = asyncio.run(self.service().deliver(self.event, self.body)).deliveries[0]
        self.assertEqual(second.next_attempt_at, "2026-10-22T12:07:00+00:00")

    def test_authentication_rejection_stops_until_credentials_change(self):
        response = httpx.Response(401, json={"error": {"code": 190}}, request=httpx.Request("POST", "https://example.test/messages"))
        self.client.access_token = "fixture-old-token"
        self.client.failures["5491100000001"] = httpx.HTTPStatusError("auth", request=response.request, response=response)
        first = asyncio.run(self.service().deliver(self.event, self.body)).deliveries[0]
        self.assertEqual(first.retry_kind, "configuration")
        self.clock.advance(86400)
        self.client.failures.clear()
        self.assertEqual(asyncio.run(self.service().deliver(self.event, self.body)).deliveries[0].attempt_count, 1)
        self.assertEqual(self.client.sent_messages, [])
        self.client.access_token = "fixture-corrected-token"
        completed = asyncio.run(self.service().deliver(self.event, self.body)).deliveries[0]
        self.assertEqual((completed.status, completed.attempt_count), ("sent", 2))

    def test_uncertain_result_requires_versioned_reconciliation_before_another_dispatch(self):
        self.client.failures["5491100000001"] = httpx.ReadTimeout("response lost")
        first = asyncio.run(self.service().deliver(self.event, self.body)).deliveries[0]
        self.clock.advance(86400)
        self.client.failures.clear()
        self.assertEqual(asyncio.run(self.service().deliver(self.event, self.body)).deliveries[0].attempt_count, 1)
        with self.assertRaises(ValueError):
            self.service().reconcile(first.id, attempt_number=2, outcome="not_delivered", reason="fixture trace")
        self.service().reconcile(first.id, attempt_number=1, outcome="not_delivered", reason="Fixture: transport trace confirms no dispatch")
        completed = asyncio.run(self.service().deliver(self.event, self.body)).deliveries[0]
        self.assertEqual((completed.status, completed.attempt_count), ("sent", 2))
        with self.database.transaction() as db:
            audit = db.execute("SELECT reconciliation_outcome,reconciliation_reason FROM doctor_notification_attempts WHERE notification_id=? AND attempt_number=1", (first.id,)).fetchone()
        self.assertEqual(audit[0], "not_delivered")
        self.assertIn("Fixture:", audit[1])

    def test_reconciled_acceptance_never_resends_and_requires_recovered_provider_id(self):
        self.client.failures["5491100000001"] = httpx.ReadTimeout("response lost")
        first = asyncio.run(self.service().deliver(self.event, self.body)).deliveries[0]
        with self.assertRaises(ValueError):
            self.service().reconcile(first.id, attempt_number=1, outcome="accepted", reason="fixture trace")
        self.service().reconcile(first.id, attempt_number=1, outcome="accepted", reason="Fixture callback confirms acceptance", provider_message_id="wamid.recovered")
        result = asyncio.run(self.service().deliver(self.event, self.body)).deliveries[0]
        self.assertEqual((result.status, result.provider_message_id, result.attempt_count), ("sent", "wamid.recovered", 1))

    def test_new_doctors_are_not_added_retroactively_to_an_existing_event(self):
        self.client.failures["5491100000001"] = httpx.ConnectError("unavailable")
        asyncio.run(self.service().deliver(self.event, self.body))
        self.settings = DoctorNotificationSettings(True, ("5491100000001", "5491100000002"))
        self.client.failures.clear()
        self.clock.advance(60)
        result = asyncio.run(self.service().deliver(self.event, self.body))
        self.assertEqual([record.recipient_number for record in result.deliveries], ["5491100000001"])
        self.assertEqual(self.client.sent_messages, [("5491100000001", self.body)])

    def test_corrected_template_rejection_preserves_the_original_attempt_snapshot(self):
        response = httpx.Response(400, json={"error": {"code": 132001}}, request=httpx.Request("POST", "https://example.test/messages"))
        class RejectOnce(delivery_fixtures.FakeDoctorWhatsAppClient):
            async def send_template(client, *args, **kwargs):
                result = await super().send_template(*args, **kwargs)
                if len(client.sent_templates) == 1:
                    raise httpx.HTTPStatusError("missing template", request=response.request, response=response)
                return result
        self.client = RejectOnce()
        mapping = json.dumps([{"type": "body", "parameters": [{"type": "text", "text": "{notification_body}"}]}])
        self.settings = DoctorNotificationSettings(True, ("5491100000001",), "template", "fixture_old", "es_MX", mapping)
        first = asyncio.run(self.service().deliver(self.event, self.body)).deliveries[0]
        asyncio.run(self.service().deliver(self.event, self.body))
        self.assertEqual(len(self.client.sent_templates), 1)
        self.settings = DoctorNotificationSettings(True, ("5491100000001",), "template", "fixture_corrected", "es_MX", mapping)
        second = asyncio.run(self.service().deliver(self.event, "Otro cuerpo")).deliveries[0]
        self.assertEqual(second.status, "sent")
        self.assertNotEqual(first.template_version, second.template_version)
        self.assertEqual([value[1] for value in self.client.sent_templates], ["fixture_old", "fixture_corrected"])
        with self.database.transaction() as db:
            attempts = db.execute("SELECT body,template_payload_json,provider_code FROM doctor_notification_attempts ORDER BY attempt_number").fetchall()
        self.assertEqual([row[0] for row in attempts], [self.body, self.body])
        self.assertEqual([json.loads(row[1])["name"] for row in attempts], ["fixture_old", "fixture_corrected"])
        self.assertEqual(attempts[0][2], 132001)

    def test_late_completion_cannot_override_a_reconciled_provider_id(self):
        self.client.failures["5491100000001"] = httpx.ReadTimeout("response lost")
        record = asyncio.run(self.service().deliver(self.event, self.body)).deliveries[0]
        service = self.service()
        service.reconcile(record.id, attempt_number=1, outcome="accepted", reason="Fixture provider trace", provider_message_id="wamid.recovered")
        with self.database.transaction() as db:
            updated = service.notifications.mark_sent(db, record.id, provider_message_id="wamid.stale", now=self.clock.now(), expected_attempt=1)
        self.assertEqual(updated.provider_message_id, "wamid.recovered")

    def test_text_acceptance_without_provider_id_is_also_uncertain(self):
        class MissingId(delivery_fixtures.FakeDoctorWhatsAppClient):
            async def send_text(client, to, body):
                await super().send_text(to, body)
                return {}
        self.client = MissingId()
        first = asyncio.run(self.service().deliver(self.event, self.body)).deliveries[0]
        self.clock.advance(86400)
        second = asyncio.run(self.service().deliver(self.event, self.body)).deliveries[0]
        self.assertEqual((first.status, second.status, second.attempt_count), ("sending", "sending", 1))
        self.assertEqual(len(self.client.sent_messages), 1)

    def test_composition_failure_keeps_the_original_registered_recipients(self):
        self.service().capture(self.event)
        self.settings = DoctorNotificationSettings(True, ("5491100000001", "5491100000002"))
        batch = self.service().record_failed(self.event, error="Fixture summary unavailable")
        self.assertEqual([row.recipient_number for row in batch.deliveries], ["5491100000001"])
