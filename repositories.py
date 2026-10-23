from dataclasses import dataclass
import sqlite3

from notification_domain import AppointmentNotificationEvent, UNPREPARED_NOTIFICATION_BODIES


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


@dataclass(frozen=True, slots=True)
class LLMFailureRecord:
    id: int
    conversation_id: int
    incoming_message_id: int
    error_type: str
    http_status_code: int | None
    created_at: str


@dataclass(frozen=True, slots=True)
class DoctorNotificationRecord:
    id: int
    event_key: str
    recipient_number: str
    notification_type: str
    patient_id: int
    conversation_id: int
    appointment_id: str
    body: str
    status: str
    attempt_count: int
    last_error: str | None
    provider_message_id: str | None
    created_at: str
    updated_at: str
    sent_at: str | None
    template_data_json: str | None = None
    template_payload_json: str | None = None
    template_version: str | None = None
    event_json: str | None = None
    context_json: str | None = None
    next_attempt_at: str | None = None
    retry_kind: str = "ready"
    blocked_configuration_key: str | None = None
    failure_count: int = 0
    delivery_status: str | None = None
    delivery_status_at: str | None = None
    delivery_error_codes_json: str | None = None
    api_accepted_at: str | None = None


@dataclass(frozen=True, slots=True)
class AppointmentRecord:
    id: int
    calendar_id: str
    google_event_id: str
    patient_id: int
    status: str
    start_at: str
    end_at: str
    reason: str
    last_synced_at: str
    created_at: str
    updated_at: str


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


