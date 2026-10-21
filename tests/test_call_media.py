"""Integracion opcional: API de laboratorio y RTP/Opus reales, sin APIs externas."""

import asyncio
import importlib.util
import math
import tempfile
import unittest
import wave
from pathlib import Path

import httpx

from calling_repository import CallingRepository
from main import create_lab_app


HAS_AUDIO = all(importlib.util.find_spec(name) is not None for name in ("aiortc", "av", "numpy"))


@unittest.skipUnless(HAS_AUDIO, "Instalar el extra audio para verificar RTP/Opus")
class RealLaboratoryAudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_realtime_bridge_transcodes_opus_to_pcm24k_and_model_pcm_back_to_rtp(self):
        import base64
        import numpy as np
        from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
        from aiortc.mediastreams import MediaStreamError
        from openai_realtime_provider import RealtimeSettings
        from scripts.probe_aiortc import ToneTrack
        from voice_fakes import FakeRealtimeProvider

        directory = self.enterContext(tempfile.TemporaryDirectory())
        provider = FakeRealtimeProvider()
        lab = create_lab_app(enabled=True, repository=CallingRepository(Path(directory) / "calls.sqlite3"),
            audio_mode="realtime", realtime_provider_factory=lambda: provider,
            voice_database_path=Path(directory) / "voice.sqlite3",
            voice_settings=RealtimeSettings(api_key="test-only-key", idle_seconds=10))
        peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        tone = ToneTrack(440)
        peer.addTrack(tone)
        received = []
        tasks = []

        async def receive(track):
            try:
                while True:
                    frame = await track.recv()
                    received.append(float(np.max(np.abs(frame.to_ndarray().astype(np.float64)))))
            except MediaStreamError:
                pass

        @peer.on("track")
        def on_track(track):
            tasks.append(asyncio.create_task(receive(track)))

        try:
            async with lab.router.lifespan_context(lab):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=lab), base_url="http://laboratory") as client:
                    await peer.setLocalDescription(await peer.createOffer())
                    response = await client.post("/lab/calls", json={"type": "offer", "sdp": peer.localDescription.sdp})
                    self.assertEqual(response.status_code, 201, response.text)
                    answer = response.json()
                    await peer.setRemoteDescription(RTCSessionDescription(type="answer", sdp=answer["sdp"]))
                    async with asyncio.timeout(10):
                        while not provider.responses or not any(event["type"] == "input_audio_buffer.append" for event in provider.commands):
                            await asyncio.sleep(.01)
                    samples = np.arange(24000 * 3)
                    pcm = (5000 * np.sin(2 * np.pi * 880 * samples / 24000)).astype("<i2").tobytes()
                    response_id = provider.responses[0]["id"]
                    await provider.events.put({"type": "response.output_audio.delta", "response_id": response_id, "item_id": "model-audio", "delta": base64.b64encode(pcm).decode()})
                    await provider.events.put({"type": "response.output_audio.done", "response_id": response_id, "item_id": "model-audio"})
                    await provider.events.put({"type": "response.done", "response": {"id": response_id, "status": "completed", "output": [{"type": "message"}]}})
                    async with asyncio.timeout(5):
                        while sum(peak > 500 for peak in received) < 10:
                            await asyncio.sleep(.01)
                    await provider.events.put({"type": "input_audio_buffer.speech_started"})
                    await provider.events.put({"type": "input_audio_buffer.committed", "item_id": "interrupting-user"})
                    async with asyncio.timeout(3):
                        while len(provider.responses) < 2:
                            await asyncio.sleep(.01)
                    await provider.events.put({"type": "response.output_audio.delta", "response_id": response_id,
                        "item_id": "model-audio", "delta": base64.b64encode(pcm[:9600]).decode()})
                    await asyncio.sleep(.6)  # Drenar encoder y jitter de lo ya emitido.
                    self.assertTrue(all(peak < 500 for peak in received[-10:]), received[-10:])
                    current = (await client.get(f"/lab/calls/{answer['session_id']}")).json()
                    output = next(item for item in current["metrics"]["voice_history"] if item["item_id"] == "model-audio")
                    self.assertEqual(output["generation_state"], "completed")
                    self.assertEqual(output["state"], "interrupted")
                    self.assertLess(output["emitted_ms"], output["generated_ms"])
                    self.assertEqual(len(current["metrics"]["voice_performance"]["local_interruptions_ms"]), 1)
                    self.assertGreater(current["metrics"]["voice_performance"]["process"]["peak_rss_mib_process_lifetime"], 0)
                    audio = [base64.b64decode(event["audio"]) for event in provider.commands if event["type"] == "input_audio_buffer.append"]
                    self.assertGreater(sum(len(chunk) for chunk in audio), 24000)
                    self.assertGreater(np.max(np.abs(np.frombuffer(b"".join(audio), dtype="<i2"))), 1000)
                    result = (await client.delete(f"/lab/calls/{answer['session_id']}")).json()
                    self.assertTrue(result["resources_released"])
                    self.assertEqual(result["metrics"]["audio_mode"], "realtime")
                    self.assertTrue(provider.closed)
        finally:
            tone.stop()
            await peer.close()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def test_known_input_and_complete_greeting_cross_real_webrtc_then_hangup(self):
        import numpy as np
        from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
        from aiortc.mediastreams import MediaStreamError
        from scripts.probe_aiortc import ToneTrack

        directory = self.enterContext(tempfile.TemporaryDirectory())
        greeting_path = Path(__file__).resolve().parents[1] / "assets/lab-greeting.wav"
        with wave.open(str(greeting_path), "rb") as source:
            greeting_seconds = source.getnframes() / source.getframerate()
        lab = create_lab_app(enabled=True, repository=CallingRepository(Path(directory) / "lab.sqlite3"), audio_mode="greeting")
        peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        tone = ToneTrack(440)
        peer.addTrack(tone)
        received = {"samples": 0, "non_silent_frames": 0, "peak": 0.0}
        receiver_tasks = []

        async def receive(track):
            try:
                while True:
                    frame = await track.recv()
                    received["samples"] += frame.samples
                    peak = float(np.max(np.abs(frame.to_ndarray().astype(np.float64))))
                    received["peak"] = max(received["peak"], peak)
                    received["non_silent_frames"] += int(peak > 500)
            except MediaStreamError:
                pass

        @peer.on("track")
        def on_track(track):
            receiver_tasks.append(asyncio.create_task(receive(track)))

        try:
            async with lab.router.lifespan_context(lab):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=lab), base_url="http://laboratory") as client:
                    # Una oferta invalida debe liberar la capacidad antes del siguiente intento.
                    invalid = await client.post("/lab/calls", json={"type": "offer", "sdp": "not-sdp"})
                    self.assertEqual(invalid.status_code, 422)
                    await peer.setLocalDescription(await peer.createOffer())
                    created = await client.post("/lab/calls", json={"type": "offer", "sdp": peer.localDescription.sdp})
                    self.assertEqual(created.status_code, 201, created.text)
                    answer = created.json()
                    self.assertIn("opus/48000/2", answer["sdp"].lower())
                    session_id = answer["session_id"]
                    await peer.setRemoteDescription(RTCSessionDescription(type="answer", sdp=answer["sdp"]))
                    async with asyncio.timeout(greeting_seconds + 10):
                        while True:
                            row = (await client.get(f"/lab/calls/{session_id}")).json()
                            if row["greeting_state"] == "completed" and received["samples"] >= math.ceil(greeting_seconds * 48000):
                                break
                            self.assertNotIn(row["state"], {"ended", "failed"})
                            await asyncio.sleep(0.025)
                    self.assertGreater(row["metrics"]["non_silent_frames"], 20)
                    self.assertGreater(row["metrics"]["received_rms_pcm16"], 1000)
                    self.assertAlmostEqual(row["metrics"]["greeting_sent_seconds"], greeting_seconds, places=2)
                    self.assertGreater(received["non_silent_frames"], 50)
                    self.assertGreater(received["peak"], 1000)
                    closed = (await client.delete(f"/lab/calls/{session_id}")).json()
                    self.assertEqual(closed["greeting_state"], "completed")
                    self.assertTrue(closed["resources_released"])
                    self.assertEqual((await client.delete(f"/lab/calls/{session_id}")).json(), closed)
        finally:
            tone.stop()
            await peer.close()
            for task in receiver_tasks:
                task.cancel()
            await asyncio.gather(*receiver_tasks, return_exceptions=True)
