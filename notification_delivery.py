"""Configuracion y entrega persistente de notificaciones por WhatsApp."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import os
import re

import httpx

from notification_domain import AppointmentNotificationEvent
from persistence import SQLiteDatabase
from repositories import (
    DoctorNotificationRecord,
    DoctorNotificationRepository,
)
from whatsapp_client import WhatsAppClient, WhatsAppConfigurationError


DEFAULT_DOCTOR_NOTIFICATIONS_ENABLED = False
DOCTOR_NOTIFICATIONS_ENABLED_VARIABLE = "DOCTOR_NOTIFICATIONS_ENABLED"
DOCTOR_WHATSAPP_NUMBERS_VARIABLE = "DOCTOR_WHATSAPP_NUMBERS"
FAILED_NOTIFICATION_BODY = "No se pudo construir la notificacion al doctor."


class DoctorNotificationConfigurationError(RuntimeError):
    """Indica que la configuracion de destinatarios no es utilizable."""


@dataclass(frozen=True, slots=True)
class DoctorNotificationSettings:
    """Destinatarios resueltos por el backend, nunca por el LLM."""

    enabled: bool
    recipient_numbers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DoctorNotificationDeliveryBatch:
    """Resultado de un intento independiente por cada destinatario."""

    enabled: bool
    deliveries: tuple[DoctorNotificationRecord, ...]

    @property
    def records(self) -> tuple[DoctorNotificationRecord, ...]:
        """Alias legible para los registros persistidos del lote."""
        return self.deliveries


class DoctorNotificationDeliveryService:
    """Encola y entrega una notificacion a todos los doctores configurados."""

    def __init__(
        self,
        database: SQLiteDatabase,
        whatsapp_client: WhatsAppClient,
        settings: DoctorNotificationSettings,
        *,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.database = database
        self.whatsapp_client = whatsapp_client
        self.settings = settings
        self.notifications = DoctorNotificationRepository()
        self.now = now or utc_now

    async def deliver(
        self,
        event: AppointmentNotificationEvent,
        body: str,
    ) -> DoctorNotificationDeliveryBatch:
        if not isinstance(body, str) or not body.strip():
            raise ValueError("body no puede estar vacio")
        if not self.settings.enabled:
            return DoctorNotificationDeliveryBatch(enabled=False, deliveries=())

        pending_records = []
        for recipient_number in self.settings.recipient_numbers:
            with self.database.transaction() as connection:
                pending_records.append(
                    self.notifications.create_pending_for_event(
                        connection,
                        event=event,
                        recipient_number=recipient_number,
                        body=body,
                        now=self.now(),
                    )
                )

        deliveries = []
        for record in pending_records:
            deliveries.append(await self._deliver_record(record))
        return DoctorNotificationDeliveryBatch(
            enabled=True,
            deliveries=tuple(deliveries),
        )

    def record_failed(
        self,
        event: AppointmentNotificationEvent,
        *,
        error: str,
        body: str = FAILED_NOTIFICATION_BODY,
    ) -> DoctorNotificationDeliveryBatch:
        """Persiste un fallo previo al envio sin mandar un cuerpo incompleto."""
        if not isinstance(error, str) or not error.strip():
            raise ValueError("error no puede estar vacio")
        if not isinstance(body, str) or not body.strip():
            raise ValueError("body no puede estar vacio")
        if not self.settings.enabled:
            return DoctorNotificationDeliveryBatch(enabled=False, deliveries=())

        deliveries = []
        for recipient_number in self.settings.recipient_numbers:
            with self.database.transaction() as connection:
                pending = self.notifications.create_pending_for_event(
                    connection,
                    event=event,
                    recipient_number=recipient_number,
                    body=body,
                    now=self.now(),
                )
                deliveries.append(
                    self.notifications.mark_failed(
                        connection,
                        pending.id,
                        error=error,
                        now=self.now(),
                    )
                )
        return DoctorNotificationDeliveryBatch(
            enabled=True,
            deliveries=tuple(deliveries),
        )

    async def _deliver_record(
        self,
        record: DoctorNotificationRecord,
    ) -> DoctorNotificationRecord:
        claimed = self._claim(record.id)
        if claimed is None:
            raise RuntimeError("No se pudo recuperar la entrega de notificacion")
        if claimed.status != "sending":
            return claimed

        try:
            provider_response = await self.whatsapp_client.send_text(
                to=claimed.recipient_number,
                body=claimed.body,
            )
            provider_message_id = extract_provider_message_id(provider_response)
        except Exception as error:
            return self._mark_failed(
                claimed.id,
                normalize_delivery_error(error),
            )

        return self._mark_sent(
            claimed.id,
            provider_message_id,
        )

    def _claim(self, notification_id: int) -> DoctorNotificationRecord | None:
        with self.database.transaction() as connection:
            claimed = self.notifications.claim_for_send(
                connection,
                notification_id,
                self.now(),
            )
            return claimed or self.notifications.get_by_id(connection, notification_id)

    def _mark_sent(
        self,
        notification_id: int,
        provider_message_id: str | None,
    ) -> DoctorNotificationRecord:
        with self.database.transaction() as connection:
            return self.notifications.mark_sent(
                connection,
                notification_id,
                provider_message_id=provider_message_id,
                now=self.now(),
            )

    def _mark_failed(
        self,
        notification_id: int,
        error: str,
    ) -> DoctorNotificationRecord:
        with self.database.transaction() as connection:
            return self.notifications.mark_failed(
                connection,
                notification_id,
                error=error,
                now=self.now(),
            )


def load_doctor_notification_settings(
    environment: Mapping[str, str] | None = None,
) -> DoctorNotificationSettings:
    """Carga la bandera y los numeros de doctores desde el entorno."""
    values = os.environ if environment is None else environment
    enabled = _parse_enabled_flag(
        values.get(
            DOCTOR_NOTIFICATIONS_ENABLED_VARIABLE,
            str(DEFAULT_DOCTOR_NOTIFICATIONS_ENABLED),
        )
    )
    if not enabled:
        return DoctorNotificationSettings(enabled=False, recipient_numbers=())

    raw_numbers = values.get(DOCTOR_WHATSAPP_NUMBERS_VARIABLE, "")
    if not raw_numbers.strip():
        raise DoctorNotificationConfigurationError(
            "DOCTOR_WHATSAPP_NUMBERS debe contener al menos un destinatario"
        )

    recipients: list[str] = []
    seen: set[str] = set()
    for raw_number in raw_numbers.split(","):
        if not raw_number.strip():
            raise DoctorNotificationConfigurationError(
                "DOCTOR_WHATSAPP_NUMBERS no puede contener destinatarios vacios"
            )
        normalized = normalize_doctor_recipient(raw_number)
        if normalized not in seen:
            seen.add(normalized)
            recipients.append(normalized)

    if not recipients:
        raise DoctorNotificationConfigurationError(
            "DOCTOR_WHATSAPP_NUMBERS debe contener al menos un destinatario"
        )
    return DoctorNotificationSettings(
        enabled=True,
        recipient_numbers=tuple(recipients),
    )


def _parse_enabled_flag(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise DoctorNotificationConfigurationError(
        f"{DOCTOR_NOTIFICATIONS_ENABLED_VARIABLE} debe ser true o false"
    )


def create_doctor_notification_delivery(
    database: SQLiteDatabase,
    *,
    environment: Mapping[str, str] | None = None,
    whatsapp_client: WhatsAppClient | None = None,
) -> DoctorNotificationDeliveryService:
    """Compone el servicio con configuracion de entorno y cliente inyectable."""
    values = os.environ if environment is None else environment
    settings = load_doctor_notification_settings(values)
    client = whatsapp_client or WhatsAppClient(
        access_token=values.get("WHATSAPP_ACCESS_TOKEN"),
        phone_number_id=values.get("WHATSAPP_PHONE_NUMBER_ID"),
    )
    return DoctorNotificationDeliveryService(
        database,
        client,
        settings,
    )


def normalize_doctor_recipient(value: str) -> str:
    """Normaliza un numero E.164 al formato numerico aceptado por WhatsApp."""
    normalized = value.strip()
    if normalized.startswith("+"):
        normalized = normalized[1:]
    if normalized.startswith("521") and len(normalized) == 13:
        normalized = "52" + normalized[3:]
    if not re.fullmatch(r"[1-9][0-9]{6,14}", normalized):
        raise DoctorNotificationConfigurationError(
            "DOCTOR_WHATSAPP_NUMBERS contiene un numero invalido"
        )
    return normalized


def normalize_delivery_error(error: Exception) -> str:
    """Convierte errores externos en mensajes persistibles sin detalles sensibles."""
    if isinstance(error, WhatsAppConfigurationError):
        return "Configuracion de WhatsApp incompleta."
    if isinstance(error, httpx.TimeoutException):
        return "Tiempo de espera agotado al enviar por WhatsApp."
    if isinstance(error, httpx.ConnectError):
        return "No se pudo conectar con WhatsApp."
    if isinstance(error, httpx.HTTPStatusError):
        return f"WhatsApp rechazo el envio (HTTP {error.response.status_code})."
    if isinstance(error, httpx.HTTPError):
        return "No se pudo comunicar con WhatsApp."
    return "Error inesperado al enviar la notificacion por WhatsApp."


def extract_provider_message_id(
    result: Mapping[str, object],
) -> str | None:
    """Extrae el ID de Meta sin asumir que la respuesta siempre lo contiene."""
    messages = result.get("messages")
    if not isinstance(messages, list) or not messages:
        return None
    first_message = messages[0]
    if not isinstance(first_message, Mapping):
        return None
    message_id = first_message.get("id")
    return message_id.strip() if isinstance(message_id, str) and message_id.strip() else None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
