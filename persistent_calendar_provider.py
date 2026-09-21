"""Persistencia local de la identidad de citas de un proveedor externo."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timezone

from calendar_domain import (
    Appointment,
    AppointmentAccessDenied,
    AppointmentNotFound,
    AvailableSlot,
    CalendarProvider,
    CalendarProviderError,
    PatientScope,
)
from persistence import SQLiteDatabase
from repositories import AppointmentRecord, AppointmentRepository


class PersistentCalendarProvider(CalendarProvider):
    """Expone IDs internos y conserva el mapeo con IDs del proveedor."""

    def __init__(
        self,
        provider: CalendarProvider,
        database: SQLiteDatabase,
        repository: AppointmentRepository | None = None,
    ) -> None:
        self.provider = provider
        self.database = database
        self.repository = repository or AppointmentRepository()

    async def check_availability(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> Sequence[AvailableSlot]:
        return await self.provider.check_availability(
            start_at=start_at,
            end_at=end_at,
        )

    async def create_appointment(
        self,
        *,
        patient_scope: PatientScope,
        start_at: datetime,
        reason: str,
    ) -> Appointment:
        appointment = await self.provider.create_appointment(
            patient_scope=patient_scope,
            start_at=start_at,
            reason=reason,
        )
        return self._persist(appointment, patient_scope)

    async def list_appointments(
        self,
        *,
        patient_scope: PatientScope,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> Sequence[Appointment]:
        appointments = await self.provider.list_appointments(
            patient_scope=patient_scope,
            start_at=start_at,
            end_at=end_at,
        )
        return tuple(
            self._persist(appointment, patient_scope)
            for appointment in appointments
        )

    async def reschedule_appointment(
        self,
        *,
        patient_scope: PatientScope,
        appointment_id: str,
        new_start_at: datetime,
    ) -> Appointment:
        record = self._get_owned_record(appointment_id, patient_scope)
        appointment = await self.provider.reschedule_appointment(
            patient_scope=patient_scope,
            appointment_id=record.google_event_id,
            new_start_at=new_start_at,
        )
        return self._persist(appointment, patient_scope)

    async def cancel_appointment(
        self,
        *,
        patient_scope: PatientScope,
        appointment_id: str,
    ) -> Appointment:
        record = self._get_owned_record(appointment_id, patient_scope)
        appointment = await self.provider.cancel_appointment(
            patient_scope=patient_scope,
            appointment_id=record.google_event_id,
        )
        return self._persist(appointment, patient_scope)

    def _get_owned_record(
        self,
        appointment_id: str,
        patient_scope: PatientScope,
    ) -> AppointmentRecord:
        try:
            internal_id = int(appointment_id)
        except (TypeError, ValueError) as error:
            raise AppointmentNotFound() from error
        if internal_id <= 0:
            raise AppointmentNotFound()

        with self.database.transaction() as connection:
            record = self.repository.get_by_id(connection, internal_id)
        if record is None:
            raise AppointmentNotFound()
        if record.patient_id != patient_scope.patient_id:
            raise AppointmentAccessDenied()
        return record

    def _persist(
        self,
        appointment: Appointment,
        patient_scope: PatientScope,
    ) -> Appointment:
        if appointment.patient_scope.patient_id != patient_scope.patient_id:
            raise AppointmentAccessDenied()
        synced_at = datetime.now(timezone.utc).isoformat()
        try:
            with self.database.transaction() as connection:
                record = self.repository.upsert_synced(
                    connection,
                    calendar_id=appointment.calendar_id,
                    google_event_id=appointment.id,
                    patient_id=patient_scope.patient_id,
                    status=appointment.status.value,
                    start_at=appointment.start_at.isoformat(),
                    end_at=appointment.end_at.isoformat(),
                    reason=appointment.reason,
                    synced_at=synced_at,
                )
        except RuntimeError as error:
            raise CalendarProviderError() from error
        return replace(appointment, id=str(record.id))
