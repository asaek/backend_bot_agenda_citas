"""Estado pendiente para solicitar el motivo antes de crear una cita."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from calendar_domain import ToolName
from llm_provider import ToolCall


PENDING_APPOINTMENT_REASON_KEY = "pending_appointment_reason"
APPOINTMENT_REASON_TTL = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class PendingAppointmentReason:
    """Solicitud de cita que espera el motivo expresado por el paciente."""

    start_at: str
    call_id: str
    created_at: str
    expires_at: str
    source_message_id: int | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.start_at, str)
            or not self.start_at.strip()
            or not isinstance(self.call_id, str)
            or not self.call_id.strip()
            or not isinstance(self.created_at, str)
            or not isinstance(self.expires_at, str)
            or (
                self.source_message_id is not None
                and (
                    not isinstance(self.source_message_id, int)
                    or self.source_message_id <= 0
                )
            )
        ):
            raise ValueError("La solicitud pendiente de cita no es valida")
        _parse_timestamp(self.created_at)
        _parse_timestamp(self.expires_at)

    @classmethod
    def from_tool_call(
        cls,
        tool_call: ToolCall,
        *,
        now: datetime | None = None,
        source_message_id: int | None = None,
    ) -> "PendingAppointmentReason | None":
        if tool_call.name != ToolName.CREATE_APPOINTMENT.value:
            return None
        if set(tool_call.arguments).difference({"start_at", "reason"}):
            return None
        start_at = tool_call.arguments.get("start_at")
        if not isinstance(start_at, str) or not start_at.strip():
            return None
        if tool_call.call_id is None or not tool_call.call_id.strip():
            return None

        created_at = now or datetime.now(timezone.utc)
        return cls(
            start_at=start_at.strip(),
            call_id=tool_call.call_id,
            created_at=created_at.isoformat(),
            expires_at=(created_at + APPOINTMENT_REASON_TTL).isoformat(),
            source_message_id=source_message_id,
        )

    @classmethod
    def from_context(cls, value: object) -> "PendingAppointmentReason | None":
        if not isinstance(value, Mapping):
            return None
        start_at = value.get("start_at")
        call_id = value.get("call_id")
        created_at = value.get("created_at")
        expires_at = value.get("expires_at")
        source_message_id = value.get("source_message_id")
        if not all(
            isinstance(item, str)
            for item in (start_at, call_id, created_at, expires_at)
        ):
            return None
        if source_message_id is not None and not isinstance(source_message_id, int):
            return None
        try:
            return cls(
                start_at=start_at,
                call_id=call_id,
                created_at=created_at,
                expires_at=expires_at,
                source_message_id=source_message_id,
            )
        except ValueError:
            return None

    @property
    def is_expired(self) -> bool:
        return _parse_timestamp(self.expires_at) <= datetime.now(timezone.utc)

    def to_context(self) -> dict[str, object]:
        context = {
            "start_at": self.start_at,
            "call_id": self.call_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }
        if self.source_message_id is not None:
            context["source_message_id"] = self.source_message_id
        return context

    def to_tool_call(self, reason: str) -> ToolCall:
        return ToolCall(
            name=ToolName.CREATE_APPOINTMENT.value,
            arguments={"start_at": self.start_at, "reason": reason},
            call_id=self.call_id,
        )


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("La fecha debe incluir una zona horaria")
    return parsed.astimezone(timezone.utc)
