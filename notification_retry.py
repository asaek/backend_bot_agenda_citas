"""Politica durable de espera y clasificacion de fallos de entrega."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

from whatsapp_client import WhatsAppConfigurationError

TRANSIENT_PROVIDER_CODES = frozenset({4, 17, 32, 613, 130429, 131056})


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class DeliveryFailure:
    kind: str
    http_status: int | None = None
    provider_code: int | None = None
    retry_after: float = 0


def classify_failure(error: Exception, now: str) -> DeliveryFailure:
    if isinstance(error, WhatsAppConfigurationError):
        return DeliveryFailure("configuration")
    if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)):
        return DeliveryFailure("transient")
    if isinstance(error, httpx.HTTPStatusError):
        response = error.response
        code = None
        transient = False
        try:
            details = response.json().get("error", {})
            raw_code = details.get("code")
            code = raw_code if isinstance(raw_code, int) and not isinstance(raw_code, bool) else None
            transient = details.get("is_transient") is True or code in TRANSIENT_PROVIDER_CODES
        except (ValueError, AttributeError, TypeError):
            pass
        delay = 0.0
        retry_after = response.headers.get("Retry-After", "")
        try:
            delay = float(retry_after)
        except ValueError:
            try:
                delay = (parsedate_to_datetime(retry_after).astimezone(timezone.utc) - parse_time(now)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                pass
        kind = "transient" if response.status_code == 429 or response.status_code >= 500 or transient else "configuration"
        return DeliveryFailure(kind, response.status_code, code, max(0, min(delay, 86400)))
    return DeliveryFailure("uncertain")


def next_retry(now: str, failure_count: int, retry_after: float = 0) -> str:
    delay = max(min(60 * 2 ** min(failure_count, 6), 3600), retry_after)
    return (parse_time(now) + timedelta(seconds=delay)).isoformat()
