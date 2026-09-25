"""Eventos de dominio para notificaciones relacionadas con citas."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from calendar_domain import (
    Appointment,
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

    @property
    def event_key(self) -> str:
        """Identidad estable de esta mutacion dentro del webhook entrante."""
        return (
            f"appointment:{self.incoming_message_id}:"
            f"{self.tool_name.value}:{self.tool_call_id}"
        )


AppointmentNotificationEventSink = Callable[[AppointmentNotificationEvent], None]


def appointment_notification_event_from_result(
    *,
    tool_name: ToolName,
    tool_call_id: str,
    incoming_message_id: int,
    patient_scope: PatientScope,
    result: ToolResult,
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
    )
