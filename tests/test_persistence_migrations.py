import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from itertools import product

from persistence import SQLiteDatabase
from repositories import DoctorNotificationRepository
from voice_repository import VoiceRepository


class PersistenceMigrationTests(unittest.TestCase):
    def test_existing_chat_and_voice_notices_gain_template_snapshots_without_rewriting_them(self) -> None:
        for kind, status in product(("chat", "voice"), ("sent", "failed", "sending")):
            with self.subTest(kind=kind, status=status), tempfile.TemporaryDirectory() as directory:
                path = os.path.join(directory, "notices.sqlite3")
                with closing(sqlite3.connect(path)) as connection:
                    connection.executescript("""
                        CREATE TABLE doctor_notifications (
                            id INTEGER PRIMARY KEY, event_key TEXT NOT NULL, recipient_number TEXT NOT NULL,
                            notification_type TEXT NOT NULL, patient_id INTEGER NOT NULL,
                            conversation_id INTEGER NOT NULL, appointment_id TEXT NOT NULL, body TEXT NOT NULL,
                            status TEXT NOT NULL, attempt_count INTEGER NOT NULL, last_error TEXT,
                            provider_message_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                            sent_at TEXT, UNIQUE(event_key, recipient_number)
                        );
                        INSERT INTO doctor_notifications VALUES (
                            1, 'legacy-event', '5491100000001', 'appointment_scheduled', 1, 1,
                            'appointment-1', 'Aviso historico', 'sent', 1, NULL, 'wamid.legacy',
                            '2026-10-17T12:00:00+00:00', '2026-10-17T12:00:00+00:00',
                            '2026-10-17T12:00:00+00:00'
                        );
                    """)
                    connection.execute("UPDATE doctor_notifications SET status=?", (status,))
                    connection.commit()
                if kind == "chat":
                    repository = SQLiteDatabase(path)
                    repository.initialize()
                else:
                    repository = VoiceRepository(path)
                    repository.start()
                    repository.close()
                    repository.start()
                try:
                    with closing(sqlite3.connect(path)) as connection:
                        connection.row_factory = sqlite3.Row
                        record = DoctorNotificationRepository().get_by_id(connection, 1)
                    self.assertEqual((record.body, record.status, record.attempt_count, record.provider_message_id),
                                     ("Aviso historico", status, 1, "wamid.legacy"))
                    self.assertIsNone(record.template_data_json)
                    self.assertIsNone(record.template_payload_json)
                    self.assertEqual(record.retry_kind, {"sent": "ready", "failed": "configuration", "sending": "uncertain"}[status])
                    self.assertIsNone(record.next_attempt_at)
                    self.assertEqual(record.delivery_status, "accepted" if status == "sent" else None)
                    self.assertIsNone(record.delivery_status_at)
                finally:
                    if kind == "voice":
                        repository.close()

    def test_reply_outbox_is_added_without_rewriting_historical_messages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "chatbot.sqlite3")
            with sqlite3.connect(database_path) as connection:
                connection.executescript("""
                    CREATE TABLE messages (
                        id INTEGER PRIMARY KEY, conversation_id INTEGER NOT NULL,
                        direction TEXT NOT NULL, provider_message_id TEXT, text TEXT NOT NULL,
                        message_type TEXT NOT NULL, status TEXT NOT NULL,
                        reply_to_message_id INTEGER, created_at TEXT NOT NULL
                    );
                    INSERT INTO messages VALUES (
                        1, 7, 'outgoing', NULL, 'Respuesta historica', 'text', 'failed',
                        2, '2026-10-08T15:31:56+00:00'
                    );
                """)

            database = SQLiteDatabase(database_path)
            # La inicializacion repetida tampoco inventa intentos de envios anteriores.
            database.initialize()
            with database.transaction() as connection:
                historical = connection.execute("SELECT text, status, created_at FROM messages").fetchone()
                outbox_count = connection.execute("SELECT COUNT(*) FROM reply_outbox").fetchone()[0]
                attempt_count = connection.execute("SELECT COUNT(*) FROM reply_delivery_attempts").fetchone()[0]

        self.assertEqual(tuple(historical), ("Respuesta historica", "failed", "2026-10-08T15:31:56+00:00"))
        self.assertEqual((outbox_count, attempt_count), (0, 0))

    def test_existing_llm_failures_table_gains_nullable_http_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "chatbot.sqlite3")
            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE llm_failures (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        conversation_id INTEGER NOT NULL,
                        incoming_message_id INTEGER NOT NULL,
                        error_type TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO llm_failures (
                        conversation_id, incoming_message_id, error_type, created_at
                    ) VALUES (1, 2, 'LLMResponseError', '2026-09-29T12:38:26+00:00')
                    """
                )

            database = SQLiteDatabase(database_path)

            with database.transaction() as connection:
                columns = {
                    row["name"]
                    for row in connection.execute("PRAGMA table_info(llm_failures)")
                }
                failure = connection.execute(
                    "SELECT error_type, http_status_code FROM llm_failures"
                ).fetchone()

        self.assertIn("http_status_code", columns)
        self.assertEqual(tuple(failure), ("LLMResponseError", None))


if __name__ == "__main__":
    unittest.main()
