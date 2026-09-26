"""Validacion local y conservadora del texto usado como motivo de cita."""

from dataclasses import dataclass
from enum import Enum
import re
import unicodedata


class AppointmentReasonValidationCode(str, Enum):
    """Resultado de las reglas de calidad minima del motivo."""

    ACCEPTED = "accepted"
    EMPTY = "empty"
    NO_LETTERS = "no_letters"
    TOO_SHORT = "too_short"
    LIKELY_GIBBERISH = "likely_gibberish"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class AppointmentReasonValidationResult:
    """Resultado publico del validador sin interpretar clinicamente el texto."""

    normalized_text: str
    code: AppointmentReasonValidationCode

    @property
    def accepted(self) -> bool:
        return self.code is AppointmentReasonValidationCode.ACCEPTED


def validate_appointment_reason(text: str) -> AppointmentReasonValidationResult:
    """Valida si el texto tiene contenido minimo util para continuar la cita.

    Las reglas detectan entradas vacias, evidentemente ilegibles o referencias vagas.
    No se usa una lista cerrada de sintomas y no se intenta diagnosticar al paciente.
    """
    if not isinstance(text, str):
        raise TypeError("El motivo de la cita debe ser texto")

    normalized = _normalize_text(text)
    if not normalized:
        return _result(normalized, AppointmentReasonValidationCode.EMPTY)

    letters = _letters(normalized)
    if not letters:
        return _result(normalized, AppointmentReasonValidationCode.NO_LETTERS)
    if len(letters) < 3:
        return _result(normalized, AppointmentReasonValidationCode.TOO_SHORT)
    if _looks_like_gibberish(normalized):
        return _result(normalized, AppointmentReasonValidationCode.LIKELY_GIBBERISH)
    if _looks_ambiguous(normalized):
        return _result(normalized, AppointmentReasonValidationCode.AMBIGUOUS)

    return _result(normalized, AppointmentReasonValidationCode.ACCEPTED)


def _result(
    normalized_text: str,
    code: AppointmentReasonValidationCode,
) -> AppointmentReasonValidationResult:
    return AppointmentReasonValidationResult(
        normalized_text=normalized_text,
        code=code,
    )


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _letters(value: str) -> str:
    return "".join(character for character in value if character.isalpha())


def _looks_like_gibberish(value: str) -> bool:
    compact_letters = _letters(value).casefold()
    if re.search(r"(.)\1{3,}", compact_letters):
        return True

    keyboard_sequences = (
        "asdf",
        "qwer",
        "zxcv",
        "qazwsx",
        "wsxedc",
        "edcrfv",
    )
    if any(sequence in compact_letters for sequence in keyboard_sequences):
        return True

    words = re.findall(r"[^\W\d_]+", value, flags=re.UNICODE)
    for word in words:
        word_letters = _letters(word)
        if len(word_letters) < 10:
            continue
        vowel_ratio = sum(_is_vowel(character) for character in word_letters) / len(
            word_letters
        )
        if vowel_ratio < 0.18 and _max_consonant_run(word_letters) >= 3:
            return True
    return False


def _looks_ambiguous(value: str) -> bool:
    normalized = unicodedata.normalize("NFD", value.casefold())
    normalized = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    )
    return any(
        re.search(pattern, normalized)
        for pattern in (
            r"\blo de siempre\b",
            r"\blo mismo de siempre\b",
            r"\bcomo siempre\b",
            r"\bla consulta de siempre\b",
        )
    )


def _is_vowel(character: str) -> bool:
    base_character = unicodedata.normalize("NFD", character)[0].casefold()
    return base_character in "aeiou"


def _max_consonant_run(value: str) -> int:
    maximum = 0
    current = 0
    for character in value:
        if _is_vowel(character):
            current = 0
            continue
        current += 1
        maximum = max(maximum, current)
    return maximum
