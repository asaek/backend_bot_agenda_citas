import asyncio
import base64
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, time, timezone
from contextlib import closing
from pathlib import Path

from openai_realtime_provider import RealtimeSettings
from calling_service import CallMediaPersistenceError
from tool_validation import BusinessHours, TimeWindow
from voice_repository import VoiceRepository
from voice_session import VoiceSession
from voice_fakes import FakeRealtimeProvider, FakeVoiceMedia


class VoiceSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.repository = VoiceRepository(Path(directory) / "voice.sqlite3")
        self.repository.start()
        self.addCleanup(self.repository.close)
        self.media, self.provider = FakeVoiceMedia(), FakeRealtimeProvider()
        hours = BusinessHours("UTC", {day: (TimeWindow(time(9), time(17)),) for day in range(5)})
        self.session = VoiceSession(session_id="session", media=self.media, provider=self.provider, repository=self.repository,
            settings=RealtimeSettings(api_key="test-only", maximum_sessions=10), business_hours=hours)
        self.addAsyncCleanup(self.session.close)
        await self.session.negotiate("offer")
        self.session.tools.executor._now = datetime(2026, 10, 19, 8, tzinfo=timezone.utc)
        self.media.events.put_nowait("connected")
        await self.wait(lambda: len(self.provider.responses) == 1 and self.session._active_response is not None)

    async def wait(self, predicate):
        async with asyncio.timeout(3):
            while not predicate():
                await asyncio.sleep(.005)

    async def speech(self, item_id):
        turn = self.session.current_turn
        await self.provider.events.put({"type": "input_audio_buffer.speech_started"})
        await self.provider.events.put({"type": "input_audio_buffer.committed", "item_id": item_id})
        await self.wait(lambda: self.session.current_turn == turn + 1 and self.session._active_response is not None and
                        self.session._responses[self.session._active_response]["turn"] == turn + 1)
        return self.session._active_response

    async def audio(self, response_id, item_id, text="Hola", *, drained=False):
        for event in (
            {"type": "response.output_audio.delta", "delta": base64.b64encode(b"\1\0" * 480).decode()},
            {"type": "response.output_audio_transcript.done", "transcript": text},
            {"type": "response.output_audio.done"},
        ):
            await self.provider.events.put({**event, "response_id": response_id, "item_id": item_id})
        await self.provider.events.put({"type": "response.done", "response": {"id": response_id, "status": "completed", "output": [{"type": "message"}], "usage": {"input_tokens": 4, "output_tokens": 5}}})
        await self.wait(lambda: self.session._active_response is None and item_id in self.session._items)
        if drained:
            await self.media.output_events.put((item_id, 20))
            await self.wait(lambda: self.session._items[item_id]["drained"])

    async def tool(self, response_id, call_id, name, arguments):
        previous = len(self.provider.responses)
        await self.provider.events.put({"type": "response.function_call_arguments.done", "response_id": response_id,
            "call_id": call_id, "name": name, "arguments": json.dumps(arguments)})
        await self.provider.events.put({"type": "response.done", "response": {"id": response_id, "status": "completed", "output": [{"type": "function_call"}]}})
        await self.wait(lambda: len(self.provider.responses) > previous and self.session._active_response is not None)
        outputs = [event["item"] for event in self.provider.commands if event["type"] == "conversation.item.create" and event["item"].get("call_id") == call_id]
        return json.loads(outputs[-1]["output"])

    async def test_audio_crosses_provider_and_partial_playback_is_cancelled_without_late_resurrection(self):
        self.media.input_audio.put_nowait(b"\2\0" * 480)
        await self.wait(lambda: any(event["type"] == "input_audio_buffer.append" for event in self.provider.commands))
        await self.speech("first-input")
        old_response = self.session._active_response
        await self.audio(old_response, "old-audio", "Una frase incompleta")
        self.assertTrue(self.media.audio)
        self.media.emitted_ms["old-audio"] = 10
        await self.speech("new-input")
        self.assertFalse(self.media.audio)
        self.assertTrue(any(event["type"] == "conversation.item.truncate" and event["audio_end_ms"] == 10 for event in self.provider.commands))
        await self.provider.events.put({"type": "response.output_audio.delta", "response_id": old_response,
            "item_id": "old-audio", "delta": base64.b64encode(b"\3\0" * 480).decode()})
        await asyncio.sleep(.03)
        self.assertFalse(self.media.audio)
        interrupted = next(item for item in self.repository.turns("session") if item["item_id"] == "old-audio")
        self.assertEqual(interrupted["state"], "interrupted")
        self.assertEqual(interrupted["generation_state"], "completed")
        self.assertEqual(interrupted["generated_ms"], 20)
        self.assertEqual(interrupted["emitted_ms"], 10)

    async def test_rtp_gap_supplies_silence_so_provider_can_finish_vad_turn(self):
        self.media.last_received_at = asyncio.get_running_loop().time()
        await self.wait(lambda: self.session.metrics["voice_input_silence_ms"] >= 100)
        chunks = [event for event in self.provider.commands if event["type"] == "input_audio_buffer.append"]
        self.assertEqual(base64.b64decode(chunks[-1]["audio"]), bytes(4800))

    async def test_listening_waits_for_every_audio_item_not_only_first_drain(self):
        response = self.session._active_response
        await self.audio(response, "first-part")
        self.session._item("second-part", response)["started"] = True
        await self.media.output_events.put(("first-part", 20))
        await self.wait(lambda: self.session._items["first-part"]["drained"])
        self.assertEqual(self.session.metrics["voice_state"], "playing")
        await self.media.output_events.put(("second-part", 20))
        await self.wait(lambda: self.session.metrics["voice_state"] == "listening")
        self.assertEqual(self.session.metrics["voice_state"], "listening")

    async def test_native_turn_replies_before_transcript_and_duplicate_transcript_cannot_execute_a_tool(self):
        await self.speech("input-1")
        self.assertGreaterEqual(len(self.provider.responses), 2)
        self.assertEqual(self.repository.turns("session")[-1]["transcript"], "")
        transcript = {"type": "conversation.item.input_audio_transcription.completed", "item_id": "input-1",
                      "transcript": "Sí, cancela todo", "usage": {"total_tokens": 7}}
        await self.provider.events.put(transcript)
        await self.provider.events.put(transcript)
        await self.wait(lambda: self.session.metrics["voice_usage"]["transcription_tokens"] == 7)
        self.assertFalse(self.session._calls)
        self.assertEqual(self.repository.turns("session")[-1]["transcript"], "Sí, cancela todo")

    async def test_prepare_question_drain_and_later_audio_turn_authorize_one_booking(self):
        response = await self.speech("booking-input")
        proposal = await self.tool(response, "prepare", "create_appointment", {
            "start_at": "2026-10-19T10:00:00+00:00", "reason": "Revisión general", "patient_name": "Asael Ponce"})
        self.assertEqual(proposal["status"], "confirmation_required")
        response = self.session._active_response
        await self.audio(response, "question", proposal["confirmation_prompt"], drained=True)
        self.assertTrue(self.session.tools.pending["armed"])
        response = await self.speech("yes-input")
        result = await self.tool(response, "confirm", "confirm_appointment_action", {"action_id": proposal["action_id"], "decision": "confirm"})
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(self.repository.appointments("developer")), 1)

    async def test_confirmation_after_interrupted_question_reasks_without_losing_booking_details(self):
        response = await self.speech("booking-input")
        proposal = await self.tool(response, "prepare", "create_appointment", {
            "start_at": "2026-10-19T10:00:00+00:00", "reason": "Revisión general", "patient_name": "Asael Ponce"})
        await self.audio(self.session._active_response, "interrupted-question", proposal["confirmation_prompt"])
        self.media.emitted_ms["interrupted-question"] = 19
        # The patient starts answering just before the question finishes playing.
        response = await self.speech("early-yes")
        renewed = await self.tool(response, "early-confirm", "confirm_appointment_action", {
            "action_id": proposal["action_id"], "decision": "confirm"})
        self.assertTrue(renewed["ok"], renewed)
        self.assertEqual(renewed["status"], "confirmation_required")
        self.assertNotEqual(renewed["action_id"], proposal["action_id"])
        self.assertEqual(renewed["confirmation_prompt"], proposal["confirmation_prompt"])
        self.assertFalse(self.repository.appointments("developer"))
        await self.audio(self.session._active_response, "renewed-question", renewed["confirmation_prompt"], drained=True)
        response = await self.speech("fresh-yes")
        result = await self.tool(response, "fresh-confirm", "confirm_appointment_action", {
            "action_id": renewed["action_id"], "decision": "confirm"})
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(self.repository.appointments("developer")), 1)

    async def test_repeated_answer_after_interruption_still_recovers_the_question(self):
        response = await self.speech("booking-input")
        proposal = await self.tool(response, "prepare", "create_appointment", {
            "start_at": "2026-10-19T10:00:00+00:00", "reason": "Revisión general", "patient_name": "Asael Ponce"})
        await self.audio(self.session._active_response, "question", proposal["confirmation_prompt"])
        response = await self.speech("early-answer")
        await self.audio(response, "unfinished-answer", "")
        response = await self.speech("repeated-answer")
        renewed = await self.tool(response, "recover-after-repeated-answer", "confirm_appointment_action", {
            "action_id": proposal["action_id"], "decision": "confirm"})
        self.assertTrue(renewed["ok"], renewed)
        self.assertEqual(renewed["confirmation_prompt"], proposal["confirmation_prompt"])
        self.assertFalse(self.repository.appointments("developer"))

    async def test_confirmation_recovers_after_intermediate_voice_response_is_interrupted(self):
        response = await self.speech("booking-input")
        proposal = await self.tool(response, "prepare", "create_appointment", {
            "start_at": "2026-10-19T10:00:00+00:00", "reason": "Revisión general", "patient_name": "Asael Ponce"})
        await self.audio(self.session._active_response, "question", proposal["confirmation_prompt"], drained=True)

        # A short VAD turn starts a response, then the actual confirmation arrives
        # before that response finishes. Realtime cancels the intermediate response.
        await self.speech("intermediate-vad-turn")
        response = await self.speech("confirmation-after-interruption")
        self.assertTrue(self.session.tools.pending["armed"])
        self.assertEqual(self.session.tools.pending["channel_turn"] + 2, self.session._channel_counts["voice"])
        self.assertLess(asyncio.get_running_loop().time(), self.session.tools.pending["expires"])
        renewed = await self.tool(response, "confirm-after-interruption", "confirm_appointment_action", {
            "action_id": proposal["action_id"], "decision": "confirm"})
        self.assertTrue(renewed["ok"], renewed)
        self.assertEqual(renewed["status"], "confirmation_required")
        self.assertNotEqual(renewed["action_id"], proposal["action_id"])
        self.assertFalse(self.repository.appointments("developer"))

        await self.audio(self.session._active_response, "renewed-question", renewed["confirmation_prompt"], drained=True)
        response = await self.speech("explicit-confirmation")
        result = await self.tool(response, "confirm-renewed-action", "confirm_appointment_action", {
            "action_id": renewed["action_id"], "decision": "confirm"})
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(self.repository.appointments("developer")), 1)

    async def test_reschedule_confirmation_accepts_explicit_answer_after_intermediate_vad_turn(self):
        response = await self.speech("booking-input")
        proposal = await self.tool(response, "prepare-booking", "create_appointment", {
            "start_at": "2026-10-19T10:00:00+00:00", "reason": "Revisión general", "patient_name": "Asael Ponce"})
        await self.audio(self.session._active_response, "booking-question", proposal["confirmation_prompt"], drained=True)
        response = await self.speech("booking-confirmation")
        created = await self.tool(response, "confirm-booking", "confirm_appointment_action", {
            "action_id": proposal["action_id"], "decision": "confirm"})
        self.assertTrue(created["ok"], created)
        appointment_id = self.repository.appointments("developer")[0]["id"]

        response = await self.speech("reschedule-request")
        move = await self.tool(response, "prepare-reschedule", "reschedule_appointment", {
            "appointment_id": appointment_id, "new_start_at": "2026-10-19T11:00:00+00:00"})
        self.assertEqual(move["status"], "confirmation_required")
        await self.audio(self.session._active_response, "reschedule-question", move["confirmation_prompt"], drained=True)

        # Realtime can split one spoken affirmation into multiple VAD turns and
        # cancel the intermediate response before it produces any useful answer.
        await self.speech("intermediate-vad-turn")
        response = await self.speech("reschedule-confirmation")
        confirmation = asyncio.create_task(self.tool(response, "confirm-reschedule", "confirm_appointment_action", {
            "action_id": move["action_id"], "decision": "confirm"}))
        await asyncio.sleep(.05)
        self.assertFalse(confirmation.done(), "espera la transcripcion del turno de voz vigente")
        await self.provider.events.put({
            "type": "conversation.item.input_audio_transcription.completed",
            "item_id": "reschedule-confirmation",
            "transcript": "Sí, confirmo",
            "usage": {"total_tokens": 2},
        })
        result = await confirmation

        self.assertTrue(result["ok"], result)
        self.assertNotEqual(result.get("status"), "confirmation_required", result)
        self.assertEqual(self.repository.appointments("developer")[0]["start_at"], "2026-10-19T11:00:00+00:00")

    async def test_shutdown_closes_both_transports_and_failure_contains_only_safe_type(self):
        await self.provider.events.put({"type": "error", "error": {"code": "invalid_api_key", "message": "secret provider body"}})
        await self.wait(lambda: self.session.metrics["voice_failure_type"] is not None)
        self.assertNotIn("secret", json.dumps(self.session.metrics))
        await self.session.close()
        self.assertTrue(self.media.closed and self.provider.closed)
        with self.repository.connection() as db:
            self.assertEqual(db.execute("SELECT state FROM voice_sessions").fetchone()[0], "ended")

    async def test_idle_timeout_is_speech_based_not_continuous_silent_rtp(self):
        self.session._active_response = None
        self.session._requesting = False
        self.session._last_activity = 0
        self.media.last_received_at = asyncio.get_running_loop().time()
        async with asyncio.timeout(2):
            while await self.session.events.get() != "disconnected":
                pass

    async def test_idle_timeout_is_suspended_during_speech_and_playback(self):
        self.session._active_response = None
        self.session._speaking = True
        self.session._last_activity = 0
        await asyncio.sleep(.35)
        self.assertNotEqual(self.session._reason, "voice_idle_timeout")
        self.session._speaking = False
        self.session._item("playing", self.provider.responses[0]["id"])["started"] = True
        self.session._last_activity = 0
        await asyncio.sleep(.35)
        self.assertNotEqual(self.session._reason, "voice_idle_timeout")

    async def test_close_retries_durable_finish_after_voice_database_writer_releases(self):
        with closing(sqlite3.connect(self.repository.path)) as writer:
            writer.execute("BEGIN IMMEDIATE")
            with self.assertRaises(CallMediaPersistenceError) as failure:
                await self.session.close()
            self.assertTrue(failure.exception.resources_released)
            self.assertTrue(self.media.closed and self.provider.closed)
        await self.session.close()
        self.assertEqual(self.media.close_count, 1)
        self.assertEqual(self.provider.close_count, 1)
        with self.repository.connection() as db:
            self.assertEqual(db.execute("SELECT state FROM voice_sessions").fetchone()[0], "ended")

    async def test_close_drains_late_transcript_without_executing_tools(self):
        await self.speech("late-input")
        closing_task = asyncio.create_task(self.session.close())
        await self.wait(lambda: self.media.closed)
        await self.provider.events.put({"type": "conversation.item.input_audio_transcription.completed",
            "item_id": "late-input", "transcript": "Quiero cambiar la cita", "usage": {"total_tokens": 8}})
        await closing_task
        history = self.repository.history("developer")
        self.assertEqual(history[-1]["content"][0]["text"], "Quiero cambiar la cita")
        self.assertFalse(self.session._calls)

    async def test_usage_preserves_modalities_cache_and_model_without_counting_duplicates(self):
        response_id = self.session._active_response
        usage = {"input_tokens": 100, "output_tokens": 30,
            "input_token_details": {"audio_tokens": 70, "text_tokens": 30, "cached_tokens": 20,
                                    "cached_tokens_details": {"text_tokens": 20, "audio_tokens": 0}},
            "output_token_details": {"audio_tokens": 25, "text_tokens": 5}, "private_body": "not-for-storage"}
        event = {"type": "response.done", "response": {"id": response_id, "status": "completed", "output": [], "usage": usage}}
        await self.provider.events.put(event)
        await self.provider.events.put(event)
        await self.wait(lambda: self.session.metrics["voice_usage"]["input_tokens"] == 100)
        recorded = self.session.metrics["voice_usage"]["responses"]
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["model"], self.session.settings.model)
        self.assertEqual(recorded[0]["usage"]["input_token_details"]["cached_tokens"], 20)
        self.assertNotIn("not-for-storage", json.dumps(recorded))

    async def test_duplicate_vad_and_audio_events_preserve_one_turn_one_chunk_and_first_emission(self):
        started = {"event_id": "vad-start", "type": "input_audio_buffer.speech_started", "item_id": "input"}
        stopped = {"event_id": "vad-stop", "type": "input_audio_buffer.speech_stopped", "item_id": "input"}
        committed = {"event_id": "commit", "type": "input_audio_buffer.committed", "item_id": "input"}
        for event in (started, started, stopped, stopped, committed, committed):
            await self.provider.events.put(event)
        await self.wait(lambda: self.session.current_turn == 1 and self.session._active_response is not None
                        and self.session._responses[self.session._active_response]["turn"] == 1)
        response = self.session._active_response
        chunk = {"event_id": "audio", "type": "response.output_audio.delta", "response_id": response,
                 "item_id": "answer", "delta": base64.b64encode(b"\1\0" * 480).decode()}
        await self.provider.events.put(chunk)
        await self.provider.events.put(chunk)
        await self.wait(lambda: "answer" in self.session._items)
        await self.media.output_started.put(("answer", asyncio.get_running_loop().time()))
        await self.wait(lambda: self.session.metrics["voice_performance"]["turns"][0]["first_audio_emitted_ms"] is not None)
        self.assertEqual(self.session._generation, 1)
        self.assertEqual(self.session.current_turn, 1)
        self.assertEqual(self.session._items["answer"]["generated_ms"], 20)
        self.assertEqual(len(self.media.audio), 1)
        performance = self.session.metrics["voice_performance"]
        self.assertEqual(performance["without_tools"]["first_audio_received_ms"]["samples"], 1)
        self.assertGreaterEqual(performance["turns"][0]["first_audio_emitted_ms"], performance["turns"][0]["first_audio_received_ms"])

    async def test_close_before_response_ack_keeps_unreported_cost_unknown(self):
        response_id = self.session._active_response
        await self.session._handle({"type": "response.done", "response": {"id": response_id, "status": "completed", "output": [],
            "usage": {"input_tokens": 0, "output_tokens": 0,
                "input_token_details": {"audio_tokens": 0, "text_tokens": 0, "cached_tokens": 0},
                "output_token_details": {"audio_tokens": 0, "text_tokens": 0}}}})
        self.assertTrue(self.session.metrics["voice_cost"]["complete"])

        async def without_ack(event):
            self.provider.commands.append(event)

        self.provider.send = without_ack
        self.session._pending_reply = (0, self.session._generation)
        await self.session._maybe_respond()
        await self.session.close()
        cost = self.session.metrics["voice_cost"]
        self.assertFalse(cost["complete"])
        self.assertIsNone(cost["total_usd"])
        self.assertEqual(cost["unpriced_records"], 1)

    async def test_commit_latency_fallback_includes_cancel_network_wait(self):
        now = [10.0]
        self.session._performance.clock = lambda: now[0]
        original = self.provider.send

        async def slow_cancel(event):
            if event["type"] == "response.cancel":
                now[0] = 10.75
            await original(event)

        self.provider.send = slow_cancel
        await self.provider.events.put({"type": "input_audio_buffer.committed", "item_id": "without-vad"})
        await self.wait(lambda: self.session.current_turn == 1 and self.session._active_response is not None
                        and self.session._responses[self.session._active_response]["turn"] == 1)
        now[0] = 11.0
        await self.audio(self.session._active_response, "answer-without-vad", drained=True)
        measurement = self.session.metrics["voice_performance"]["turns"][0]
        self.assertEqual(measurement["reference"], "committed_received")
        self.assertEqual(measurement["first_audio_received_ms"], 1000)
