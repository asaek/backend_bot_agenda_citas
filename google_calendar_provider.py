"""Adaptador REST de Google Calendar para el contrato `CalendarProvider`."""

import asyncio
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from google.auth.credentials import Credentials as GoogleCredentials
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as OAuthCredentials

from calendar_domain import (
    APPOINTMENT_DURATION,
    Appointment,
    AppointmentAccessDenied,
    AppointmentNotFound,
    AppointmentStatus,
    AvailableSlot,
    CalendarProvider,
    CalendarProviderError,
    CalendarProviderUnavailable,
    InvalidAppointmentState,
    InvalidToolArguments,
    PatientScope,
    SlotUnavailable,
)


GOOGLE_CALENDAR_API_BASE_URL = "https://www.googleapis.com/calendar/v3"
GOOGLE_OAUTH_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_SCOPES = (
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.freebusy",
)
MANAGED_BY_PROPERTY = "managed_by"
MANAGED_BY_VALUE = "whatsapp_chatbot"
PATIENT_ID_PROPERTY = "patient_id"
CONVERSATION_ID_PROPERTY = "conversation_id"


class GoogleCalendarConfigurationError(ValueError):
    """Indica que falta configuracion para acceder a Google Calendar."""


class AccessTokenProvider(Protocol):
    async def get_access_token(self) -> str:
        """Devuelve un token Bearer vigente."""


@dataclass(frozen=True, slots=True)
class StaticAccessTokenProvider:
    """Credencial determinista para pruebas del adaptador HTTP."""

    token: str

    def __post_init__(self) -> None:
        if not isinstance(self.token, str) or not self.token.strip():
            raise GoogleCalendarConfigurationError("El token de prueba no puede estar vacio")
        object.__setattr__(self, "token", self.token.strip())

    async def get_access_token(self) -> str:
        return self.token


class GoogleAuthTokenProvider:
    """Adapta `google-auth` para refrescar OAuth o cuenta de servicio."""

    def __init__(self, credentials: GoogleCredentials) -> None:
        self.credentials = credentials

    async def get_access_token(self) -> str:
        if not self.credentials.valid:
            try:
                await asyncio.to_thread(
                    self.credentials.refresh,
                    GoogleAuthRequest(),
                )
            except Exception as error:
                raise CalendarProviderUnavailable() from error

        token = self.credentials.token
        if not isinstance(token, str) or not token.strip():
            raise CalendarProviderUnavailable()
        return token


def create_oauth_token_provider(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str | None = None,
    access_token: str | None = None,
    token_uri: str = GOOGLE_OAUTH_TOKEN_URI,
    scopes: Sequence[str] = GOOGLE_CALENDAR_SCOPES,
) -> GoogleAuthTokenProvider:
    """Crea credenciales OAuth usando un token existente o un refresh token."""
    _require_text(client_id, "client_id")
    _require_text(client_secret, "client_secret")
    if not (refresh_token and refresh_token.strip()) and not (
        access_token and access_token.strip()
    ):
        raise GoogleCalendarConfigurationError(
            "OAuth requiere refresh_token o access_token"
        )
    credentials = OAuthCredentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=list(scopes),
    )
    return GoogleAuthTokenProvider(credentials)


def create_service_account_token_provider(
    service_account_info: Mapping[str, object],
    *,
    scopes: Sequence[str] = GOOGLE_CALENDAR_SCOPES,
    subject: str | None = None,
) -> GoogleAuthTokenProvider:
    """Crea credenciales de cuenta de servicio desde un JSON validado."""
    try:
        credentials = service_account.Credentials.from_service_account_info(
            dict(service_account_info),
            scopes=list(scopes),
        )
    except (TypeError, ValueError, GoogleAuthError) as error:
        raise GoogleCalendarConfigurationError(
            "La configuracion de la cuenta de servicio no es valida"
        ) from error
    if subject is not None and subject.strip():
        credentials = credentials.with_subject(subject.strip())
    return GoogleAuthTokenProvider(credentials)


