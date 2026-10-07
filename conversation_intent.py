"""Clasificacion de interrupciones para los flujos pendientes de conversacion."""

from enum import StrEnum
import re
import unicodedata


class PendingConversationFlow(StrEnum):
    NONE = "none"
    BOOKING_DATE = "booking_date"
    BOOKING_AVAILABILITY = "booking_availability"
    RESCHEDULE_AVAILABILITY = "reschedule_availability"
    BOOKING_DETAILS = "booking_details"
    APPOINTMENT_CONFIRMATION = "appointment_confirmation"


class PendingInterruption(StrEnum):
    NONE = "none"
    ABANDON = "abandon"
    CLARIFY = "clarify"
    AMBIGUOUS_CANCEL = "ambiguous_cancel"
    SWITCH = "switch"


_ABANDON_PATTERNS = (
    r"\b(?:dejala|dejalo|deja\s+la\s+cita|deja\s+la\s+reserva)\s+"
    r"(?:asi|como\s+esta|tal\s+cual|igual)\b",
    r"\b(?:mejor\s+no|no\s+gracias|no\s+quiero\s+seguir|"
    r"no\s+quiero\s+continuar|no\s+quiero\s+agendar|"
    r"no\s+quiero\s+reservar|no\s+quiero\s+cambiar|"
    r"no\s+quiero\s+reprogramar|no\s+quiero\s+cancelar)\b",
    r"\bno\s+(?:la\s+)?(?:cambies|reprogrames|canceles)\b",
    r"\b(?:cancela|cancelar|deten|detener|olvida|olvidar|abandona|"
    r"abandonar|para)\b.{0,30}\b(?:esta\s+)?(?:solicitud|reserva|"
    r"busqueda|cambio|reprogramacion|agendamiento)\b",
)
_BOOKING_PATTERNS = (
    r"\b(?:agendame|reservame|programame|sacar\s+(?:una\s+)?cita)\b",
    r"\b(?:quiero|quisiera|necesito|busco|solicito)\s+(?:agendar|"
    r"reservar|programar)\b",
    r"\b(?:quiero|quisiera|necesito|busco)\s+(?:una\s+)?cita\b",
)
_APPOINTMENT_LIST_PATTERNS = (
    r"\bmis\s+citas\b",
    r"\b(?:que|cuales?)\s+citas?\b",
    r"\bcitas?\s+(?:tengo|programadas|agendadas)\b",
    r"\b(?:ver|consultar|revisar|mostrar|listar)\s+(?:mis\s+)?citas?\b",
)
_RESCHEDULE_PATTERN = r"\b(?:cambiar|modificar|reprogramar|mover)\w*\b"
_RESCHEDULE_REFERENCE_PATTERN = (
    r"\b(?:cita|hora|horario)\b|"
    r"\b(?:cambiarla|modificarla|reprogramarla|moverla)\b"
)
_RESCHEDULE_TARGET_TIME_PATTERNS = (
    r"\b(?:a|para)\s+(?:las?\s+)?\d{1,2}(?::\d{2})?\b",
    r"\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b",
    r"\b(?:mediodia|medianoche)\b",
)
_CANCEL_PATTERN = r"\b(?:cancela\w*|cancelar|cancelame)\b"
_AVAILABILITY_PATTERNS = (
    r"\b(?:que|cuales?)\s+horarios?\b",
    r"\b(?:ver|consultar|revisar|mostrar|dime)\s+(?:los?\s+)?horarios?\b",
    r"\bhorarios?\s+disponibles?\b",
    r"\bdisponibilidad\b",
    r"\bhoras?\s+libres\b",
)
_GENERAL_SWITCH_PATTERNS = (
    r"^(?:hola|holi|hey|buenos\s+dias|buenas\s+tardes|buenas\s+noches|buenas)\b",
    r"\bolvida\s+(?:lo\s+que\s+)?estas\s+(?:haciendo|haces)\b",
    r"\bte\s+estoy\s+saludando\b",
    r"\botra\s+pregunta\b",
    r"\bcambiando\s+de\s+tema\b",
    r"\bquiero\s+preguntarte\s+otra\s+cosa\b",
    r"\bpasemos\s+a\s+otra\s+cosa\b",
)
_QUESTION_START = re.compile(
    r"^(?:que|quien|quienes|como|cuando|donde|cual|cuales|cuanto|"
    r"cuanta|por\s+que|puedes|podrias|tienen|hay|me\s+puedes)\b"
)


def classify_pending_interruption(
    text: str,
    *,
    flow: PendingConversationFlow,
    expected_reply: bool = False,
) -> PendingInterruption:
    """Decide si un mensaje abandona o reemplaza el paso conversacional activo."""
    if flow is PendingConversationFlow.NONE or not isinstance(text, str):
        return PendingInterruption.NONE

    normalized = _normalize(text)
    if not normalized:
        return PendingInterruption.NONE

    if _is_abandonment(normalized):
        return PendingInterruption.ABANDON

    if _starts_new_appointment_task(normalized):
        return PendingInterruption.SWITCH

    if _matches_any(normalized, (_CANCEL_PATTERN,)):
        return PendingInterruption.AMBIGUOUS_CANCEL

    if _looks_like_question(text, normalized):
        if expected_reply or flow is PendingConversationFlow.APPOINTMENT_CONFIRMATION:
            return PendingInterruption.CLARIFY
        return PendingInterruption.SWITCH

    if expected_reply:
        return PendingInterruption.NONE

    if flow in {
        PendingConversationFlow.BOOKING_DATE,
        PendingConversationFlow.BOOKING_AVAILABILITY,
        PendingConversationFlow.RESCHEDULE_AVAILABILITY,
    }:
        return PendingInterruption.CLARIFY

    return PendingInterruption.NONE


def is_reschedule_request_without_target_time(text: str) -> bool:
    """Reconoce una peticion explicita de cambio que aun no elige hora destino."""
    if not isinstance(text, str):
        return False
    normalized = _normalize(text)
    if not _matches_any(normalized, (_RESCHEDULE_PATTERN,)):
        return False
    if not _matches_any(normalized, (_RESCHEDULE_REFERENCE_PATTERN,)):
        return False
    return not _matches_any(text.casefold(), _RESCHEDULE_TARGET_TIME_PATTERNS)


def _is_abandonment(normalized: str) -> bool:
    return normalized in {"no", "nop", "no gracias", "mejor no"} or _matches_any(
        normalized,
        _ABANDON_PATTERNS,
    )


def _starts_new_appointment_task(normalized: str) -> bool:
    if _matches_any(normalized, _BOOKING_PATTERNS + _APPOINTMENT_LIST_PATTERNS):
        return True
    if _matches_any(normalized, (_RESCHEDULE_PATTERN,)):
        return True
    if _matches_any(normalized, (_CANCEL_PATTERN,)) and re.search(
        r"\bcitas?\b",
        normalized,
    ):
        return True
    if _matches_any(normalized, _AVAILABILITY_PATTERNS):
        return True
    return _matches_any(normalized, _GENERAL_SWITCH_PATTERNS)


def _looks_like_question(raw_text: str, normalized: str) -> bool:
    return "?" in raw_text or _QUESTION_START.search(normalized) is not None


def _matches_any(value: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, value) is not None for pattern in patterns)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    return re.sub(r"[^a-z0-9\s]", " ", without_marks).strip()
