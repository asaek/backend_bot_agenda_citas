"""Estado pendiente para solicitar datos antes de crear una cita."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from appointment_reason_evaluation import AppointmentReasonEvaluation
from calendar_domain import ToolName
from llm_provider import ToolCall


PENDING_APPOINTMENT_REASON_KEY = "pending_appointment_reason"
LAST_APPOINTMENT_REASON_EVALUATION_KEY = "last_appointment_reason_evaluation"
APPOINTMENT_REASON_TTL = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class PendingAppointmentReason:
    """Solicitud de cita que espera datos expresados por el paciente."""

    start_at: str
    call_id: str
    created_at: str
    expires_at: str
    source_message_id: int | None = None
    attempt_count: int = 0
    last_evaluation: AppointmentReasonEvaluation | None = None
    name_message_id: int | None = None
    name_required: bool | None = True

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
            or (
                self.name_message_id is not None
                and (
                    not isinstance(self.name_message_id, int)
                    or self.name_message_id <= 0
                )
            )
            or (
                self.name_required is not None
                and type(self.name_required) is not bool
            )
            or type(self.attempt_count) is not int
            or self.attempt_count < 0
            or (
                self.last_evaluation is not None
                and not isinstance(self.last_evaluation, AppointmentReasonEvaluation)
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

        return cls.from_start_at(
            start_at,
            call_id=tool_call.call_id,
            now=now,
            source_message_id=source_message_id,
        )

    @classmethod
    def from_start_at(
        cls,
        start_at: str,
        *,
        call_id: str,
        now: datetime | None = None,
        source_message_id: int | None = None,
    ) -> "PendingAppointmentReason":
        if not isinstance(start_at, str) or not start_at.strip():
            raise ValueError("start_at no puede estar vacio")
        if not isinstance(call_id, str) or not call_id.strip():
            raise ValueError("call_id no puede estar vacio")

        created_at = now or datetime.now(timezone.utc)
        return cls(
            start_at=start_at.strip(),
            call_id=call_id,
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
        name_message_id = value.get("name_message_id")
        name_required = value.get("name_required")
        attempt_count = value.get("attempt_count", 0)
        last_evaluation_value = value.get("last_evaluation")
        if not all(
            isinstance(item, str)
            for item in (start_at, call_id, created_at, expires_at)
        ):
            return None
        if source_message_id is not None and not isinstance(source_message_id, int):
            return None
        if name_message_id is not None and not isinstance(name_message_id, int):
            return None
        if name_required is not None and type(name_required) is not bool:
            return None
        if type(attempt_count) is not int or attempt_count < 0:
            return None
        last_evaluation = None
        if last_evaluation_value is not None:
            last_evaluation = AppointmentReasonEvaluation.from_context(
                last_evaluation_value
            )
            if last_evaluation is None:
                return None
        try:
            return cls(
                start_at=start_at,
                call_id=call_id,
                created_at=created_at,
                expires_at=expires_at,
                source_message_id=source_message_id,
                name_message_id=name_message_id,
                name_required=name_required,
                attempt_count=attempt_count,
                last_evaluation=last_evaluation,
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
            "attempt_count": self.attempt_count,
        }
        if self.name_required is not None:
            context["name_required"] = self.name_required
        if self.source_message_id is not None:
            context["source_message_id"] = self.source_message_id
        if self.name_message_id is not None:
            context["name_message_id"] = self.name_message_id
        if self.last_evaluation is not None:
            context["last_evaluation"] = self.last_evaluation.to_context()
        return context

    def with_name_message(self, message_id: int) -> "PendingAppointmentReason":
        if message_id <= 0:
            raise ValueError("message_id debe ser positivo")
        return replace(self, name_message_id=message_id, name_required=False)

    def with_evaluation(
        self,
        evaluation: AppointmentReasonEvaluation,
    ) -> "PendingAppointmentReason":
        return replace(
            self,
            attempt_count=self.attempt_count + 1,
            last_evaluation=evaluation,
        )

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
