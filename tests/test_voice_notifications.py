import asyncio
import copy
import json
import tempfile
import unittest
from datetime import datetime, time, timezone
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from calling_repository import CallingRepository
from main import create_lab_app
from notification_delivery import DoctorNotificationSettings
from notification_trigger import DoctorNotificationTrigger
from openai_realtime_provider import RealtimeSettings
import test_voice_session as session_fixtures
import test_voice_tools as fixtures
from tool_validation import BusinessHours, TimeWindow
from voice_fakes import FakeRealtimeProvider, FakeVoiceMedia
from voice_notifications import VoiceDoctorNotifications
from voice_repository import VoiceRepository
from voice_session import VoiceSession
from voice_tools import VoiceTools
from test_notification_retry import Clock


class SummaryProvider:
    def __init__(self):
        self.messages = []
        self.failure = False

    async def generate(self, messages):
        if self.failure:
            raise RuntimeError("summary unavailable")
        self.messages.append(messages)
        return '{"summary":"El paciente solicita una revisión general de los ojos.","priority_signals":[]}'


class RecordingWhatsApp:
    def __init__(self):
        self.sent = []
        self.failures = 0
        self.attempts = 0
        self.template_attempts = []
        self.sent_templates = []

    async def send_template(self, to, name, language_code, components):
        self.attempts += 1
        request = (to, name, language_code, copy.deepcopy(components))
        self.template_attempts.append(request)
        if self.failures:
            self.failures -= 1
            raise httpx.ConnectError("WhatsApp unavailable")
        self.sent_templates.append(request)
        return {"messages": [{"id": "wamid.voice-template"}]}

    async def send_text(self, to, body):
        self.attempts += 1
        if self.failures:
            self.failures -= 1
            raise httpx.ConnectError("WhatsApp unavailable")
        self.sent.append((to, body))
        return {"messages": [{"id": "wamid.doctor"}]}


class VoiceNotificationTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.VoiceToolsTests.asyncSetUp
    propose = fixtures.VoiceToolsTests.propose
    arm = fixtures.VoiceToolsTests.arm
    confirm = fixtures.VoiceToolsTests.confirm

    def notifications(self, client=None, settings=None):
        self.client = client or RecordingWhatsApp()
        self.summary = SummaryProvider()
        trigger = DoctorNotificationTrigger(
            self.repository, self.summary, whatsapp_client=self.client,
            settings=settings or DoctorNotificationSettings(True, ("5491100000001",)),
        )
        self.clock = getattr(self, "clock", Clock())
        trigger.delivery.now = self.clock.now
        notifications = VoiceDoctorNotifications(self.repository, trigger)
        self.tools = VoiceTools(repository=self.repository, session_id="call-a", profile="tester",
            executor=self.executor, scope=self.tools.scope, notifications=notifications)
        return notifications

    async def test_incomplete_template_preserves_voice_event_without_composition_and_recovers(self):
        settings = DoctorNotificationSettings(True, ("5491100000001",), transport="template")
        notifications = self.notifications(settings=settings)
        self.summary.failure = True
        proposal = await self.propose()
        self.arm(proposal)
        self.assertTrue((await self.confirm(proposal))["ok"])
        await notifications.flush()
        self.assertEqual(self.client.attempts, 0)
        self.assertEqual(self.summary.messages, [])
        self.assertEqual(len(self.repository.pending_notifications()), 1)
        with self.repository.connection() as db:
            records = db.execute("SELECT status,last_error,attempt_count FROM doctor_notifications").fetchall()
        self.assertEqual([tuple(row) for row in records], [("pending", "Configuración de plantilla incompleta.", 0)])

        self.repository.close()
        self.repository.start()
        client = self.client
        notifications = self.notifications(client=client, settings=settings)
        await notifications.flush()
        self.assertEqual(client.attempts, 0)
        self.assertEqual(len(self.repository.pending_notifications()), 1)

        notifications = self.notifications(client=client)
        await notifications.flush()
        await notifications.flush()
        self.assertEqual(client.attempts, 1)
        self.assertEqual(client.sent[0][0], "5491100000001")
        self.assertTrue(client.sent[0][1].startswith("NOTIFICACION INTERNA DE CITA\n"))
        self.assertFalse(self.repository.pending_notifications())
        self.assertEqual(len(self.provider.appointments), 1)

    async def test_confirmed_voice_booking_uses_the_doctor_message_and_never_notifies_a_proposal(self):
        notifications = self.notifications()
        self.repository.turn("call-a", "request", "user", "Quiero una revisión general", "received")
        proposal = await self.propose()
        await notifications.flush()
        self.assertEqual(self.client.sent, [])
        self.arm(proposal)
        result = await self.confirm(proposal)
        self.assertTrue(result["ok"], result)
        await notifications.flush()
        self.assertEqual(self.client.sent, [("5491100000001", "\n".join((
            "NOTIFICACION INTERNA DE CITA",
            "Tipo de evento: Cita agendada", "", "CITA",
            "Fecha: 2026-10-19", "Hora: 10:00-10:30", "Motivo: Revisión general",
            "Estado: programada", "", "PACIENTE", "Nombre: Asael Ponce",
            "Telefono: No informado", "", "RESUMEN DE LA CONVERSACION",
            "El paciente solicita una revisión general de los ojos.", "",
            "SENALES DE PRIORIDAD", "- Ninguna detectada.",
        )))])
        self.assertIn("Quiero una revisión general", self.summary.messages[0][-1].content)
        self.assertEqual(await self.confirm(proposal), result)
        await notifications.flush()
        self.assertEqual(len(self.client.sent), 1)
        self.assertEqual(len(self.provider.appointments), 1)

    async def test_voice_template_retries_frozen_notice_after_restart_without_summary_provider(self):
        client = RecordingWhatsApp()
        client.failures = 1
        mapping = json.dumps([{"type": "body", "parameters": [{"type": "text", "text": "{notification_body}"}]}])
        settings = DoctorNotificationSettings(True, ("5491100000001",), "template", "fixture_voz", "es_MX", mapping)
        notifications = self.notifications(client=client, settings=settings)
        self.repository.turn("call-a", "request", "user", "Quiero una revisión general", "received")
        proposal = await self.propose()
        self.arm(proposal)
        self.assertTrue((await self.confirm(proposal))["ok"])
        await notifications.flush()
        self.assertEqual(len(self.repository.pending_notifications()), 1)
        self.repository.close()
        self.repository.start()
        self.summary.failure = True
        self.clock.advance(60)
        await notifications.flush()
        await notifications.flush()
        self.assertEqual(client.attempts, 2)
        self.assertEqual(client.template_attempts[0], client.template_attempts[1])
        self.assertEqual(len(client.sent_templates), 1)
        self.assertEqual(client.sent_templates[0][:3], ("5491100000001", "fixture_voz", "es_MX"))
        text = client.sent_templates[0][3][0]["parameters"][0]["text"]
        for expected in ("Cita agendada", "2026-10-19", "10:00-10:30", "Revisión general", "Asael Ponce",
                         "Telefono: No informado", "RESUMEN DE LA CONVERSACION", "SENALES DE PRIORIDAD"):
            self.assertIn(expected, text)
        self.assertNotIn("\n", text)
        self.assertEqual(client.sent, [])
        self.assertFalse(self.repository.pending_notifications())
        self.assertEqual(len(self.provider.appointments), 1)

    async def test_whatsapp_failure_retries_the_prepared_notice_even_when_summary_provider_is_down(self):
        client = RecordingWhatsApp()
        client.failures = 1
        notifications = self.notifications(client)
        proposal = await self.propose()
        self.arm(proposal)
        result = await self.confirm(proposal)
        self.assertTrue(result["ok"], result)
        await notifications.flush()
        self.assertEqual(client.attempts, 1)
        self.assertEqual(client.sent, [])
        self.repository.close()
        self.repository.start()
        self.summary.failure = True
        self.clock.advance(60)
        await notifications.flush()
        self.assertEqual(len(client.sent), 1)
        self.assertIn("NOTIFICACION INTERNA DE CITA", client.sent[0][1])
        self.assertEqual(client.attempts, 2)

        self.assertEqual(len(self.provider.appointments), 1)
        await notifications.flush()
        self.assertEqual(client.attempts, 2)

    async def test_lost_meta_response_is_not_automatically_resent_after_restart(self):
        class AcceptedThenTimeout(RecordingWhatsApp):
            async def send_text(client, to, body):
                await super().send_text(to, body)
                raise httpx.ReadTimeout("response lost after acceptance")

        client = AcceptedThenTimeout()
        notifications = self.notifications(client)
        proposal = await self.propose()
        self.arm(proposal)
        self.assertTrue((await self.confirm(proposal))["ok"])
        await notifications.flush()
        self.repository.close()
        self.repository.start()
        await notifications.flush()
        await notifications.flush()
        self.assertEqual(len(client.sent), 1)
        self.assertEqual(client.attempts, 1)
        self.assertEqual(len(self.provider.appointments), 1)

    async def test_summary_failure_survives_restart_and_retries_the_message_without_rebooking(self):
        notifications = self.notifications()
        self.summary.failure = True
        proposal = await self.propose()
        self.arm(proposal)
        result = await self.confirm(proposal)
        self.assertTrue(result["ok"], result)
        await notifications.flush()
        self.assertEqual(self.client.sent, [])
        self.repository.close()
        self.repository.start()
        self.summary.failure = False
        self.clock.advance(60)
        await notifications.flush()
        self.assertEqual(len(self.client.sent), 1)
        self.assertIn("NOTIFICACION INTERNA DE CITA", self.client.sent[0][1])
        self.assertIn("Nombre: Asael Ponce", self.client.sent[0][1])
        await notifications.flush()
        self.assertEqual(len(self.client.sent), 1)
        self.assertEqual(len(self.provider.appointments), 1)

    async def test_rejected_and_failed_mutations_never_notify_the_doctor(self):
        notifications = self.notifications()
        proposal = await self.propose()
        rejected = await self.tools.execute("reject", "confirm_appointment_action",
            {"action_id": proposal["action_id"], "decision": "reject"}, 2)
        self.assertEqual(rejected["status"], "not_executed")
        proposal = await self.propose("second-proposal", 3)
        self.arm(proposal)
        self.provider.register_busy_period(calendar_id="calendar-1",
            start_at=datetime(2026, 10, 19, 10, tzinfo=timezone.utc),
            end_at=datetime(2026, 10, 19, 10, 30, tzinfo=timezone.utc))
        failed = await self.confirm(proposal, "failed-booking", 4)
        self.assertFalse(failed["ok"], failed)
        await notifications.flush()
        self.assertEqual(self.client.sent, [])
        self.assertFalse(self.repository.pending_notifications())

    async def test_new_workflow_excludes_symptoms_from_an_abandoned_request(self):
        notifications = self.notifications()
        self.repository.turn("call-a", "old-symptoms", "user", "Me duele mucho el ojo", "received")
        await self.propose()
        self.repository.turn("call-a", "new-request", "user", "Empecemos otra gestion para revision general", "received")
        renewed = await self.tools.execute("new-workflow", "manage_appointment_workflow", {"mode": "new"}, 2)
        self.assertEqual(renewed["status"], "new_workflow")
        self.repository.turn("call-a", "routine", "user", "Quiero una revision general", "received")
        proposal = await self.propose("new-proposal", 3)
        self.arm(proposal)
        self.assertTrue((await self.confirm(proposal, "new-confirm", 4))["ok"])
        await notifications.flush()
        self.assertEqual(len(self.client.sent), 1)
        self.assertIn("SENALES DE PRIORIDAD\n- Ninguna detectada.", self.client.sent[0][1])
        self.assertNotIn("Me duele mucho el ojo", self.summary.messages[0][-1].content)
        self.assertIn("Quiero una revision general", self.summary.messages[0][-1].content)

    async def test_new_workflow_keeps_current_symptoms_even_if_assistant_placeholder_already_exists(self):
        notifications = self.notifications()
        self.repository.turn("call-a", "old-symptoms", "user", "Me duele mucho el ojo", "received")
        await self.propose()
        request = "Empecemos otra gestion: tengo lagañas amarillas y abundantes"
        self.repository.turn("call-a", "new-request", "user", request, "received")
        self.repository.turn("call-a", "assistant-placeholder", "assistant", "", "generating")
        renewed = await self.tools.execute("new-workflow", "manage_appointment_workflow", {"mode": "new"}, 2)
        self.assertEqual(renewed["status"], "new_workflow")
        proposal = await self.propose("new-proposal", 3)
        self.arm(proposal)
        self.assertTrue((await self.confirm(proposal, "new-confirm", 4))["ok"])
        await notifications.flush()
        self.assertIn(request, self.summary.messages[0][-1].content)
        self.assertNotIn("Me duele mucho el ojo", self.summary.messages[0][-1].content)
        self.assertIn("secreción ocular", self.client.sent[0][1])

    async def test_lab_factory_delivers_durable_notices_after_a_process_restart(self):
        self.notifications()
        proposal = await self.propose()
        self.arm(proposal)
        self.assertTrue((await self.confirm(proposal))["ok"])
        self.assertEqual(self.client.sent, [])
        self.repository.close()
        lab = create_lab_app(enabled=True, audio_mode="realtime",
            repository=CallingRepository(self.repository.path.with_name("calls.sqlite3")),
            voice_database_path=self.repository.path, media_factory=FakeVoiceMedia,
            realtime_provider_factory=FakeRealtimeProvider,
            voice_settings=RealtimeSettings(api_key="test-only", maximum_sessions=10),
            doctor_notification_trigger_factory=lambda repository: DoctorNotificationTrigger(
                repository, self.summary, whatsapp_client=self.client,
                settings=DoctorNotificationSettings(True, ("5491100000001",))))
        with TestClient(lab) as client:
            self.assertEqual(client.get("/lab/health").status_code, 200)
            async with asyncio.timeout(3):
                while len(self.client.sent) != 1:
                    await asyncio.sleep(.01)
        self.assertIn("Tipo de evento: Cita agendada", self.client.sent[0][1])
        self.assertFalse(self.repository.pending_notifications())
        self.assertEqual(len(self.provider.appointments), 1)


