import asyncio
import base64
import json
import tempfile
import unittest
from datetime import time
from pathlib import Path

from openai_realtime_provider import RealtimeSettings
from tool_validation import BusinessHours, TimeWindow
from voice_repository import VoiceRepository
from voice_session import VoiceSession
from voice_fakes import FakeRealtimeProvider, FakeVoiceMedia


class VoiceGreetingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.repository = VoiceRepository(Path(directory) / "voice.sqlite3")
        self.repository.start()
        self.addCleanup(self.repository.close)
        self.repository.begin("previous-voice", "developer", 10)
        self.repository.turn("previous-voice", "question", "assistant", "¿Confirmas la cita?", "completed")
        self.repository.turn("previous-voice", "yes", "user", "Sí, confirmo.", "completed")
        self.repository.finish("previous-voice", "hangup", {})
        self.repository.begin("previous-text", "developer", 10)
        self.repository.turn("previous-text", "topic", "user", "Quiero hablar de mis estudios.", "completed", "text")
        self.repository.finish("previous-text", "hangup", {})
        self.history = self.repository.history("developer")
        self.media, self.provider = FakeVoiceMedia(), FakeRealtimeProvider()
        self.session = VoiceSession(
            session_id="new-call", media=self.media, provider=self.provider,
            repository=self.repository, settings=RealtimeSettings(api_key="test-only", maximum_sessions=10),
            business_hours=BusinessHours("UTC", {day: (TimeWindow(time(9), time(17)),) for day in range(5)}),
        )
        self.addAsyncCleanup(self.session.close)
        await self.session.negotiate("offer")

    async def wait(self, predicate):
        async with asyncio.timeout(3):
            while not predicate():
                await asyncio.sleep(.005)

    def requests(self):
        return [event["response"] for event in self.provider.commands if event["type"] == "response.create"]

    async def connect_call(self):
        await self.media.events.put("connected")
        await self.wait(lambda: len(self.provider.responses) == 1)
        return self.provider.responses[0]["id"]

    async def speech(self, item_id="current-input"):
        await self.provider.events.put({"type": "input_audio_buffer.speech_started"})
        await self.provider.events.put({"type": "input_audio_buffer.committed", "item_id": item_id})
        await self.provider.events.put({
            "type": "conversation.item.input_audio_transcription.completed", "item_id": item_id,
            "transcript": "Quiero continuar hablando de mis estudios.",
        })

    async def test_new_call_greeting_excludes_history_but_next_voice_response_uses_it(self):
        response_id = await self.connect_call()
        self.assertEqual(self.provider.history, self.history, "la memoria se prepara al conectar")
        greeting = self.requests()[0]
        self.assertEqual(greeting.get("conversation"), "none")
        self.assertEqual(greeting.get("input"), [])
        self.assertEqual(greeting.get("tools"), [])
        self.assertEqual(greeting.get("tool_choice"), "none")
        self.assertIn("asistente virtual", greeting["instructions"])
        self.assertNotIn("Sí, confirmo", greeting["instructions"])

        for event in (
            {"type": "response.output_audio.delta", "delta": base64.b64encode(b"\1\0" * 480).decode()},
            {"type": "response.output_audio_transcript.done", "transcript": "Hola, soy el asistente virtual."},
            {"type": "response.output_audio.done"},
        ):
            await self.provider.events.put({**event, "response_id": response_id, "item_id": "greeting"})
        await self.provider.events.put({"type": "response.done", "response": {
            "id": response_id, "status": "completed", "output": [{"type": "message"}],
        }})
        await self.media.output_events.put(("greeting", 20))
        await self.wait(lambda: self.session.metrics["voice_state"] == "listening")
        await self.speech()
        await self.wait(lambda: len(self.requests()) == 2)
        continuation = self.requests()[1]
        self.assertNotIn("input", continuation, "el turno actual usa la conversacion con memoria")
        self.assertNotEqual(continuation.get("conversation"), "none")
        self.assertNotEqual(continuation.get("tool_choice"), "none")
        self.assertEqual(self.provider.history, self.history)
        self.assertEqual(self.session.metrics["turn_count"], 1)
        self.assertFalse(self.session.metrics["confirmation_pending"])
        self.assertFalse(self.repository.appointments("developer"))

    async def test_interrupting_greeting_cancels_audio_without_editing_conversation_items(self):
        response_id = await self.connect_call()
        audio = {"type": "response.output_audio.delta", "response_id": response_id,
                 "item_id": "greeting", "delta": base64.b64encode(b"\1\0" * 480).decode()}
        await self.provider.events.put(audio)
        await self.wait(lambda: bool(self.media.audio))
        self.media.emitted_ms["greeting"] = 10
        await self.speech()
        await self.wait(lambda: len(self.requests()) == 2)
        self.assertFalse(self.media.audio)
        self.assertTrue(any(event["type"] == "response.cancel" and event["response_id"] == response_id
                            for event in self.provider.commands))
        edits = [event for event in self.provider.commands
                 if event["type"] in {"conversation.item.truncate", "conversation.item.delete"}]
        self.assertEqual(edits, [], "el saludo fuera de banda no tiene items en la conversacion")
        self.assertEqual(self.requests()[1]["metadata"]["voice_turn"], "1")
        self.assertEqual(self.provider.history, self.history)

        await self.provider.events.put(audio)
        await self.provider.events.put({"type": "response.output_audio_transcript.done", "response_id": response_id,
                                        "item_id": "greeting", "transcript": "Saludo tardio"})
        await self.media.events.put("connected")
        await self.wait(lambda: self.provider.events.empty() and self.media.events.empty())
        self.assertFalse(self.media.audio)
        self.assertEqual(len(self.requests()), 2)
        turns = self.repository.turns("new-call")
        greeting = next(item for item in turns if item["item_id"] == "greeting")
        self.assertEqual(greeting["state"], "interrupted")
        self.assertEqual(greeting["emitted_ms"], 10)
        self.assertNotIn("Saludo tardio", str(turns))

    async def test_greeting_cannot_dispatch_tools_even_if_provider_emits_a_call(self):
        response_id = await self.connect_call()
        await self.provider.events.put({
            "type": "response.function_call_arguments.done", "response_id": response_id,
            "call_id": "unexpected-greeting-tool", "name": "confirm_appointment_action",
            "arguments": json.dumps({"action_id": "previous-action", "decision": "confirm"}),
        })
        await self.speech()
        await self.wait(lambda: self.session.metrics["turn_count"] == 1 and len(self.requests()) >= 2)
        self.assertEqual(self.session.metrics["voice_tool_calls"], 0)
        self.assertFalse(any(event["type"] == "conversation.item.create"
                             and event["item"].get("type") == "function_call_output"
                             for event in self.provider.commands))
        self.assertFalse(self.repository.appointments("developer"))

    async def test_speech_before_greeting_ack_cancels_late_response_and_keeps_current_turn(self):
        original_send = self.provider.send

        async def delayed_greeting_ack(event):
            if event["type"] == "response.create" and not self.provider.responses:
                self.provider.commands.append(event)
                self.provider.responses.append({"id": "response-1", "metadata": event["response"]["metadata"]})
            else:
                await original_send(event)

        self.provider.send = delayed_greeting_ack
        response_id = await self.connect_call()
        await self.speech()
        await self.wait(lambda: self.session.metrics["turn_count"] == 1)
        self.assertEqual(len(self.requests()), 1, "espera el ACK para cancelar por ID")
        await self.provider.events.put({"type": "response.created", "response": self.provider.responses[0]})
        await self.wait(lambda: len(self.requests()) == 2)
        self.assertTrue(any(event["type"] == "response.cancel" and event["response_id"] == response_id
                            for event in self.provider.commands))
        self.assertEqual(self.requests()[1]["metadata"]["voice_turn"], "1")
        self.assertNotEqual(self.requests()[1].get("conversation"), "none")
        self.assertEqual(self.provider.history, self.history)
        self.assertIsNone(self.session.metrics["voice_failure_code"])

    async def test_patient_speaking_before_connected_does_not_get_a_delayed_greeting(self):
        await self.speech()
        await self.wait(lambda: len(self.requests()) == 1)
        await self.media.events.put("connected")
        await self.wait(lambda: self.media.events.empty())
        self.assertEqual(len(self.requests()), 1)
        self.assertEqual(self.requests()[0]["metadata"]["voice_turn"], "1")
        self.assertNotEqual(self.requests()[0].get("conversation"), "none")
        self.assertEqual(self.provider.history, self.history)

    async def test_text_interrupts_greeting_and_uses_the_shared_conversation(self):
        response_id = await self.connect_call()
        message = asyncio.create_task(self.session.submit_text("¿Que comente sobre mis estudios?"))
        self.addAsyncCleanup(self.cancel_task, message)
        await self.wait(lambda: len(self.requests()) == 2)
        response = self.provider.responses[-1]
        request = self.requests()[-1]
        self.assertEqual(request["output_modalities"], ["text"])
        self.assertNotIn("input", request)
        self.assertNotEqual(request.get("tool_choice"), "none")
        self.assertEqual(self.provider.history, self.history)
        self.assertTrue(any(event["type"] == "response.cancel" and event["response_id"] == response_id
                            for event in self.provider.commands))
        await self.provider.events.put({"type": "response.output_text.done", "response_id": response["id"],
                                        "item_id": "text-reply", "text": "Comentaste que querias hablar de tus estudios."})
        await self.provider.events.put({"type": "response.done", "response": {
            **response, "status": "completed", "output": [{"type": "message"}],
        }})
        result = await asyncio.wait_for(message, 3)
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["reply"], "Comentaste que querias hablar de tus estudios.")
        self.assertFalse(self.session.metrics["confirmation_pending"])

    async def cancel_task(self, task):
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
