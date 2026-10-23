"""Disparador unico: resumen, formato y entrega al doctor para texto y voz."""

import logging
import json
from dataclasses import asdict, dataclass
from collections.abc import Sequence

from notification_composer import (
    DEFAULT_NOTIFICATION_MAX_HISTORY_MESSAGES,
    DoctorNotificationComposer,
    DoctorNotificationService,
    NotificationCompositionError,
)
from notification_delivery import (
    DoctorNotificationConfigurationError,
    DoctorNotificationDeliveryService,
    DoctorNotificationSettings,
    load_doctor_notification_settings,
)
from notification_domain import AppointmentNotificationEvent, UNPREPARED_NOTIFICATION_BODIES
from repositories import MessageRecord
from whatsapp_client import WhatsAppClient


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DoctorNotificationContext:
    patient_name: str | None
    history: Sequence[MessageRecord]


class DoctorNotificationTrigger:
    def __init__(self, database, summary_provider, *, whatsapp_client=None, settings=None,
                 max_history_messages=DEFAULT_NOTIFICATION_MAX_HISTORY_MESSAGES):
        self.database = database
        self.configuration_invalid = False
        try:
            self.settings = settings if settings is not None else load_doctor_notification_settings()
        except DoctorNotificationConfigurationError:
            logger.warning("No se pudo configurar la entrega al doctor: DoctorNotificationConfigurationError")
            self.settings = DoctorNotificationSettings(False, ())
            self.configuration_invalid = True
        self.delivery = DoctorNotificationDeliveryService(database,
            whatsapp_client if whatsapp_client is not None else WhatsAppClient(), self.settings)
        self.composer = DoctorNotificationComposer(summary_provider, max_history_messages=max_history_messages)
        self.service = DoctorNotificationService(database, summary_provider, max_history_messages=max_history_messages)

    @property
    def enabled(self):
        return self.settings.enabled or self.configuration_invalid

    async def notify(self, event, *, context: DoctorNotificationContext | None = None) -> bool:
        """Un fallo de resumen, persistencia o WhatsApp nunca deshace una cita."""
        if not self.enabled or self.configuration_invalid:
            return False
        try:
            records = self.delivery.capture(event)
            if records and all(record.status == "sent" for record in records):
                return True
            prepared = next((record for record in records if record.body not in UNPREPARED_NOTIFICATION_BODIES), None)
            if prepared is None:
                snapshot = next((record.context_json for record in records if record.context_json), None)
                if snapshot:
                    value = json.loads(snapshot)
                    context = DoctorNotificationContext(value["patient_name"], [MessageRecord(**m) for m in value["history"]])
                elif context is None:
                    name, history = self.service.context_for_event(event)
                    context = DoctorNotificationContext(name, history)
                context = DoctorNotificationContext(context.patient_name, self.composer.history_for_event(event, context.history))
                snapshots = self.delivery.capture(event, json.dumps({"patient_name": context.patient_name,
                    "history": [asdict(message) for message in context.history]}, ensure_ascii=False))
                frozen = json.loads(next(record.context_json for record in snapshots if record.context_json))
                context = DoctorNotificationContext(frozen["patient_name"], [MessageRecord(**m) for m in frozen["history"]])
            if self.delivery.blocked_reason:
                batch = self.delivery.record_deferred(event, reason=self.delivery.blocked_reason)
                return bool(batch.deliveries) and all(record.status == "sent" for record in batch.deliveries)
            if not any(self.delivery.is_due(record) for record in records):
                return False
            if prepared is not None:
                batch = await self.delivery.deliver(event, prepared.body)
                return bool(batch.deliveries) and all(record.status == "sent" for record in batch.deliveries)
            try:
                if self.composer.summary_provider is None:
                    raise NotificationCompositionError("No hay proveedor de resumen")
                message = await self.composer.compose(event, patient_name=context.patient_name, history=context.history)
            except Exception as error:
                self.delivery.record_failed(event, error="No se pudo construir la notificacion al doctor.")
                logger.warning("No se pudo componer la notificacion al doctor: %s", type(error).__name__)
                return False
            batch = await self.delivery.deliver(event, message.body, template_data=message.template_data)
            return bool(batch.deliveries) and all(record.status == "sent" for record in batch.deliveries)
        except Exception as error:
            # Una entrega que quedo en sending es incierta: no se convierte en
            # failed ni se reenvia automaticamente tras un fallo de persistencia.
            logger.warning("No se pudo completar la notificacion al doctor: %s", type(error).__name__)
            return False

    async def recover_pending(self, exclude=()):
        if not self.enabled:
            return
        with self.database.transaction() as db:
            records = self.delivery.notifications.recovery_records(db)
        seen = set(exclude)
        for record in records:
            if record.event_key in seen or not self.delivery.is_due(record):
                continue
            seen.add(record.event_key)
            await self.notify(AppointmentNotificationEvent.from_json(record.event_json))
