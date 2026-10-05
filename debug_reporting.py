"""Diagnostico temporal de fallos limitado a remitentes autorizados."""

from collections.abc import Mapping
import os
import re


DEBUG_MODE_ENV = "DEBUG_MODE"
DEBUG_WHATSAPP_NUMBERS_ENV = "DEBUG_WHATSAPP_NUMBERS"

_SAFE_LABEL = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")


def format_debug_fallback_reply(
    recipient_number: str,
    *,
    error_type: str,
    provider_name: str | None = None,
    http_status_code: int | None = None,
    diagnostic_code: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> str | None:
    """Devuelve detalles no sensibles solo en modo debug y a un numero permitido."""
    values = os.environ if environment is None else environment
    enabled = values.get(DEBUG_MODE_ENV, "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not enabled:
        return None

    recipient = _normalize_number(recipient_number)
    allowed_numbers = {
        _normalize_number(value)
        for value in values.get(DEBUG_WHATSAPP_NUMBERS_ENV, "").split(",")
        if _normalize_number(value)
    }
    if not recipient or recipient not in allowed_numbers:
        return None

    details: list[str] = []
    if isinstance(provider_name, str) and _SAFE_LABEL.fullmatch(provider_name):
        details.append(f"proveedor={provider_name}")
    safe_error_type = (
        error_type if isinstance(error_type, str) and _SAFE_LABEL.fullmatch(error_type)
        else "UnknownError"
    )
    details.append(f"error={safe_error_type}")
    if (
        type(http_status_code) is int
        and 100 <= http_status_code <= 599
    ):
        details.append(f"HTTP={http_status_code}")
    if isinstance(diagnostic_code, str) and _SAFE_LABEL.fullmatch(diagnostic_code):
        details.append(f"code={diagnostic_code}")

    return "Diagnóstico debug: " + "; ".join(details) + "."


def _normalize_number(value: str) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(character for character in value if "0" <= character <= "9")
