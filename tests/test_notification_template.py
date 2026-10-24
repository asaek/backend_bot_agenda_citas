import json
import asyncio
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import dotenv_values

from notification_template import TemplateMappingError, build_template_components, load_template_components
from calendar_domain import Appointment, AppointmentStatus, PatientScope, ToolName
from notification_composer import NotificationSummary, render_doctor_notification
from notification_delivery import load_doctor_notification_settings
from notification_domain import AppointmentNotificationEvent, AppointmentNotificationType
from whatsapp_client import WhatsAppClient


class TemplateMappingTests(unittest.TestCase):
    def test_approved_doctor_template_uses_nine_positional_body_parameters(self):
        settings = load_doctor_notification_settings({
            **dotenv_values(Path(__file__).resolve().parents[1] / ".env.example"),
            "DOCTOR_NOTIFICATIONS_ENABLED": "true",
        })
        self.assertEqual((settings.template_name, settings.template_language), ("aviso_cita_medico", "es_MX"))
        self.assertIsNone(settings.configuration_error)
        scope = PatientScope(1, 1, "lab:developer")
        appointment = Appointment(
            id="fixture-cancelled", patient_scope=scope, calendar_id="fixture-calendar",
            start_at=datetime(2026, 10, 23, 10, tzinfo=timezone.utc),
            end_at=datetime(2026, 10, 23, 10, 30, tzinfo=timezone.utc),
            reason="Revisión general", status=AppointmentStatus.CANCELLED,
        )
        event = AppointmentNotificationEvent(
            AppointmentNotificationType.CANCELLED, ToolName.CANCEL_APPOINTMENT,
            appointment, scope, 1, "fixture-approved-template",
        )
        message = render_doctor_notification(event, patient_name="Paciente de prueba", summary=NotificationSummary(
            "El paciente solicita una revisión general de los ojos.", (),
        ))
        components = build_template_components(settings.template_components, message.template_data)
        requests = []
        async def scenario():
            def handler(request):
                requests.append(request)
                return httpx.Response(200, json={"messages": [{"id": "wamid.approved-fixture"}]})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
                client = WhatsAppClient(access_token="fixture-token", phone_number_id="fixture-phone", http_client=http_client)
                await client.send_template(settings.recipient_numbers[0], settings.template_name,
                                           settings.template_language, components)
        asyncio.run(scenario())
        self.assertEqual(json.loads(requests[0].content)["template"], {
            "name": "aviso_cita_medico", "language": {"code": "es_MX"},
            "components": [{"type": "body", "parameters": [
                {"type": "text", "text": "Cita cancelada"},
                {"type": "text", "text": "2026-10-23"},
                {"type": "text", "text": "10:00-10:30"},
                {"type": "text", "text": "Revisión general"},
                {"type": "text", "text": "cancelada"},
                {"type": "text", "text": "Paciente de prueba"},
                {"type": "text", "text": "No informado"},
                {"type": "text", "text": "El paciente solicita una revisión general de los ojos."},
                {"type": "text", "text": "Ninguna detectada."},
            ]}],
        })

    def test_preserves_component_order_named_parameters_and_literal_braces(self):
        raw = json.dumps([
            {"type": "header", "parameters": [{"type": "text", "text": "Aviso"}]},
            {"type": "body", "parameters": [{"type": "text", "parameter_name": "aviso", "text": "{{CITA}} {notification_body}"}]},
            {"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": "detalle"}]},
        ])
        components = build_template_components(raw, {"notification_body": "Nombre: Ana\n\tEstado: confirmada"})
        self.assertEqual(components[1]["parameters"][0], {"type": "text", "parameter_name": "aviso", "text": "{CITA} Nombre: Ana Estado: confirmada"})
        self.assertEqual(components[2]["index"], "0")
        self.assertEqual(load_template_components(raw)[1]["parameters"][0]["text"], "{{CITA}} {notification_body}")

    def test_missing_or_invalid_mapping_has_a_stable_error_without_configuration_values(self):
        for raw, reason in (("", "Mapeo de plantilla pendiente."), ("[]", "Mapeo de plantilla no válido."),
                            ("invalid-secret-value", "Mapeo de plantilla no válido.")):
            with self.subTest(raw=raw):
                with self.assertRaises(TemplateMappingError) as caught:
                    load_template_components(raw)
                self.assertEqual(str(caught.exception), reason)

    def test_rejects_unknown_sources_expressions_or_a_mapping_that_drops_notice_fields(self):
        for value in ("{unknown}", "{patient_name}", "{notification_body.__class__}",
                      "{notification_body!r}", "{notification_body:>20}", "{notification_body"):
            with self.subTest(value=value):
                raw = json.dumps([{"type": "body", "parameters": [{"type": "text", "text": value}]}])
                with self.assertRaises(TemplateMappingError):
                    load_template_components(raw)

    def test_missing_source_data_cannot_be_substituted_with_invented_values(self):
        raw = json.dumps([{"type": "body", "parameters": [{"type": "text", "text": "{notification_body}"}]}])
        with self.assertRaises(TemplateMappingError) as caught:
            build_template_components(raw, {})
        self.assertEqual(str(caught.exception), "Datos de plantilla no disponibles para este aviso.")
