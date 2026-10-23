"""Bloques compartidos de cita y paciente para mensajes de WhatsApp."""

from enum import StrEnum
import re

from appointment_availability import format_patient_time
from calendar_domain import Appointment, AppointmentStatus, ToolName


class AppointmentMessageAudience(StrEnum):
    PATIENT = "patient"
    DOCTOR = "doctor"


def appointment_message_fields(
    appointment: Appointment,
    *,
    tool_name: ToolName,
    patient_name: str | None,
    audience: AppointmentMessageAudience,
) -> dict[str, str]:
    """Presenta datos definitivos sin consultas externas ni identificadores internos."""
    event_label = {
        ToolName.CREATE_APPOINTMENT: "Cita agendada",
        ToolName.RESCHEDULE_APPOINTMENT: "Cita modificada",
        ToolName.CANCEL_APPOINTMENT: "Cita cancelada",
    }[tool_name]
    status_label = {
        AppointmentStatus.SCHEDULED: "programada",
        AppointmentStatus.CONFIRMED: "confirmada",
        AppointmentStatus.CANCELLED: "cancelada",
        AppointmentStatus.COMPLETED: "completada",
        AppointmentStatus.NO_SHOW: "no asistio",
    }[appointment.status]
    start = appointment.start_at
    if audience is AppointmentMessageAudience.DOCTOR:
        title = "NOTIFICACION INTERNA DE CITA"
        date_label = start.date().isoformat()
        end = appointment.end_at.astimezone(start.tzinfo)
        time_label = f"{start:%H:%M}-{end:%H:%M}"
    else:
        title = "CONFIRMACION DE CITA"
        date_label = f"{start:%d/%m/%Y}"
        time_label = format_patient_time(start)
    name = _compact_text(patient_name or "") or "No informado"
    number = appointment.patient_scope.whatsapp_number
    phone = re.sub(r"\D", "", number)[-10:] if re.fullmatch(r"\+?\d+", number) else "No informado"
    return {
        "title": title, "event_type": event_label, "date": date_label, "time": time_label,
        "reason": _compact_text(appointment.reason), "status": status_label,
        "patient_name": name, "patient_phone": phone,
    }


def render_appointment_message(
    appointment: Appointment,
    *,
    tool_name: ToolName,
    patient_name: str | None,
    audience: AppointmentMessageAudience,
) -> str:
    fields = appointment_message_fields(
        appointment, tool_name=tool_name, patient_name=patient_name, audience=audience,
    )
    return "\n".join(
        (
            fields["title"],
            f"Tipo de evento: {fields['event_type']}",
            "",
            "CITA",
            f"Fecha: {fields['date']}",
            f"Hora: {fields['time']}",
            f"Motivo: {fields['reason']}",
            f"Estado: {fields['status']}",
            "",
            "PACIENTE",
            f"Nombre: {fields['patient_name']}",
            f"Telefono: {fields['patient_phone']}",
        )
    )


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\x00", " ")).strip()
