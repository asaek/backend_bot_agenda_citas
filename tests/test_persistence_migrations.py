import os
import sqlite3
import tempfile
import unittest

from persistence import SQLiteDatabase


class PersistenceMigrationTests(unittest.TestCase):
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
