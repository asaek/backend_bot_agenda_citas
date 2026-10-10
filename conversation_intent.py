"""Clasificacion de interrupciones para los flujos pendientes de conversacion."""

from enum import StrEnum
import re
import unicodedata

from appointment_availability import normalize_time_selection_punctuation


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
    PAUSE = "pause"


_ABANDON_PATTERNS = (
    r"\b(?:dejala|dejalo|dejarla|dejarlo|deja\s+la\s+cita|deja\s+la\s+reserva)\s+"
    r"(?:asi|como\s+esta|tal\s+cual|igual)\b",
    r"\b(?:mejor\s+no|no\s+gracias|no\s+quiero\s+seguir|"
    r"no\s+quiero\s+continuar|no\s+quiero\s+agendar|"
    r"no\s+quiero\s+reservar|no\s+quiero\s+cambiar|"
    r"no\s+quiero\s+(?:reprogramar|cancelar|modificar|cambiar)(?:la)?)\b",
    r"\b(?:ya\s+)?no\s+(?:la\s+)?(?:cambies|modifiques|reprogrames|canceles)\b",
    r"\bya\s+no\s+quiero\s+(?:agendar|reservar|seguir|continuar|cambiar|modificar|cancelar)\b",
    r"\b(?:cancela|cancelar|deten|detener|olvida|olvidar|abandona|"
    r"abandonar|para)\b.{0,30}\b(?:esta\s+)?(?:solicitud|reserva|"
    r"busqueda|cambio|reprogramacion|agendamiento)\b",
)
_BOOKING_REQUEST_PREFIX = r"(?:quiero|quisiera|necesito|deseo|me\s+gustaria)"
_BOOKING_PATTERNS = (
    r"\b(?:agendame|reservame|programame|sacar\s+(?:una\s+)?cita)\b",
    rf"\b(?:{_BOOKING_REQUEST_PREFIX}|busco|solicito)\s+(?:agendar|"
    r"reservar|programar)\b",
    rf"\b(?:{_BOOKING_REQUEST_PREFIX}|busco)\s+(?:(?:una|otra)\s+)?cita\b",
)
_APPOINTMENT_LIST_PATTERNS = (
    r"\bmis\s+citas\b",
    r"\b(?:que|cuales?)\s+citas?\b",
    r"\bcitas?\s+(?:tengo|programadas|agendadas)\b",
    r"\b(?:ver|consultar|revisar|mostrar|listar)\s+(?:mis\s+)?citas?\b",
)
_RESCHEDULE_INFINITIVE_VERB = r"(?:cambiar|modificar|reprogramar|mover|pasar|poner)"
_RESCHEDULE_IMPERATIVE_VERB = r"(?:cambia|modifica|reprograma|mueve|pasa|pon)"
_RESCHEDULE_LEAVE_REQUEST = (
    r"\b(?:dejarla|dejala|(?:dejar|deja)\s+(?:(?:la|mi|esa|otra)\s+)?"
    r"(?:cita|hora|horario))\b"
)
_RESCHEDULE_PATTERN = (
    rf"\b(?:{_RESCHEDULE_INFINITIVE_VERB}\w*|{_RESCHEDULE_IMPERATIVE_VERB}(?:la|me)?)\b|"
    rf"{_RESCHEDULE_LEAVE_REQUEST}"
)
_RESCHEDULE_REFERENCE_PATTERN = (
    r"\b(?:cita|hora|horario)\b|"
    rf"\b(?:{_RESCHEDULE_INFINITIVE_VERB}|{_RESCHEDULE_IMPERATIVE_VERB})(?:la|me)\b|"
    rf"{_RESCHEDULE_LEAVE_REQUEST}"
)
_RESCHEDULE_TARGET_TIME_PATTERNS = (
    r"\b(?:a|para)\s+(?:las?\s+)?\d{1,2}(?::\d{2})?\b",
    r"\b\d{1,2}(?::\d{2})?\s*(?:a\s*\.?\s*m\.?|p\s*\.?\s*m\.?|"
    r"del\s+(?:mediodia|dia)|de\s+la\s+(?:manana|tarde|noche))\b",
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
    r"\bolvida\s+(?:lo\s+que\s+)?estas\s+(?:haciendo|haces)\b",
)
_GENERAL_PAUSE_PATTERNS = (
    r"^(?:hola|holi|hey|buenos\s+dias|buenas\s+tardes|buenas\s+noches|buenas)\b",
    r"\bte\s+estoy\s+saludando\b",
    r"\botra\s+pregunta\b",
    r"\bcambiando\s+de\s+tema\b",
    r"\bquiero\s+preguntarte\s+otra\s+cosa\b",
    r"\bpasemos\s+a\s+otra\s+cosa\b",
    r"\b(?:precio|costo|ubicacion|direccion)\b",
)
_QUESTION_START = re.compile(
    r"^(?:que|quien|quienes|como|cuando|donde|cual|cuales|cuanto|"
    r"cuanta|por\s+que|puedes|podrias|tienen|hay|me\s+puedes)\b"
)
_COST_QUESTION_START = re.compile(
    r"^(?:(?:cual|que)\s+(?:(?:es|seria|sera)\s+)?(?:el\s+)?(?:costo|precio)|"
    r"cuanto\s+(?:cuesta|costaria|vale))\b"
)
_TIME_REPLY = (
    r"(?:(?:(?:a|para)\s+)?(?:las?\s+)?\d{1,2}"
    r"(?:[:.]\d{2})?\s*(?:a\s*\.?\s*m\.?|p\s*\.?\s*m\.?|"
    r"de\s+la\s+(?:manana|tarde|noche)|del\s+(?:mediodia|dia))?|"
    r"(?:(?:a|para)\s+)?(?:el\s+)?mediodia|al\s+mediodia)"
)
_INCOMPLETE_TIME_REPLY = (
    r"(?:(?:a|para)\s+)?(?:las?\s+)?\d{1,2}(?:[:.]\d{2})?\s*[ap]\.?"
)
_RESCHEDULE_SELECTION_VERB = rf"(?:{_RESCHEDULE_INFINITIVE_VERB}|dejar)(?:la|me)?"
_POLITE_RESCHEDULE_PREFIX = (
    rf"(?:me\s+)?(?:puedes|podrias)\s+{_RESCHEDULE_SELECTION_VERB}"
)
_RESCHEDULE_SELECTION_PREFIX = (
    rf"(?:{_RESCHEDULE_IMPERATIVE_VERB}(?:la|me)?|deja(?:la|me)?|"
    rf"(?:quiero|quisiera|necesito|deseo|prefiero|me\s+gustaria)\s+{_RESCHEDULE_SELECTION_VERB}|"
    rf"{_POLITE_RESCHEDULE_PREFIX}|"
    r"elijo|prefiero|mejor|que\s+sea|me\s+sirve|me\s+viene\s+bien|me\s+quedo\s+con)"
)


