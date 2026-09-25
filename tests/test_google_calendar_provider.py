import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx

from calendar_domain import (
    AppointmentAccessDenied,
    AppointmentStatus,
    CalendarProviderError,
    CalendarProviderUnavailable,
    InvalidAppointmentState,
    PatientScope,
    SlotUnavailable,
)
from google_calendar_provider import (
    CONVERSATION_ID_PROPERTY,
    MANAGED_BY_PROPERTY,
    MANAGED_BY_VALUE,
    PATIENT_ID_PROPERTY,
    GoogleCalendarConfigurationError,
    GoogleCalendarProvider,
    StaticAccessTokenProvider,
    create_google_calendar_provider_from_environment,
)


class GoogleCalendarProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.patient = PatientScope(
            patient_id=7,
            conversation_id=42,
            whatsapp_number="5491100000000",
        )
        self.other_patient = PatientScope(
            patient_id=8,
            conversation_id=43,
            whatsapp_number="5491100000001",
        )
        self.start = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)
        self.requests: list[httpx.Request] = []
        self.mode = ""

    async def asyncSetUp(self) -> None:
        self.client = httpx.AsyncClient(
            transport=httpx.MockTransport(self._handle_request),
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    def provider_for(self, *calendar_ids: str) -> GoogleCalendarProvider:
        return GoogleCalendarProvider(
            calendar_ids=calendar_ids,
            access_token_provider=StaticAccessTokenProvider("test-token"),
            timezone_name="UTC",
            base_url="https://calendar.test/v3",
            http_client=self.client,
        )

    async def test_check_availability_queries_all_configured_calendars(self) -> None:
        self.mode = "availability"

        slots = await self.provider_for("calendar-1", "calendar-2").check_availability(
            start_at=self.start,
            end_at=self.start + timedelta(hours=1),
        )

        self.assertEqual(
            [(slot.calendar_id, slot.start_at) for slot in slots],
            [
                ("calendar-2", self.start),
                ("calendar-1", self.start + timedelta(minutes=30)),
                ("calendar-2", self.start + timedelta(minutes=30)),
            ],
        )
        request = self.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url.path, "/v3/freeBusy")
        self.assertEqual(request.headers["Authorization"], "Bearer test-token")
        body = json.loads(request.content)
        self.assertEqual(body["items"], [{"id": "calendar-1"}, {"id": "calendar-2"}])
        self.assertEqual(body["timeZone"], "UTC")

    async def test_create_writes_private_scope_properties(self) -> None:
        self.mode = "create"
        provider = self.provider_for("calendar-1")

        appointment = await provider.create_appointment(
            patient_scope=self.patient,
            start_at=self.start,
            reason="  Revision corneal  ",
        )

        self.assertEqual(appointment.patient_scope, self.patient)
        self.assertEqual(appointment.reason, "Revision corneal")
        self.assertEqual(appointment.status, AppointmentStatus.CONFIRMED)
        event_request = self.requests[1]
        self.assertEqual(event_request.method, "POST")
        self.assertEqual(event_request.url.path, "/v3/calendars/calendar-1/events")
        self.assertEqual(event_request.url.params["sendUpdates"], "all")
        body = json.loads(event_request.content)
        self.assertEqual(
            body["extendedProperties"]["private"],
            {
                MANAGED_BY_PROPERTY: MANAGED_BY_VALUE,
                PATIENT_ID_PROPERTY: "7",
                CONVERSATION_ID_PROPERTY: "42",
            },
        )
        self.assertEqual(body["description"], "Revision corneal")

    async def test_list_follows_pages_and_requires_private_metadata(self) -> None:
        self.mode = "list"
        provider = self.provider_for("calendar-1")

        appointments = await provider.list_appointments(patient_scope=self.patient)

        self.assertEqual([appointment.id for appointment in appointments], ["event-early", "event-late"])
        self.assertTrue(all(appointment.patient_scope == self.patient for appointment in appointments))
        self.assertEqual(len(self.requests), 2)
        for request in self.requests:
            properties = request.url.params.get_list("privateExtendedProperty")
            self.assertIn(f"{MANAGED_BY_PROPERTY}={MANAGED_BY_VALUE}", properties)
            self.assertIn(f"{PATIENT_ID_PROPERTY}=7", properties)
        self.assertEqual(self.requests[1].url.params["pageToken"], "page-2")

    async def test_list_omits_cancelled_events_from_current_appointments(self) -> None:
        self.mode = "list-with-cancelled"

        appointments = await self.provider_for("calendar-1").list_appointments(
            patient_scope=self.patient,
        )

        self.assertEqual([appointment.id for appointment in appointments], ["event-active"])
        self.assertEqual(self.requests[0].url.params["showDeleted"], "false")

    async def test_reschedule_and_cancel_use_event_patch(self) -> None:
        self.mode = "reschedule"
        provider = self.provider_for("calendar-1")
        new_start = self.start + timedelta(hours=2)

        moved = await provider.reschedule_appointment(
            patient_scope=self.patient,
            appointment_id="event-1",
            new_start_at=new_start,
        )

        self.assertEqual(moved.start_at, new_start)
        patch_request = self.requests[-1]
        self.assertEqual(patch_request.method, "PATCH")
        self.assertEqual(patch_request.url.params["sendUpdates"], "all")
        patch_body = json.loads(patch_request.content)
        self.assertEqual(patch_body["start"]["dateTime"], "2026-09-21T12:00:00Z")
        self.assertEqual(patch_body["end"]["dateTime"], "2026-09-21T12:30:00Z")

        self.requests.clear()
        self.mode = "cancel"
        cancelled = await provider.cancel_appointment(
            patient_scope=self.patient,
            appointment_id="event-1",
        )

        self.assertEqual(cancelled.status, AppointmentStatus.CANCELLED)
        self.assertEqual(self.requests[-1].method, "PATCH")
        self.assertEqual(self.requests[-1].url.params["sendUpdates"], "all")
        self.assertEqual(json.loads(self.requests[-1].content), {"status": "cancelled"})

    async def test_reschedule_rejects_a_busy_target_before_patching(self) -> None:
        self.mode = "reschedule-conflict"
        provider = self.provider_for("calendar-1")

        with self.assertRaises(SlotUnavailable):
            await provider.reschedule_appointment(
                patient_scope=self.patient,
                appointment_id="event-1",
                new_start_at=self.start + timedelta(hours=2),
            )

        self.assertEqual([request.method for request in self.requests], ["GET", "POST"])

    async def test_cancel_partial_response_keeps_the_cancelled_state(self) -> None:
        self.mode = "cancel-partial"

        cancelled = await self.provider_for("calendar-1").cancel_appointment(
            patient_scope=self.patient,
            appointment_id="event-1",
        )

        self.assertEqual(cancelled.status, AppointmentStatus.CANCELLED)

    async def test_cancel_rejects_a_response_that_is_not_cancelled(self) -> None:
        self.mode = "cancel-unconfirmed"

        with self.assertRaises(CalendarProviderError):
            await self.provider_for("calendar-1").cancel_appointment(
                patient_scope=self.patient,
                appointment_id="event-1",
            )

    async def test_event_for_another_patient_is_not_modifiable(self) -> None:
        self.mode = "access-denied"

        with self.assertRaises(AppointmentAccessDenied):
            await self.provider_for("calendar-1").cancel_appointment(
                patient_scope=self.patient,
                appointment_id="event-1",
            )

    async def test_cancelled_event_cannot_be_rescheduled(self) -> None:
        self.mode = "cancelled"

        with self.assertRaises(InvalidAppointmentState):
            await self.provider_for("calendar-1").reschedule_appointment(
                patient_scope=self.patient,
                appointment_id="event-1",
                new_start_at=self.start + timedelta(hours=1),
            )

    async def test_cancelled_event_without_times_cannot_be_rescheduled(self) -> None:
        self.mode = "cancelled-minimal"

        with self.assertRaises(InvalidAppointmentState):
            await self.provider_for("calendar-1").reschedule_appointment(
                patient_scope=self.patient,
                appointment_id="event-1",
                new_start_at=self.start + timedelta(hours=1),
            )

    async def test_transient_google_error_becomes_provider_unavailable(self) -> None:
        self.mode = "unavailable"

        with self.assertRaises(CalendarProviderUnavailable):
            await self.provider_for("calendar-1").check_availability(
                start_at=self.start,
                end_at=self.start + timedelta(minutes=30),
            )

    async def test_environment_factory_supports_oauth_and_service_account_modes(self) -> None:
        oauth_provider = create_google_calendar_provider_from_environment(
            {
                "GOOGLE_CALENDAR_IDS": "calendar-1, calendar-2",
                "GOOGLE_CALENDAR_AUTH": "oauth",
                "GOOGLE_OAUTH_CLIENT_ID": "client-id",
                "GOOGLE_OAUTH_CLIENT_SECRET": "client-secret",
                "GOOGLE_OAUTH_ACCESS_TOKEN": "access-token",
                "GOOGLE_CALENDAR_TIMEZONE": "America/Argentina/Buenos_Aires",
            },
            http_client=self.client,
        )
        self.assertEqual(oauth_provider.calendar_ids, ("calendar-1", "calendar-2"))
        self.assertEqual(
            oauth_provider.timezone_name,
            "America/Argentina/Buenos_Aires",
        )
        self.assertEqual(
            oauth_provider.access_token_provider.credentials.token,
            "access-token",
        )

        service_account_provider = StaticAccessTokenProvider("service-token")
        with patch(
            "google_calendar_provider.create_service_account_token_provider_from_file",
            return_value=service_account_provider,
        ) as factory:
            provider = create_google_calendar_provider_from_environment(
                {
                    "GOOGLE_CALENDAR_IDS": "calendar-1",
                    "GOOGLE_CALENDAR_AUTH": "service_account",
                    "GOOGLE_SERVICE_ACCOUNT_FILE": "/run/secrets/google.json",
                    "GOOGLE_SERVICE_ACCOUNT_SUBJECT": "doctor@example.com",
                },
                http_client=self.client,
            )

        factory.assert_called_once_with(
            "/run/secrets/google.json",
            subject="doctor@example.com",
        )
        self.assertIs(provider.access_token_provider, service_account_provider)

    def test_provider_rejects_more_than_google_freebusy_limit(self) -> None:
        with self.assertRaises(GoogleCalendarConfigurationError):
            self.provider_for(*(f"calendar-{index}" for index in range(51)))

    def _handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if self.mode == "availability" and path.endswith("/freeBusy"):
            return self._freebusy_response(request, busy_calendar="calendar-1")
        if self.mode == "create" and path.endswith("/freeBusy"):
            return self._freebusy_response(request)
        if self.mode == "create" and request.method == "POST":
            event = self._event("event-1")
            event["description"] = json.loads(request.content)["description"]
            return self._json_response(request, event)
        if self.mode == "list" and request.method == "GET":
            if request.url.params.get("pageToken") == "page-2":
                return self._json_response(
                    request,
                    {"items": [self._event("event-early", self.start)]},
                )
            return self._json_response(
                request,
                {
                    "items": [
                        self._event(
                            "event-late",
                            self.start + timedelta(hours=1),
                        )
                    ],
                    "nextPageToken": "page-2",
                },
            )
        if self.mode == "list-with-cancelled" and request.method == "GET":
            return self._json_response(
                request,
                {
                    "items": [
                        self._event("event-cancelled", status="cancelled"),
                        self._event("event-active"),
                    ]
                },
            )
        if self.mode == "reschedule":
            if request.method == "GET":
                return self._json_response(request, self._event("event-1"))
            if path.endswith("/freeBusy"):
                return self._freebusy_response(request)
            return self._json_response(
                request,
                self._event("event-1", self.start + timedelta(hours=2)),
            )
        if self.mode == "reschedule-conflict":
            if request.method == "GET":
                return self._json_response(request, self._event("event-1"))
            if path.endswith("/freeBusy"):
                return self._freebusy_response(
                    request,
                    busy_calendar="calendar-1",
                    busy_start=self.start + timedelta(hours=2),
                )
            raise AssertionError(f"No se esperaba modificar un conflicto: {request.url}")
        if self.mode == "cancel":
            if request.method == "GET":
                return self._json_response(request, self._event("event-1"))
            return self._json_response(
                request,
                self._event("event-1", status="cancelled"),
            )
        if self.mode == "cancel-partial":
            if request.method == "GET":
                return self._json_response(request, self._event("event-1"))
            event = self._event("event-1", status="cancelled")
            event.pop("status")
            return self._json_response(request, event)
        if self.mode == "cancel-unconfirmed":
            return self._json_response(request, self._event("event-1"))
        if self.mode == "access-denied":
            return self._json_response(
                request,
                self._event("event-1", patient_id=self.other_patient.patient_id),
            )
        if self.mode == "cancelled":
            return self._json_response(
                request,
                self._event("event-1", status="cancelled"),
            )
        if self.mode == "cancelled-minimal":
            return self._json_response(
                request,
                self._event("event-1", status="cancelled", minimal=True),
            )
        if self.mode == "unavailable":
            return httpx.Response(503, json={"error": "temporarily unavailable"}, request=request)
        raise AssertionError(f"Ruta no esperada: {request.method} {request.url}")

    def _freebusy_response(
        self,
        request: httpx.Request,
        *,
        busy_calendar: str | None = None,
        busy_start: datetime | None = None,
    ) -> httpx.Response:
        calendars = {
            "calendar-1": {"busy": []},
            "calendar-2": {"busy": []},
        }
        if busy_calendar is not None:
            busy_start = busy_start or self.start
            calendars[busy_calendar] = {
                "busy": [
                    {
                        "start": self._format_datetime(busy_start),
                        "end": self._format_datetime(
                            busy_start + timedelta(minutes=30)
                        ),
                    }
                ]
            }
        return self._json_response(request, {"calendars": calendars})

    def _event(
        self,
        event_id: str,
        start_at: datetime | None = None,
        *,
        patient_id: int | None = None,
        status: str = "confirmed",
        managed: bool = True,
        minimal: bool = False,
    ) -> dict[str, object]:
        private = {
            PATIENT_ID_PROPERTY: str(
                self.patient.patient_id if patient_id is None else patient_id
            ),
            CONVERSATION_ID_PROPERTY: str(self.patient.conversation_id),
        }
        if managed:
            private[MANAGED_BY_PROPERTY] = MANAGED_BY_VALUE
        if minimal:
            return {
                "id": event_id,
                "status": status,
                "extendedProperties": {"private": private},
            }
        start_at = start_at or self.start
        return {
            "id": event_id,
            "status": status,
            "summary": "Cita medica",
            "description": "Revision",
            "start": {"dateTime": self._format_datetime(start_at)},
            "end": {
                "dateTime": self._format_datetime(start_at + timedelta(minutes=30))
            },
            "extendedProperties": {"private": private},
        }

    @staticmethod
    def _format_datetime(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    @staticmethod
    def _json_response(
        request: httpx.Request,
        payload: object,
    ) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)


if __name__ == "__main__":
    unittest.main()
