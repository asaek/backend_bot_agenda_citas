"""Bandeja durable de callbacks de Meta y proyeccion por mensaje/destinatario."""

import asyncio
import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from notification_delivery import normalize_doctor_recipient, utc_now
from notification_retry import TRANSIENT_PROVIDER_CODES, next_retry
from notification_schema import migrate_doctor_notifications
from persistence import SQLiteDatabase


logger = logging.getLogger(__name__)
STATUS_RANK = {None: -1, "accepted": 0, "sent": 1, "failed": 2, "delivered": 3, "read": 4}


def recipient_matches(value, recipient):
    try:
        return normalize_doctor_recipient(value) == recipient
    except (RuntimeError, ValueError, TypeError, AttributeError):
        return False


@dataclass(frozen=True)
class MetaDeliveryStatus:
    message_id: str
    recipient: str
    status: str
    timestamp: int
    codes: tuple[int, ...]
    phone_number_id: str = ""

    @property
    def key(self):
        values = [self.message_id, self.recipient, self.status, self.timestamp, self.codes, self.phone_number_id]
        return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def extract_delivery_statuses(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("entry"), list):
        return []
    result = []
    for entry in payload["entry"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("changes"), list):
            continue
        for change in entry["changes"]:
            value = change.get("value") if isinstance(change, dict) else None
            if not isinstance(value, dict) or not isinstance(value.get("statuses"), list):
                continue
            metadata = value.get("metadata", {})
            phone_id = metadata.get("phone_number_id", "") if isinstance(metadata, dict) else ""
            for status in value["statuses"]:
                if not isinstance(status, dict):
                    continue
                try:
                    message_id, recipient = status["id"], status["recipient_id"]
                    state, timestamp = status["status"], status["timestamp"]
                    if not isinstance(message_id, str) or not message_id.strip() or not isinstance(recipient, str):
                        continue
                    if not isinstance(state, str) or state not in {"sent", "delivered", "read", "failed"}:
                        continue
                    if isinstance(timestamp, bool) or not str(timestamp).isdigit():
                        continue
                    timestamp = int(timestamp)
                    datetime.fromtimestamp(timestamp, timezone.utc)
                    recipient = normalize_doctor_recipient(recipient)
                    errors = status.get("errors", [])
                    codes = tuple(sorted({error["code"] for error in errors if isinstance(error, dict)
                        and isinstance(error.get("code"), int) and not isinstance(error["code"], bool)
                        and error["code"] >= 0})) if isinstance(errors, list) else ()
                    result.append(MetaDeliveryStatus(message_id.strip(), recipient, state, timestamp,
                                                     codes, phone_id if isinstance(phone_id, str) else ""))
                except (KeyError, ValueError, TypeError, OverflowError, OSError, RuntimeError):
                    continue
    return result


@contextmanager
def target_connection(path):
    if not path.is_file():
        yield None
        return
    connection = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='doctor_notifications'").fetchone():
            yield None
            return
        columns = {row[1] for row in connection.execute("PRAGMA table_info(doctor_notifications)")}
        if "delivery_status" not in columns:
            migrate_doctor_notifications(connection)
            connection.commit()
        yield connection
    finally:
        connection.close()