class VoiceSessionNotificationTests(unittest.IsolatedAsyncioTestCase):
    wait = session_fixtures.VoiceSessionTests.wait
    speech = session_fixtures.VoiceSessionTests.speech
    audio = session_fixtures.VoiceSessionTests.audio
    tool = session_fixtures.VoiceSessionTests.tool

    async def asyncSetUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.repository = VoiceRepository(Path(directory) / "voice.sqlite3")
        self.repository.start()
        self.addCleanup(self.repository.close)
        self.client = RecordingWhatsApp()
        self.notifications = VoiceDoctorNotifications(self.repository,
            DoctorNotificationTrigger(self.repository, SummaryProvider(), whatsapp_client=self.client,
                settings=DoctorNotificationSettings(True, ("5491100000001",))))
        self.notifications.start()
        self.addAsyncCleanup(self.notifications.close)
        self.media, self.provider = FakeVoiceMedia(), FakeRealtimeProvider()
        hours = BusinessHours("UTC", {day: (TimeWindow(time(9), time(17)),) for day in range(5)})
        self.session = VoiceSession(session_id="session", media=self.media, provider=self.provider,
            repository=self.repository, settings=RealtimeSettings(api_key="test-only", maximum_sessions=10),
            business_hours=hours, notifications=self.notifications)
        self.addAsyncCleanup(self.session.close)
        await self.session.negotiate("offer")
        self.session.tools.executor._now = datetime(2026, 10, 19, 8, tzinfo=timezone.utc)
        self.media.events.put_nowait("connected")
        await self.wait(lambda: len(self.provider.responses) == 1 and self.session._active_response is not None)

    async def test_each_confirmed_voice_mutation_automatically_notifies_once(self):
        for index, name in enumerate(("create_appointment", "reschedule_appointment", "cancel_appointment")):
            response = await self.speech("request-" + str(index))
            if index == 0:
                arguments = {"start_at": "2026-10-19T10:00:00+00:00", "reason": "Revisión general", "patient_name": "Asael Ponce"}
            else:
                arguments = {"appointment_id": self.repository.appointments("developer")[0]["id"]}
                if index == 1:
                    arguments["new_start_at"] = "2026-10-19T11:00:00+00:00"
            proposal = await self.tool(response, "prepare-" + str(index), name, arguments)
            self.assertEqual(proposal["status"], "confirmation_required")
            self.assertEqual(len(self.client.sent), index)
            await self.audio(self.session._active_response, "question-" + str(index), proposal["confirmation_prompt"], drained=True)
            response = await self.speech("confirm-input-" + str(index))
            result = await self.tool(response, "confirm-" + str(index), "confirm_appointment_action",
                {"action_id": proposal["action_id"], "decision": "confirm"})
            self.assertTrue(result["ok"], result)
            await self.wait(lambda: len(self.client.sent) == index + 1)
        self.assertEqual([recipient for recipient, _ in self.client.sent], ["5491100000001"] * 3)
        for body, label in zip((body for _, body in self.client.sent), ("agendada", "modificada", "cancelada")):
            self.assertIn("Tipo de evento: Cita " + label, body)
            self.assertIn("Nombre: Asael Ponce", body)
            self.assertIn("RESUMEN DE LA CONVERSACION", body)
            self.assertIn("SENALES DE PRIORIDAD", body)
        self.assertIn("Hora: 11:00-11:30", self.client.sent[1][1])
        self.assertIn("Estado: cancelada", self.client.sent[2][1])
        await self.notifications.flush()
        self.assertEqual(len(self.client.sent), 3)
