from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3


DEFAULT_DATABASE_PATH = "data/chatbot.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    whatsapp_number TEXT NOT NULL UNIQUE,
    name TEXT,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('active', 'closed')),
    state TEXT NOT NULL CHECK (state IN ('new', 'active')),
    context_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_conversation_per_patient
ON conversations(patient_id)
WHERE status = 'active';

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    direction TEXT NOT NULL CHECK (direction IN ('incoming', 'outgoing')),
    provider_message_id TEXT,
    text TEXT NOT NULL,
    message_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('received', 'sent', 'failed')),
    reply_to_message_id INTEGER REFERENCES messages(id),
    created_at TEXT NOT NULL,
    UNIQUE(direction, provider_message_id)
);

CREATE INDEX IF NOT EXISTS messages_by_conversation
ON messages(conversation_id, id);
"""


class SQLiteDatabase:
    def __init__(self, path: str) -> None:
        self.path = path
        self._create_parent_directory()
        self.initialize()

    def _create_parent_directory(self) -> None:
        if self.path == ":memory:":
            return
        Path(self.path).expanduser().parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        connection = self.connect()
        try:
            connection.executescript(SCHEMA)
            connection.commit()
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