class MetaDeliveryStatusService:
    def __init__(self, inbox_path, targets, *, now=utc_now):
        self.path = Path(inbox_path).expanduser().resolve()
        self.targets = {}
        seen = set()
        for channel, path in targets.items():
            path = Path(path).expanduser().resolve()
            if path not in seen:
                self.targets[channel] = path
                seen.add(path)
        self.now = now

    def receive(self, payload, *, reconcile=True):
        statuses = extract_delivery_statuses(payload)
        if not statuses:
            return 0
        database = SQLiteDatabase(str(self.path))
        with database.transaction() as db:
            for status in statuses:
                db.execute("""INSERT INTO whatsapp_delivery_receipts
                    (event_key,provider_message_id,recipient_number,status,provider_timestamp,
                     error_codes_json,phone_number_id,received_at) VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(event_key) DO NOTHING""",
                    (status.key, status.message_id, status.recipient, status.status, status.timestamp,
                     json.dumps(status.codes), status.phone_number_id, self.now()))
        if reconcile:
            self.flush()
        return len(statuses)

    def flush(self):
        try:
            self._flush_pending()
        except (sqlite3.Error, OSError) as error:
            logger.warning("Proyeccion Meta pendiente: %s", type(error).__name__)

    def _flush_pending(self):
        if not self.path.is_file():
            return
        database = SQLiteDatabase(str(self.path))
        with database.transaction() as db:
            pairs = db.execute("""SELECT DISTINCT provider_message_id,recipient_number
                FROM whatsapp_delivery_receipts WHERE applied_at IS NULL""").fetchall()
        for message_id, recipient in pairs:
            try:
                self._apply_pair(database, message_id, recipient)
            except (sqlite3.Error, OSError, ValueError, TypeError) as error:
                # El callback ya esta persistido; otro ciclo puede completar su proyeccion.
                logger.warning("Estado Meta pendiente de correlacion: %s", type(error).__name__)

    def _find_target(self, message_id, recipient):
        candidates = set()
        for channel, path in self.targets.items():
            with target_connection(path) as db:
                if db is None:
                    continue
                attempts = db.execute("""SELECT n.id,n.recipient_number,a.attempt_number
                    FROM doctor_notification_attempts a JOIN doctor_notifications n ON n.id=a.notification_id
                    WHERE a.provider_message_id=?""", (message_id,)).fetchall()
                matching = {row["id"] for row in attempts if recipient_matches(row["recipient_number"], recipient)}
                candidates.update((channel, row["id"], row["attempt_number"]) for row in attempts if row["id"] in matching)
                for row in db.execute("SELECT id,recipient_number FROM doctor_notifications WHERE provider_message_id=?", (message_id,)):
                    if row["id"] not in matching and recipient_matches(row["recipient_number"], recipient):
                        candidates.add((channel, row["id"], None))
        return next(iter(candidates)) if len(candidates) == 1 else None

    def _apply_pair(self, database, message_id, recipient):
        with database.transaction() as db:
            rows = db.execute("""SELECT * FROM whatsapp_delivery_receipts
                WHERE provider_message_id=? AND recipient_number=?""", (message_id, recipient)).fetchall()
            bindings = {(row["target_channel"], row["notification_id"], row["attempt_number"])
                        for row in rows if row["target_channel"] in self.targets and row["notification_id"] is not None}
        target = next(iter(bindings)) if len(bindings) == 1 else self._find_target(message_id, recipient)
        if target is None:
            if self._is_patient_reply(database, message_id, recipient):
                with database.transaction() as db:
                    db.executemany("UPDATE whatsapp_delivery_receipts SET target_channel='patient',applied_at=? WHERE event_key=?",
                                   [(self.now(), row["event_key"]) for row in rows])
            return
        channel, notification_id, attempt_number = target
        with database.transaction() as db:
            db.executemany("""UPDATE whatsapp_delivery_receipts SET target_channel=?,notification_id=?,attempt_number=?
                WHERE event_key=? AND applied_at IS NULL""",
                [(channel, notification_id, attempt_number, row["event_key"]) for row in rows])
        strongest = max(rows, key=lambda row: (STATUS_RANK[row["status"]], row["provider_timestamp"], row["event_key"]))
        with target_connection(self.targets[channel]) as db:
            if db is None or not self._project(db, notification_id, attempt_number, message_id, recipient, strongest):
                return
        with database.transaction() as db:
            db.executemany("UPDATE whatsapp_delivery_receipts SET applied_at=? WHERE event_key=? AND applied_at IS NULL",
                           [(self.now(), row["event_key"]) for row in rows])

    def _is_patient_reply(self, database, message_id, recipient):
        with database.transaction() as db:
            rows = db.execute("""SELECT p.whatsapp_number FROM messages m
                JOIN conversations c ON c.id=m.conversation_id JOIN patients p ON p.id=c.patient_id
                WHERE m.direction='outgoing' AND m.provider_message_id=?""", (message_id,)).fetchall()
        return any(recipient_matches(row[0], recipient) for row in rows)

    def _project(self, db, notification_id, attempt_number, message_id, recipient, receipt):
        db.execute("BEGIN IMMEDIATE")
        try:
            notice = db.execute("SELECT * FROM doctor_notifications WHERE id=?", (notification_id,)).fetchone()
            if notice is None or not recipient_matches(notice["recipient_number"], recipient):
                return False
            attempt = None
            if attempt_number is not None:
                attempt = db.execute("""SELECT * FROM doctor_notification_attempts
                    WHERE notification_id=? AND attempt_number=? AND provider_message_id=?""",
                    (notification_id, attempt_number, message_id)).fetchone()
                if attempt is None:
                    return False
            current = notice["provider_message_id"] == message_id and (attempt_number is None or notice["attempt_count"] == attempt_number)
            existing = attempt if attempt is not None else notice
            state = receipt["status"]
            if STATUS_RANK.get(existing["delivery_status"], -1) > STATUS_RANK[state]:
                return True
            at = datetime.fromtimestamp(receipt["provider_timestamp"], timezone.utc).isoformat()
            if existing["delivery_status"] == state and existing["delivery_status_at"] and existing["delivery_status_at"] > at:
                return True
            codes = json.loads(receipt["error_codes_json"]) if state == "failed" else []
            if state == "failed" and existing["delivery_status"] == state and existing["delivery_status_at"] == at:
                codes = sorted(set(codes) | set(json.loads(existing["delivery_error_codes_json"] or "[]")))
            values = (state, at, json.dumps(codes))
            if attempt is not None:
                db.execute("""UPDATE doctor_notification_attempts SET delivery_status=?,delivery_status_at=?,delivery_error_codes_json=?
                    WHERE notification_id=? AND attempt_number=?""", (*values, notification_id, attempt_number))
            if current:
                db.execute("""UPDATE doctor_notifications SET delivery_status=?,delivery_status_at=?,delivery_error_codes_json=?
                    WHERE id=?""", (*values, notification_id))
                if state == "failed" and notice["delivery_status"] != "failed":
                    kind = "transient" if TRANSIENT_PROVIDER_CODES.intersection(codes) else "configuration"
                    key = attempt["configuration_key"] if attempt is not None else None
                    due = next_retry(self.now(), notice["failure_count"]) if kind == "transient" else None
                    reason = "Meta informó un fallo de entrega" + (" (" + ",".join(map(str, codes)) + ")" if codes else "") + "."
                    db.execute("""UPDATE doctor_notifications SET status='failed',retry_kind=?,next_attempt_at=?,
                        blocked_configuration_key=?,last_error=?,failure_count=failure_count+1,updated_at=? WHERE id=?""",
                        (kind, due, key, reason, self.now(), notification_id))
                    if attempt is not None:
                        db.execute("""UPDATE doctor_notification_attempts SET classification=?,provider_code=?
                            WHERE notification_id=? AND attempt_number=?""",
                            (kind, codes[0] if codes else None, notification_id, attempt_number))
                elif state in {"delivered", "read"}:
                    db.execute("""UPDATE doctor_notifications SET status='sent',retry_kind='ready',next_attempt_at=NULL,
                        blocked_configuration_key=NULL,last_error=NULL,failure_count=0 WHERE id=?""", (notification_id,))
            db.commit()
            return True
        finally:
            if db.in_transaction:
                db.rollback()


class MetaDeliveryStatusWorker:
    def __init__(self, service, *, interval_seconds=5):
        self.service = service
        self.interval_seconds = interval_seconds
        self._task = None

    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def _run(self):
        while True:
            try:
                await asyncio.to_thread(self.service.flush)
            except (sqlite3.Error, OSError) as error:
                logger.warning("No se pudo recuperar la bandeja de estados Meta: %s", type(error).__name__)
            await asyncio.sleep(self.interval_seconds)

    async def close(self):
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
