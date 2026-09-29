import os
import sqlite3
import tempfile
import unittest

from persistence import SQLiteDatabase


class PersistenceMigrationTests(unittest.TestCase):
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
