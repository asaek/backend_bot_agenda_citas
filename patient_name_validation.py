"""Calidad minima del nombre, sin inferir ni corregir la identidad del paciente."""

from dataclasses import dataclass
from enum import StrEnum
import re
import unicodedata

from appointment_confirmation import ConfirmationDecision


_CONVERSATIONAL_NAME_PATTERNS = (
    r"^(?:ya\s+)?(?:te|se)\s+(?:lo\s+)?"
    r"(?:(?:he|habia)\s+|acabo\s+de\s+)?(?:dich[oa]?|dije|decir|di|enviado|mande)\b",
    r"^ya\s+lo\s+(?:dich[oa]?|dije|he\s+dicho|habia\s+dicho)\b",
    r"^no\s+(?:se|recuerdo)(?:\s|$)",
    r"^no\s+quiero\s+(?:dar(?:te)?|decir(?:te)?|compartir)\s+(?:mi\s+)?nombre\b",
    r"^(?:tengo|siento|padezco)\s+(?:los?|las?|un[oa]s?|dolor|molestias?|problemas?)\b",
    r"^me\s+(?:duelen?|arden?|molestan?|pican?)\b",
    r"^veo\s+(?:borroso|mal|doble|oscuro)\b",
)


class PatientNameValidationCode(StrEnum):
    ACCEPTED = "accepted"
    INVALID = "invalid"
    NEEDS_CONFIRMATION = "needs_confirmation"


@dataclass(frozen=True, slots=True)
class PatientNameValidationResult:
    normalized_text: str
    code: PatientNameValidationCode


def _normalize_name_reply(text: str) -> str:
    """Normaliza para comparar frases, nunca para guardar el nombre."""
    normalized = unicodedata.normalize("NFD", text.casefold())
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^\w\s]", " ", normalized).split())


def classify_patient_name_confirmation(text: str) -> ConfirmationDecision:
    """Reconoce respuestas completas a la pregunta por el nombre recibido."""
    normalized = _normalize_name_reply(text)
    if normalized in {
        "si", "si es correcto", "si esta correcto", "si esta bien",
        "si ese es mi nombre", "correcto", "es correcto", "esta correcto",
        "ese es mi nombre", "asi es", "confirmo", "confirmo mi nombre",
    }:
        return ConfirmationDecision.CONFIRMED
    if normalized in {
        "no", "no es correcto", "no esta correcto", "esta mal",
        "no es mi nombre", "esta mal escrito",
    }:
        return ConfirmationDecision.REJECTED
    return ConfirmationDecision.UNKNOWN


def validate_patient_name(text: str) -> PatientNameValidationResult:
    """Conserva todas las partes del nombre; las dudas requieren confirmacion.

    No se usan diccionarios de nombres ni reglas foneticas para otros alfabetos.
    Una señal de texto de prueba no implica que el apellido sea invalido.
    """
    if not isinstance(text, str):
        raise TypeError("El nombre del paciente debe ser texto")
    normalized = " ".join(text.split())
    if (
        not 2 <= len(normalized) <= 120
        or not any(c.isalpha() for c in normalized)
        or any(
            not (c.isalpha() or unicodedata.category(c).startswith("M") or c in " .'-’")
            for c in normalized
        )
        or any(not any(c.isalpha() for c in part) for part in normalized.split())
        or classify_patient_name_confirmation(normalized) is not ConfirmationDecision.UNKNOWN
        or normalized.casefold() in {"ok", "okay", "gracias", "claro"}
        or _is_conversational_name_reply(normalized)
    ):
        return PatientNameValidationResult(normalized, PatientNameValidationCode.INVALID)

    words = re.findall(r"[^\W\d_]+", unicodedata.normalize("NFC", normalized))
    suspicious = any(_is_suspicious_latin_word(word) for word in words)
    return PatientNameValidationResult(
        normalized,
        PatientNameValidationCode.NEEDS_CONFIRMATION if suspicious else PatientNameValidationCode.ACCEPTED,
    )


def _is_conversational_name_reply(text: str) -> bool:
    normalized = _normalize_name_reply(text)
    return any(re.search(pattern, normalized) for pattern in _CONVERSATIONAL_NAME_PATTERNS)


def _is_suspicious_latin_word(word: str) -> bool:
    if not all(unicodedata.name(c, "").startswith("LATIN ") for c in word):
        return False
    decomposed = unicodedata.normalize("NFD", word.casefold())
    letters = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    if letters in {"asdf", "qwerty", "qwertyuiop", "zxcv", "zxcvbnm", "qazwsx"}:
        return True
    if re.search(r"(.)\1{3,}", letters):
        return True
    if len(letters) < 8:
        return False
    # 'y' cuenta como vocal para no penalizar nombres como Krzysztof.
    vowels = sum(c in "aeiouy" for c in letters)
    consonant_runs = re.split(r"[aeiouy]", letters)
    return vowels / len(letters) <= 0.25 and max(map(len, consonant_runs)) >= 4
