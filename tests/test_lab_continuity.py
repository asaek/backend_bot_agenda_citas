import asyncio
import base64
import json
import tempfile
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from calling_repository import CallingRepository
from main import app, create_lab_app
from openai_realtime_provider import RealtimeSettings
import test_voice_session as voice_session_fixtures
from voice_fakes import FakeRealtimeProvider, FakeVoiceMedia


class RespondingTextProvider(FakeRealtimeProvider):
    async def send(self, event):
        await super().send(event)
        if event["type"] == "response.create" and event["response"].get("output_modalities") == ["text"]:
            response = self.responses[-1]
            item_id = "answer-" + str(len(self.responses))
            await self.events.put({"type": "response.output_text.done", "response_id": response["id"],
                                   "item_id": item_id, "text": "Respuesta del mismo paciente ficticio"})
            await self.events.put({"type": "response.done", "response": {
                "id": response["id"], "status": "completed", "output": [{"type": "message", "id": item_id}],
            }})


class LaboratoryTextAPITests(unittest.TestCase):
    def make_lab(self, directory, providers):
        def factory():
            provider = RespondingTextProvider()
            providers.append(provider)
            return provider

        return create_lab_app(enabled=True, audio_mode="realtime",
            repository=CallingRepository(Path(directory) / "calls.sqlite3"), voice_database_path=Path(directory) / "voice.sqlite3",
            media_factory=FakeVoiceMedia, realtime_provider_factory=factory,
            voice_settings=RealtimeSettings(api_key="test-only", maximum_sessions=10))

    def test_text_is_token_free_idempotent_and_history_is_not_a_whatsapp_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            providers = []
            with TestClient(self.make_lab(directory, providers)) as client:
                self.assertEqual(client.app.state.calling_service.maximum_seconds, 300)
                payload = {"message_id": "message-1", "text": "Hola"}
                self.assertEqual(client.get("/lab/history").status_code, 200)
                first = client.post("/lab/messages", json=payload)
                self.assertEqual(first.status_code, 200, first.text)
                self.assertEqual(first.json()["state"], "completed")
                self.assertEqual(client.post("/lab/messages", json=payload).json(), first.json())
                self.assertEqual(len(providers), 1)
                self.assertEqual(len(providers[0].responses), 1)
                self.assertEqual(client.post("/lab/messages", json={**payload, "text": "Otro texto"}).status_code, 409)
                self.assertEqual(client.post("/lab/messages", json={**payload, "patient_id": 2}).status_code, 400)
                history = client.get("/lab/history").json()["history"]
                self.assertEqual([item["channel"] for item in history], ["text", "text"])
                self.assertEqual([item["role"] for item in history], ["user", "assistant"])
                self.assertEqual(history[-1]["generation_state"], "completed")
                self.assertEqual(history[-1]["emitted_ms"], 0)
            self.assertTrue(providers[0].closed)
        with TestClient(app) as client:
            self.assertEqual(client.post("/lab/messages", json={}).status_code, 404)
            self.assertEqual(client.get("/lab/history").status_code, 404)

    def test_text_to_voice_closes_old_provider_and_loads_shared_history(self):
        with tempfile.TemporaryDirectory() as directory:
            providers = []
            with TestClient(self.make_lab(directory, providers)) as client:
                sent = client.post("/lab/messages", json={"message_id": "first", "text": "Mi nombre es Asael Ponce"})
                self.assertEqual(sent.status_code, 200)
                voice = client.post("/lab/calls", json={"type": "offer", "sdp": "offer"})
                self.assertEqual(voice.status_code, 201, voice.text)
                self.assertTrue(providers[0].closed)
                self.assertEqual(len(providers), 2)
                self.assertIn("Asael Ponce", json.dumps(providers[1].history))
                during = client.post("/lab/messages", json={"message_id": "during", "text": "¿Recuerdas mi nombre?"})
                self.assertEqual(during.status_code, 200, during.text)
                self.assertEqual(len(providers), 2)
                self.assertEqual(client.delete("/lab/calls/" + voice.json()["session_id"]).status_code, 200)

    def test_result_persistence_retry_returns_original_reply_without_second_model_call(self):
        with tempfile.TemporaryDirectory() as directory:
            providers = []
            lab = self.make_lab(directory, providers)
            with TestClient(lab) as client:
                repository = lab.state.voice_repository
                original = repository.finish_text
                failed = False

                def fail_once(*args):
                    nonlocal failed
                    if not failed:
                        failed = True
                        raise sqlite3.OperationalError("test writer unavailable")
                    return original(*args)

                payload = {"message_id": "persist-retry", "text": "Un mensaje"}
                with patch.object(repository, "finish_text", side_effect=fail_once):
                    self.assertEqual(client.post("/lab/messages", json=payload).status_code, 503)
                    retried = client.post("/lab/messages", json=payload)
                self.assertEqual(retried.status_code, 200, retried.text)
                self.assertEqual(retried.json()["state"], "completed")
                self.assertEqual(len(providers), 1)
                self.assertEqual(len(providers[0].responses), 1)
                self.assertFalse(lab.state.pending_text_results)


