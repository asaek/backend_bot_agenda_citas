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

CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calendar_id TEXT NOT NULL,
    google_event_id TEXT NOT NULL,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (
        status IN ('scheduled', 'confirmed', 'cancelled', 'completed', 'no_show')
    ),
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    last_synced_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(calendar_id, google_event_id)
);

CREATE INDEX IF NOT EXISTS appointments_by_patient_start
ON appointments(patient_id, start_at, id);

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

CREATE TABLE IF NOT EXISTS reply_outbox (
    incoming_message_id INTEGER PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (
        status IN ('processing', 'ready', 'sending', 'sent', 'failed', 'superseded', 'uncertain')
    ),
    body TEXT,
    notification_events_json TEXT NOT NULL DEFAULT '[]',
    notifications_completed INTEGER NOT NULL DEFAULT 0 CHECK (notifications_completed IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reply_delivery_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incoming_message_id INTEGER NOT NULL REFERENCES reply_outbox(incoming_message_id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('sending', 'sent', 'failed', 'uncertain')),
    provider_message_id TEXT,
    error_type TEXT,
    http_status_code INTEGER CHECK (http_status_code BETWEEN 100 AND 599),
    started_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS reply_attempts_by_message
ON reply_delivery_attempts(incoming_message_id, id);

CREATE TABLE IF NOT EXISTS llm_failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    incoming_message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    error_type TEXT NOT NULL,
    http_status_code INTEGER CHECK (http_status_code BETWEEN 100 AND 599),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS llm_failures_by_conversation
ON llm_failures(conversation_id, id);

CREATE TABLE IF NOT EXISTS doctor_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key TEXT NOT NULL CHECK (length(trim(event_key)) > 0),
    recipient_number TEXT NOT NULL CHECK (length(trim(recipient_number)) > 0),
    notification_type TEXT NOT NULL CHECK (
        notification_type IN (
            'appointment_scheduled',
            'appointment_modified',
            'appointment_cancelled'
        )
    ),
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    appointment_id TEXT NOT NULL CHECK (length(trim(appointment_id)) > 0),
    body TEXT NOT NULL CHECK (length(trim(body)) > 0),
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'sending', 'sent', 'failed')
    ),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_error TEXT,
    provider_message_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    sent_at TEXT,
    UNIQUE(event_key, recipient_number)
);

CREATE INDEX IF NOT EXISTS doctor_notifications_by_status
ON doctor_notifications(status, updated_at, id);

CREATE INDEX IF NOT EXISTS doctor_notifications_by_event
ON doctor_notifications(event_key, id);
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
            self._migrate_llm_failure_http_status(connection)
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _migrate_llm_failure_http_status(
        connection: sqlite3.Connection,
    ) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(llm_failures)")
        }
        if "http_status_code" not in columns:
            connection.execute(
                """
                ALTER TABLE llm_failures
                ADD COLUMN http_status_code INTEGER
                    CHECK (http_status_code BETWEEN 100 AND 599)
                """
            )

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
