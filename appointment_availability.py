"""Deteccion y presentacion segura de disponibilidad para una fecha."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
import unicodedata
from zoneinfo import ZoneInfo

from calendar_domain import AvailableSlot, ToolErrorCode, ToolResult
from tool_contracts import CheckAvailabilityOutput


@dataclass(frozen=True, slots=True)
class DateOnlyAvailabilityRequest:
    """Rango de un dia que el paciente quiere explorar antes de elegir hora."""

    start_at: datetime
    end_at: datetime


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
