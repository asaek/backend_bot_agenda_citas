import os
import tempfile
import unittest

from persistence import SQLiteDatabase
from repositories import DoctorNotificationRepository


class DoctorNotificationRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = SQLiteDatabase(
            os.path.join(self.directory.name, "notifications.sqlite3")
        )
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO patients (whatsapp_number, created_at, last_seen_at)
                VALUES (?, ?, ?)
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
                    patient_id, status, state, context_json, created_at, updated_at
                ) VALUES (1, 'active', 'active', '{}', ?, ?)
                """,
                (
                    "2026-09-20T12:00:00+00:00",
                    "2026-09-20T12:00:00+00:00",
                ),
            )
        self.repository = DoctorNotificationRepository()

    def create_pending(self, recipient_number: str = "5491100000001"):
        with self.database.transaction() as connection:
            return self.repository.create_pending(
                connection,
                event_key="appointment:message-1:create:call-1",
                recipient_number=recipient_number,
                notification_type="appointment_scheduled",
                patient_id=1,
                conversation_id=1,
                appointment_id="appointment-1",
                body="Cita agendada para el paciente.",
                now="2026-09-20T12:01:00+00:00",
            )

    def test_creates_pending_record_with_delivery_metadata(self) -> None:
        record = self.create_pending()

        self.assertEqual(record.status, "pending")
        self.assertEqual(record.attempt_count, 0)
        self.assertIsNone(record.last_error)
        self.assertIsNone(record.provider_message_id)
        self.assertIsNone(record.sent_at)

    def test_same_event_and_recipient_is_idempotent_after_success(self) -> None:
        first = self.create_pending(" 5491100000001 ")
        with self.database.transaction() as connection:
            claimed = self.repository.claim_for_send(
                connection,
                first.id,
                "2026-09-20T12:02:00+00:00",
            )
            self.assertIsNotNone(claimed)
            sent = self.repository.mark_sent(
                connection,
                first.id,
                provider_message_id=" wamid.doctor.1 ",
                now="2026-09-20T12:03:00+00:00",
            )

        duplicate = self.create_pending("5491100000001")

        self.assertEqual(duplicate.id, first.id)
        self.assertEqual(duplicate.status, "sent")
        self.assertEqual(duplicate.attempt_count, 1)
        self.assertEqual(duplicate.provider_message_id, "wamid.doctor.1")
        self.assertEqual(duplicate.body, first.body)
        self.assertEqual(sent.sent_at, "2026-09-20T12:03:00+00:00")
        with self.database.transaction() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM doctor_notifications"
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_same_event_has_independent_delivery_per_recipient(self) -> None:
        first = self.create_pending("5491100000001")
        second = self.create_pending("5491100000002")

        self.assertNotEqual(first.id, second.id)
        with self.database.transaction() as connection:
            records = self.repository.list_for_event(
                connection,
                "appointment:message-1:create:call-1",
            )
            recipient_records = self.repository.list_for_recipient(
                connection,
                "5491100000001",
            )
        self.assertEqual([record.recipient_number for record in records], [
            "5491100000001",
            "5491100000002",
        ])
        self.assertEqual(recipient_records, [first])

    def test_failed_delivery_can_be_claimed_again_and_records_attempts(self) -> None:
        record = self.create_pending()
        with self.database.transaction() as connection:
            first_claim = self.repository.claim_for_send(
                connection,
                record.id,
                "2026-09-20T12:02:00+00:00",
            )
            self.assertIsNotNone(first_claim)
            failed = self.repository.mark_failed(
                connection,
                record.id,
                error="timeout de WhatsApp",
                now="2026-09-20T12:03:00+00:00",
            )
            self.assertEqual(failed.status, "failed")
            self.assertEqual(failed.last_error, "timeout de WhatsApp")
            self.assertEqual(
                [item.id for item in self.repository.list_retryable(connection)],
                [record.id],
            )
            second_claim = self.repository.claim_for_send(
                connection,
                record.id,
                "2026-09-20T12:04:00+00:00",
            )
            self.assertIsNotNone(second_claim)
            self.assertEqual(second_claim.attempt_count, 2)
            self.assertEqual(second_claim.status, "sending")
            self.assertIsNone(second_claim.last_error)
            sent = self.repository.mark_sent(
                connection,
                record.id,
                provider_message_id="wamid.doctor.2",
                now="2026-09-20T12:05:00+00:00",
            )
            self.assertEqual(sent.status, "sent")

            self.assertEqual(self.repository.list_retryable(connection), [])
            self.assertIsNone(
                self.repository.claim_for_send(
                    connection,
                    record.id,
                    "2026-09-20T12:06:00+00:00",
                )
            )

    def test_sent_delivery_cannot_be_regressed_to_failed(self) -> None:
        record = self.create_pending()
        with self.database.transaction() as connection:
            self.repository.mark_sent(
                connection,
                record.id,
                provider_message_id="wamid.doctor.1",
                now="2026-09-20T12:03:00+00:00",
            )
            unchanged = self.repository.mark_failed(
                connection,
                record.id,
                error="error tardio",
                now="2026-09-20T12:04:00+00:00",
            )

        self.assertEqual(unchanged.status, "sent")
        self.assertIsNone(unchanged.last_error)
        self.assertEqual(unchanged.provider_message_id, "wamid.doctor.1")
