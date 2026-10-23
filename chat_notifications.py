"""Recuperacion de avisos de chat sin regenerar turnos ni invocar herramientas."""

import json
from pathlib import Path

from notification_delivery import utc_now
from notification_domain import AppointmentNotificationEvent
from notification_recovery import NotificationBatch, NotificationRecoveryWorker
from persistence import SQLiteDatabase
from reply_delivery_repository import ReplyDeliveryRepository


class ChatDoctorNotifications(NotificationRecoveryWorker):
    def __init__(self, database_path, trigger_factory, *, retry_seconds=60):
        self.path = Path(database_path)
        self.repository = ReplyDeliveryRepository()
        self.database = None

        def refresh():
            if not self.path.is_file():
                return None
            self.database = SQLiteDatabase(str(self.path))
            return trigger_factory(self.database)

        super().__init__(None, self._pending, self._complete,
                         retry_seconds=retry_seconds, trigger_factory=refresh)

    def _pending(self):
        with self.database.transaction() as db:
            records = self.repository.pending_notifications(db)
        return [NotificationBatch(row["incoming_message_id"], tuple(
            AppointmentNotificationEvent.from_json(json.dumps(event))
            for event in json.loads(row["notification_events_json"]))) for row in records]

    def _complete(self, source_id):
        with self.database.transaction() as db:
            self.repository.complete_notifications(db, source_id, utc_now())