def is_pending_slot_selection(
    text: str,
    flow: PendingConversationFlow,
    *,
    allow_incomplete_period: bool = False,
) -> bool:
    """Reconoce una seleccion contextual; un periodo incompleto solo sirve para aclarar."""
    if flow not in {
        PendingConversationFlow.BOOKING_AVAILABILITY,
        PendingConversationFlow.RESCHEDULE_AVAILABILITY,
    }:
        return False
    prefix = (
        r"(?:agendame|reservame|programame|damela|dame|elijo|prefiero|"
        rf"{_BOOKING_REQUEST_PREFIX}"
        r"(?:\s+(?:agendar|reservar|programar))?)"
    )
    time_reply = _TIME_REPLY
    if flow is PendingConversationFlow.RESCHEDULE_AVAILABILITY:
        prefix = _RESCHEDULE_SELECTION_PREFIX
        if allow_incomplete_period:
            time_reply = rf"(?:{_TIME_REPLY}|{_INCOMPLETE_TIME_REPLY})"
    # Reparar separadores entre palabras sin cambiar '10.30' ni los signos de pregunta.
    normalized = unicodedata.normalize("NFD", normalize_time_selection_punctuation(text).casefold())
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    normalized = re.sub(
        r"[,;]\s*(?=(?:por\s+favor|gracias|esta\s+bien|me\s+parece\s+bien)\b)",
        " ", normalized,
    )
    normalized = " ".join(normalized.split()).strip(" .!,")
    if "?" in normalized or "¿" in normalized:
        unwrapped = normalized.replace("¿", "").rstrip("?").strip()
        if flow is not PendingConversationFlow.RESCHEDULE_AVAILABILITY or re.match(
            rf"(?:hola[,\s]+)?(?:por\s+favor[,\s]+)?{_POLITE_RESCHEDULE_PREFIX}\s+",
            unwrapped,
        ) is None:
            return False
        normalized = unwrapped.replace("?", "")
    return re.fullmatch(
        rf"(?:hola[,\s]+)?(?:por\s+favor[,\s]+)?"
        rf"(?:{prefix}\s+(?:(?:una|la|esa|mi)\s+cita\s+)?)?"
        rf"(?:(?:el|ese)\s+horario\s+(?:de\s+)?)?"
        rf"{time_reply}(?:\s+(?:esta\s+bien|me\s+parece\s+bien))?"
        rf"(?:\s+(?:por\s+favor|gracias))?",
        normalized,
    ) is not None


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

    if is_pending_slot_selection(text, flow, allow_incomplete_period=True):
        return PendingInterruption.NONE if expected_reply else PendingInterruption.CLARIFY

    if _COST_QUESTION_START.search(normalized) is not None:
        return PendingInterruption.PAUSE

    if _starts_new_appointment_task(normalized):
        return PendingInterruption.SWITCH

    if _matches_any(normalized, (_CANCEL_PATTERN,)):
        return PendingInterruption.AMBIGUOUS_CANCEL

    if _matches_any(normalized, _GENERAL_PAUSE_PATTERNS):
        return PendingInterruption.PAUSE

    if _looks_like_question(text, normalized):
        tentative = text.strip().strip("¿?").strip()
        if expected_reply and (
            is_pending_slot_selection(tentative, flow)
            or (
                flow is PendingConversationFlow.BOOKING_DATE
                and len(normalized.split()) <= 3
                and _QUESTION_START.search(normalized) is None
            )
            or (
                flow is PendingConversationFlow.APPOINTMENT_CONFIRMATION
                and re.fullmatch(r"(?:si|no|claro|confirmo|de acuerdo)(?: por favor)?", normalized)
            )
        ):
            return PendingInterruption.CLARIFY
        return PendingInterruption.PAUSE

    if expected_reply:
        return PendingInterruption.NONE

    if flow in {
        PendingConversationFlow.BOOKING_DATE,
        PendingConversationFlow.BOOKING_AVAILABILITY,
        PendingConversationFlow.RESCHEDULE_AVAILABILITY,
    }:
        return PendingInterruption.CLARIFY

    return PendingInterruption.NONE