def _appointment_from_row(row: sqlite3.Row) -> AppointmentRecord:
    return AppointmentRecord(
        id=row["id"],
        calendar_id=row["calendar_id"],
        google_event_id=row["google_event_id"],
        patient_id=row["patient_id"],
        status=row["status"],
        start_at=row["start_at"],
        end_at=row["end_at"],
        reason=row["reason"],
        last_synced_at=row["last_synced_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _doctor_notification_from_row(row: sqlite3.Row) -> DoctorNotificationRecord:
    return DoctorNotificationRecord(
        id=row["id"],
        event_key=row["event_key"],
        recipient_number=row["recipient_number"],
        notification_type=row["notification_type"],
        patient_id=row["patient_id"],
        conversation_id=row["conversation_id"],
        appointment_id=row["appointment_id"],
        body=row["body"],
        status=row["status"],
        attempt_count=row["attempt_count"],
        last_error=row["last_error"],
        provider_message_id=row["provider_message_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        sent_at=row["sent_at"],
        template_data_json=row["template_data_json"],
        template_payload_json=row["template_payload_json"],
        template_version=row["template_version"],
        event_json=row["event_json"],
        context_json=row["context_json"],
        next_attempt_at=row["next_attempt_at"],
        retry_kind=row["retry_kind"],
        blocked_configuration_key=row["blocked_configuration_key"],
        failure_count=row["failure_count"],
        delivery_status=row["delivery_status"],
        delivery_status_at=row["delivery_status_at"],
        delivery_error_codes_json=row["delivery_error_codes_json"],
        api_accepted_at=row["api_accepted_at"],
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

    def update_name(
        self,
        connection: sqlite3.Connection,
        patient_id: int,
        name: str,
        now: str,
    ) -> PatientRecord:
        connection.execute(
            "UPDATE patients SET name = ?, last_seen_at = ? WHERE id = ?",
            (name, now, patient_id),
        )
        patient = self.get_by_id(connection, patient_id)
        if patient is None:
            raise RuntimeError("No se pudo recuperar el paciente actualizado")
        return patient


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

    def update_context(
        self,
        connection: sqlite3.Connection,
        conversation_id: int,
        context_json: str,
        now: str,
    ) -> None:
        connection.execute(
            """
            UPDATE conversations
            SET context_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (context_json, now, conversation_id),
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


class LLMFailureRepository:
    def create(
        self,
        connection: sqlite3.Connection,
        conversation_id: int,
        incoming_message_id: int,
        error_type: str,
        now: str,
        http_status_code: int | None = None,
    ) -> LLMFailureRecord:
        cursor = connection.execute(
            """
            INSERT INTO llm_failures (
                conversation_id, incoming_message_id, error_type,
                http_status_code, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                incoming_message_id,
                error_type,
                http_status_code,
                now,
            ),
        )
        row = connection.execute(
            "SELECT * FROM llm_failures WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        if row is None:
            raise RuntimeError("No se pudo recuperar el fallo del LLM")
        return LLMFailureRecord(
            id=row["id"],
            conversation_id=row["conversation_id"],
            incoming_message_id=row["incoming_message_id"],
            error_type=row["error_type"],
            http_status_code=row["http_status_code"],
            created_at=row["created_at"],
        )


class DoctorNotificationRepository:
    def previous_event_message_id(
        self,
        connection: sqlite3.Connection,
        *,
        event: AppointmentNotificationEvent,
    ) -> int:
        """Encuentra la ultima gestion notificada anterior, incluso si el envio fallo."""
        rows = connection.execute(
            """
            SELECT DISTINCT event_key FROM doctor_notifications
            WHERE patient_id = ? AND conversation_id = ?
            """,
            (event.patient_scope.patient_id, event.patient_scope.conversation_id),
        ).fetchall()
        previous_id = 0
        for row in rows:
            parts = row["event_key"].split(":", 2)
            if len(parts) != 3 or parts[0] != "appointment" or not parts[1].isdigit():
                continue
            message_id = int(parts[1])
            if previous_id < message_id < event.incoming_message_id:
                previous_id = message_id
        return previous_id

    def get_by_id(
        self,
        connection: sqlite3.Connection,
        notification_id: int,
    ) -> DoctorNotificationRecord | None:
        row = connection.execute(
            "SELECT * FROM doctor_notifications WHERE id = ?",
            (notification_id,),
        ).fetchone()
        return _doctor_notification_from_row(row) if row else None

    def get_by_event_and_recipient(
        self,
        connection: sqlite3.Connection,
        event_key: str,
        recipient_number: str,
    ) -> DoctorNotificationRecord | None:
        row = connection.execute(
            """
            SELECT * FROM doctor_notifications
            WHERE event_key = ? AND recipient_number = ?
            """,
            (event_key.strip(), recipient_number.strip()),
        ).fetchone()
        return _doctor_notification_from_row(row) if row else None

    def create_pending(
        self,
        connection: sqlite3.Connection,
        *,
        event_key: str,
        recipient_number: str,
        notification_type: str,
        patient_id: int,
        conversation_id: int,
        appointment_id: str,
        body: str,
        now: str,
        template_data_json: str | None = None,
    ) -> DoctorNotificationRecord:
        event_key = event_key.strip()
        recipient_number = recipient_number.strip()
        notification_type = getattr(notification_type, "value", notification_type)
        connection.execute(
            """
            INSERT INTO doctor_notifications (
                event_key, recipient_number, notification_type,
                patient_id, conversation_id, appointment_id, body,
                status, attempt_count, created_at, updated_at, template_data_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?)
            ON CONFLICT(event_key, recipient_number) DO NOTHING
            """,
            (
                event_key,
                recipient_number,
                notification_type,
                patient_id,
                conversation_id,
                appointment_id,
                body,
                now,
                now,
                template_data_json,
            ),
        )
        record = self.get_by_event_and_recipient(
            connection,
            event_key,
            recipient_number,
        )
        if record is None:
            raise RuntimeError("No se pudo recuperar la notificacion creada")
        return record

    def create_pending_for_event(
        self,
        connection: sqlite3.Connection,
        *,
        event: AppointmentNotificationEvent,
        recipient_number: str,
        body: str,
        now: str,
        template_data_json: str | None = None,
    ) -> DoctorNotificationRecord:
        return self.create_pending(
            connection,
            event_key=event.event_key,
            recipient_number=recipient_number,
            notification_type=event.notification_type.value,
            patient_id=event.patient_scope.patient_id,
            conversation_id=event.patient_scope.conversation_id,
            appointment_id=event.appointment.id,
            body=body,
            now=now,
            template_data_json=template_data_json,
        )

    def prepare_content(
        self, connection: sqlite3.Connection, *, event_key: str, body: str,
        template_data_json: str | None = None,
    ) -> tuple[str, str | None]:
        """Congela un cuerpo por evento; solo completa marcadores sin intentos."""
        records = self.list_for_event(connection, event_key)
        prepared = next((record for record in records if record.body not in UNPREPARED_NOTIFICATION_BODIES), None)
        if prepared is not None:
            body = prepared.body
            template_data_json = prepared.template_data_json
        connection.execute("""UPDATE doctor_notifications SET body=?, template_data_json=?
            WHERE event_key=? AND status IN ('pending','failed') AND attempt_count=0 AND body IN (?,?)""",
            (body, template_data_json, event_key, *UNPREPARED_NOTIFICATION_BODIES))
        return body, template_data_json

    def mark_pending(
        self, connection: sqlite3.Connection, notification_id: int, *, reason: str, now: str,
        configuration_key: str | None = None,
    ) -> DoctorNotificationRecord:
        """Retiene un aviso sin reclamar un envio ni alterar resultados definitivos."""
        connection.execute(
            """UPDATE doctor_notifications SET status='pending', last_error=?, updated_at=?,
                   retry_kind='configuration', blocked_configuration_key=?
               WHERE id=? AND status IN ('pending','failed')""",
            (reason, now, configuration_key, notification_id),
        )
        record = self.get_by_id(connection, notification_id)
        if record is None:
            raise RuntimeError("No se pudo recuperar la notificacion pendiente")
        return record

    def save_event_context(self, connection, event_key, event_json, context_json):
        connection.execute("""UPDATE doctor_notifications
            SET event_json=COALESCE(event_json,?), context_json=COALESCE(context_json,?)
            WHERE event_key=?""", (event_json, context_json, event_key))

    def recovery_records(self, connection):
        rows = connection.execute("""SELECT * FROM doctor_notifications
            WHERE status IN ('pending','failed') AND event_json IS NOT NULL ORDER BY id""").fetchall()
        return [_doctor_notification_from_row(row) for row in rows]

    def list_for_event(
        self,
        connection: sqlite3.Connection,
        event_key: str,
    ) -> list[DoctorNotificationRecord]:
        rows = connection.execute(
            """
            SELECT * FROM doctor_notifications
            WHERE event_key = ?
            ORDER BY id
            """,
            (event_key.strip(),),
        ).fetchall()
        return [_doctor_notification_from_row(row) for row in rows]

    def list_for_recipient(
        self,
        connection: sqlite3.Connection,
        recipient_number: str,
    ) -> list[DoctorNotificationRecord]:
        rows = connection.execute(
            """
            SELECT * FROM doctor_notifications
            WHERE recipient_number = ?
            ORDER BY id
            """,
            (recipient_number.strip(),),
        ).fetchall()
        return [_doctor_notification_from_row(row) for row in rows]

    def list_retryable(
        self,
        connection: sqlite3.Connection,
    ) -> list[DoctorNotificationRecord]:
        rows = connection.execute(
            """
            SELECT * FROM doctor_notifications
            WHERE status IN ('pending', 'failed')
            ORDER BY id
            """
        ).fetchall()
        return [_doctor_notification_from_row(row) for row in rows]

    def claim_for_send(
        self,
        connection: sqlite3.Connection,
        notification_id: int,
        now: str,
        template_payload_json: str | None = None,
        configuration_key: str = "",
        template_version: str | None = None,
        replace_payload: bool = False,
    ) -> DoctorNotificationRecord | None:
        """Claims one pending/failed row without claiming it twice concurrently."""
        cursor = connection.execute(
            """
            UPDATE doctor_notifications
            SET status = 'sending',
                attempt_count = attempt_count + 1,
                last_error = NULL,
                provider_message_id = NULL,
                sent_at = NULL,
                template_payload_json = CASE WHEN ? THEN ? ELSE COALESCE(template_payload_json, ?) END,
                template_version = CASE WHEN ? THEN ? ELSE COALESCE(template_version, ?) END,
                retry_kind = 'uncertain', blocked_configuration_key = NULL, next_attempt_at = NULL,
                delivery_status = NULL, delivery_status_at = NULL, delivery_error_codes_json = NULL, api_accepted_at = NULL,
                updated_at = ?
            WHERE id = ? AND status IN ('pending', 'failed')
                AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                AND (retry_kind <> 'configuration' OR
                     (blocked_configuration_key IS NOT NULL AND blocked_configuration_key <> ?))
            """,
            (replace_payload, template_payload_json, template_payload_json,
             replace_payload, template_version, template_version, now, notification_id, now, configuration_key),
        )
        if cursor.rowcount != 1:
            return None
        record = self.get_by_id(connection, notification_id)
        connection.execute("""INSERT INTO doctor_notification_attempts
            (notification_id,attempt_number,state,transport,body,template_payload_json,template_version,started_at,configuration_key)
            VALUES (?,?,'sending',?,?,?,?,?,?)""",
            (record.id, record.attempt_count, "template" if record.template_payload_json else "text",
             record.body, record.template_payload_json, record.template_version, now, configuration_key))
        return record

    def mark_sent(
        self,
        connection: sqlite3.Connection,
        notification_id: int,
        *,
        provider_message_id: str | None,
        now: str,
        expected_attempt: int | None = None,
    ) -> DoctorNotificationRecord:
        normalized_provider_message_id = (
            provider_message_id.strip()
            if provider_message_id is not None and provider_message_id.strip()
            else None
        )
        connection.execute(
            """
            UPDATE doctor_notifications
            SET status = 'sent',
                last_error = NULL,
                retry_kind = 'ready', next_attempt_at = NULL, blocked_configuration_key = NULL,
                provider_message_id = ?,
                delivery_status = COALESCE(delivery_status,'accepted'), api_accepted_at = COALESCE(api_accepted_at,?),
                sent_at = ?,
                updated_at = ?
            WHERE id = ? AND status <> 'sent' AND (? IS NULL OR (status='sending' AND attempt_count=?))
            """,
            (
                normalized_provider_message_id,
                now,
                now,
                now,
                notification_id,
                expected_attempt,
                expected_attempt,
            ),
        )
        if expected_attempt is not None:
            connection.execute("""UPDATE doctor_notification_attempts SET state='sent', completed_at=?, provider_message_id=?,
                    delivery_status=COALESCE(delivery_status,'accepted'), api_accepted_at=COALESCE(api_accepted_at,?)
                WHERE notification_id=? AND attempt_number=? AND state='sending'""",
                (now, normalized_provider_message_id, now, notification_id, expected_attempt))
        record = self.get_by_id(connection, notification_id)
        if record is None:
            raise RuntimeError("No se pudo recuperar la notificacion enviada")
        return record

    def mark_failed(
        self,
        connection: sqlite3.Connection,
        notification_id: int,
        *,
        error: str,
        now: str,
        retry_kind: str = "transient",
        next_attempt_at: str | None = None,
        configuration_key: str | None = None,
        expected_attempt: int | None = None,
        http_status: int | None = None,
        provider_code: int | None = None,
    ) -> DoctorNotificationRecord:
        error = error.strip()
        if not error:
            raise ValueError("error no puede estar vacio")
        connection.execute(
            """
            UPDATE doctor_notifications
            SET status = 'failed',
                last_error = ?,
                retry_kind = ?, next_attempt_at = ?, blocked_configuration_key = ?,
                failure_count = failure_count + 1,
                provider_message_id = NULL,
                sent_at = NULL,
                updated_at = ?
            WHERE id = ? AND status <> 'sent' AND (? IS NULL OR (status='sending' AND attempt_count=?))
            """,
            (error, retry_kind, next_attempt_at, configuration_key, now, notification_id, expected_attempt, expected_attempt),
        )
        if expected_attempt is not None:
            connection.execute("""UPDATE doctor_notification_attempts
                SET state='failed', completed_at=?, classification=?, http_status=?, provider_code=?
                WHERE notification_id=? AND attempt_number=? AND state='sending'""",
                (now, retry_kind, http_status, provider_code, notification_id, expected_attempt))
        record = self.get_by_id(connection, notification_id)
        if record is None:
            raise RuntimeError("No se pudo recuperar la notificacion fallida")
        return record

    def mark_uncertain(
        self, connection: sqlite3.Connection, notification_id: int, *, error: str, now: str,
        expected_attempt: int | None = None,
    ) -> DoctorNotificationRecord:
        connection.execute("""UPDATE doctor_notifications SET last_error=?, updated_at=?, retry_kind='uncertain'
            WHERE id=? AND status='sending' AND (? IS NULL OR attempt_count=?)""",
            (error, now, notification_id, expected_attempt, expected_attempt))
        if expected_attempt is not None:
            connection.execute("""UPDATE doctor_notification_attempts
                SET state='uncertain', completed_at=?, classification='uncertain'
                WHERE notification_id=? AND attempt_number=? AND state='sending'""", (now, notification_id, expected_attempt))
        record = self.get_by_id(connection, notification_id)
        if record is None:
            raise RuntimeError("No se pudo recuperar la notificacion incierta")
        return record

    def reconcile(self, connection, notification_id, *, attempt_number, outcome, reason, now,
                  provider_message_id=None):
        record = self.get_by_id(connection, notification_id)
        if record is None or record.attempt_count != attempt_number:
            raise ValueError("El aviso o el numero de intento no coincide")
        if outcome == "configuration_fixed":
            if record.status not in {"pending", "failed"} or record.retry_kind != "configuration":
                raise ValueError("El aviso no esta detenido por configuracion")
            connection.execute("""UPDATE doctor_notifications SET retry_kind='ready',
                blocked_configuration_key=NULL, next_attempt_at=?, last_error=?, updated_at=?,
                template_payload_json=NULL, template_version=NULL WHERE id=?""",
                (now, reason, now, notification_id))
        else:
            if record.status != "sending" or outcome not in {"accepted", "not_delivered"}:
                raise ValueError("Solo se concilian envios inciertos")
            if outcome == "accepted" and not (provider_message_id or "").strip():
                raise ValueError("Se requiere el identificador recuperado de Meta")
            connection.execute("""INSERT INTO doctor_notification_attempts
                (notification_id,attempt_number,state,transport,body,template_payload_json,template_version)
                VALUES (?,?,'uncertain',?,?,?,?) ON CONFLICT(notification_id,attempt_number) DO NOTHING""",
                (record.id, record.attempt_count, "template" if record.template_payload_json else "text",
                 record.body, record.template_payload_json, record.template_version))
            if outcome == "accepted":
                connection.execute("""UPDATE doctor_notifications SET status='sent', retry_kind='ready',
                    provider_message_id=?, next_attempt_at=NULL, last_error=NULL, sent_at=?, updated_at=?,
                    delivery_status=COALESCE(delivery_status,'accepted'), api_accepted_at=COALESCE(api_accepted_at,?) WHERE id=?""",
                    (provider_message_id.strip(), now, now, now, notification_id))
            else:
                connection.execute("""UPDATE doctor_notifications SET status='failed', retry_kind='transient',
                    blocked_configuration_key=NULL, next_attempt_at=?, last_error=?, updated_at=? WHERE id=?""",
                    (now, reason, now, notification_id))
        connection.execute("""UPDATE doctor_notification_attempts
            SET state=CASE WHEN ?='accepted' THEN 'sent' ELSE 'failed' END,
                reconciliation_outcome=?, reconciliation_reason=?, reconciled_at=?
                , provider_message_id=COALESCE(?,provider_message_id)
                , delivery_status=CASE WHEN ?='accepted' THEN COALESCE(delivery_status,'accepted') ELSE delivery_status END
                , api_accepted_at=CASE WHEN ?='accepted' THEN COALESCE(api_accepted_at,?) ELSE api_accepted_at END
            WHERE notification_id=? AND attempt_number=?""",
            (outcome, outcome, reason, now, provider_message_id, outcome, outcome, now, notification_id, attempt_number))
        return self.get_by_id(connection, notification_id)


class AppointmentRepository:
    def get_by_id(
        self,
        connection: sqlite3.Connection,
        appointment_id: int,
    ) -> AppointmentRecord | None:
        row = connection.execute(
            "SELECT * FROM appointments WHERE id = ?",
            (appointment_id,),
        ).fetchone()
        return _appointment_from_row(row) if row else None

    def get_by_google_event(
        self,
        connection: sqlite3.Connection,
        calendar_id: str,
        google_event_id: str,
    ) -> AppointmentRecord | None:
        row = connection.execute(
            """
            SELECT * FROM appointments
            WHERE calendar_id = ? AND google_event_id = ?
            """,
            (calendar_id, google_event_id),
        ).fetchone()
        return _appointment_from_row(row) if row else None

    def list_for_patient(
        self,
        connection: sqlite3.Connection,
        patient_id: int,
    ) -> list[AppointmentRecord]:
        rows = connection.execute(
            """
            SELECT * FROM appointments
            WHERE patient_id = ?
            ORDER BY start_at, id
            """,
            (patient_id,),
        ).fetchall()
        return [_appointment_from_row(row) for row in rows]

    def upsert_synced(
        self,
        connection: sqlite3.Connection,
        *,
        calendar_id: str,
        google_event_id: str,
        patient_id: int,
        status: str,
        start_at: str,
        end_at: str,
        reason: str,
        synced_at: str,
    ) -> AppointmentRecord:
        existing = self.get_by_google_event(connection, calendar_id, google_event_id)
        if existing is None:
            cursor = connection.execute(
                """
                INSERT INTO appointments (
                    calendar_id, google_event_id, patient_id, status,
                    start_at, end_at, reason, last_synced_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    calendar_id,
                    google_event_id,
                    patient_id,
                    status,
                    start_at,
                    end_at,
                    reason,
                    synced_at,
                    synced_at,
                    synced_at,
                ),
            )
            appointment_id = cursor.lastrowid
        else:
            if existing.patient_id != patient_id:
                raise RuntimeError("El evento de Google pertenece a otro paciente")
            connection.execute(
                """
                UPDATE appointments
                SET status = ?, start_at = ?, end_at = ?, reason = ?,
                    last_synced_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    start_at,
                    end_at,
                    reason,
                    synced_at,
                    synced_at,
                    existing.id,
                ),
            )
            appointment_id = existing.id

        row = self.get_by_id(connection, appointment_id)
        if row is None:
            raise RuntimeError("No se pudo recuperar la cita persistida")
        return row
