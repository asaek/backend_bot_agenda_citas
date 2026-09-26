"""Deteccion, persistencia y presentacion segura de disponibilidad."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
import re
import unicodedata
from zoneinfo import ZoneInfo

from calendar_domain import APPOINTMENT_DURATION, AvailableSlot, ToolErrorCode, ToolResult
from tool_contracts import CheckAvailabilityOutput


PENDING_APPOINTMENT_AVAILABILITY_KEY = "pending_appointment_availability"
APPOINTMENT_AVAILABILITY_TTL = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class DateOnlyAvailabilityRequest:
    """Rango de un dia que el paciente quiere explorar antes de elegir hora."""

    start_at: datetime
    end_at: datetime


@dataclass(frozen=True, slots=True)
class PendingAvailabilitySlot:
    """Horario que el backend mostro y que puede seleccionar el paciente."""

    start_at: str
    end_at: str

    def __post_init__(self) -> None:
        start_at = _parse_timestamp(self.start_at)
        end_at = _parse_timestamp(self.end_at)
        if end_at - start_at != APPOINTMENT_DURATION:
            raise ValueError("El slot pendiente debe durar 30 minutos")


@dataclass(frozen=True, slots=True)
class PendingAppointmentAvailability:
    """Estado persistente de slots ofrecidos antes de elegir una hora."""

    target_date: str
    slots: Sequence[PendingAvailabilitySlot]
    created_at: str
    expires_at: str

    def __post_init__(self) -> None:
        try:
            date.fromisoformat(self.target_date)
        except (TypeError, ValueError) as error:
            raise ValueError("La fecha de disponibilidad no es valida") from error
        if isinstance(self.slots, (str, bytes)) or not self.slots:
            raise ValueError("La disponibilidad pendiente requiere slots")
        normalized_slots = tuple(self.slots)
        if any(not isinstance(slot, PendingAvailabilitySlot) for slot in normalized_slots):
            raise ValueError("La disponibilidad pendiente contiene un slot invalido")
        object.__setattr__(self, "slots", normalized_slots)
        _parse_timestamp(self.created_at)
        _parse_timestamp(self.expires_at)

    @classmethod
    def from_slots(
        cls,
        request: DateOnlyAvailabilityRequest,
        slots: Sequence[AvailableSlot],
        *,
        timezone: ZoneInfo,
        now: datetime | None = None,
    ) -> "PendingAppointmentAvailability | None":
        unique_slots: dict[tuple[str, str], None] = {}
        for slot in slots:
            start_at = slot.start_at.astimezone(timezone).isoformat()
            end_at = slot.end_at.astimezone(timezone).isoformat()
            unique_slots[(start_at, end_at)] = None
        if not unique_slots:
            return None

        created_at = now or datetime.now(dt_timezone.utc)
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("now debe incluir una zona horaria")
        return cls(
            target_date=request.start_at.astimezone(timezone).date().isoformat(),
            slots=tuple(
                PendingAvailabilitySlot(start_at=start_at, end_at=end_at)
                for start_at, end_at in unique_slots
            ),
            created_at=created_at.isoformat(),
            expires_at=(created_at + APPOINTMENT_AVAILABILITY_TTL).isoformat(),
        )

    @classmethod
    def from_context(cls, value: object) -> "PendingAppointmentAvailability | None":
        if not isinstance(value, Mapping):
            return None
        target_date = value.get("target_date")
        created_at = value.get("created_at")
        expires_at = value.get("expires_at")
        raw_slots = value.get("slots")
        if not all(isinstance(item, str) for item in (target_date, created_at, expires_at)):
            return None
        if not isinstance(raw_slots, (list, tuple)):
            return None

        slots: list[PendingAvailabilitySlot] = []
        for raw_slot in raw_slots:
            if not isinstance(raw_slot, Mapping):
                return None
            start_at = raw_slot.get("start_at")
            end_at = raw_slot.get("end_at")
            if not isinstance(start_at, str) or not isinstance(end_at, str):
                return None
            try:
                slots.append(PendingAvailabilitySlot(start_at, end_at))
            except ValueError:
                return None

        try:
            return cls(
                target_date=target_date,
                slots=slots,
                created_at=created_at,
                expires_at=expires_at,
            )
        except ValueError:
            return None

    @property
    def is_expired(self) -> bool:
        return self.is_expired_at(datetime.now(dt_timezone.utc))

    def is_expired_at(self, now: datetime) -> bool:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now debe incluir una zona horaria")
        return _parse_timestamp(self.expires_at) <= now.astimezone(dt_timezone.utc)

    def to_context(self) -> dict[str, object]:
        return {
            "target_date": self.target_date,
            "slots": [
                {
                    "start_at": slot.start_at,
                    "end_at": slot.end_at,
                }
                for slot in self.slots
            ],
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    def matching_slot(
        self,
        text: str,
        *,
        timezone: ZoneInfo,
    ) -> PendingAvailabilitySlot | None:
        selected_time = parse_time_selection(text)
        if selected_time is None:
            return None
        candidate_times = {selected_time}
        if not _has_explicit_period(text) and selected_time[0] < 12:
            candidate_times.add((selected_time[0] + 12, selected_time[1]))
        matching_slots = [
            slot
            for slot in self.slots
            if _slot_local_time(slot, timezone) in candidate_times
        ]
        return matching_slots[0] if len(matching_slots) == 1 else None


_WEEKDAYS = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "domingo": 6,
}
_AVAILABILITY_INTENT_PATTERNS = (
    r"\b(?:agend\w*|reserv\w*|program\w*)\b",
    r"\b(?:quiero|necesito|busco|solicito)\s+(?:una\s+)?cita\b",
    r"\bsacar\s+(?:una\s+)?cita\b",
    r"\bhorarios?\b",
    r"\bdisponibilidad\b",
)
_EXACT_TIME_PATTERNS = (
    r"\b(?:a|para)\s+las?\s+\d{1,2}(?:[:.]\d{2})?\b",
    r"\b\d{1,2}(?:[:.]\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b",
    r"\b\d{1,2}:\d{2}\b",
    r"\b(?:mediodia|medianoche)\b",
)


def date_only_availability_request(
    text: str,
    *,
    now: datetime,
    timezone: ZoneInfo,
) -> DateOnlyAvailabilityRequest | None:
    """Detecta una solicitud de agenda con fecha, pero sin hora exacta."""
    normalized = _normalize(text)
    if not _matches_any(normalized, _AVAILABILITY_INTENT_PATTERNS):
        return None
    if _matches_any(normalized, _EXACT_TIME_PATTERNS):
        return None

    local_now = now.astimezone(timezone)
    requested_date = _requested_date(normalized, local_now.date())
    if requested_date is None:
        return None

    start_at = datetime.combine(requested_date, time.min, tzinfo=timezone)
    end_at = start_at + timedelta(days=1)
    if requested_date == local_now.date():
        start_at = _next_half_hour(local_now)
        if start_at >= end_at:
            return None
    return DateOnlyAvailabilityRequest(start_at=start_at, end_at=end_at)


def format_availability_reply(
    result: ToolResult,
    request: DateOnlyAvailabilityRequest,
    *,
    timezone: ZoneInfo,
) -> str:
    """Construye una lista de horarios sin exponer calendarios internos."""
    requested_date = request.start_at.astimezone(timezone).strftime("%d/%m/%Y")
    if not result.ok:
        if result.error is not None:
            if result.error.code is ToolErrorCode.OUTSIDE_BUSINESS_HOURS:
                return f"No hay horario laboral disponible para el {requested_date}."
            return result.error.message
        return "No pude consultar los horarios disponibles. Intenta nuevamente."

    if not isinstance(result.data, CheckAvailabilityOutput):
        return "No pude consultar los horarios disponibles. Intenta nuevamente."

    slots = _unique_slots(result.data.slots, timezone)
    if not slots:
        return (
            f"No encontre horarios disponibles para el {requested_date}. "
            "Si quieres, reviso otro dia."
        )

    lines = [f"- {start:%H:%M} a {end:%H:%M}" for start, end in slots]
    return (
        f"Horarios disponibles para el {requested_date}:\n"
        + "\n".join(lines)
        + "\n\nElige uno de estos horarios y te preguntare el motivo de la consulta."
    )


_TIME_SELECTION_PATTERN = re.compile(
    r"\b(?:a\s+las?\s+)?(?P<hour>\d{1,2})"
    r"(?:(?:[:.])(?P<minute>\d{2}))?\s*"
    r"(?P<period>a\s*\.?\s*m\.?|p\s*\.?\s*m\.?|"
    r"de\s+la\s+(?:manana|tarde|noche))?\b"
)


def parse_time_selection(text: str) -> tuple[int, int] | None:
    """Extrae una hora expresada por el paciente para compararla con un slot."""
    if not isinstance(text, str):
        return None
    normalized = _normalize(text)
    match = _TIME_SELECTION_PATTERN.search(normalized)
    if match is None:
        return None

    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    period = match.group("period")
    if period is None:
        return (hour, minute) if 0 <= hour <= 23 else None

    compact_period = re.sub(r"[\s.]", "", period)
    if compact_period == "am":
        if not 1 <= hour <= 12:
            return None
        return (0 if hour == 12 else hour, minute)
    if compact_period == "pm":
        if not 1 <= hour <= 12:
            return None
        return (12 if hour == 12 else hour + 12, minute)

    if not 1 <= hour <= 12:
        return None
    if compact_period == "delamanana":
        return (0 if hour == 12 else hour, minute)
    return (12 if hour == 12 else hour + 12, minute)


def _requested_date(value: str, current_date: date) -> date | None:
    if re.search(r"\bpasado\s+manana\b", value):
        return current_date + timedelta(days=2)
    if re.search(r"\bmanana\b", value):
        return current_date + timedelta(days=1)
    if re.search(r"\bhoy\b", value):
        return current_date

    for weekday_name, weekday in _WEEKDAYS.items():
        if re.search(rf"\b{weekday_name}\b", value):
            days_ahead = (weekday - current_date.weekday()) % 7
            return current_date + timedelta(days=days_ahead)
    return None


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    without_marks = re.sub(r"\bma[;,:]ana\b", "manana", without_marks)
    return re.sub(r"[^a-z0-9:,.\s]", " ", without_marks)


def _matches_any(value: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, value) for pattern in patterns)


def _next_half_hour(value: datetime) -> datetime:
    rounded = value.replace(second=0, microsecond=0)
    if rounded.minute < 30:
        return rounded.replace(minute=30)
    return (rounded + timedelta(hours=1)).replace(minute=0)


def _unique_slots(
    slots: Sequence[AvailableSlot],
    timezone: ZoneInfo,
) -> list[tuple[datetime, datetime]]:
    unique: dict[tuple[datetime, datetime], None] = {}
    for slot in slots:
        start_at = slot.start_at.astimezone(timezone)
        end_at = slot.end_at.astimezone(timezone)
        unique[(start_at, end_at)] = None
    return sorted(unique)


def _slot_local_time(
    slot: PendingAvailabilitySlot,
    timezone: ZoneInfo,
) -> tuple[int, int]:
    start_at = datetime.fromisoformat(slot.start_at).astimezone(timezone)
    return start_at.hour, start_at.minute


def _has_explicit_period(text: str) -> bool:
    normalized = _normalize(text)
    return bool(
        re.search(
            r"\b(?:a\s*\.?\s*m\.?|p\s*\.?\s*m\.?|"
            r"de\s+la\s+(?:manana|tarde|noche))\b",
            normalized,
        )
    )


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("La fecha debe incluir una zona horaria")
    return parsed.astimezone(dt_timezone.utc)
