import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from calendar_domain import Appointment, AppointmentStatus, PatientScope, ToolName
from llm_provider import ToolCall
from notification_composer import (
    DoctorNotificationComposer,
    DoctorNotificationMessage,
    DoctorNotificationService,
    NotificationCompositionError,
    NotificationSummary,
    render_doctor_notification,
)
from notification_domain import AppointmentNotificationEvent, AppointmentNotificationType
from persistence import SQLiteDatabase
from repositories import MessageRecord, MessageRepository
from fakes import FakeLLMProvider


class NotificationCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scope = PatientScope(
            patient_id=777,
            conversation_id=888,
            whatsapp_number="5217531363338",
        )
        self.appointment = Appointment(
            id="appointment-internal-9",
            patient_scope=self.scope,
            calendar_id="calendar-secret-1",
            start_at=datetime(2026, 9, 21, 10, tzinfo=timezone.utc),
            end_at=datetime(2026, 9, 21, 10, 30, tzinfo=timezone.utc),
            reason="Revision de cornea",
            status=AppointmentStatus.CONFIRMED,
        )
        self.event = AppointmentNotificationEvent(
            notification_type=AppointmentNotificationType.SCHEDULED,
            tool_name=ToolName.CREATE_APPOINTMENT,
            appointment=self.appointment,
            patient_scope=self.scope,
            incoming_message_id=999,
            tool_call_id="tool-call-internal-1",
        )

    def event_with_reason(self, reason: str) -> AppointmentNotificationEvent:
        appointment = Appointment(
            id=self.appointment.id,
            patient_scope=self.scope,
            calendar_id=self.appointment.calendar_id,
            start_at=self.appointment.start_at,
            end_at=self.appointment.end_at,
            reason=reason,
            status=self.appointment.status,
        )
        return AppointmentNotificationEvent(
            notification_type=self.event.notification_type,
            tool_name=self.event.tool_name,
            appointment=appointment,
            patient_scope=self.scope,
            incoming_message_id=self.event.incoming_message_id,
            tool_call_id=self.event.tool_call_id,
        )

    def test_renders_one_format_with_appointment_patient_summary_and_priority(self) -> None:
        message = render_doctor_notification(
            self.event,
            patient_name="Ana Prueba",
            summary=NotificationSummary(
                summary="El paciente solicito una revision y confirmo el horario.",
                priority_signals=("El paciente solicita atención prioritaria.",),
            ),
        )

        self.assertIsInstance(message, DoctorNotificationMessage)
        self.assertIn("Tipo de evento: Cita agendada", message.body)
        self.assertIn("Fecha: 2026-09-21", message.body)
        self.assertIn("Hora: 10:00-10:30", message.body)
        self.assertNotIn("Zona horaria:", message.body)
        self.assertNotIn("Duracion:", message.body)
        self.assertIn("Motivo: Revision de cornea", message.body)
        self.assertIn("Estado: confirmada", message.body)
        self.assertIn("Nombre: Ana Prueba", message.body)
        self.assertIn("Telefono: 7531363338", message.body)
        self.assertNotIn("Telefono: 5217531363338", message.body)
        self.assertIn(message.summary, message.body)
        self.assertIn("El paciente solicita atención prioritaria.", message.body)

    def test_format_changes_only_event_label_for_the_three_mutations(self) -> None:
        cases = (
            (
                AppointmentNotificationType.SCHEDULED,
                ToolName.CREATE_APPOINTMENT,
                AppointmentStatus.CONFIRMED,
                "Tipo de evento: Cita agendada",
            ),
            (
                AppointmentNotificationType.MODIFIED,
                ToolName.RESCHEDULE_APPOINTMENT,
                AppointmentStatus.CONFIRMED,
                "Tipo de evento: Cita modificada",
            ),
            (
                AppointmentNotificationType.CANCELLED,
                ToolName.CANCEL_APPOINTMENT,
                AppointmentStatus.CANCELLED,
                "Tipo de evento: Cita cancelada",
            ),
        )
        for notification_type, tool_name, status, expected_label in cases:
            event = AppointmentNotificationEvent(
                notification_type=notification_type,
                tool_name=tool_name,
                appointment=self.appointment.__class__(
                    id=self.appointment.id,
                    patient_scope=self.scope,
                    calendar_id=self.appointment.calendar_id,
                    start_at=self.appointment.start_at,
                    end_at=self.appointment.end_at,
                    reason=self.appointment.reason,
                    status=status,
                ),
                patient_scope=self.scope,
                incoming_message_id=999,
                tool_call_id="tool-call-internal-1",
            )
            message = render_doctor_notification(
                event,
                patient_name=None,
                summary=NotificationSummary("Resumen seguro.", ()),
            )
            self.assertIn(expected_label, message.body)
            self.assertIn("Nombre: No informado", message.body)
            self.assertIn("- Ninguna detectada.", message.body)

    def test_service_uses_persisted_history_and_name_without_exposing_internal_values(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database = SQLiteDatabase(os.path.join(directory.name, "test.sqlite3"))
        with database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO patients (id, whatsapp_number, name, created_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self.scope.patient_id,
                    self.scope.whatsapp_number,
                    "Ana Prueba",
                    "2026-09-20T12:00:00+00:00",
                    "2026-09-20T12:00:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO conversations (
                    id, patient_id, status, state, context_json, created_at, updated_at
                ) VALUES (?, ?, 'active', 'active', '{}', ?, ?)
                """,
                (
                    self.scope.conversation_id,
                    self.scope.patient_id,
                    "2026-09-20T12:00:00+00:00",
                    "2026-09-20T12:00:00+00:00",
                ),
            )
            messages = MessageRepository()
            messages.create_incoming(
                connection,
                conversation_id=self.scope.conversation_id,
                provider_message_id="wamid.incoming",
                text="Necesito una cita y es urgente.",
                message_type="text",
                now="2026-09-20T12:01:00+00:00",
            )
            messages.save_reply(
                connection,
                incoming_message_id=1,
                conversation_id=self.scope.conversation_id,
                text="Puedo ayudarte a gestionar el horario.",
                status="sent",
                provider_message_id="wamid.outgoing",
                now="2026-09-20T12:02:00+00:00",
            )

        provider = FakeLLMProvider(
            reply=json.dumps(
                {
                    "summary": "El paciente solicito gestionar una cita.",
                    "priority_signals": ["urgent_request"],
                }
            )
        )
        service = DoctorNotificationService(database, provider)

        message = asyncio.run(
            service.compose(
                self.event_with_reason("Necesito una cita y es urgente.")
            )
        )

        self.assertIn("Nombre: Ana Prueba", message.body)
        self.assertIn("Telefono: 7531363338", message.body)
        self.assertIn("El paciente solicito gestionar una cita.", message.body)
        self.assertIn("El paciente solicita atención prioritaria.", message.body)
        self.assertNotIn(self.appointment.id, message.body)
        self.assertNotIn(self.appointment.calendar_id, message.body)
        self.assertNotIn(self.event.event_key, message.body)
        self.assertNotIn(str(self.scope.patient_id), message.body)
        self.assertNotIn(str(self.scope.conversation_id), message.body)
        self.assertNotIn(str(self.event.incoming_message_id), message.body)
        self.assertNotIn(self.event.tool_call_id, message.body)
        self.assertEqual(provider.call_count, 1)
        prompt = provider.received_messages[0][1].content
        self.assertIn("Necesito una cita y es urgente.", prompt)
        self.assertNotIn(self.appointment.id, prompt)
        self.assertNotIn(self.appointment.calendar_id, prompt)

    def test_summary_falls_back_when_provider_returns_diagnosis_or_transcript(self) -> None:
        history = []
        provider = FakeLLMProvider(
            reply=json.dumps(
                {
                    "summary": (
                        "Diagnostico: glaucoma. Paciente: Necesito una cita. "
                        "Asistente: Puedo ayudarte."
                    ),
                    "priority_signals": ["diagnostico: glaucoma"],
                }
            )
        )
        composer = DoctorNotificationComposer(provider)

        message = asyncio.run(
            composer.compose(
                self.event,
                patient_name=None,
                history=history,
            )
        )

        self.assertEqual(message.summary, "La conversacion se relaciona con la gestion de una cita. Revisar la solicitud del paciente durante la atencion.")
        self.assertNotIn("glaucoma", message.body.lower())
        self.assertNotIn("diagnost", message.body.lower())
        self.assertNotIn("Paciente: Necesito una cita", message.body)
        self.assertEqual(message.priority_signals, ())

    def test_detected_priority_signal_uses_operational_language_without_diagnosis(self) -> None:
        provider = FakeLLMProvider(
            reply=json.dumps(
                {
                    "summary": "El paciente refiere una molestia ocular.",
                    "priority_signals": [],
                }
            )
        )
        history = (
            MessageRecord(
                id=1,
                conversation_id=self.scope.conversation_id,
                direction="incoming",
                provider_message_id="wamid.incoming",
                text="Tuve contacto con una sustancia química en el ojo.",
                message_type="text",
                status="received",
                reply_to_message_id=None,
                created_at="2026-09-20T12:01:00+00:00",
            ),
        )
        composer = DoctorNotificationComposer(provider)

        message = asyncio.run(
            composer.compose(
                self.event_with_reason("Tuve contacto con una sustancia química en el ojo."),
                patient_name=None,
                history=history,
            )
        )

        self.assertIn(
            "El paciente refiere contacto ocular con una sustancia química que podría "
            "requerir atención prioritaria.",
            message.body,
        )
        self.assertNotIn("glaucoma", message.body.lower())
        self.assertNotIn("desprendimiento", message.body.lower())

    def test_red_eyes_are_reported_as_priority_and_model_status_noise_is_rejected(self) -> None:
        expected_signal = (
            "El paciente refiere ojos rojos que podrían requerir atención prioritaria."
        )
        provider = FakeLLMProvider(
            reply=json.dumps(
                {
                    "summary": "El paciente refiere ojos rojos.",
                    "priority_signals": ["cita confirmada"],
                }
            )
        )
        history = (
            MessageRecord(
                id=1,
                conversation_id=self.scope.conversation_id,
                direction="incoming",
                provider_message_id="wamid.red-eyes",
                text="Tengo los ojos rojos",
                message_type="text",
                status="received",
                reply_to_message_id=None,
                created_at="2026-10-05T13:36:00+00:00",
            ),
        )
        composer = DoctorNotificationComposer(provider)

        message = asyncio.run(
            composer.compose(
                self.event_with_reason("Tengo los ojos rojos"),
                patient_name="Asael Ponce Silva",
                history=history,
            )
        )

        self.assertEqual(message.priority_signals, (expected_signal,))
        self.assertIn(expected_signal, message.body)

    def test_previous_appointment_signal_is_not_reused_for_the_current_reason(self) -> None:
        current_appointment = Appointment(
            id="appointment-current",
            patient_scope=self.scope,
            calendar_id="calendar-current",
            start_at=datetime(2026, 10, 6, 9, tzinfo=timezone.utc),
            end_at=datetime(2026, 10, 6, 9, 30, tzinfo=timezone.utc),
            reason="Tengo lagañas en los ojos",
            status=AppointmentStatus.CONFIRMED,
        )
        current_event = AppointmentNotificationEvent(
            notification_type=AppointmentNotificationType.SCHEDULED,
            tool_name=ToolName.CREATE_APPOINTMENT,
            appointment=current_appointment,
            patient_scope=self.scope,
            incoming_message_id=1001,
            tool_call_id="tool-call-current",
        )
        provider = FakeLLMProvider(
            reply=json.dumps(
                {
                    "summary": "El paciente refiere lagañas en los ojos.",
                    "priority_signals": [],
                }
            )
        )
        history = (
            MessageRecord(
                id=1,
                conversation_id=self.scope.conversation_id,
                direction="incoming",
                provider_message_id="wamid.previous-red-eyes",
                text="Tengo los ojos rojos",
                message_type="text",
                status="received",
                reply_to_message_id=None,
                created_at="2026-10-05T13:00:00+00:00",
            ),
            MessageRecord(
                id=2,
                conversation_id=self.scope.conversation_id,
                direction="incoming",
                provider_message_id="wamid.current-lagañas",
                text="Tengo lagañas en los ojos",
                message_type="text",
                status="received",
                reply_to_message_id=None,
                created_at="2026-10-05T14:22:00+00:00",
            ),
        )

        message = asyncio.run(
            DoctorNotificationComposer(provider).compose(
                current_event,
                patient_name="Ana Prueba",
                history=history,
            )
        )

        self.assertEqual(message.priority_signals, ())
        self.assertIn("- Ninguna detectada.", message.body)

    def test_renderer_sanitizes_untrusted_summary_values(self) -> None:
        message = render_doctor_notification(
            self.event,
            patient_name=None,
            summary=NotificationSummary(
                "Diagnostico: glaucoma. appointment-internal-9",
                ("Diagnostico: glaucoma", "tool-call-internal-1"),
            ),
        )

        self.assertNotIn("glaucoma", message.body.lower())
        self.assertNotIn("diagnost", message.body.lower())
        self.assertNotIn(self.appointment.id, message.body)
        self.assertNotIn(self.event.tool_call_id, message.body)
        self.assertEqual(message.priority_signals, ())

    def test_rejects_tool_call_from_summary_provider(self) -> None:
        provider = FakeLLMProvider(
            reply=ToolCall(name="create_appointment", arguments={})
        )
        composer = DoctorNotificationComposer(provider)

        with self.assertRaises(NotificationCompositionError):
            asyncio.run(
                composer.compose(
                    self.event,
                    patient_name=None,
                    history=(),
                )
            )
