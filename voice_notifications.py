"""Adaptador de los eventos durables del laboratorio al ciclo comun de avisos."""

from notification_domain import AppointmentNotificationEvent
from notification_recovery import NotificationBatch, NotificationRecoveryWorker


class VoiceDoctorNotifications(NotificationRecoveryWorker):
    def __init__(self, repository, trigger, *, retry_seconds=60):
        self.repository = repository
        super().__init__(trigger, self._pending, repository.notification_sent, retry_seconds=retry_seconds)

    def _pending(self):
        return [NotificationBatch(record["action_id"],
                    (AppointmentNotificationEvent.from_json(record["event_json"]),),
                    self.repository.notification_context(record))
                for record in self.repository.pending_notifications()]