class VoiceAndTextSessionTests(unittest.IsolatedAsyncioTestCase):
    """Casos de continuidad; se reutilizan las fixtures de transportes existentes."""

    asyncSetUp = voice_session_fixtures.VoiceSessionTests.asyncSetUp
    wait = voice_session_fixtures.VoiceSessionTests.wait
    speech = voice_session_fixtures.VoiceSessionTests.speech
    audio = voice_session_fixtures.VoiceSessionTests.audio
    tool = voice_session_fixtures.VoiceSessionTests.tool

    async def text_turn(self, text):
        previous = len(self.provider.responses)
        task = asyncio.create_task(self.session.submit_text(text))
        await self.wait(lambda: len(self.provider.responses) > previous and self.session._active_response is not None and
                        self.session._responses[self.session._active_response]["channel"] == "text")
        return task, self.session._active_response

    async def finish_text(self, task, text):
        response_id = self.session._active_response
        await self.provider.events.put({"type": "response.output_text.done", "response_id": response_id,
                                       "item_id": "text-answer-" + response_id, "text": text})
        await self.provider.events.put({"type": "response.done", "response": {
            "id": response_id, "status": "completed", "output": [{"type": "message"}],
        }})
        result = await asyncio.wait_for(task, 3)
        await self.session.publish_text(result["turn_id"])
        return result

    async def prepare_voice_question(self):
        response = await self.speech("booking-input")
        proposal = await self.tool(response, "prepare", "create_appointment", {
            "start_at": "2026-10-19T10:00:00+00:00", "reason": "Revisión general", "patient_name": "Asael Ponce"})
        await self.audio(self.session._active_response, "voice-question", proposal["confirmation_prompt"], drained=True)
        return proposal

    async def test_written_yes_does_not_consume_voice_authorization_or_its_channel_sequence(self):
        proposal = await self.prepare_voice_question()
        text_task, response = await self.text_turn("Sí")
        result = await self.tool(response, "wrong-channel", "confirm_appointment_action", {
            "action_id": proposal["action_id"], "decision": "confirm"})
        self.assertFalse(result["ok"])
        self.assertTrue(self.session.tools.pending["armed"])
        self.assertEqual(len(self.repository.appointments("developer")), 0)
        await self.finish_text(text_task, "La pregunta pertenece a la llamada; retoma para continuar por texto.")
        voice = await self.speech("spoken-yes")
        confirmed = await self.tool(voice, "right-channel", "confirm_appointment_action", {
            "action_id": proposal["action_id"], "decision": "confirm"})
        self.assertTrue(confirmed["ok"], confirmed)

    async def test_resume_in_text_creates_a_new_question_and_new_authorization(self):
        proposal = await self.prepare_voice_question()
        text_task, response = await self.text_turn("Retomemos la cita")
        renewed = await self.tool(response, "resume", "manage_appointment_workflow", {"mode": "resume"})
        self.assertTrue(renewed["ok"], renewed)
        self.assertNotEqual(renewed["action_id"], proposal["action_id"])
        await self.finish_text(text_task, renewed["confirmation_prompt"])
        self.assertEqual(self.session.tools.pending["channel"], "text")
        self.assertTrue(self.session.tools.pending["armed"])
        next_task, response = await self.text_turn("Sí, por favor")
        confirmed = await self.tool(response, "text-confirm", "confirm_appointment_action", {
            "action_id": renewed["action_id"], "decision": "confirm"})
        self.assertTrue(confirmed["ok"], confirmed)
        await self.finish_text(next_task, "La herramienta confirmó la cita.")
        self.assertEqual(len(self.repository.appointments("developer")), 1)

    async def test_text_backend_rejects_model_confirmation_that_contradicts_actual_text(self):
        await self.prepare_voice_question()
        task, response = await self.text_turn("Retomemos la cita")
        renewed = await self.tool(response, "resume", "manage_appointment_workflow", {"mode": "resume"})
        await self.finish_text(task, renewed["confirmation_prompt"])
        task, response = await self.text_turn("Sí, pero mejor a las once")
        result = await self.tool(response, "contradiction", "confirm_appointment_action", {
            "action_id": renewed["action_id"], "decision": "confirm"})
        self.assertFalse(result["ok"])
        self.assertFalse(self.repository.appointments("developer"))
        await self.finish_text(task, "Indica el nuevo horario para preparar otra propuesta.")

    async def test_pcm_chunks_can_split_a_sample_but_late_chunks_cannot_resurrect_it(self):
        response = self.session._active_response
        for chunk in (b"\x01", b"\x00\x02\x00"):
            await self.provider.events.put({"type": "response.output_audio.delta", "response_id": response,
                "item_id": "split", "delta": base64.b64encode(chunk).decode()})
        await self.wait(lambda: bool(self.media.audio))
        self.assertEqual(self.media.audio[-1][1], b"\x01\x00\x02\x00")
        await self.speech("interrupt-split")
        self.assertFalse(self.media.audio)

    async def test_text_waiting_to_cancel_cannot_overwrite_newer_voice_input(self):
        original_send = self.provider.send
        entered, release = asyncio.Event(), asyncio.Event()
        blocked_once = False

        async def delayed_send(event):
            nonlocal blocked_once
            if event["type"] == "response.cancel" and not blocked_once:
                blocked_once = True
                entered.set()
                await release.wait()
            await original_send(event)

        self.provider.send = delayed_send
        text_task = asyncio.create_task(self.session.submit_text("Texto obsoleto"))
        await asyncio.wait_for(entered.wait(), 2)
        try:
            await self.speech("newer-voice")
        finally:
            release.set()
        result = await asyncio.wait_for(text_task, 3)
        self.assertEqual(result["state"], "interrupted")
        self.assertEqual(self.session.metrics["voice_turn_count"], 1)
        self.assertEqual(self.session.metrics["text_turn_count"], 0)

    async def test_generated_text_question_is_not_authorized_until_published(self):
        await self.prepare_voice_question()
        task, response = await self.text_turn("Retomemos la cita")
        renewed = await self.tool(response, "resume-unpublished", "manage_appointment_workflow", {"mode": "resume"})
        response = self.session._active_response
        await self.provider.events.put({"type": "response.output_text.done", "response_id": response,
            "item_id": "unpublished-question", "text": renewed["confirmation_prompt"]})
        await self.wait(lambda: self.session.tools.pending and self.session.tools.pending["item_id"] == "unpublished-question")
        self.assertFalse(self.session.tools.pending["armed"])
        await self.speech("interrupt-before-publication")
        self.assertEqual((await task)["state"], "interrupted")
        self.assertIsNone(self.session.tools.pending)
        self.assertFalse(self.repository.appointments("developer"))

    async def test_hangup_keeps_partial_audio_progress_and_unknown_generation_explicit(self):
        response = self.session._active_response
        await self.provider.events.put({"type": "response.output_audio.delta", "response_id": response,
            "item_id": "partial-on-close", "delta": base64.b64encode(b"\1\0" * 4800).decode()})
        await self.wait(lambda: bool(self.media.audio))
        self.media.emitted_ms["partial-on-close"] = 80
        await self.session.close()
        row = next(item for item in self.repository.turns("session") if item["item_id"] == "partial-on-close")
        self.assertEqual(row["generated_ms"], 200)
        self.assertEqual(row["emitted_ms"], 80)
        self.assertEqual(row["state"], "interrupted")
        self.assertEqual(row["generation_state"], "unknown")

    async def test_cancel_request_does_not_override_later_definitive_generation_result(self):
        response = self.session._active_response
        await self.provider.events.put({"type": "response.output_audio.delta", "response_id": response,
            "item_id": "finished-at-provider", "delta": base64.b64encode(b"\1\0" * 480).decode()})
        await self.wait(lambda: bool(self.media.audio))
        original_send = self.provider.send

        async def cancel_without_ack(event):
            if event["type"] == "response.cancel":
                self.provider.commands.append(event)
            else:
                await original_send(event)

        self.provider.send = cancel_without_ack
        speech_task = asyncio.create_task(self.speech("next-input"))
        await self.wait(lambda: self.session._items["finished-at-provider"]["interrupted"])
        await self.provider.events.put({"type": "response.done", "response": {"id": response, "status": "completed", "output": []}})
        await speech_task
        row = next(item for item in self.repository.turns("session") if item["item_id"] == "finished-at-provider")
        self.assertEqual(row["generation_state"], "completed")
        self.assertEqual(row["state"], "interrupted")
