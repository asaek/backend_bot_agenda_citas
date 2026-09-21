import os
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import httpx

from calendar_domain import (
    AppointmentAccessDenied,
    AppointmentNotFound,
    AppointmentStatus,
    PatientScope,
)
from fake_calendar_provider import FakeCalendarProvider
from google_calendar_provider import (
    CONVERSATION_ID_PROPERTY,
    MANAGED_BY_PROPERTY,
    MANAGED_BY_VALUE,
    PATIENT_ID_PROPERTY,
    GoogleCalendarProvider,
    StaticAccessTokenProvider,
)
from persistence import SQLiteDatabase
from persistent_calendar_provider import PersistentCalendarProvider
from repositories import AppointmentRepository


class AppointmentRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = SQLiteDatabase(os.path.join(self.directory.name, "test.sqlite3"))
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO patients (whatsapp_number, created_at, last_seen_at)
                VALUES (?, ?, ?)
                """,
                ("5491100000000", "2026-09-20T12:00:00+00:00", "2026-09-20T12:00:00+00:00"),
            )
        self.repository = AppointmentRepository()

    def test_upsert_separates_internal_and_google_ids_and_updates_sync_state(self) -> None:
        with self.database.transaction() as connection:
            created = self.repository.upsert_synced(
                connection,
                calendar_id="calendar-1",
                google_event_id="google-event-1",
                patient_id=1,
                status="confirmed",
                start_at="2026-09-21T10:00:00+00:00",
                end_at="2026-09-21T10:30:00+00:00",
                reason="Revision",
                synced_at="2026-09-20T12:00:00+00:00",
            )

        with self.database.transaction() as connection:
            updated = self.repository.upsert_synced(
                connection,
                calendar_id="calendar-1",
                google_event_id="google-event-1",
                patient_id=1,
                status="cancelled",
                start_at="2026-09-21T10:00:00+00:00",
                end_at="2026-09-21T10:30:00+00:00",
                reason="Revision cancelada",
                synced_at="2026-09-20T12:05:00+00:00",
            )

        self.assertEqual(created.id, 1)
        self.assertEqual(created.google_event_id, "google-event-1")
        self.assertEqual(updated.id, created.id)
        self.assertEqual(updated.status, "cancelled")
        self.assertEqual(updated.last_synced_at, "2026-09-20T12:05:00+00:00")
        self.assertEqual(updated.created_at, created.created_at)
        with self.database.transaction() as connection:
            self.assertEqual(self.repository.list_for_patient(connection, 1), [updated])


class PersistentCalendarProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = SQLiteDatabase(os.path.join(self.directory.name, "test.sqlite3"))
        with self.database.transaction() as connection:
            for whatsapp_number in ("5491100000000", "5491100000001"):
                connection.execute(
                    """
                    INSERT INTO patients (whatsapp_number, created_at, last_seen_at)
                    VALUES (?, ?, ?)
                    """,
                    (whatsapp_number, "2026-09-20T12:00:00+00:00", "2026-09-20T12:00:00+00:00"),
                )
        self.patient = PatientScope(
            patient_id=1,
            conversation_id=1,
            whatsapp_number="5491100000000",
        )
        self.other_patient = PatientScope(
            patient_id=2,
            conversation_id=2,
            whatsapp_number="5491100000001",
        )
        self.start = datetime(2026, 9, 21, 10, tzinfo=timezone.utc)

    async def asyncSetUp(self) -> None:
        self.requests: list[httpx.Request] = []
        self.client = httpx.AsyncClient(
            transport=httpx.MockTransport(self._handle_google_request),
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_provider_returns_internal_id_and_persists_google_mapping(self) -> None:
        provider = PersistentCalendarProvider(
            FakeCalendarProvider(),
            self.database,
        )

        created = await provider.create_appointment(
            patient_scope=self.patient,
            start_at=self.start,
            reason="Revision",
        )
        listed = await provider.list_appointments(patient_scope=self.patient)
        moved = await provider.reschedule_appointment(
            patient_scope=self.patient,
            appointment_id=created.id,
            new_start_at=self.start + timedelta(hours=1),
        )
        cancelled = await provider.cancel_appointment(
            patient_scope=self.patient,
            appointment_id=created.id,
        )

        self.assertEqual(created.id, "1")
        self.assertEqual(listed[0].id, "1")
        self.assertEqual(moved.id, "1")
        self.assertEqual(cancelled.id, "1")
        self.assertEqual(cancelled.status, AppointmentStatus.CANCELLED)
        with self.database.transaction() as connection:
            record = AppointmentRepository().get_by_id(connection, 1)
        self.assertIsNotNone(record)
        self.assertEqual(record.google_event_id, "appointment-1")
        self.assertEqual(record.patient_id, self.patient.patient_id)
        self.assertEqual(record.status, AppointmentStatus.CANCELLED.value)
        self.assertEqual(record.start_at, moved.start_at.isoformat())
        self.assertTrue(record.last_synced_at)

    async def test_patient_cannot_use_another_patients_internal_id(self) -> None:
        provider = PersistentCalendarProvider(
            FakeCalendarProvider(),
            self.database,
        )
        created = await provider.create_appointment(
            patient_scope=self.patient,
            start_at=self.start,
            reason="Revision",
        )

        with self.assertRaises(AppointmentAccessDenied):
            await provider.cancel_appointment(
                patient_scope=self.other_patient,
                appointment_id=created.id,
            )
        self.assertEqual(
            await provider.list_appointments(patient_scope=self.other_patient),
            (),
        )

    async def test_unknown_internal_id_is_not_found(self) -> None:
        provider = PersistentCalendarProvider(FakeCalendarProvider(), self.database)

        with self.assertRaises(AppointmentNotFound):
            await provider.cancel_appointment(
                patient_scope=self.patient,
                appointment_id="999",
            )

    async def test_reschedule_maps_internal_id_to_google_patch(self) -> None:
        google_provider = GoogleCalendarProvider(
            calendar_ids=("calendar-1",),
            access_token_provider=StaticAccessTokenProvider("test-token"),
            timezone_name="UTC",
            base_url="https://calendar.test/v3",
            http_client=self.client,
        )
        provider = PersistentCalendarProvider(google_provider, self.database)

        created = await provider.create_appointment(
            patient_scope=self.patient,
            start_at=self.start,
            reason="Revision",
        )
        moved = await provider.reschedule_appointment(
            patient_scope=self.patient,
            appointment_id=created.id,
            new_start_at=self.start + timedelta(hours=1),
        )

        self.assertEqual(created.id, "1")
        self.assertEqual(moved.id, "1")
        self.assertEqual(moved.start_at, self.start + timedelta(hours=1))
        patch_request = self.requests[-1]
        self.assertEqual(patch_request.method, "PATCH")
        self.assertEqual(
            patch_request.url.path,
            "/v3/calendars/calendar-1/events/event-1",
        )
        self.assertEqual(
            json.loads(patch_request.content)["start"]["dateTime"],
            "2026-09-21T11:00:00Z",
        )

    async def test_cancel_maps_internal_id_to_google_patch_and_persists_state(self) -> None:
        google_provider = GoogleCalendarProvider(
            calendar_ids=("calendar-1",),
            access_token_provider=StaticAccessTokenProvider("test-token"),
            timezone_name="UTC",
            base_url="https://calendar.test/v3",
            http_client=self.client,
        )
        provider = PersistentCalendarProvider(google_provider, self.database)

        created = await provider.create_appointment(
            patient_scope=self.patient,
            start_at=self.start,
            reason="Revision",
        )
        cancelled = await provider.cancel_appointment(
            patient_scope=self.patient,
            appointment_id=created.id,
        )

        self.assertEqual(cancelled.id, "1")
        self.assertEqual(cancelled.status, AppointmentStatus.CANCELLED)
        patch_request = self.requests[-1]
        self.assertEqual(patch_request.method, "PATCH")
        self.assertEqual(json.loads(patch_request.content), {"status": "cancelled"})
        with self.database.transaction() as connection:
            record = AppointmentRepository().get_by_id(connection, 1)
        self.assertIsNotNone(record)
        self.assertEqual(record.status, AppointmentStatus.CANCELLED.value)

    def _handle_google_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/freeBusy"):
            return httpx.Response(
                200,
                json={"calendars": {"calendar-1": {"busy": []}}},
                request=request,
            )
        if request.method == "POST":
            body = json.loads(request.content)
            start_at = datetime.fromisoformat(
                body["start"]["dateTime"].replace("Z", "+00:00")
            )
            return self._google_event_response(
                request,
                start_at=start_at,
                reason=body["description"],
            )
        if request.method == "GET":
            return self._google_event_response(request, start_at=self.start)
        if request.method == "PATCH":
            body = json.loads(request.content)
            if body.get("status") == "cancelled":
                return self._google_event_response(
                    request,
                    start_at=self.start,
                    status="cancelled",
                )
            start_at = datetime.fromisoformat(
                body["start"]["dateTime"].replace("Z", "+00:00")
            )
            return self._google_event_response(request, start_at=start_at)
        raise AssertionError(f"Ruta Google no esperada: {request.method} {request.url}")

    def _google_event_response(
        self,
        request: httpx.Request,
        *,
        start_at: datetime,
        reason: str = "Revision",
        status: str = "confirmed",
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "event-1",
                "status": status,
                "summary": "Cita medica",
                "description": reason,
                "start": {"dateTime": self._format_datetime(start_at)},
                "end": {
                    "dateTime": self._format_datetime(
                        start_at + timedelta(minutes=30)
                    )
                },
                "extendedProperties": {
                    "private": {
                        MANAGED_BY_PROPERTY: MANAGED_BY_VALUE,
                        PATIENT_ID_PROPERTY: str(self.patient.patient_id),
                        CONVERSATION_ID_PROPERTY: str(self.patient.conversation_id),
                    }
                },
            },
            request=request,
        )

    @staticmethod
    def _format_datetime(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")
