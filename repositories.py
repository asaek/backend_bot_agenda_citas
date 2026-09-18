from dataclasses import dataclass
import sqlite3


@dataclass(frozen=True, slots=True)
class PatientRecord:
    id: int
    whatsapp_number: str
    name: str | None
    created_at: str
    last_seen_at: str


@dataclass(frozen=True, slots=True)
class ConversationRecord:
    id: int
    patient_id: int
    status: str
    state: str
    context_json: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class MessageRecord:
    id: int
    conversation_id: int
    direction: str
    provider_message_id: str | None
    text: str
    message_type: str
    status: str
    reply_to_message_id: int | None
    created_at: str


def _patient_from_row(row: sqlite3.Row) -> PatientRecord:
    return PatientRecord(
        id=row["id"],
        whatsapp_number=row["whatsapp_number"],
        name=row["name"],
        created_at=row["created_at"],
        last_seen_at=row["last_seen_at"],
    )


def _conversation_from_row(row: sqlite3.Row) -> ConversationRecord:
    return ConversationRecord(
        id=row["id"],
        patient_id=row["patient_id"],
        status=row["status"],
        state=row["state"],
        context_json=row["context_json"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _message_from_row(row: sqlite3.Row) -> MessageRecord:
    return MessageRecord(
        id=row["id"],
        conversation_id=row["conversation_id"],
        direction=row["direction"],
        provider_message_id=row["provider_message_id"],
        text=row["text"],
        message_type=row["message_type"],
        status=row["status"],
        reply_to_message_id=row["reply_to_message_id"],
        created_at=row["created_at"],
    )


class PatientRepository:
    def get_by_id(self, connection: sqlite3.Connection, patient_id: int) -> PatientRecord | None:
        row = connection.execute(
            "SELECT * FROM patients WHERE id = ?",
            (patient_id,),
        ).fetchone()
        return _patient_from_row(row) if row else None

    def get_or_create(
        self,
        connection: sqlite3.Connection,
        whatsapp_number: str,
        now: str,
    ) -> PatientRecord:
        connection.execute(
            """
            INSERT OR IGNORE INTO patients (whatsapp_number, created_at, last_seen_at)
            VALUES (?, ?, ?)
            """,
            (whatsapp_number, now, now),
        )
        connection.execute(
            "UPDATE patients SET last_seen_at = ? WHERE whatsapp_number = ?",
            (now, whatsapp_number),
        )

        result = connection.execute(
            "SELECT * FROM patients WHERE whatsapp_number = ?",
            (whatsapp_number,),
        ).fetchone()
        if result is None:
            raise RuntimeError("No se pudo recuperar el paciente creado")
        return _patient_from_row(result)


class ConversationRepository:
    def get_by_id(
        self,
        connection: sqlite3.Connection,
        conversation_id: int,
    ) -> ConversationRecord | None:
        row = connection.execute(
            "SELECT * FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        return _conversation_from_row(row) if row else None

    def get_or_create_active(
        self,
        connection: sqlite3.Connection,
        patient_id: int,
        now: str,
    ) -> ConversationRecord:
        row = connection.execute(
            """
            SELECT * FROM conversations
            WHERE patient_id = ? AND status = 'active'
            ORDER BY id DESC
            LIMIT 1
            """,
            (patient_id,),
        ).fetchone()

        if row is None:
            try:
                connection.execute(
                    """
                    INSERT INTO conversations (
                        patient_id, status, state, context_json, created_at, updated_at
                    ) VALUES (?, 'active', 'new', '{}', ?, ?)
                    """,
                    (patient_id, now, now),
                )
            except sqlite3.IntegrityError:
                pass

        result = connection.execute(
            """
            SELECT * FROM conversations
            WHERE patient_id = ? AND status = 'active'
            ORDER BY id DESC
            LIMIT 1
            """,
            (patient_id,),
        ).fetchone()
        if result is None:
            raise RuntimeError("No se pudo recuperar la conversacion activa")
        return _conversation_from_row(result)

    def mark_active(self, connection: sqlite3.Connection, conversation_id: int, now: str) -> None:
        connection.execute(
            """
            UPDATE conversations
            SET state = 'active', updated_at = ?
            WHERE id = ?
            """,
            (now, conversation_id),
        )


class MessageRepository:
    def get_by_provider_id(
        self,
        connection: sqlite3.Connection,
        direction: str,
        provider_message_id: str,
    ) -> MessageRecord | None:
        row = connection.execute(
            """
            SELECT * FROM messages
            WHERE direction = ? AND provider_message_id = ?
            """,
            (direction, provider_message_id),
        ).fetchone()
        return _message_from_row(row) if row else None

    def create_incoming(
        self,
        connection: sqlite3.Connection,
        conversation_id: int,
        provider_message_id: str,
        text: str,
        message_type: str,
        now: str,
    ) -> MessageRecord:
        connection.execute(
            """
            INSERT OR IGNORE INTO messages (
                conversation_id, direction, provider_message_id, text,
                message_type, status, created_at
            ) VALUES (?, 'incoming', ?, ?, ?, 'received', ?)
            """,
            (conversation_id, provider_message_id, text, message_type, now),
        )
        row = connection.execute(
            """
            SELECT * FROM messages
            WHERE direction = 'incoming' AND provider_message_id = ?
            """,
            (provider_message_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("No se pudo recuperar el mensaje entrante")
        return _message_from_row(row)

    def get_reply(
        self,
        connection: sqlite3.Connection,
        incoming_message_id: int,
    ) -> MessageRecord | None:
        row = connection.execute(
            """
            SELECT * FROM messages
            WHERE direction = 'outgoing' AND reply_to_message_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (incoming_message_id,),
        ).fetchone()
        return _message_from_row(row) if row else None

    def save_reply(
        self,
        connection: sqlite3.Connection,
        incoming_message_id: int,
        conversation_id: int,
        text: str,
        status: str,
        provider_message_id: str | None,
        now: str,
    ) -> MessageRecord:
        existing = self.get_reply(connection, incoming_message_id)
        if existing is None:
            cursor = connection.execute(
                """
                INSERT INTO messages (
                    conversation_id, direction, provider_message_id, text,
                    message_type, status, reply_to_message_id, created_at
                ) VALUES (?, 'outgoing', ?, ?, 'text', ?, ?, ?)
                """,
                (
                    conversation_id,
                    provider_message_id,
                    text,
                    status,
                    incoming_message_id,
                    now,
                ),
            )
            message_id = cursor.lastrowid
        else:
            if existing.status == "sent" and status == "failed":
                return existing
            connection.execute(
                """
                UPDATE messages
                SET provider_message_id = ?, text = ?, status = ?
                WHERE id = ?
                """,
                (provider_message_id, text, status, existing.id),
            )
            message_id = existing.id

        row = connection.execute(
            "SELECT * FROM messages WHERE id = ?",
            (message_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("No se pudo recuperar la respuesta saliente")
        return _message_from_row(row)

    def list_for_conversation(
        self,
        connection: sqlite3.Connection,
        conversation_id: int,
    ) -> list[MessageRecord]:
        rows = connection.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
        return [_message_from_row(row) for row in rows]
