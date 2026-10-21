import asyncio
import json
import tempfile
import threading
import unittest
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx

from calendar_domain import PatientScope
from fake_calendar_provider import FakeCalendarProvider
from google_calendar_provider import (
    MANAGED_BY_PROPERTY,
    GoogleCalendarProvider,
    StaticAccessTokenProvider,
)
from tool_executor import ToolExecutor
from tool_validation import BusinessHours, TimeWindow
from voice_repository import VoiceRepository
from voice_session import VOICE_LAB_MANAGED_BY_VALUE, laboratory_executor
from voice_tools import VoiceTools


class ProviderWithoutAppointments:
    """Replica un proveedor remoto sin el estado en memoria del adaptador fake."""

    def __init__(self, provider):
        self._provider = provider

    def __getattr__(self, name):
        if name == "appointments":
            raise AttributeError(name)
        return getattr(self._provider, name)


class VoiceToolsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.repository = VoiceRepository(Path(directory) / "voice.sqlite3")
        self.repository.start()
        self.addCleanup(self.repository.close)
        self.repository.begin("call-a", "tester", 10)
        self.now = datetime(2026, 10, 19, 8, tzinfo=timezone.utc)
        hours = BusinessHours("UTC", {day: (TimeWindow(time(9), time(17)),) for day in range(5)})
        self.provider = FakeCalendarProvider()
        self.executor = ToolExecutor(provider=self.provider, business_hours=hours, now=self.now)
        self.tools = VoiceTools(repository=self.repository, session_id="call-a", profile="tester", executor=self.executor, scope=PatientScope(1, 1, "laboratory:tester"))
        self.arguments = {"start_at": "2026-10-19T10:00:00+00:00", "reason": "Revisión general", "patient_name": "Asael Ponce"}

    async def propose(self, call_id="prepare", turn=1):
        result = await self.tools.execute(call_id, "create_appointment", self.arguments, turn)
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(self.provider.appointments), 0)
        return result

    def arm(self, proposal, item="question"):
        self.tools.bind_prompt(item, proposal["confirmation_prompt"])
        self.tools.emitted(item)

    async def confirm(self, proposal, call_id="confirm", turn=2):
        return await self.tools.execute(call_id, "confirm_appointment_action", {"action_id": proposal["action_id"], "decision": "confirm"}, turn)

    async def test_create_requires_exact_question_emission_and_later_turn_then_is_durable_and_idempotent(self):
        proposal = await self.propose()
        self.arm(proposal)
        result = await self.confirm(proposal)
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(self.provider.appointments), 1)
        self.assertEqual(await self.confirm(proposal), result)
        self.assertEqual(len(self.provider.appointments), 1)
        self.assertFalse((await self.confirm(proposal, "another-call-id"))["ok"])
        saved = self.repository.appointments("tester")
        self.assertEqual(saved[0]["reason"], "Revisión general")
        self.assertEqual(saved[0]["id"], self.provider.appointments[0].id)

    async def test_confirmation_prompts_present_time_before_mexican_date(self):
        booking = await self.propose()
        self.assertEqual(
            booking["confirmation_prompt"],
            "¿Confirmas agendar la cita a las 10:00 AM del 19/10/2026, "
            "a nombre de Asael Ponce, por Revisión general?",
        )
        self.arm(booking)
        self.assertTrue((await self.confirm(booking))["ok"])

        appointment_id = self.provider.appointments[0].id
        move = await self.tools.execute("move-format", "reschedule_appointment", {
            "appointment_id": appointment_id,
            "new_start_at": "2026-10-19T11:00:00+00:00",
        }, 3)
        self.assertEqual(
            move["confirmation_prompt"],
            "¿Confirmas cambiar la cita de las 10:00 AM del 19/10/2026, "
            "por Revisión general, a las 11:00 AM del 19/10/2026?",
        )

        cancel = await self.tools.execute(
            "cancel-format", "cancel_appointment", {"appointment_id": appointment_id}, 4,
        )
        self.assertEqual(
            cancel["confirmation_prompt"],
            "¿Confirmas cancelar la cita de las 10:00 AM del 19/10/2026, "
            "por Revisión general?",
        )

    async def test_unemitted_changed_same_turn_or_expired_confirmation_renews_without_authorizing(self):
        for case in ("unemitted", "changed", "same-turn", "expired"):
            with self.subTest(case=case):
                proposal = await self.propose("prepare-" + case)
                if case == "changed":
                    self.tools.bind_prompt("question", "¿Confirmas una cita diferente?")
                    self.tools.emitted("question")
                elif case in {"same-turn", "expired"}:
                    self.arm(proposal)
                    if case == "expired":
                        self.tools.pending["expires"] = 0
                result = await self.confirm(proposal, "confirm-" + case, turn=1 if case == "same-turn" else 2)
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["status"], "confirmation_required")
                self.assertNotEqual(result["action_id"], proposal["action_id"])
                self.assertFalse(self.tools.pending["armed"])
                self.assertEqual(len(self.provider.appointments), 0)

    async def test_reschedule_after_vad_gap_requires_an_unambiguous_current_affirmation(self):
        booking = await self.propose("prepare-initial-booking")
        self.arm(booking, "booking-question")
        self.assertTrue((await self.confirm(booking, "confirm-initial-booking")).get("ok"))
        appointment_id = self.provider.appointments[0].id

        move = await self.tools.execute("prepare-move", "reschedule_appointment", {
            "appointment_id": appointment_id,
            "new_start_at": "2026-10-19T11:00:00+00:00",
        }, 3)
        self.arm(move, "move-question")
        result = await self.tools.execute("ambiguous-vad-answer", "confirm_appointment_action", {
            "action_id": move["action_id"], "decision": "confirm",
        }, 5, channel_turn=5, source_text="Sí, pero mejor a las once")

        self.assertEqual(result["status"], "confirmation_required")
        self.assertNotEqual(result["action_id"], move["action_id"])
        self.assertEqual(self.provider.appointments[0].start_at.isoformat(), "2026-10-19T10:00:00+00:00")

    async def test_interrupted_proposal_cannot_be_recovered_by_wrong_action_or_other_channel(self):
        proposal = await self.propose()
        await self.tools.interrupt()
        wrong = await self.confirm({"action_id": "unrelated"}, "wrong-action")
        self.assertFalse(wrong["ok"])
        crossed = await self.tools.execute("other-channel", "confirm_appointment_action", {
            "action_id": proposal["action_id"], "decision": "confirm"}, 2,
            channel="text", channel_turn=1, source_text="Sí")
        self.assertFalse(crossed["ok"])
        self.assertFalse(self.provider.appointments)
        renewed = await self.confirm(proposal, "recover", turn=3)
        self.assertEqual(renewed["status"], "confirmation_required")
        self.assertFalse(self.tools.pending["armed"])
        self.assertFalse(self.provider.appointments)

    async def test_reject_correction_or_new_workflow_discards_interrupted_proposal(self):
        for decision in ("reject", "correct", "new"):
            with self.subTest(decision=decision):
                proposal = await self.propose("prepare-" + decision)
                await self.tools.interrupt()
                if decision == "new":
                    result = await self.tools.execute("discard-new", "manage_appointment_workflow", {"mode": "new"}, 2)
                else:
                    result = await self.tools.execute("discard-" + decision, "confirm_appointment_action", {
                        "action_id": proposal["action_id"], "decision": decision}, 2)
                self.assertTrue(result["ok"], result)
                self.assertFalse((await self.confirm(proposal, "stale-" + decision, turn=3))["ok"])
                self.assertFalse(self.provider.appointments)

    async def test_recovering_interrupted_question_revalidates_availability(self):
        proposal = await self.propose()
        await self.tools.interrupt()
        self.provider.register_busy_period(calendar_id="calendar-1",
            start_at=datetime.fromisoformat(self.arguments["start_at"]),
            end_at=datetime(2026, 10, 19, 10, 30, tzinfo=timezone.utc))
        result = await self.confirm(proposal)
        self.assertFalse(result["ok"])
        self.assertIn("disponible", result["error"])
        self.assertFalse(self.provider.appointments)

    async def test_name_reason_identity_foreign_appointment_and_range_are_validated(self):
        for extra in ({"patient_id": 2}, {"patient_name": "tengo los ojos rojos"}, {"reason": "1234"}):
            arguments = {**self.arguments, **extra}
            result = await self.tools.execute("bad-" + str(len(json.dumps(extra))), "create_appointment", arguments, 1)
            self.assertFalse(result["ok"])
        result = await self.tools.execute("foreign", "cancel_appointment", {"appointment_id": "another-patient"}, 1)
        self.assertFalse(result["ok"])
        result = await self.tools.execute("range", "check_availability", {"start_at": self.now.isoformat(), "end_at": (self.now + timedelta(days=100)).isoformat()}, 1)
        self.assertFalse(result["ok"])

    async def test_reject_change_of_topic_stale_turn_and_close_invalidate_authorization(self):
        proposal = await self.propose()
        self.arm(proposal)
        await self.tools.end_turn(2)
        self.assertFalse((await self.confirm(proposal))["ok"])
        self.tools.current_turn = 3
        self.assertFalse((await self.tools.execute("old-turn", "create_appointment", self.arguments, 1))["ok"])
        proposal = await self.propose("new-proposal", 3)
        self.arm(proposal)
        await self.tools.close()
        self.assertFalse((await self.confirm(proposal, "after-close", 4))["ok"])

    async def test_reschedule_and_cancel_use_owned_snapshot_and_reconfirm(self):
        proposal = await self.propose()
        self.arm(proposal)
        await self.confirm(proposal)
        appointment_id = self.provider.appointments[0].id
        change = await self.tools.execute("move", "reschedule_appointment", {"appointment_id": appointment_id, "new_start_at": "2026-10-19T11:00:00+00:00"}, 3)
        self.arm(change, "move-question")
        result = await self.confirm(change, "move-confirm", 4)
        self.assertTrue(result["ok"], result)
        cancel = await self.tools.execute("cancel", "cancel_appointment", {"appointment_id": appointment_id}, 5)
        self.arm(cancel, "cancel-question")
        self.assertTrue((await self.confirm(cancel, "cancel-confirm", 6))["ok"])
        self.assertEqual(self.repository.appointments("tester")[0]["status"], "cancelled")

    async def test_restart_invalidates_pending_and_preserves_history_without_assuming_full_playback(self):
        await self.propose()
        self.repository.turn("call-a", "input", "user", "Quiero una cita", "received")
        self.repository.turn("call-a", "output", "assistant", "Una respuesta que no termino", "playing")
        self.repository.close()
        self.repository.start()
        with self.repository.connection() as db:
            self.assertEqual(db.execute("SELECT state FROM voice_actions").fetchone()[0], "invalidated")
        history = self.repository.history("tester")
        self.assertEqual(history[0]["content"][0]["text"], "Quiero una cita")
        self.assertIn("interrumpida", history[1]["content"][0]["text"])
        self.assertNotIn("no termino", history[1]["content"][0]["text"])

    async def test_quota_and_database_isolation_and_exclusive_owner(self):
        with self.assertRaises(ValueError):
            self.repository.begin("too-many", "tester", 1)
        other = VoiceRepository(self.repository.path)
        with self.assertRaises(BlockingIOError):
            other.start()
        with self.repository.connection() as db:
            db.execute("CREATE TABLE patients(id INTEGER)")
        self.repository.close()
        with self.assertRaises(ValueError):
            self.repository.start()

    async def test_voice_repository_supports_explicit_unlimited_session_cap(self):
        for index in range(7):
            session_id = f"unlimited-{index}"
            self.repository.begin(session_id, "unlimited-profile", maximum_sessions=None)
            self.repository.finish(session_id, "hangup", {})

        with self.repository.connection() as db:
            count = db.execute(
                "SELECT COUNT(*) FROM voice_sessions WHERE profile=?",
                ("unlimited-profile",),
            ).fetchone()[0]
        self.assertEqual(count, 7)

    async def test_interrupt_or_hangup_before_sql_claim_prevents_mutation(self):
        original = self.repository.execute_action
        for case in ("interruption", "hangup"):
            with self.subTest(case=case):
                proposal = await self.propose("prepare-" + case)
                self.arm(proposal)
                entered, release = threading.Event(), threading.Event()

                def delayed_claim(*args):
                    entered.set()
                    release.wait(timeout=2)
                    return original(*args)

                with patch.object(self.repository, "execute_action", side_effect=delayed_claim):
                    confirmation = asyncio.create_task(self.confirm(proposal, "confirm-" + case))
                    self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                    if case == "interruption":
                        self.tools.supersede(1)
                    else:
                        self.tools.closed = True
                    release.set()
                    result = await confirmation
                self.assertFalse(result["ok"])
                self.assertEqual(len(self.provider.appointments), 0)

    async def test_queued_old_generation_cannot_confirm_when_new_speech_starts(self):
        proposal = await self.propose()
        self.arm(proposal)
        await self.tools._lock.acquire()
        try:
            pending = asyncio.create_task(self.tools.execute("queued", "confirm_appointment_action", {
                "action_id": proposal["action_id"], "decision": "confirm",
            }, 2, generation=0))
            await asyncio.sleep(0)
            self.tools.supersede(1)
        finally:
            self.tools._lock.release()
        self.assertFalse((await pending)["ok"])
        self.assertEqual(len(self.provider.appointments), 0)

    async def test_missing_transcript_preserves_user_turn_and_no_orphan_response(self):
        self.repository.turn("call-a", "input-missing", "user", None, "received")
        self.repository.turn("call-a", "answer", "assistant", "Una respuesta", "completed")
        self.repository.finish("call-a", "hangup", {})
        history = self.repository.history("tester")
        self.assertEqual([item["role"] for item in history], ["user", "assistant"])
        self.assertIn("sin transcripcion", history[0]["content"][0]["text"])

    async def test_new_text_session_resumes_data_without_inheriting_voice_authorization(self):
        original = await self.propose()
        self.arm(original)
        await self.tools.close()
        self.repository.finish("call-a", "hangup", {})
        self.repository.begin("text-b", "tester", 10)
        following = VoiceTools(repository=self.repository, session_id="text-b", profile="tester", executor=self.executor,
                               scope=PatientScope(1, 1, "laboratory:tester"))
        renewed = await following.execute("resume", "manage_appointment_workflow", {"mode": "resume"}, 1,
            channel="text", channel_turn=1, source_text="Retomemos la cita")
        self.assertTrue(renewed["ok"], renewed)
        self.assertNotEqual(renewed["action_id"], original["action_id"])
        wrong = await following.execute("old-permission", "confirm_appointment_action", {
            "action_id": original["action_id"], "decision": "confirm"}, 2, channel="text", channel_turn=2, source_text="Sí")
        self.assertFalse(wrong["ok"])
        self.assertFalse(self.provider.appointments)
        following.bind_prompt("text-question", renewed["confirmation_prompt"])
        following.emitted("text-question")
        confirmed = await following.execute("fresh-permission", "confirm_appointment_action", {
            "action_id": renewed["action_id"], "decision": "confirm"}, 2, channel="text", channel_turn=2, source_text="Sí")
        self.assertTrue(confirmed["ok"], confirmed)
        self.assertEqual(len(self.provider.appointments), 1)

    async def test_late_transcript_updates_original_order_and_cannot_promote_interrupted_output(self):
        self.repository.turn("call-a", "first-input", "user", None, "received")
        self.repository.turn("call-a", "answer", "assistant", "Respuesta generada", "playing")
        self.repository.progress("call-a", "answer", generated_ms=1000, emitted_ms=100, generation_state="completed")
        self.repository.turn("call-a", "answer", "assistant", None, "interrupted")
        self.repository.turn("call-a", "second-input", "user", "Otro mensaje", "completed", "text")
        self.repository.turn("call-a", "first-input", "user", "Texto tardío", "completed")
        self.repository.turn("call-a", "answer", "assistant", None, "completed")
        rows = self.repository.turns("call-a")
        self.assertEqual([row["item_id"] for row in rows], ["first-input", "answer", "second-input"])
        self.assertEqual(rows[0]["transcript"], "Texto tardío")
        self.assertEqual(rows[1]["state"], "interrupted")
        self.assertNotIn("Respuesta generada", json.dumps(self.repository.history("tester")))

    async def test_new_workflow_supersedes_old_data_and_resume_cannot_resurrect_it(self):
        await self.propose()
        new = await self.tools.execute("new-management", "manage_appointment_workflow", {"mode": "new"}, 2)
        self.assertTrue(new["ok"])
        self.assertIsNone(self.repository.latest_action("tester"))
        resumed = await self.tools.execute("resume-replaced", "manage_appointment_workflow", {"mode": "resume"}, 3)
        self.assertFalse(resumed["ok"])
        with self.repository.connection() as db:
            self.assertEqual(db.execute("SELECT state FROM voice_actions").fetchone()[0], "superseded")

    async def test_successful_remote_provider_mutation_does_not_require_fake_appointments_attribute(self):
        executor = ToolExecutor(
            provider=ProviderWithoutAppointments(self.provider),
            business_hours=self.executor.business_hours,
            now=self.now,
        )
        tools = VoiceTools(
            repository=self.repository,
            session_id="call-a",
            profile="tester",
            executor=executor,
            scope=PatientScope(1, 1, "laboratory:tester"),
        )
        proposal = await tools.execute("remote-prepare", "create_appointment", self.arguments, 1)
        self.assertEqual(proposal["status"], "confirmation_required")
        tools.bind_prompt("remote-question", proposal["confirmation_prompt"])
        tools.emitted("remote-question")

        result = await tools.execute(
            "remote-confirm",
            "confirm_appointment_action",
            {"action_id": proposal["action_id"], "decision": "confirm"},
            2,
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(len(self.provider.appointments), 1)
        self.assertEqual(self.repository.appointments("tester"), [])

    async def test_laboratory_selects_google_only_when_explicit_and_keeps_fake_default(self):
        scope, fake_executor = laboratory_executor(
            self.repository,
            "tester",
            self.executor.business_hours,
            environment={},
        )
        self.assertEqual(scope, PatientScope(1, 1, "laboratory:tester"))
        self.assertIsInstance(fake_executor.provider, FakeCalendarProvider)

        configured = {"VOICE_CALENDAR_PROVIDER": "google"}
        with patch(
            "google_calendar_provider.create_google_calendar_provider_from_environment",
            return_value=self.provider,
        ) as factory:
            scope, google_executor = laboratory_executor(
                self.repository,
                "tester",
                self.executor.business_hours,
                environment=configured,
            )

        self.assertEqual(scope, PatientScope(1, 1, "laboratory:tester"))
        self.assertIs(google_executor.provider, self.provider)
        factory.assert_called_once_with(
            configured,
            managed_by_value=VOICE_LAB_MANAGED_BY_VALUE,
        )

    async def test_google_calendar_voice_booking_can_list_reschedule_and_cancel_in_isolated_namespace(self):
        events = {}
        requests = []
        events_path = "/v3/calendars/voice-calendar/events"

        def response(request, status=200, payload=None):
            return httpx.Response(status, json=payload, request=request)

        def handle_request(request):
            requests.append(request)
            path = request.url.path
            if path == "/v3/freeBusy":
                return response(request, payload={"calendars": {"voice-calendar": {"busy": []}}})
            if path == events_path and request.method == "GET":
                properties = [tuple(item.split("=", 1)) for item in request.url.params.get_list("privateExtendedProperty")]
                items = [
                    event for event in events.values()
                    if all(event["extendedProperties"]["private"].get(key) == value for key, value in properties)
                ]
                return response(request, payload={"items": items})
            if path == events_path and request.method == "POST":
                event = {**json.loads(request.content), "id": "google-event-1", "status": "confirmed"}
                events[event["id"]] = event
                return response(request, payload=event)
            if path.startswith(events_path + "/"):
                event_id = path.rsplit("/", 1)[-1]
                event = events.get(event_id)
                if event is None:
                    return response(request, status=404, payload={})
                if request.method == "PATCH":
                    patch_data = json.loads(request.content)
                    event.update(patch_data)
                return response(request, payload=event)
            raise AssertionError(f"Unexpected Google Calendar request: {request.method} {path}")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:
            provider = GoogleCalendarProvider(
                calendar_ids=("voice-calendar",),
                access_token_provider=StaticAccessTokenProvider("test-token"),
                timezone_name="UTC",
                base_url="https://calendar.test/v3",
                http_client=client,
                managed_by_value=VOICE_LAB_MANAGED_BY_VALUE,
            )
            scope = PatientScope(1, 1, "laboratory:tester")
            executor = ToolExecutor(provider=provider, business_hours=self.executor.business_hours, now=self.now)
            tools = VoiceTools(
                repository=self.repository,
                session_id="call-a",
                profile="tester",
                executor=executor,
                scope=scope,
            )

            proposal = await tools.execute("google-prepare", "create_appointment", self.arguments, 1)
            tools.bind_prompt("google-create-question", proposal["confirmation_prompt"])
            tools.emitted("google-create-question")
            created = await tools.execute(
                "google-create-confirm",
                "confirm_appointment_action",
                {"action_id": proposal["action_id"], "decision": "confirm"},
                2,
            )
            self.assertTrue(created["ok"], created)
            appointment_id = created["data"]["appointment"]["id"]
            self.assertEqual(
                events[appointment_id]["extendedProperties"]["private"][MANAGED_BY_PROPERTY],
                VOICE_LAB_MANAGED_BY_VALUE,
            )
            self.assertEqual([item.id for item in await provider.list_appointments(patient_scope=scope)], [appointment_id])

            whatsapp_provider = GoogleCalendarProvider(
                calendar_ids=("voice-calendar",),
                access_token_provider=StaticAccessTokenProvider("test-token"),
                timezone_name="UTC",
                base_url="https://calendar.test/v3",
                http_client=client,
            )
            self.assertEqual(await whatsapp_provider.list_appointments(patient_scope=scope), ())

            move = await tools.execute(
                "google-move",
                "reschedule_appointment",
                {"appointment_id": appointment_id, "new_start_at": "2026-10-19T11:00:00+00:00"},
                3,
            )
            tools.bind_prompt("google-move-question", move["confirmation_prompt"])
            tools.emitted("google-move-question")
            moved = await tools.execute(
                "google-move-confirm",
                "confirm_appointment_action",
                {"action_id": move["action_id"], "decision": "confirm"},
                4,
            )
            self.assertTrue(moved["ok"], moved)
            self.assertEqual(events[appointment_id]["start"]["dateTime"], "2026-10-19T11:00:00Z")

            cancel = await tools.execute(
                "google-cancel",
                "cancel_appointment",
                {"appointment_id": appointment_id},
                5,
            )
            tools.bind_prompt("google-cancel-question", cancel["confirmation_prompt"])
            tools.emitted("google-cancel-question")
            cancelled = await tools.execute(
                "google-cancel-confirm",
                "confirm_appointment_action",
                {"action_id": cancel["action_id"], "decision": "confirm"},
                6,
            )
            self.assertTrue(cancelled["ok"], cancelled)
            self.assertEqual(events[appointment_id]["status"], "cancelled")
            self.assertEqual(self.repository.appointments("tester"), [])
            mutations = [request for request in requests if request.method in {"POST", "PATCH"} and request.url.path != "/v3/freeBusy"]
            self.assertEqual([request.method for request in mutations], ["POST", "PATCH", "PATCH"])
            self.assertTrue(all(request.url.params.get("sendUpdates") == "all" for request in mutations))
