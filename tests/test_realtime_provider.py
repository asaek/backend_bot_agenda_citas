import asyncio
import base64
import importlib.util
import json
import unittest

from openai_realtime_provider import OpenAIRealtimeProvider, RealtimeError, RealtimeSettings, greeting_response


@unittest.skipUnless(importlib.util.find_spec("websockets"), "Instalar el extra voice")
class RealtimeWebSocketTests(unittest.IsolatedAsyncioTestCase):
    async def test_ga_handshake_audio_and_tools_cross_a_real_local_websocket(self):
        from websockets.asyncio.client import connect
        from websockets.asyncio.server import serve

        received = []
        finished = asyncio.Event()

        async def server(socket):
            await socket.send(json.dumps({"type": "session.created"}))
            received.append(json.loads(await socket.recv()))
            await socket.send(json.dumps({"type": "session.updated"}))
            received.append(json.loads(await socket.recv()))
            await socket.send(json.dumps({"type": "response.output_audio.delta", "delta": base64.b64encode(b"\0\1" * 480).decode()}))
            received.append(json.loads(await socket.recv()))
            finished.set()
            await socket.wait_closed()

        async with serve(server, "127.0.0.1", 0) as listener:
            port = listener.sockets[0].getsockname()[1]

            async def connector(uri, **kwargs):
                self.assertTrue(uri.startswith("wss://api.openai.com/v1/realtime?model="))
                self.assertNotIn("OpenAI-Beta", kwargs["additional_headers"])
                return await connect(f"ws://127.0.0.1:{port}", **kwargs)

            settings = RealtimeSettings(api_key="dummy-private-test-key")
            self.assertNotIn(settings.api_key, repr(settings))
            provider = OpenAIRealtimeProvider(settings, connector=connector)
            try:
                await provider.connect("Español", [{"type": "function", "name": "example"}], [])
                await provider.send_audio(b"\x01\x02" * 480)
                event = await provider.receive()
                self.assertEqual(len(base64.b64decode(event["delta"])), 960)
                await provider.send({"type": "conversation.item.create", "item": {"type": "function_call_output", "call_id": "tool-1", "output": "{}"}})
                await asyncio.wait_for(finished.wait(), 2)
            finally:
                await provider.close()
                await provider.close()
        session = received[0]["session"]
        self.assertEqual(session["audio"]["input"]["format"], {"type": "audio/pcm", "rate": 24000})
        self.assertFalse(session["audio"]["input"]["turn_detection"]["create_response"])
        self.assertEqual(session["audio"]["input"]["transcription"]["language"], "es")
        self.assertEqual(base64.b64decode(received[1]["audio"]), b"\x01\x02" * 480)
        self.assertEqual(received[2]["item"]["call_id"], "tool-1")

    async def test_greeting_has_empty_input_while_history_and_current_input_stay_in_default_conversation(self):
        from websockets.asyncio.client import connect
        from websockets.asyncio.server import serve

        received = []
        finished = asyncio.Event()
        history = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Sí, confirmo."}]},
                   {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Cita confirmada."}]}]

        async def server(socket):
            await socket.send(json.dumps({"type": "session.created"}))
            received.append(json.loads(await socket.recv()))
            await socket.send(json.dumps({"type": "session.updated"}))
            for _ in range(5):
                received.append(json.loads(await socket.recv()))
            finished.set()
            await socket.wait_closed()

        async with serve(server, "127.0.0.1", 0) as listener:
            port = listener.sockets[0].getsockname()[1]

            async def connector(uri, **kwargs):
                return await connect(f"ws://127.0.0.1:{port}", **kwargs)

            provider = OpenAIRealtimeProvider(RealtimeSettings(api_key="test-only"), connector=connector)
            try:
                await provider.connect("Atiende el turno actual.", [{"type": "function", "name": "example"}], history)
                await provider.send({"type": "response.create", "response": greeting_response({"voice_turn": "0"})})
                await provider.send({"type": "conversation.item.create", "item": {
                    "type": "message", "role": "user", "content": [{"type": "input_text", "text": "Quiero consultar mi cita."}],
                }})
                await provider.send({"type": "response.create", "response": {"metadata": {"voice_turn": "1"}}})
                await asyncio.wait_for(finished.wait(), 2)
            finally:
                await provider.close()
        self.assertEqual([event["item"] for event in received[1:3]], history)
        greeting = received[3]["response"]
        self.assertEqual(greeting["conversation"], "none")
        self.assertEqual(greeting["input"], [])
        self.assertEqual(greeting["tools"], [])
        self.assertEqual(greeting["tool_choice"], "none")
        self.assertEqual(received[4]["item"]["role"], "user")
        self.assertNotIn("input", received[5]["response"])
        self.assertNotIn("conversation", received[5]["response"])
        self.assertEqual(received[0]["session"]["tool_choice"], "auto")

    async def test_rejected_handshake_closes_socket_and_sanitizes_error(self):
        class Socket:
            closed = False

            async def recv(self):
                return json.dumps({"type": "error", "error": {"message": "a provider body with sensitive material"}})

            async def close(self):
                self.closed = True

        socket = Socket()

        async def connector(*args, **kwargs):
            return socket

        provider = OpenAIRealtimeProvider(RealtimeSettings(api_key="test-private-key"), connector=connector)
        with self.assertRaisesRegex(RealtimeError, "No se pudo iniciar") as failure:
            await provider.connect("instructions", [], [])
        self.assertTrue(socket.closed)
        self.assertNotIn("sensitive", str(failure.exception))


class RealtimeConfigurationTests(unittest.TestCase):
    def test_credentials_are_explicit_and_text_provider_generic_key_is_not_reused(self):
        with self.assertRaises(ValueError):
            RealtimeSettings.from_environment({"LLM_API_KEY": "text-provider-key"})
        settings = RealtimeSettings.from_environment({"OPENAI_API_KEY": "dedicated-openai-key"})
        self.assertEqual(settings.model, "gpt-realtime-2.1")
        self.assertEqual(settings.maximum_seconds, 300)
        configured = RealtimeSettings.from_environment({
            "OPENAI_API_KEY": "test-key", "VOICE_MAXIMUM_SECONDS": "300",
        })
        self.assertEqual(configured.maximum_seconds, 300)
        self.assertEqual(configured.maximum_sessions, 5)
        unlimited = RealtimeSettings.from_environment({
            "OPENAI_API_KEY": "test-key", "VOICE_MAX_SESSIONS": "unlimited",
        })
        self.assertIsNone(unlimited.maximum_sessions)
        for value in ("nan", "inf", "0", "601"):
            with self.assertRaises(ValueError):
                RealtimeSettings.from_environment({"OPENAI_API_KEY": "test-key", "VOICE_MAXIMUM_SECONDS": value})
        for value in ("0", "101", "many"):
            with self.assertRaises(ValueError):
                RealtimeSettings.from_environment({"OPENAI_API_KEY": "test-key", "VOICE_MAX_SESSIONS": value})
