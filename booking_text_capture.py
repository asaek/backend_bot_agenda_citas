"""Separa datos literales de reserva; no infiere nombres ni motivos del asistente."""

from dataclasses import dataclass
import re

from patient_name_validation import PatientNameValidationCode, validate_patient_name


_NAME_PREFIX = re.compile(
    r"^(?:(?:me llamo|mi nombre(?: completo)? es|soy)\b|nombre(?: completo)?\s*:)\s*",
    re.IGNORECASE,
)
_NAME_LABEL = re.compile(
    r"\b(?:(?:me llamo|mi nombre(?: completo)? es)\b|nombre(?: completo)?\s*:)\s*",
    re.IGNORECASE,
)
_REASON_LABEL = re.compile(
    r"\b(?:(?:y\s+)?(?:el|mi)\s+)?motivo"
    r"(?:\s+de\s+(?:la\s+)?consulta)?\s*(?::|es\b)\s*(?:por\s+)?",
    re.IGNORECASE,
)
_REASON_CLAUSE = re.compile(
    r"(?:[,;]\s*|\s+y\s+)(?=(?:tengo|siento|padezco|me duele|me duelen|"
    r"veo|vengo por|necesito una revisi[oó]n)\b)", re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class CapturedBookingText:
    patient_name: str | None = None
    reason: str | None = None


def capture_booking_text(text: str, *, expected: str | None = None) -> CapturedBookingText:
    """Los delimitadores explicitos permiten recibir ambos campos en cualquier paso."""
    text = " ".join(text.split())
    separator = _REASON_LABEL.search(text)
    if separator is not None and not text[:separator.start()].strip():
        name_label = _NAME_LABEL.search(text, separator.end())
        if name_label is not None:
            reason = text[separator.end():name_label.start()].strip(" ,;.")
            reason = re.sub(r"\s+y$", "", reason, flags=re.IGNORECASE)
            return CapturedBookingText(text[name_label.end():] or None, reason or None)
    if separator is None and (expected != "reason" or _NAME_LABEL.match(text)):
        candidate = _REASON_CLAUSE.search(text)
        if candidate is not None:
            name = _NAME_PREFIX.sub("", text[:candidate.start()].strip())
            if validate_patient_name(name).code is not PatientNameValidationCode.INVALID:
                separator = candidate
    if separator is not None:
        name = text[:separator.start()].strip(" ,;.\n")
        reason = text[separator.end():].strip()
        return CapturedBookingText(_NAME_PREFIX.sub("", name) or None, reason or None)
    if expected == "name" or _NAME_LABEL.match(text) or (expected is None and _NAME_PREFIX.match(text)):
        return CapturedBookingText(patient_name=_NAME_PREFIX.sub("", text) or None)
    if expected == "reason":
        return CapturedBookingText(reason=text)
    return CapturedBookingText()


def requested_booking_field(reply: str) -> str | None:
    """Solo preguntas de captura, nunca agradecimientos ni nombres citados."""
    questions = re.findall(r"(?:¿|^)([^¿?]+)\?", reply.casefold())
    if not questions:
        return None
    question = questions[-1]
    if "confirm" in question:
        return None
    if "nombre completo" in question or "cómo te llamas" in question:
        return "name"
    if "motivo" in question or "qué deseas revisar" in question:
        return "reason"
    return None
