"""Estado y reglas para confirmar cambios destructivos de citas."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import re
import unicodedata

from calendar_domain import Appointment, ToolName
from llm_provider import ToolCall


PENDING_APPOINTMENT_ACTION_KEY = "pending_appointment_action"
APPOINTMENT_CONFIRMATION_TTL = timedelta(minutes=10)
DESTRUCTIVE_APPOINTMENT_TOOLS = frozenset(
    {
        ToolName.RESCHEDULE_APPOINTMENT,
        ToolName.CANCEL_APPOINTMENT,
    }
)


class ConfirmationDecision(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class AppointmentConfirmationDetails:
    """Datos publicables de la cita que el paciente debe confirmar."""

    start_at: str
    end_at: str
    reason: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.start_at, str)
            or not isinstance(self.end_at, str)
            or not isinstance(self.reason, str)
            or not self.start_at.strip()
            or not self.end_at.strip()
            or not self.reason.strip()
        ):
            raise ValueError("Los datos de la cita no son validos")
        start_at = _parse_timestamp(self.start_at)
        end_at = _parse_timestamp(self.end_at)
        if end_at <= start_at:
            raise ValueError("end_at debe ser posterior a start_at")

    @classmethod
    def from_appointment(
        cls,
        appointment: Appointment,
    ) -> "AppointmentConfirmationDetails":
        return cls(
            start_at=appointment.start_at.isoformat(),
            end_at=appointment.end_at.isoformat(),
            reason=appointment.reason,
        )

    @classmethod
    def from_context(
        cls,
        value: object,
    ) -> "AppointmentConfirmationDetails | None":
        if not isinstance(value, Mapping):
            return None
        start_at = value.get("start_at")
        end_at = value.get("end_at")
        reason = value.get("reason")
        if not all(isinstance(item, str) for item in (start_at, end_at, reason)):
            return None
        try:
            return cls(start_at=start_at, end_at=end_at, reason=reason)
        except ValueError:
            return None

    def to_context(self) -> dict[str, str]:
        return {
            "start_at": self.start_at,
            "end_at": self.end_at,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PendingAppointmentAction:
    """Mutacion exacta que espera una confirmacion del paciente."""

    tool_name: ToolName
    arguments: Mapping[str, str]
    call_id: str
    created_at: str
    expires_at: str
    appointment_details: AppointmentConfirmationDetails | None = None

    @classmethod
    def from_tool_call(
        cls,
        tool_call: ToolCall,
        *,
        now: datetime | None = None,
        appointment: Appointment | None = None,
    ) -> "PendingAppointmentAction | None":
        try:
            tool_name = ToolName(tool_call.name)
        except (TypeError, ValueError):
            return None
        if tool_name not in DESTRUCTIVE_APPOINTMENT_TOOLS:
            return None

        expected_arguments = {"appointment_id"}
        if tool_name is ToolName.RESCHEDULE_APPOINTMENT:
            expected_arguments.add("new_start_at")
        if set(tool_call.arguments) != expected_arguments:
            return None

        arguments = {
            name: value
            for name, value in tool_call.arguments.items()
            if isinstance(value, str) and value.strip()
        }
        if set(arguments) != expected_arguments:
            return None
        if tool_call.call_id is None or not tool_call.call_id.strip():
            return None

        created_at = now or datetime.now(timezone.utc)
        return cls(
            tool_name=tool_name,
            arguments=arguments,
            call_id=tool_call.call_id,
            created_at=created_at.isoformat(),
            expires_at=(created_at + APPOINTMENT_CONFIRMATION_TTL).isoformat(),
            appointment_details=(
                AppointmentConfirmationDetails.from_appointment(appointment)
                if appointment is not None
                else None
            ),
        )

    @classmethod
    def from_context(cls, value: object) -> "PendingAppointmentAction | None":
        if not isinstance(value, Mapping):
            return None
        try:
            tool_name = ToolName(value["tool_name"])
            arguments = value["arguments"]
            call_id = value["call_id"]
            created_at = value["created_at"]
            expires_at = value["expires_at"]
        except (KeyError, TypeError, ValueError):
            return None
        if tool_name not in DESTRUCTIVE_APPOINTMENT_TOOLS:
            return None
        if (
            not isinstance(arguments, Mapping)
            or not isinstance(call_id, str)
            or not call_id.strip()
            or not isinstance(created_at, str)
            or not isinstance(expires_at, str)
        ):
            return None
        normalized_arguments = {
            name: argument
            for name, argument in arguments.items()
            if isinstance(name, str)
            and isinstance(argument, str)
            and argument.strip()
        }
        expected_arguments = {"appointment_id"}
        if tool_name is ToolName.RESCHEDULE_APPOINTMENT:
            expected_arguments.add("new_start_at")
        if set(normalized_arguments) != expected_arguments:
            return None
        try:
            _parse_timestamp(created_at)
            _parse_timestamp(expires_at)
        except ValueError:
            return None
        raw_appointment_details = value.get("appointment_details")
        if raw_appointment_details is None:
            appointment_details = None
        else:
            appointment_details = AppointmentConfirmationDetails.from_context(
                raw_appointment_details
            )
            if appointment_details is None:
                return None
        return cls(
            tool_name=tool_name,
            arguments=normalized_arguments,
            call_id=call_id,
            created_at=created_at,
            expires_at=expires_at,
            appointment_details=appointment_details,
        )

    @property
    def is_expired(self) -> bool:
        return _parse_timestamp(self.expires_at) <= datetime.now(timezone.utc)

    def to_context(self) -> dict[str, object]:
        context: dict[str, object] = {
            "tool_name": self.tool_name.value,
            "arguments": dict(self.arguments),
            "call_id": self.call_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }
        if self.appointment_details is not None:
            context["appointment_details"] = self.appointment_details.to_context()
        return context

    def to_tool_call(self) -> ToolCall:
        return ToolCall(
            name=self.tool_name.value,
            arguments=dict(self.arguments),
            call_id=self.call_id,
        )

    def confirmation_prompt(self) -> str:
        appointment_details = self._format_appointment_details()
        if self.tool_name is ToolName.RESCHEDULE_APPOINTMENT:
            requested_start = self.arguments["new_start_at"]
            requested_start = _format_requested_start(requested_start)
            if appointment_details:
                return (
                    "¿Confirmas que deseas reprogramar esta cita?\n\n"
                    f"{appointment_details}\n"
                    f"Nueva fecha y hora: {requested_start}.\n\n"
                    "Responde Sí o No."
                )
            return (
                "¿Confirmas que deseas reprogramar la cita para "
                f"{requested_start}? Responde Sí o No."
            )
        if appointment_details:
            return (
                "¿Confirmas que deseas cancelar esta cita?\n\n"
                f"{appointment_details}\n\n"
                "Responde Sí o No."
            )
        return "¿Confirmas que deseas cancelar la cita? Responde Sí o No."

    def _format_appointment_details(self) -> str:
        if self.appointment_details is None:
            return ""
        start_at = datetime.fromisoformat(self.appointment_details.start_at)
        end_at = datetime.fromisoformat(self.appointment_details.end_at)
        reason = re.sub(r"\s+", " ", self.appointment_details.reason).strip()
        return "\n".join(
            (
                "Datos de la cita:",
                f"Fecha: {start_at:%d/%m/%Y}",
                f"Hora: {start_at:%H:%M} - {end_at:%H:%M}",
                f"Motivo: {reason}",
            )
        )


def classify_confirmation(value: str) -> ConfirmationDecision:
    normalized = _normalize(value)
    if normalized in {
        "si",
        "confirmo",
        "confirmar",
        "de acuerdo",
        "adelante",
        "ok",
        "okay",
        "correcto",
        "hazlo",
        "si quiero",
        "si deseo",
    }:
        return ConfirmationDecision.CONFIRMED
    if normalized in {
        "no",
        "no quiero",
        "mejor no",
        "cancelar",
        "dejala asi",
        "mantenerla",
        "conservarla",
    }:
        return ConfirmationDecision.REJECTED
    return ConfirmationDecision.UNKNOWN


def confirmation_reply(tool_name: ToolName) -> str:
    if tool_name is ToolName.CANCEL_APPOINTMENT:
        return "Tu cita ha sido cancelada."
    return "Tu cita ha sido modificada."


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.strip().lower())
    without_marks = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    )
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", without_marks)).strip()


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("La fecha debe incluir una zona horaria")
    return parsed.astimezone(timezone.utc)


def _format_requested_start(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed.strftime("%d/%m/%Y a las %H:%M")
