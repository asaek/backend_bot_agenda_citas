"""Eventos de dominio para notificaciones relacionadas con citas."""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
import json

from calendar_domain import (
    Appointment,
    AppointmentStatus,
    DomainValidationError,
    PatientScope,
    ToolName,
    ToolResult,
)
from tool_contracts import (
    CancelAppointmentOutput,
    CreateAppointmentOutput,
    RescheduleAppointmentOutput,
)


FAILED_NOTIFICATION_BODY = "No se pudo construir la notificacion al doctor."
PENDING_NOTIFICATION_BODY = "Notificacion pendiente de composicion."
UNPREPARED_NOTIFICATION_BODIES = (FAILED_NOTIFICATION_BODY, PENDING_NOTIFICATION_BODY)


class AppointmentNotificationType(StrEnum):
    SCHEDULED = "appointment_scheduled"
    MODIFIED = "appointment_modified"
    CANCELLED = "appointment_cancelled"


class DoctorNotificationStatus(StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"


_NOTIFICATION_TYPE_BY_TOOL = {
    ToolName.CREATE_APPOINTMENT: AppointmentNotificationType.SCHEDULED,
    ToolName.RESCHEDULE_APPOINTMENT: AppointmentNotificationType.MODIFIED,
    ToolName.CANCEL_APPOINTMENT: AppointmentNotificationType.CANCELLED,
}
_OUTPUT_TYPE_BY_TOOL = {
    ToolName.CREATE_APPOINTMENT: CreateAppointmentOutput,
    ToolName.RESCHEDULE_APPOINTMENT: RescheduleAppointmentOutput,
    ToolName.CANCEL_APPOINTMENT: CancelAppointmentOutput,
}


@dataclass(frozen=True, slots=True)
class AppointmentNotificationEvent:
    """Resultado exitoso de una mutacion de cita listo para ser notificado."""

    notification_type: AppointmentNotificationType
    tool_name: ToolName
    appointment: Appointment
    patient_scope: PatientScope
    incoming_message_id: int
    tool_call_id: str
    source_key: str | None = None

    def __post_init__(self) -> None:
        expected_type = _NOTIFICATION_TYPE_BY_TOOL.get(self.tool_name)
        if expected_type is None or expected_type is not self.notification_type:
            raise DomainValidationError(
                "El tipo de notificacion no corresponde a la herramienta"
            )
        if self.appointment.patient_scope != self.patient_scope:
            raise DomainValidationError(
                "La cita de la notificacion no pertenece al alcance del paciente"
            )
        if self.incoming_message_id <= 0:
            raise DomainValidationError("incoming_message_id debe ser positivo")
        if not isinstance(self.tool_call_id, str) or not self.tool_call_id.strip():
            raise DomainValidationError("tool_call_id no puede estar vacio")
        if self.source_key is not None and (not isinstance(self.source_key, str) or not self.source_key.strip()):
            raise DomainValidationError("source_key no puede estar vacio")

    @property
    def event_key(self) -> str:
        """Identidad estable de la mutacion, independiente del canal de entrega."""
        if self.source_key is not None:
            return f"{self.source_key}:{self.tool_name.value}"
        return (
            f"appointment:{self.incoming_message_id}:"
            f"{self.tool_name.value}:{self.tool_call_id}"
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=lambda value: value.isoformat(), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "AppointmentNotificationEvent":
        value = json.loads(raw)
        appointment = value.pop("appointment")
        appointment["patient_scope"] = PatientScope(**appointment["patient_scope"])
        appointment["start_at"] = datetime.fromisoformat(appointment["start_at"])
        appointment["end_at"] = datetime.fromisoformat(appointment["end_at"])
        appointment["status"] = AppointmentStatus(appointment["status"])
        return cls(**{**value, "notification_type": AppointmentNotificationType(value["notification_type"]),
            "tool_name": ToolName(value["tool_name"]), "patient_scope": PatientScope(**value["patient_scope"]),
            "appointment": Appointment(**appointment)})


AppointmentNotificationEventSink = Callable[[AppointmentNotificationEvent], None]


def appointment_notification_event_from_result(
    *,
    tool_name: ToolName,
    tool_call_id: str,
    incoming_message_id: int,
    patient_scope: PatientScope,
    result: ToolResult,
    source_key: str | None = None,
) -> AppointmentNotificationEvent | None:
    """Convierte solo resultados exitosos de mutaciones en eventos de cita."""
    notification_type = _NOTIFICATION_TYPE_BY_TOOL.get(tool_name)
    if not result.ok or notification_type is None:
        return None

    output = result.data
    expected_output_type = _OUTPUT_TYPE_BY_TOOL.get(tool_name)
    if expected_output_type is None or not isinstance(output, expected_output_type):
        return None
    return AppointmentNotificationEvent(
        notification_type=notification_type,
        tool_name=tool_name,
        appointment=output.appointment,
        patient_scope=patient_scope,
        incoming_message_id=incoming_message_id,
        tool_call_id=tool_call_id,
        source_key=source_key,
    )
