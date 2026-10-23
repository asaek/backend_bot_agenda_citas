"""La misma bandeja de entrega para pacientes operativos y perfiles de laboratorio."""

import sqlite3


def migrate_doctor_notifications(connection: sqlite3.Connection) -> None:
    if not connection.in_transaction:
        connection.execute("BEGIN IMMEDIATE")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(doctor_notifications)")}
    additions = {
        "template_data_json": "TEXT", "template_payload_json": "TEXT", "template_version": "TEXT",
        "event_json": "TEXT", "context_json": "TEXT", "next_attempt_at": "TEXT",
        "retry_kind": "TEXT NOT NULL DEFAULT 'ready'", "blocked_configuration_key": "TEXT",
        "failure_count": "INTEGER NOT NULL DEFAULT 0",
        "delivery_status": "TEXT", "delivery_status_at": "TEXT", "delivery_error_codes_json": "TEXT",
        "api_accepted_at": "TEXT",
    }
    for name, definition in additions.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE doctor_notifications ADD COLUMN {name} {definition}")
    if "retry_kind" not in columns:
        connection.execute("UPDATE doctor_notifications SET retry_kind='configuration' WHERE status='failed'")
        connection.execute("UPDATE doctor_notifications SET retry_kind='uncertain' WHERE status='sending'")
    if "delivery_status" not in columns:
        connection.execute("""UPDATE doctor_notifications SET delivery_status='accepted', api_accepted_at=sent_at
            WHERE status='sent' AND provider_message_id IS NOT NULL""")
    connection.execute("""CREATE TABLE IF NOT EXISTS doctor_notification_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        notification_id INTEGER NOT NULL REFERENCES doctor_notifications(id) ON DELETE CASCADE,
        attempt_number INTEGER NOT NULL, state TEXT NOT NULL, transport TEXT NOT NULL,
        body TEXT NOT NULL, template_payload_json TEXT, template_version TEXT,
        started_at TEXT, completed_at TEXT, http_status INTEGER, provider_code INTEGER,
        classification TEXT, provider_message_id TEXT, reconciliation_outcome TEXT, reconciliation_reason TEXT, reconciled_at TEXT,
        UNIQUE(notification_id, attempt_number)
    )""")
    attempt_columns = {row[1] for row in connection.execute("PRAGMA table_info(doctor_notification_attempts)")}
    for name in ("provider_message_id", "delivery_status", "delivery_status_at", "delivery_error_codes_json", "api_accepted_at", "configuration_key"):
        if name not in attempt_columns:
            connection.execute(f"ALTER TABLE doctor_notification_attempts ADD COLUMN {name} TEXT")
    if "delivery_status" not in attempt_columns:
        connection.execute("""UPDATE doctor_notification_attempts SET delivery_status='accepted', api_accepted_at=completed_at
            WHERE state='sent' AND provider_message_id IS NOT NULL""")
    connection.execute("CREATE INDEX IF NOT EXISTS doctor_notifications_due ON doctor_notifications(status,next_attempt_at,id)")
    connection.execute("CREATE INDEX IF NOT EXISTS doctor_notifications_provider_id ON doctor_notifications(provider_message_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS doctor_attempts_provider_id ON doctor_notification_attempts(provider_message_id)")


def delivery_receipts_schema(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS whatsapp_delivery_receipts (
        event_key TEXT PRIMARY KEY, provider_message_id TEXT NOT NULL, recipient_number TEXT NOT NULL,
        status TEXT NOT NULL, provider_timestamp INTEGER NOT NULL, error_codes_json TEXT NOT NULL,
        phone_number_id TEXT NOT NULL, received_at TEXT NOT NULL, applied_at TEXT,
        target_channel TEXT, notification_id INTEGER, attempt_number INTEGER
    )""")
    connection.execute("CREATE INDEX IF NOT EXISTS whatsapp_receipts_pending ON whatsapp_delivery_receipts(applied_at,provider_message_id,recipient_number)")


def doctor_notifications_schema(*, patient_references: bool = True) -> str:
    patient_reference = " REFERENCES patients(id) ON DELETE CASCADE" if patient_references else ""
    conversation_reference = " REFERENCES conversations(id) ON DELETE CASCADE" if patient_references else ""
    return f"""
CREATE TABLE IF NOT EXISTS doctor_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key TEXT NOT NULL CHECK (length(trim(event_key)) > 0),
    recipient_number TEXT NOT NULL CHECK (length(trim(recipient_number)) > 0),
    notification_type TEXT NOT NULL CHECK (notification_type IN (
        'appointment_scheduled', 'appointment_modified', 'appointment_cancelled'
    )),
    patient_id INTEGER NOT NULL{patient_reference},
    conversation_id INTEGER NOT NULL{conversation_reference},
    appointment_id TEXT NOT NULL CHECK (length(trim(appointment_id)) > 0),
    body TEXT NOT NULL CHECK (length(trim(body)) > 0),
    template_data_json TEXT,
    template_payload_json TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'sending', 'sent', 'failed')),
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
