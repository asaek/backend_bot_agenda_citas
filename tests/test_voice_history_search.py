import base64
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, time, timezone
from pathlib import Path

from calendar_domain import PatientScope
from fake_calendar_provider import FakeCalendarProvider
from tool_contracts import realtime_tool_definitions
from tool_executor import ToolExecutor
from tool_validation import BusinessHours, TimeWindow
from voice_repository import VoiceRepository
from voice_tools import VoiceTools
import test_voice_session as voice_session_fixtures
import test_lab_continuity as lab_continuity_fixtures


class VoiceHistoryRepositoryTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.repository = VoiceRepository(Path(directory) / "voice.sqlite3")
        self.repository.start()
        self.addCleanup(self.repository.close)

    def add_session(self, session_id, profile, created_at, text, channel="voice", role="user", state="completed"):
        self.repository.begin(session_id, profile, None)
        self.repository.turn(session_id, "item-" + session_id, role, text, state, channel)
        self.repository.finish(session_id, "hangup", {})
        with self.repository.connection() as db:
            db.execute("UPDATE voice_sessions SET created_at=? WHERE session_id=?", (created_at, session_id))

    def test_search_combines_topic_local_date_channel_and_server_profile_beyond_recent_window(self):
        text = "Detalle previo. " * 80 + "Revisión de ESTUDIOS para la consulta." + " Mas contexto." * 80
        self.add_session("old-text", "patient-a", "2026-10-11T05:30:00+00:00", text, "text")
        self.add_session("old-voice", "patient-a", "2026-10-11T05:30:00+00:00", "Revision de estudios", "voice")
        self.add_session("next-day", "patient-a", "2026-10-11T06:01:00+00:00", "Revision de estudios", "text")
        self.add_session("foreign", "patient-b", "2026-10-11T05:30:00+00:00", "Revision de estudios privados", "text")
        self.repository.begin("current", "patient-a", None)
        for index in range(14):
            self.repository.turn("current", f"recent-{index}", "user", "Revision de estudios actuales", "completed", "text")
        self.assertNotIn("Detalle previo", str(self.repository.history("patient-a")))

        result = self.repository.search_history(
            "patient-a", query="revision estudios", start_date="2026-10-10", end_date="2026-10-10",
            channel="text", exclude_session_id="current", timezone_name="America/Mexico_City",
        )

        self.assertEqual(result["date_basis"], "session_started_at")
        self.assertEqual(result["timezone"], "America/Mexico_City")
        self.assertFalse(result["has_more"])
        self.assertEqual(len(result["fragments"]), 1)
        fragment = result["fragments"][0]
        self.assertEqual(fragment["session_id"], "old-text")
        self.assertEqual(fragment["session_state"], "ended")
        self.assertEqual(fragment["session_started_at"], "2026-10-11T05:30:00+00:00")
        self.assertEqual(fragment["channel"], "text")
        self.assertEqual(fragment["role"], "user")
        self.assertEqual(fragment["sequence"], 1)
        self.assertIn("Revisión de ESTUDIOS", fragment["text"])
        self.assertLessEqual(len(fragment["text"]), 600)
        self.assertTrue(fragment["truncated"])

    def test_results_are_bounded_ordered_and_report_additional_matches(self):
        self.add_session("past", "tester", "2026-10-10T12:00:00+00:00", "Estudios " * 1000)
        for index in range(2, 9):
            self.repository.turn("past", f"item-{index}", "user", "Estudios " * 1000, "completed")
        result = self.repository.search_history("tester", exclude_session_id="current", query="ESTUDIOS")
        self.assertTrue(result["has_more"])
        self.assertEqual([item["sequence"] for item in result["fragments"]], [8, 7, 6, 5, 4, 3])
        self.assertTrue(all(len(item["text"]) <= 600 and item["truncated"] for item in result["fragments"]))

    def test_search_terms_are_literal_and_unknown_topic_returns_no_matches(self):
        self.add_session("literal", "tester", "2026-10-10T12:00:00+00:00", "Descuento del 10% y nombre_con_guion")
        self.add_session("ordinary", "tester", "2026-10-11T12:00:00+00:00", "Un mensaje ordinario")
        for query in ("%", "_", "10%"):
            with self.subTest(query=query):
                result = self.repository.search_history("tester", exclude_session_id="current", query=query)
                self.assertEqual([item["session_id"] for item in result["fragments"]], ["literal"])
        for query in ("' OR 1=1 --", "Tema inexistente"):
            result = self.repository.search_history("tester", exclude_session_id="current", query=query)
            self.assertEqual(result["fragments"], [])
            self.assertFalse(result["has_more"])

    def test_missing_transcript_and_partial_emission_keep_their_provenance(self):
        self.add_session("missing", "tester", "2026-10-10T12:00:00+00:00", "", state="received")
        self.add_session("partial", "tester", "2026-10-11T12:00:00+00:00", "Respuesta generada pero interrumpida",
                         role="assistant", state="playing")
        self.repository.progress("partial", "item-partial", generated_ms=1000, emitted_ms=200)
        result = self.repository.search_history("tester", exclude_session_id="current")
        partial, missing = result["fragments"]
        self.assertEqual(partial["state"], "interrupted")
        self.assertEqual(partial["generated_ms"], 1000)
        self.assertEqual(partial["emitted_ms"], 200)
        self.assertTrue(partial["transcript_available"])
        self.assertEqual(missing["state"], "transcription_missing")
        self.assertFalse(missing["transcript_available"])
        self.assertIn("sin transcripcion", missing["text"])

    def test_invalid_filters_are_rejected_and_open_date_bounds_are_supported(self):
        self.add_session("past", "tester", "2026-10-10T12:00:00+00:00", "Estudios")
        for filters in ({"query": None}, {"query": "x" * 121}, {"query": "uno dos tres cuatro cinco seis siete ocho nueve"},
                        {"channel": "all"}, {"channel": []}, {"start_date": "2026-02-30"},
                        {"start_date": "20261010"}, {"end_date": 12}, {"end_date": "9999-12-31"},
                        {"start_date": "2026-10-11", "end_date": "2026-10-10"}):
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                self.repository.search_history("tester", exclude_session_id="current", **filters)
        for filters in ({"start_date": "2026-10-10"}, {"end_date": "2026-10-10"}):
            result = self.repository.search_history("tester", exclude_session_id="current", **filters)
            self.assertEqual(len(result["fragments"]), 1)

    def test_date_bounds_preserve_microseconds_at_midnight(self):
        self.add_session("just-before", "tester", "2026-10-10T23:59:59.999999+00:00", "Estudios previos")
        self.add_session("midnight", "tester", "2026-10-11T00:00:00.000000+00:00", "Estudios nuevos")
        previous = self.repository.search_history("tester", exclude_session_id="current",
                                                  start_date="2026-10-10", end_date="2026-10-10")
        following = self.repository.search_history("tester", exclude_session_id="current",
                                                   start_date="2026-10-11", end_date="2026-10-11")
        self.assertEqual([item["session_id"] for item in previous["fragments"]], ["just-before"])
        self.assertEqual([item["session_id"] for item in following["fragments"]], ["midnight"])