def create_service_account_token_provider_from_file(
    path: str | Path,
    *,
    scopes: Sequence[str] = GOOGLE_CALENDAR_SCOPES,
    subject: str | None = None,
) -> GoogleAuthTokenProvider:
    """Carga una cuenta de servicio desde un archivo fuera del repositorio."""
    try:
        credentials = service_account.Credentials.from_service_account_file(
            str(path),
            scopes=list(scopes),
        )
    except (OSError, ValueError, GoogleAuthError) as error:
        raise GoogleCalendarConfigurationError(
            "No se pudo cargar el archivo de cuenta de servicio"
        ) from error
    if subject is not None and subject.strip():
        credentials = credentials.with_subject(subject.strip())
    return GoogleAuthTokenProvider(credentials)


def create_google_calendar_provider_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> "GoogleCalendarProvider":
    """Compone el adaptador usando variables de entorno y secretos externos."""
    values = os.environ if environment is None else environment
    calendar_ids = tuple(
        item.strip()
        for item in values.get("GOOGLE_CALENDAR_IDS", "").split(",")
        if item.strip()
    )
    if not calendar_ids:
        raise GoogleCalendarConfigurationError(
            "GOOGLE_CALENDAR_IDS debe contener al menos un calendario"
        )

    auth_mode = values.get("GOOGLE_CALENDAR_AUTH", "service_account").strip().lower()
    if auth_mode == "oauth":
        token_provider = create_oauth_token_provider(
            client_id=values.get("GOOGLE_OAUTH_CLIENT_ID", ""),
            client_secret=values.get("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            refresh_token=values.get("GOOGLE_OAUTH_REFRESH_TOKEN"),
            access_token=values.get("GOOGLE_OAUTH_ACCESS_TOKEN"),
        )
    elif auth_mode == "service_account":
        service_account_file = values.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
        if not service_account_file:
            raise GoogleCalendarConfigurationError(
                "GOOGLE_SERVICE_ACCOUNT_FILE no esta configurado"
            )
        token_provider = create_service_account_token_provider_from_file(
            service_account_file,
            subject=values.get("GOOGLE_SERVICE_ACCOUNT_SUBJECT"),
        )
    else:
        raise GoogleCalendarConfigurationError(
            "GOOGLE_CALENDAR_AUTH debe ser oauth o service_account"
        )

    try:
        timeout_seconds = float(values.get("GOOGLE_CALENDAR_TIMEOUT_SECONDS", "20"))
    except ValueError as error:
        raise GoogleCalendarConfigurationError(
            "GOOGLE_CALENDAR_TIMEOUT_SECONDS debe ser numerico"
        ) from error
    if timeout_seconds <= 0:
        raise GoogleCalendarConfigurationError(
            "GOOGLE_CALENDAR_TIMEOUT_SECONDS debe ser positivo"
        )

    return GoogleCalendarProvider(
        calendar_ids=calendar_ids,
        access_token_provider=token_provider,
        timezone_name=values.get("GOOGLE_CALENDAR_TIMEZONE", "UTC"),
        base_url=values.get(
            "GOOGLE_CALENDAR_BASE_URL",
            GOOGLE_CALENDAR_API_BASE_URL,
        ),
        timeout_seconds=timeout_seconds,
        http_client=http_client,
    )


class _GoogleCalendarNotFound(Exception):
    """Indica que un evento no existe en un calendario concreto."""


class GoogleCalendarProvider(CalendarProvider):
    """Implementacion REST de `CalendarProvider` sobre Google Calendar v3."""

    def __init__(
        self,
        *,
        calendar_ids: Sequence[str],
        access_token_provider: AccessTokenProvider,
        timezone_name: str = "UTC",
        base_url: str = GOOGLE_CALENDAR_API_BASE_URL,
        timeout_seconds: float = 20.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        normalized_calendar_ids = tuple(calendar_ids)
        if not normalized_calendar_ids:
            raise GoogleCalendarConfigurationError(
                "Debe existir al menos un calendario configurado"
            )
        if len(normalized_calendar_ids) > 50:
            raise GoogleCalendarConfigurationError(
                "Google Calendar permite como maximo 50 calendarios por freeBusy"
            )
        if len(set(normalized_calendar_ids)) != len(normalized_calendar_ids):
            raise GoogleCalendarConfigurationError(
                "Los calendarios configurados no pueden repetirse"
            )
        for calendar_id in normalized_calendar_ids:
            _require_text(calendar_id, "calendar_id")
        if timeout_seconds <= 0:
            raise GoogleCalendarConfigurationError(
                "timeout_seconds debe ser positivo"
            )
        try:
            timezone_value = ZoneInfo(timezone_name)
        except (TypeError, ZoneInfoNotFoundError) as error:
            raise GoogleCalendarConfigurationError(
                f"Zona horaria invalida: {timezone_name}"
            ) from error
        if not isinstance(base_url, str) or not base_url.startswith("https://"):
            raise GoogleCalendarConfigurationError(
                "base_url debe utilizar HTTPS"
            )

        self.calendar_ids = normalized_calendar_ids
        self.access_token_provider = access_token_provider
        self.timezone_name = timezone_name
        self._timezone = timezone_value
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client

    async def check_availability(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> Sequence[AvailableSlot]:
        _validate_range(start_at, end_at)
        busy_by_calendar = await self._query_busy_periods(start_at, end_at)
        slots: list[AvailableSlot] = []
        candidate_start = start_at
        while candidate_start + APPOINTMENT_DURATION <= end_at:
            candidate_end = candidate_start + APPOINTMENT_DURATION
            for calendar_id in self.calendar_ids:
                if not _overlaps_any(
                    candidate_start,
                    candidate_end,
                    busy_by_calendar[calendar_id],
                ):
                    slots.append(
                        AvailableSlot(
                            calendar_id=calendar_id,
                            start_at=candidate_start,
                            end_at=candidate_end,
                        )
                    )
            candidate_start = candidate_end
        return tuple(slots)

    async def create_appointment(
        self,
        *,
        patient_scope: PatientScope,
        start_at: datetime,
        reason: str,
    ) -> Appointment:
        _require_text(reason, "reason")
        end_at = start_at + APPOINTMENT_DURATION
        _validate_range(start_at, end_at)
        busy_by_calendar = await self._query_busy_periods(start_at, end_at)
        calendar_id = next(
            (
                candidate
                for candidate in self.calendar_ids
                if not _overlaps_any(
                    start_at,
                    end_at,
                    busy_by_calendar[candidate],
                )
            ),
            None,
        )
        if calendar_id is None:
            raise SlotUnavailable()

        event = await self._request(
            "POST",
            self._events_path(calendar_id),
            params=(
                ("sendUpdates", "all"),
            ),
            json_body=self._event_body(patient_scope, start_at, end_at, reason),
        )
        return self._require_appointment(
            calendar_id,
            event,
            patient_scope=patient_scope,
        )

    async def list_appointments(
        self,
        *,
        patient_scope: PatientScope,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> Sequence[Appointment]:
        if (start_at is None) != (end_at is None):
            raise InvalidToolArguments()
        if start_at is not None and end_at is not None:
            _validate_range(start_at, end_at)

        # Las consultas normales representan citas vigentes, no tombstones de Google.
        appointments: list[Appointment] = []
        for calendar_id in self.calendar_ids:
            events = await self._list_events(
                calendar_id,
                patient_scope=patient_scope,
                start_at=start_at,
                end_at=end_at,
            )
            for event in events:
                appointment = self._translate_event(
                    calendar_id,
                    event,
                    patient_scope=patient_scope,
                )
                if (
                    appointment is not None
                    and appointment.status is not AppointmentStatus.CANCELLED
                ):
                    appointments.append(appointment)
        return tuple(sorted(appointments, key=lambda item: (item.start_at, item.id)))

    async def reschedule_appointment(
        self,
        *,
        patient_scope: PatientScope,
        appointment_id: str,
        new_start_at: datetime,
    ) -> Appointment:
        _require_text(appointment_id, "appointment_id")
        _validate_range(new_start_at, new_start_at + APPOINTMENT_DURATION)
        calendar_id, _, appointment = await self._find_event(
            appointment_id,
            patient_scope,
        )
        if not appointment.can_be_rescheduled:
            raise InvalidAppointmentState()
        new_end_at = new_start_at + APPOINTMENT_DURATION
        busy_by_calendar = await self._query_busy_periods(new_start_at, new_end_at)
        busy_periods = tuple(
            period
            for period in busy_by_calendar[calendar_id]
            if not (
                period[0] == appointment.start_at
                and period[1] == appointment.end_at
            )
        )
        if _overlaps_any(new_start_at, new_end_at, busy_periods):
            raise SlotUnavailable()

        updated_event = await self._request(
            "PATCH",
            self._event_path(calendar_id, appointment_id),
            params=(
                ("sendUpdates", "all"),
            ),
            json_body={
                "start": self._event_time(new_start_at),
                "end": self._event_time(new_end_at),
            },
        )
        return self._require_appointment(
            calendar_id,
            updated_event,
            patient_scope=patient_scope,
        )

    async def cancel_appointment(
        self,
        *,
        patient_scope: PatientScope,
        appointment_id: str,
    ) -> Appointment:
        _require_text(appointment_id, "appointment_id")
        calendar_id, _, appointment = await self._find_event(
            appointment_id,
            patient_scope,
        )
        if not appointment.can_be_cancelled:
            raise InvalidAppointmentState()
        cancelled_event = await self._request(
            "PATCH",
            self._event_path(calendar_id, appointment_id),
            params=(
                ("sendUpdates", "all"),
            ),
            json_body={"status": "cancelled"},
        )
        response_status = cancelled_event.get("status")
        if response_status not in {None, AppointmentStatus.CANCELLED.value}:
            raise CalendarProviderError()
        translated = self._translate_event(
            calendar_id,
            cancelled_event,
            patient_scope=patient_scope,
        )
        if translated is None or translated.status is not AppointmentStatus.CANCELLED:
            return replace(appointment, status=AppointmentStatus.CANCELLED)
        return translated

    async def _query_busy_periods(
        self,
        start_at: datetime,
        end_at: datetime,
    ) -> dict[str, tuple[tuple[datetime, datetime], ...]]:
        response = await self._request(
            "POST",
            "/freeBusy",
            json_body={
                "timeMin": _format_datetime(start_at),
                "timeMax": _format_datetime(end_at),
                "timeZone": self.timezone_name,
                "items": [{"id": calendar_id} for calendar_id in self.calendar_ids],
            },
        )
        calendars = response.get("calendars")
        if not isinstance(calendars, Mapping):
            raise CalendarProviderError()

        result: dict[str, tuple[tuple[datetime, datetime], ...]] = {}
        for calendar_id in self.calendar_ids:
            calendar = calendars.get(calendar_id)
            if not isinstance(calendar, Mapping):
                raise CalendarProviderError()
            if calendar.get("errors"):
                raise CalendarProviderError()
            raw_busy = calendar.get("busy", [])
            if not isinstance(raw_busy, list):
                raise CalendarProviderError()
            busy_periods: list[tuple[datetime, datetime]] = []
            for period in raw_busy:
                if not isinstance(period, Mapping):
                    raise CalendarProviderError()
                start = period.get("start")
                end = period.get("end")
                if not isinstance(start, str) or not isinstance(end, str):
                    raise CalendarProviderError()
                parsed_start = self._parse_datetime(start)
                parsed_end = self._parse_datetime(end)
                if parsed_end <= parsed_start:
                    raise CalendarProviderError()
                busy_periods.append((parsed_start, parsed_end))
            result[calendar_id] = tuple(busy_periods)
        return result

    async def _list_events(
        self,
        calendar_id: str,
        *,
        patient_scope: PatientScope,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> tuple[Mapping[str, object], ...]:
        page_token: str | None = None
        seen_page_tokens: set[str] = set()
        events: list[Mapping[str, object]] = []
        while True:
            params: list[tuple[str, str]] = [
                ("singleEvents", "true"),
                ("showDeleted", "false"),
                ("orderBy", "startTime"),
                ("maxResults", "2500"),
                (
                    "privateExtendedProperty",
                    f"{MANAGED_BY_PROPERTY}={MANAGED_BY_VALUE}",
                ),
                (
                    "privateExtendedProperty",
                    f"{PATIENT_ID_PROPERTY}={patient_scope.patient_id}",
                ),
            ]
            if start_at is not None and end_at is not None:
                params.extend(
                    (
                        ("timeMin", _format_datetime(start_at)),
                        ("timeMax", _format_datetime(end_at)),
                    )
                )
            if page_token is not None:
                params.append(("pageToken", page_token))

            response = await self._request(
                "GET",
                self._events_path(calendar_id),
                params=tuple(params),
            )
            raw_items = response.get("items", [])
            if not isinstance(raw_items, list):
                raise CalendarProviderError()
            events.extend(
                item for item in raw_items if isinstance(item, Mapping)
            )
            next_page_token = response.get("nextPageToken")
            if not isinstance(next_page_token, str) or not next_page_token:
                return tuple(events)
            if next_page_token in seen_page_tokens:
                raise CalendarProviderError()
            seen_page_tokens.add(next_page_token)
            page_token = next_page_token

    async def _find_event(
        self,
        appointment_id: str,
        patient_scope: PatientScope,
    ) -> tuple[str, Mapping[str, object], Appointment]:
        for calendar_id in self.calendar_ids:
            try:
                event = await self._request(
                    "GET",
                    self._event_path(calendar_id, appointment_id),
                )
            except _GoogleCalendarNotFound:
                continue
            if not _event_matches_patient(event, patient_scope):
                raise AppointmentAccessDenied()
            if event.get("status") == AppointmentStatus.CANCELLED.value:
                raise InvalidAppointmentState()
            appointment = self._translate_event(
                calendar_id,
                event,
                patient_scope=patient_scope,
            )
            if appointment is None:
                raise CalendarProviderError()
            return calendar_id, event, appointment
        raise AppointmentNotFound()

    def _require_appointment(
        self,
        calendar_id: str,
        event: Mapping[str, object],
        *,
        patient_scope: PatientScope,
    ) -> Appointment:
        appointment = self._translate_event(
            calendar_id,
            event,
            patient_scope=patient_scope,
        )
        if appointment is None:
            raise CalendarProviderError()
        return appointment

    def _translate_event(
        self,
        calendar_id: str,
        event: Mapping[str, object],
        *,
        patient_scope: PatientScope,
    ) -> Appointment | None:
        if not _event_matches_patient(event, patient_scope):
            return None

        event_id = event.get("id")
        start_data = event.get("start")
        end_data = event.get("end")
        if not isinstance(event_id, str):
            return None
        if not isinstance(start_data, Mapping) or not isinstance(end_data, Mapping):
            return None
        start_value = start_data.get("dateTime")
        end_value = end_data.get("dateTime")
        if not isinstance(start_value, str) or not isinstance(end_value, str):
            return None
        try:
            start_at = self._parse_datetime(start_value)
            end_at = self._parse_datetime(end_value)
        except ValueError:
            return None
        if end_at - start_at != APPOINTMENT_DURATION:
            return None

        status = {
            "confirmed": AppointmentStatus.CONFIRMED,
            "cancelled": AppointmentStatus.CANCELLED,
        }.get(event.get("status"), AppointmentStatus.SCHEDULED)
        description = event.get("description")
        summary = event.get("summary")
        reason = description if isinstance(description, str) and description.strip() else summary
        if not isinstance(reason, str) or not reason.strip():
            reason = "Cita medica"
        return Appointment(
            id=event_id,
            patient_scope=patient_scope,
            calendar_id=calendar_id,
            start_at=start_at,
            end_at=end_at,
            reason=reason.strip(),
            status=status,
        )

    def _event_body(
        self,
        patient_scope: PatientScope,
        start_at: datetime,
        end_at: datetime,
        reason: str,
    ) -> dict[str, object]:
        _require_text(reason, "reason")
        return {
            "summary": "Cita medica",
            "description": reason.strip(),
            "start": self._event_time(start_at),
            "end": self._event_time(end_at),
            "status": "confirmed",
            "transparency": "opaque",
            "visibility": "private",
            "extendedProperties": {
                "private": {
                    MANAGED_BY_PROPERTY: MANAGED_BY_VALUE,
                    PATIENT_ID_PROPERTY: str(patient_scope.patient_id),
                    CONVERSATION_ID_PROPERTY: str(patient_scope.conversation_id),
                }
            },
        }

    def _event_time(self, value: datetime) -> dict[str, str]:
        return {
            "dateTime": _format_datetime(value),
            "timeZone": self.timezone_name,
        }

    def _parse_datetime(self, value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return parsed.replace(tzinfo=self._timezone)
        return parsed

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Sequence[tuple[str, str]] = (),
        json_body: Mapping[str, object] | None = None,
    ) -> Mapping[str, object]:
        try:
            access_token = await self.access_token_provider.get_access_token()
        except (CalendarProviderUnavailable, CalendarProviderError):
            raise
        except Exception as error:
            raise CalendarProviderUnavailable() from error

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        try:
            if self.http_client is not None:
                response = await self.http_client.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=headers,
                    params=list(params),
                    json=json_body,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.request(
                        method,
                        f"{self.base_url}{path}",
                        headers=headers,
                        params=list(params),
                        json=json_body,
                    )
        except (httpx.TimeoutException, httpx.ConnectError) as error:
            raise CalendarProviderUnavailable() from error
        except httpx.HTTPError as error:
            raise CalendarProviderError() from error

        if response.status_code == 404:
            raise _GoogleCalendarNotFound()
        if response.status_code in {408, 429, 500, 502, 503, 504}:
            raise CalendarProviderUnavailable()
        if response.status_code >= 400:
            raise CalendarProviderError()
        try:
            data = response.json()
        except ValueError as error:
            raise CalendarProviderError() from error
        if not isinstance(data, Mapping):
            raise CalendarProviderError()
        return data

    def _events_path(self, calendar_id: str) -> str:
        return f"/calendars/{quote(calendar_id, safe='')}/events"

    def _event_path(self, calendar_id: str, event_id: str) -> str:
        return f"{self._events_path(calendar_id)}/{quote(event_id, safe='')}"


def _private_properties(event: Mapping[str, object]) -> Mapping[str, str]:
    extended_properties = event.get("extendedProperties")
    if not isinstance(extended_properties, Mapping):
        return {}
    private = extended_properties.get("private")
    if not isinstance(private, Mapping):
        return {}
    return {
        key: value
        for key, value in private.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _event_matches_patient(
    event: Mapping[str, object],
    patient_scope: PatientScope,
) -> bool:
    private = _private_properties(event)
    return (
        private.get(MANAGED_BY_PROPERTY) == MANAGED_BY_VALUE
        and private.get(PATIENT_ID_PROPERTY) == str(patient_scope.patient_id)
    )


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Google Calendar requiere fechas con zona horaria")
    formatted = value.isoformat()
    return formatted.replace("+00:00", "Z")


def _validate_range(start_at: datetime, end_at: datetime) -> None:
    try:
        _format_datetime(start_at)
        _format_datetime(end_at)
    except ValueError as error:
        raise InvalidToolArguments() from error
    if end_at <= start_at:
        raise InvalidToolArguments()


def _overlaps_any(
    start_at: datetime,
    end_at: datetime,
    busy_periods: Sequence[tuple[datetime, datetime]],
) -> bool:
    return any(
        start_at < busy_end and end_at > busy_start
        for busy_start, busy_end in busy_periods
    )


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise GoogleCalendarConfigurationError(f"{name} no puede estar vacio")
