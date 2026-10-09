"""Separa el procesamiento de un turno de sus reintentos de transporte."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
import json
import logging
from pathlib import Path
from weakref import WeakValueDictionary

import httpx

from calendar_domain import Appointment, AppointmentStatus, PatientScope, ToolName
from conversation_service import ConversationContext, utc_now
from notification_domain import AppointmentNotificationEvent, AppointmentNotificationType
from persistence import SQLiteDatabase
from reply_delivery_repository import ReplyDeliveryRepository
from repositories import MessageRepository


logger = logging.getLogger(__name__)
_patient_locks: WeakValueDictionary[tuple[asyncio.AbstractEventLoop, str, str], asyncio.Lock] = (
    WeakValueDictionary()
)


@asynccontextmanager
async def patient_turn(database_path: str, sender: str) -> AsyncIterator[None]:
    """Serializa el runtime de un proceso sin retener bloqueos de pacientes inactivos."""
    key = (asyncio.get_running_loop(), str(Path(database_path).resolve()), sender)
    lock = _patient_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _patient_locks[key] = lock
    async with lock:
        yield


@dataclass(frozen=True, slots=True)
class ReplyPlan:
    body: str | None
    events: tuple[AppointmentNotificationEvent, ...] = ()
    send_required: bool = True


def _encode_events(events: Sequence[AppointmentNotificationEvent]) -> str:
    return json.dumps([asdict(event) for event in events], default=lambda value: value.isoformat())


def _decode_events(raw: str) -> tuple[AppointmentNotificationEvent, ...]:
    events = []
    for value in json.loads(raw):
        scope = PatientScope(**value["patient_scope"])
        appointment = dict(value["appointment"])
        appointment["patient_scope"] = PatientScope(**appointment["patient_scope"])
        appointment["start_at"] = datetime.fromisoformat(appointment["start_at"])
        appointment["end_at"] = datetime.fromisoformat(appointment["end_at"])
        appointment["status"] = AppointmentStatus(appointment["status"])
        events.append(AppointmentNotificationEvent(
            notification_type=AppointmentNotificationType(value["notification_type"]),
            tool_name=ToolName(value["tool_name"]),
            appointment=Appointment(**appointment),
            patient_scope=scope,
            incoming_message_id=value["incoming_message_id"],
            tool_call_id=value["tool_call_id"],
        ))
    return tuple(events)


class ReplyDeliveryService:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database
        self.replies = ReplyDeliveryRepository()
        self.messages = MessageRepository()

    def begin(self, context: ConversationContext) -> ReplyPlan | None:
        """Reclama un turno nuevo, recupera su texto o descarta un reintento antiguo."""
        incoming_id = context.incoming_message_id
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            outgoing = self.messages.get_reply(connection, incoming_id)
            saved = self.replies.get(connection, incoming_id)
            if outgoing is not None and outgoing.status == "sent":
                if saved is not None and not saved.notifications_completed:
                    return ReplyPlan(saved.body, _decode_events(saved.notification_events_json), False)
                return None
            if self.replies.has_later_processed_turn(connection, context.conversation_id, incoming_id):
                if saved is None:
                    self.replies.create(connection, incoming_id, "superseded", now)
                else:
                    self.replies.set_status(connection, incoming_id, "superseded", now)
                logger.info("Webhook retry ignored: incoming_id=%s reason=superseded", incoming_id)
                return None
            if saved is not None:
                if saved.status in {"ready", "failed"}:
                    return ReplyPlan(saved.body, _decode_events(saved.notification_events_json))
                self.replies.interrupt(connection, incoming_id, now)
                logger.warning(
                    "Webhook retry ignored: incoming_id=%s state=%s", incoming_id, saved.status,
                )
                return None
            self.replies.create(connection, incoming_id, "processing", now)
            # Respuestas historicas fallidas se recuperan sin inventar eventos ni regenerarlas.
            return ReplyPlan(outgoing.text if outgoing is not None else None)

    def prepare(
        self, context: ConversationContext, body: str, events: Sequence[AppointmentNotificationEvent],
    ) -> None:
        with self.database.transaction() as connection:
            self.replies.prepare(connection, context.incoming_message_id, body, _encode_events(events), utc_now())

    def start_send(self, context: ConversationContext) -> int:
        with self.database.transaction() as connection:
            return self.replies.start_attempt(connection, context.incoming_message_id, utc_now())

    def record_sent(
        self, context: ConversationContext, attempt_id: int, body: str, provider_message_id: str | None,
    ) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            self.messages.save_reply(
                connection, context.incoming_message_id, context.conversation_id,
                body, "sent", provider_message_id, now,
            )
            self.replies.finish_attempt(connection, attempt_id, "sent", now, provider_message_id)
            self.replies.set_status(connection, context.incoming_message_id, "sent", now)

    def record_failed(
        self, context: ConversationContext, attempt_id: int, body: str, error: Exception,
    ) -> None:
        # Una falla de lectura/escritura puede ocurrir despues de que Meta acepto el mensaje.
        uncertain = isinstance(error, httpx.TransportError) and not isinstance(
            error, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout),
        )
        status = "uncertain" if uncertain else "failed"
        http_status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
        now = utc_now()
        with self.database.transaction() as connection:
            self.messages.save_reply(
                connection, context.incoming_message_id, context.conversation_id,
                body, "failed", None, now,
            )
            self.replies.finish_attempt(
                connection, attempt_id, status, now,
                error_type=type(error).__name__, http_status_code=http_status,
            )
            self.replies.set_status(connection, context.incoming_message_id, status, now)
        if uncertain:
            logger.warning("WhatsApp delivery uncertain: incoming_id=%s", context.incoming_message_id)

    def interrupt(self, context: ConversationContext) -> None:
        with self.database.transaction() as connection:
            self.replies.interrupt(connection, context.incoming_message_id, utc_now())

    def complete_notifications(self, context: ConversationContext) -> None:
        with self.database.transaction() as connection:
            self.replies.complete_notifications(connection, context.incoming_message_id, utc_now())