def is_resume_request(text: str) -> bool:
    normalized = _normalize(text)
    return re.fullmatch(
        r"(?:(?:quiero|quisiera)\s+)?"
        r"(?:retomemos|retomar|retoma|continuemos|continuar|continua|sigamos|seguir)"
        r"(?:\s+(?:con\s+)?(?:la\s+|mi\s+|el\s+)?"
        r"(?:cita|reserva|solicitud|agendamiento|cancelacion|reprogramacion|cambio))?"
        r"(?:\s+por\s+favor)?",
        " ".join(normalized.split()),
    ) is not None


def is_cancellation_request(text: str) -> bool:
    """Reconoce una peticion directa de cancelar una cita, no una pregunta informativa."""
    if not isinstance(text, str):
        return False
    normalized = " ".join(_normalize(text).split())
    return (
        re.match(
            r"^(?:hola\s+)?(?:por\s+favor\s+)?"
            r"(?:(?:quiero|quisiera|necesito|deseo|me\s+gustaria)\s+)?"
            r"(?:cancelar(?:la)?|cancela(?:la|me)?|"
            r"(?:me\s+)?(?:puedes|podrias)\s+cancelar(?:la)?)\b",
            normalized,
        ) is not None
        and re.search(r"\b(?:cita|cancelarla|cancelala|la\s+de\s+(?:las?\s+)?\d{1,2})\b", normalized) is not None
    )


def is_reschedule_request_without_target_time(text: str) -> bool:
    """Reconoce una peticion explicita de cambio que aun no elige hora destino."""
    if not isinstance(text, str):
        return False
    normalized = _normalize(text)
    if not _matches_any(normalized, (_RESCHEDULE_PATTERN,)):
        return False
    if not _matches_any(normalized, (_RESCHEDULE_REFERENCE_PATTERN,)):
        return False
    return not _matches_any(normalized, _RESCHEDULE_TARGET_TIME_PATTERNS)


def _is_abandonment(normalized: str) -> bool:
    return normalized in {
        "no", "nop", "no gracias", "mejor no", "prefiero no", "no quiero",
        "mantenerla", "conservarla", "prefiero no gracias",
    } or _matches_any(
        normalized,
        _ABANDON_PATTERNS,
    )


def _starts_new_appointment_task(normalized: str) -> bool:
    if is_cancellation_request(normalized):
        return True
    if _matches_any(normalized, _BOOKING_PATTERNS + _APPOINTMENT_LIST_PATTERNS):
        return True
    if (
        _matches_any(normalized, (_RESCHEDULE_PATTERN,))
        and _matches_any(normalized, (_RESCHEDULE_REFERENCE_PATTERN,))
    ):
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
