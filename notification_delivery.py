"""Configuracion y entrega persistente de notificaciones por WhatsApp."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import hashlib
import os
import re

import httpx

from notification_domain import (
    AppointmentNotificationEvent,
    FAILED_NOTIFICATION_BODY,
    PENDING_NOTIFICATION_BODY,
    UNPREPARED_NOTIFICATION_BODIES,
)
from persistence import SQLiteDatabase
from repositories import (
    DoctorNotificationRecord,
    DoctorNotificationRepository,
)
from whatsapp_client import WhatsAppClient, WhatsAppConfigurationError
from notification_template import (
    TEMPLATE_FIELDS, TemplateMappingError, build_template_components, load_template_components,
)
from notification_retry import DeliveryFailure, classify_failure, next_retry, parse_time


DEFAULT_DOCTOR_NOTIFICATIONS_ENABLED = False
DOCTOR_NOTIFICATIONS_ENABLED_VARIABLE = "DOCTOR_NOTIFICATIONS_ENABLED"
DOCTOR_WHATSAPP_NUMBERS_VARIABLE = "DOCTOR_WHATSAPP_NUMBERS"
INCOMPLETE_TEMPLATE_CONFIGURATION = "Configuración de plantilla incompleta."


class DoctorNotificationConfigurationError(RuntimeError):
    """Indica que la configuracion de destinatarios no es utilizable."""


@dataclass(frozen=True, slots=True)
class DoctorNotificationSettings:
    """Captura independiente de la disponibilidad del transporte de entrega."""

    enabled: bool
    recipient_numbers: tuple[str, ...]
    transport: str = "text"
    template_name: str = ""
    template_language: str = ""
    template_components: str = ""

    @property
    def configuration_error(self) -> str | None:
        if self.transport not in {"text", "template"}:
            return "Transporte de notificaciones no válido."
        if self.transport == "text":
            return None
        if not self.template_name or not self.template_language:
            return INCOMPLETE_TEMPLATE_CONFIGURATION
        if not re.fullmatch(r"[a-z0-9_]{1,512}", self.template_name):
            return "Nombre de plantilla no válido."
        if not re.fullmatch(r"[a-z]{2,3}(?:_[A-Z]{2})?", self.template_language):
            return "Idioma de plantilla no válido."
        try:
            load_template_components(self.template_components)
        except TemplateMappingError as error:
            return str(error)
        return None


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

    @property
    def blocked_reason(self) -> str | None:
        return self.settings.configuration_error

    def configuration_key(self, recipient: str) -> str:
        # La huella permite detectar correcciones sin persistir credenciales.
        values = [self.settings.transport, self.settings.template_name, self.settings.template_language,
                  self.settings.template_components, recipient, recipient in self.settings.recipient_numbers,
                  getattr(self.whatsapp_client, "access_token", ""), getattr(self.whatsapp_client, "phone_number_id", "")]
        return hashlib.sha256(json.dumps(values).encode()).hexdigest()

    def is_due(self, record: DoctorNotificationRecord) -> bool:
        if record.status not in {"pending", "failed"}:
            return False
        if record.next_attempt_at and parse_time(record.next_attempt_at) > parse_time(self.now()):
            return False
        if record.retry_kind == "configuration":
            return record.blocked_configuration_key is not None and record.blocked_configuration_key != self.configuration_key(record.recipient_number)
        return True

    def event_recipients(self, connection, event):
        records = self.notifications.list_for_event(connection, event.event_key)
        return tuple(record.recipient_number for record in records) if records else self.settings.recipient_numbers

    def capture(self, event, context_json=None):
        with self.database.transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for recipient in self.event_recipients(connection, event):
                self.notifications.create_pending_for_event(connection, event=event, recipient_number=recipient,
                    body=PENDING_NOTIFICATION_BODY, now=self.now())
            self.notifications.save_event_context(connection, event.event_key, event.to_json(), context_json)
            for record in self.notifications.list_for_event(connection, event.event_key):
                if record.retry_kind == "configuration" and record.blocked_configuration_key is None:
                    self.notifications.mark_pending(connection, record.id,
                        reason=record.last_error or "Fallo histórico pendiente de revisión.", now=self.now(),
                        configuration_key=self.configuration_key(record.recipient_number))
            return self.notifications.list_for_event(connection, event.event_key)

    def reconcile(self, notification_id, *, attempt_number, outcome, reason, provider_message_id=None):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("La conciliacion requiere una referencia a la evidencia")
        with self.database.transaction() as db:
            db.execute("BEGIN IMMEDIATE")
            return self.notifications.reconcile(db, notification_id, attempt_number=attempt_number,
                outcome=outcome, reason=reason.strip(), now=self.now(), provider_message_id=provider_message_id)

    def record_deferred(
        self,
        event: AppointmentNotificationEvent,
        *,
        reason: str,
        body: str = PENDING_NOTIFICATION_BODY,
        template_data: Mapping[str, str] | None = None,
    ) -> DoctorNotificationDeliveryBatch:
        """Captura el aviso aunque el transporte todavia no permita despacharlo."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason no puede estar vacio")
        if not isinstance(body, str) or not body.strip():
            raise ValueError("reason y body no pueden estar vacios")
        if not self.settings.enabled:
            return DoctorNotificationDeliveryBatch(enabled=False, deliveries=())
        records = []
        with self.database.transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            body, data_json = self.notifications.prepare_content(connection, event_key=event.event_key,
                body=body, template_data_json=serialize_template_data(body, template_data))
            for recipient in self.event_recipients(connection, event):
                pending = self.notifications.create_pending_for_event(
                    connection, event=event, recipient_number=recipient, body=body, now=self.now(),
                    template_data_json=data_json,
                )
                records.append(self.notifications.mark_pending(
                    connection, pending.id, reason=reason, now=self.now(),
                    configuration_key=self.configuration_key(recipient),
                ))
            self.notifications.save_event_context(connection, event.event_key, event.to_json(), None)
        return DoctorNotificationDeliveryBatch(enabled=True, deliveries=tuple(records))

    async def deliver(
        self,
        event: AppointmentNotificationEvent,
        body: str,
        *,
        template_data: Mapping[str, str] | None = None,
    ) -> DoctorNotificationDeliveryBatch:
        if not isinstance(body, str) or not body.strip():
            raise ValueError("body no puede estar vacio")
        if not self.settings.enabled:
            return DoctorNotificationDeliveryBatch(enabled=False, deliveries=())
        if self.blocked_reason:
            return self.record_deferred(event, reason=self.blocked_reason, body=body, template_data=template_data)

        pending_records = []
        with self.database.transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            body, data_json = self.notifications.prepare_content(connection, event_key=event.event_key,
                body=body, template_data_json=serialize_template_data(body, template_data))
            for recipient_number in self.event_recipients(connection, event):
                pending_records.append(
                    self.notifications.create_pending_for_event(
                        connection,
                        event=event,
                        recipient_number=recipient_number,
                        body=body,
                        now=self.now(),
                        template_data_json=data_json,
                    )
                )
            self.notifications.save_event_context(connection, event.event_key, event.to_json(), None)

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
        with self.database.transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for recipient_number in self.event_recipients(connection, event):
                pending = self.notifications.create_pending_for_event(
                    connection,
                    event=event,
                    recipient_number=recipient_number,
                    body=body,
                    now=self.now(),
                )
                self.notifications.save_event_context(connection, event.event_key, event.to_json(), None)
                if pending.status not in {"pending", "failed"} or pending.body not in UNPREPARED_NOTIFICATION_BODIES:
                    deliveries.append(pending)
                    continue
                if not self.is_due(pending):
                    deliveries.append(pending)
                    continue
                deliveries.append(
                    self.notifications.mark_failed(
                        connection,
                        pending.id,
                        error=error,
                        now=self.now(),
                        next_attempt_at=next_retry(self.now(), pending.failure_count),
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
        if record.recipient_number not in self.settings.recipient_numbers:
            with self.database.transaction() as connection:
                return self.notifications.mark_pending(connection, record.id,
                    reason="El destinatario ya no está configurado.", now=self.now(),
                    configuration_key=self.configuration_key(record.recipient_number))
        if record.retry_kind == "configuration" and record.blocked_configuration_key is None:
            with self.database.transaction() as connection:
                return self.notifications.mark_pending(connection, record.id,
                    reason=record.last_error or "Fallo histórico pendiente de revisión.", now=self.now(),
                    configuration_key=self.configuration_key(record.recipient_number))
        if not self.is_due(record):
            return record
        replace_payload = record.retry_kind == "configuration"
        payload_json = None if replace_payload else record.template_payload_json
        if self.settings.transport == "template" and payload_json is None and record.status in {"pending", "failed"}:
            try:
                data = json.loads(record.template_data_json) if record.template_data_json else {"notification_body": record.body}
                components = build_template_components(self.settings.template_components, data)
                payload_json = json.dumps({"name": self.settings.template_name,
                    "language_code": self.settings.template_language, "components": components}, ensure_ascii=False)
            except TemplateMappingError as error:
                with self.database.transaction() as connection:
                    return self.notifications.mark_pending(connection, record.id, reason=str(error), now=self.now(),
                        configuration_key=self.configuration_key(record.recipient_number))
        version = record.template_version
        if payload_json and (version is None or replace_payload):
            version = hashlib.sha256(json.dumps([self.settings.template_name, self.settings.template_language,
                self.settings.template_components]).encode()).hexdigest()
        claimed = self._claim(record, payload_json, version, replace_payload)
        if claimed is None:
            with self.database.transaction() as connection:
                current = self.notifications.get_by_id(connection, record.id)
            if current is None:
                raise RuntimeError("No se pudo recuperar la entrega de notificacion")
            return current

        try:
            if claimed.template_payload_json is not None:
                template = json.loads(claimed.template_payload_json)
                provider_response = await self.whatsapp_client.send_template(to=claimed.recipient_number, **template)
            else:
                provider_response = await self.whatsapp_client.send_text(to=claimed.recipient_number, body=claimed.body)
            provider_message_id = extract_provider_message_id(provider_response)
            if not provider_message_id:
                raise ValueError("Meta no devolvio un identificador para el aviso")
        except Exception as error:
            failure = classify_failure(error, self.now())
            if failure.kind == "uncertain":
                # Meta puede haber aceptado el mensaje antes de perder la
                # respuesta. Mantener sending impide un reenvio automatico.
                with self.database.transaction() as connection:
                    return self.notifications.mark_uncertain(connection, claimed.id,
                        error=normalize_delivery_error(error), now=self.now(), expected_attempt=claimed.attempt_count)
            return self._mark_failed(
                claimed,
                normalize_delivery_error(error),
                failure,
            )

        return self._mark_sent(
            claimed,
            provider_message_id,
        )

    def _claim(self, record, template_payload_json=None, template_version=None, replace_payload=False):
        with self.database.transaction() as connection:
            return self.notifications.claim_for_send(
                connection,
                record.id,
                self.now(),
                template_payload_json=template_payload_json,
                configuration_key=self.configuration_key(record.recipient_number),
                template_version=template_version,
                replace_payload=replace_payload,
            )

    def _mark_sent(
        self,
        record: DoctorNotificationRecord,
        provider_message_id: str | None,
    ) -> DoctorNotificationRecord:
        with self.database.transaction() as connection:
            return self.notifications.mark_sent(
                connection,
                record.id,
                provider_message_id=provider_message_id,
                now=self.now(),
                expected_attempt=record.attempt_count,
            )

    def _mark_failed(
        self,
        record: DoctorNotificationRecord,
        error: str,
        failure: DeliveryFailure,
    ) -> DoctorNotificationRecord:
        with self.database.transaction() as connection:
            return self.notifications.mark_failed(
                connection,
                record.id,
                error=error,
                now=self.now(),
                retry_kind=failure.kind,
                next_attempt_at=next_retry(self.now(), record.failure_count, failure.retry_after) if failure.kind == "transient" else None,
                configuration_key=self.configuration_key(record.recipient_number) if failure.kind == "configuration" else None,
                expected_attempt=record.attempt_count,
                http_status=failure.http_status,
                provider_code=failure.provider_code,
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
        transport=values.get("DOCTOR_NOTIFICATION_TRANSPORT", "text").strip().lower(),
        template_name=values.get("DOCTOR_WHATSAPP_TEMPLATE_NAME", "").strip(),
        template_language=values.get("DOCTOR_WHATSAPP_TEMPLATE_LANGUAGE", "").strip(),
        template_components=values.get("DOCTOR_WHATSAPP_TEMPLATE_COMPONENTS", "").strip(),
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


def serialize_template_data(body: str, data: Mapping[str, str] | None) -> str | None:
    if body in UNPREPARED_NOTIFICATION_BODIES:
        return None
    fields = {key: value for key, value in (data or {}).items() if key in TEMPLATE_FIELDS and isinstance(value, str)}
    fields["notification_body"] = body
    return json.dumps(fields, ensure_ascii=False)