class VoiceHistoryToolTests(unittest.IsolatedAsyncioTestCase):
    add_session = VoiceHistoryRepositoryTests.add_session

    async def asyncSetUp(self):
        VoiceHistoryRepositoryTests.setUp(self)
        self.add_session("past-text", "tester", "2026-10-10T12:00:00+00:00", "Quiero revisar mis estudios.", "text")
        self.add_session("foreign-text", "other", "2026-10-10T12:00:00+00:00", "Mis estudios privados.", "text")
        self.repository.begin("call-a", "tester", None)
        self.provider = FakeCalendarProvider()
        hours = BusinessHours("UTC", {day: (TimeWindow(time(9), time(17)),) for day in range(5)})
        executor = ToolExecutor(provider=self.provider, business_hours=hours, now=datetime(2026, 10, 19, 8, tzinfo=timezone.utc))
        self.tools = VoiceTools(repository=self.repository, session_id="call-a", profile="tester", executor=executor,
                                scope=PatientScope(1, 1, "laboratory:tester"))

    async def test_history_lookup_preserves_armed_proposal_through_end_of_turn(self):
        proposal = await self.tools.execute("prepare", "create_appointment", {
            "start_at": "2026-10-19T10:00:00+00:00", "reason": "Revision general", "patient_name": "Asael Ponce",
        }, 1)
        self.assertTrue(proposal["ok"], proposal)
        self.tools.bind_prompt("question", proposal["confirmation_prompt"])
        self.tools.emitted("question")
        before = deepcopy(self.tools.pending)
        durable_before = self.repository.latest_action("tester")

        result = await self.tools.execute("history", "search_conversation_history", {
            "query": "estudios", "start_date": "2026-10-10", "end_date": "2026-10-10", "channel": "text",
        }, 2)
        self.assertTrue(result["ok"], result)
        await self.tools.end_turn(2)
        self.assertEqual(self.tools.pending, before)
        self.assertEqual(self.repository.latest_action("tester"), durable_before)
        self.assertEqual([item["session_id"] for item in result["data"]["fragments"]], ["past-text"])
        self.assertFalse(self.provider.appointments)

        definition = next(item for item in realtime_tool_definitions() if item["name"] == "search_conversation_history")
        self.assertEqual(set(definition["parameters"]["properties"]), {"query", "start_date", "end_date", "channel"})
        self.assertFalse(definition["parameters"]["additionalProperties"])

    async def test_invalid_filters_and_identity_injection_do_not_change_proposals(self):
        proposal = await self.tools.execute("prepare", "create_appointment", {
            "start_at": "2026-10-19T10:00:00+00:00", "reason": "Revision general", "patient_name": "Asael Ponce",
        }, 1)
        self.tools.bind_prompt("question", proposal["confirmation_prompt"])
        self.tools.emitted("question")
        self.tools.pending["expires"] = 0
        before = deepcopy(self.tools.pending)
        durable_before = self.repository.latest_action("tester")
        for index, filters in enumerate(({"profile": "other"}, {"patient_id": 2}, {"session_id": "foreign-text"},
                                         {"timezone_name": "UTC"}, {"limit": 1000}, {"channel": "other"},
                                         {"start_date": "no-es-fecha"}, {"query": "x" * 121})):
            with self.subTest(filters=filters):
                result = await self.tools.execute(f"bad-search-{index}", "search_conversation_history", filters, index + 2)
                self.assertFalse(result["ok"], result)
                await self.tools.end_turn(index + 2)
                self.assertEqual(self.tools.pending, before, "no renueva siquiera el vencimiento")
                self.assertEqual(self.repository.latest_action("tester"), durable_before)
        self.assertFalse(self.provider.appointments)

    async def test_repeated_lookup_reuses_original_result_and_does_not_create_a_workflow(self):
        result = await self.tools.execute("history", "search_conversation_history", {"query": "estudios"}, 1)
        self.assertTrue(result["ok"], result)
        self.repository.turn("past-text", "item-past-text", "user", "Texto corregido sin esa palabra", "completed", "text")
        self.assertEqual(await self.tools.execute("history", "search_conversation_history", {"query": "estudios"}, 1), result)
        self.assertEqual(self.tools.calls, 1)
        await self.tools.end_turn(1)
        self.assertIsNone(self.tools.pending)
        self.assertIsNone(self.repository.latest_action("tester"))
        self.assertFalse(self.provider.appointments)

    async def test_other_tools_in_same_turn_keep_normal_proposal_invalidation(self):
        proposal = await self.tools.execute("prepare", "create_appointment", {
            "start_at": "2026-10-19T10:00:00+00:00", "reason": "Revision general", "patient_name": "Asael Ponce",
        }, 1)
        self.tools.bind_prompt("question", proposal["confirmation_prompt"])
        self.tools.emitted("question")
        self.assertTrue((await self.tools.execute("history", "search_conversation_history", {"query": "estudios"}, 2))["ok"])
        invalid_confirmation = await self.tools.execute("wrong-confirm", "confirm_appointment_action", {
            "action_id": "foreign-action", "decision": "confirm",
        }, 2)
        self.assertFalse(invalid_confirmation["ok"])
        await self.tools.end_turn(2)
        self.assertIsNone(self.tools.pending)
        self.assertFalse(self.provider.appointments)


class VoiceHistorySessionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = voice_session_fixtures.VoiceSessionTests.asyncSetUp
    wait = voice_session_fixtures.VoiceSessionTests.wait
    speech = voice_session_fixtures.VoiceSessionTests.speech
    audio = voice_session_fixtures.VoiceSessionTests.audio
    tool = voice_session_fixtures.VoiceSessionTests.tool
    add_session = VoiceHistoryRepositoryTests.add_session
    text_turn = lab_continuity_fixtures.VoiceAndTextSessionTests.text_turn
    finish_text = lab_continuity_fixtures.VoiceAndTextSessionTests.finish_text

    async def test_recalling_an_old_question_cannot_rebind_the_current_proposal(self):
        response = await self.speech("booking-input")
        proposal = await self.tool(response, "prepare", "create_appointment", {
            "start_at": "2026-10-19T10:00:00+00:00", "reason": "Revision general", "patient_name": "Asael Ponce",
        })
        await self.audio(self.session._active_response, "current-question", proposal["confirmation_prompt"], drained=True)
        self.add_session("past-question", "developer", "2026-10-10T12:00:00+00:00",
                         proposal["confirmation_prompt"], role="assistant")
        before = deepcopy(self.session.tools.pending)
        durable_before = self.repository.latest_action("developer")

        response = await self.speech("history-input")
        result = await self.tool(response, "history", "search_conversation_history", {"query": "confirmas"})
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["data"]["fragments"][0]["session_id"], "past-question")
        await self.audio(self.session._active_response, "historical-quote", proposal["confirmation_prompt"], drained=True)

        self.assertEqual(self.session.tools.pending, before)
        self.assertEqual(self.repository.latest_action("developer"), durable_before)
        self.assertFalse(self.repository.appointments("developer"))

    async def test_publishing_a_historical_text_question_does_not_rebind_or_renew_a_proposal(self):
        task, response = await self.text_turn("Quiero una cita")
        proposal = await self.tool(response, "prepare-text", "create_appointment", {
            "start_at": "2026-10-19T10:00:00+00:00", "reason": "Revision general", "patient_name": "Asael Ponce",
        })
        await self.finish_text(task, proposal["confirmation_prompt"])
        self.add_session("past-text-question", "developer", "2026-10-10T12:00:00+00:00",
                         proposal["confirmation_prompt"], channel="text", role="assistant")
        before = deepcopy(self.session.tools.pending)
        durable_before = self.repository.latest_action("developer")

        task, response = await self.text_turn("¿Que pregunta me hiciste por texto?")
        result = await self.tool(response, "history-text", "search_conversation_history", {"query": "confirmas", "channel": "text"})
        self.assertTrue(result["ok"], result)
        await self.finish_text(task, proposal["confirmation_prompt"])
        self.assertEqual(self.session.tools.pending, before)
        self.assertEqual(self.repository.latest_action("developer"), durable_before)
        self.assertFalse(self.repository.appointments("developer"))

    async def test_quote_streamed_before_lookup_call_cannot_rebind_the_proposal(self):
        response = await self.speech("booking-input")
        proposal = await self.tool(response, "prepare", "create_appointment", {
            "start_at": "2026-10-19T10:00:00+00:00", "reason": "Revision general", "patient_name": "Asael Ponce",
        })
        await self.audio(self.session._active_response, "current-question", proposal["confirmation_prompt"], drained=True)
        self.add_session("past-question", "developer", "2026-10-10T12:00:00+00:00",
                         proposal["confirmation_prompt"], role="assistant")
        before = deepcopy(self.session.tools.pending)
        response = await self.speech("history-input")
        for event in (
            {"type": "response.output_audio.delta", "delta": base64.b64encode(b"\1\0" * 480).decode()},
            {"type": "response.output_audio_transcript.done", "transcript": proposal["confirmation_prompt"]},
            {"type": "response.output_audio.done"},
        ):
            await self.provider.events.put({**event, "response_id": response, "item_id": "preface-quote"})
        await self.wait(lambda: any(item["item_id"] == "preface-quote" and item.get("text") == proposal["confirmation_prompt"]
                                   for item in self.session.metrics["voice_history"]))
        await self.media.output_events.put(("preface-quote", 20))
        await self.wait(lambda: any(item["item_id"] == "preface-quote" and item["state"] == "completed"
                                   for item in self.session.metrics["voice_history"]))
        result = await self.tool(response, "history", "search_conversation_history", {"query": "confirmas"})
        self.assertTrue(result["ok"], result)
        await self.audio(self.session._active_response, "history-answer", "Recupere la pregunta anterior.", drained=True)
        self.assertEqual(self.session.tools.pending, before)
        self.assertFalse(self.repository.appointments("developer"))
