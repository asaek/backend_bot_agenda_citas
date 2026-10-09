"""Persistencia de respuestas preparadas e intentos de entrega al paciente."""

from dataclasses import dataclass
import sqlite3


@dataclass(frozen=True, slots=True)
class PreparedReplyRecord:
    incoming_message_id: int
    status: str
    body: str | None
    notification_events_json: str
    notifications_completed: bool


class ReplyDeliveryRepository:
    def get(self, connection: sqlite3.Connection, incoming_id: int) -> PreparedReplyRecord | None:
        row = connection.execute(
            "SELECT * FROM reply_outbox WHERE incoming_message_id = ?", (incoming_id,),
        ).fetchone()
        if row is None:
            return None
        return PreparedReplyRecord(
            incoming_message_id=row["incoming_message_id"],
            status=row["status"],
            body=row["body"],
            notification_events_json=row["notification_events_json"],
            notifications_completed=bool(row["notifications_completed"]),
        )

    def has_later_processed_turn(
        self, connection: sqlite3.Connection, conversation_id: int, incoming_id: int,
    ) -> bool:
        row = connection.execute(
            """
            SELECT 1 FROM messages incoming
            WHERE incoming.conversation_id = ? AND incoming.direction = 'incoming'
              AND incoming.id > ? AND (
                EXISTS (SELECT 1 FROM messages outgoing
                        WHERE outgoing.reply_to_message_id = incoming.id
                          AND outgoing.direction = 'outgoing')
                OR EXISTS (SELECT 1 FROM reply_outbox r
                           WHERE r.incoming_message_id = incoming.id
                             AND r.status IN ('ready', 'sending', 'sent', 'failed', 'uncertain'))
              )
            LIMIT 1
            """,
            (conversation_id, incoming_id),
        ).fetchone()
        return row is not None

    def create(self, connection: sqlite3.Connection, incoming_id: int, status: str, now: str) -> None:
        connection.execute(
            """
            INSERT INTO reply_outbox (incoming_message_id, status, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (incoming_id, status, now, now),
        )

    def set_status(self, connection: sqlite3.Connection, incoming_id: int, status: str, now: str) -> None:
        connection.execute(
            "UPDATE reply_outbox SET status = ?, updated_at = ? WHERE incoming_message_id = ?",
            (status, now, incoming_id),
        )

    def prepare(
        self, connection: sqlite3.Connection, incoming_id: int, body: str, events_json: str, now: str,
    ) -> None:
        cursor = connection.execute(
            """
            UPDATE reply_outbox
            SET status = 'ready', body = ?, notification_events_json = ?, updated_at = ?
            WHERE incoming_message_id = ? AND status IN ('processing', 'ready', 'failed')
            """,
            (body, events_json, now, incoming_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("La respuesta no esta disponible para preparacion")

    def start_attempt(self, connection: sqlite3.Connection, incoming_id: int, now: str) -> int:
        cursor = connection.execute(
            """
            UPDATE reply_outbox SET status = 'sending', updated_at = ?
            WHERE incoming_message_id = ? AND status = 'ready' AND body IS NOT NULL
            """,
            (now, incoming_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("La respuesta no esta disponible para envio")
        cursor = connection.execute(
            """
            INSERT INTO reply_delivery_attempts (incoming_message_id, status, started_at)
            VALUES (?, 'sending', ?)
            """,
            (incoming_id, now),
        )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def finish_attempt(
        self, connection: sqlite3.Connection, attempt_id: int, status: str, now: str,
        provider_message_id: str | None = None, error_type: str | None = None,
        http_status_code: int | None = None,
    ) -> None:
        connection.execute(
            """
            UPDATE reply_delivery_attempts
            SET status = ?, completed_at = ?, provider_message_id = ?,
                error_type = ?, http_status_code = ?
            WHERE id = ? AND status = 'sending'
            """,
            (status, now, provider_message_id, error_type, http_status_code, attempt_id),
        )

    def interrupt(self, connection: sqlite3.Connection, incoming_id: int, now: str) -> None:
        connection.execute(
            """
            UPDATE reply_outbox SET status = 'uncertain', updated_at = ?
            WHERE incoming_message_id = ? AND status IN ('processing', 'sending')
            """,
            (now, incoming_id),
        )
        connection.execute(
            """
            UPDATE reply_delivery_attempts
            SET status = 'uncertain', completed_at = ?, error_type = 'InterruptedProcessing'
            WHERE incoming_message_id = ? AND status = 'sending'
            """,
            (now, incoming_id),
        )

    def complete_notifications(self, connection: sqlite3.Connection, incoming_id: int, now: str) -> None:
        connection.execute(
            """
            UPDATE reply_outbox SET notifications_completed = 1, updated_at = ?
            WHERE incoming_message_id = ? AND status = 'sent'
            """,
            (now, incoming_id),
        )
