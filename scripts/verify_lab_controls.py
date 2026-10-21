"""Prueba de UI/transportes sin APIs: voz y texto del paciente ficticio."""

import asyncio
import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import httpx
from voice_fakes import FakeRealtimeProvider


class ScriptedProvider(FakeRealtimeProvider):
    def __init__(self):
        super().__init__()
        self.speech_sent = False

    async def send(self, event):
        await super().send(event)
        if event["type"] == "input_audio_buffer.append" and not self.speech_sent:
            import numpy as np
            pcm = np.frombuffer(base64.b64decode(event["audio"]), dtype="<i2")
            if pcm.size and float(np.max(np.abs(pcm.astype(float)))) > 500:
                self.speech_sent = True
                await self.events.put({"type": "input_audio_buffer.speech_started"})
                await self.events.put({"type": "input_audio_buffer.committed", "item_id": "known-voice-input"})
                await self.events.put({"type": "conversation.item.input_audio_transcription.completed",
                    "item_id": "known-voice-input", "transcript": "Entrada de voz de prueba"})
        if event["type"] != "response.create":
            return
        response_id = self.responses[-1]["id"]
        item_id = "answer-" + response_id
        if event["response"].get("output_modalities") == ["text"]:
            text = "Contexto compartido recuperado" if self.history else "Respuesta de texto de prueba"
            await self.events.put({"type": "response.output_text.done", "response_id": response_id,
                                   "item_id": item_id, "text": text})
        else:
            import numpy as np
            samples = np.arange(12000)
            pcm = (5000 * np.sin(2 * np.pi * 880 * samples / 24000)).astype("<i2").tobytes()
            await self.events.put({"type": "response.output_audio.delta", "response_id": response_id,
                                   "item_id": item_id, "delta": base64.b64encode(pcm).decode()})
            await self.events.put({"type": "response.output_audio_transcript.done", "response_id": response_id,
                                   "item_id": item_id, "transcript": "Respuesta de voz de prueba"})
            await self.events.put({"type": "response.output_audio.done", "response_id": response_id, "item_id": item_id})
        await self.events.put({"type": "response.done", "response": {"id": response_id,
            "status": "completed", "output": [{"type": "message", "id": item_id}]}})


def create_verification_app():
    from main import create_lab_app
    from openai_realtime_provider import RealtimeSettings
    return create_lab_app(audio_mode="realtime", realtime_provider_factory=ScriptedProvider,
                          voice_settings=RealtimeSettings(api_key="no-network-test-key", maximum_sessions=10))


async def verify(*, cdp_url=None, port=0):
    from verify_lab_browser import safe_backend_state, wait_state
    from playwright.async_api import async_playwright

    with tempfile.TemporaryDirectory(prefix="lab-controls-") as directory:
        with socket.socket() as reservation:
            reservation.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            reservation.bind(("127.0.0.1", port))
            port = reservation.getsockname()[1]
        environment = dict(os.environ, LAB_CALLS_ENABLED="true",
            LAB_DATABASE_PATH=str(Path(directory) / "calls.sqlite3"), VOICE_DATABASE_PATH=str(Path(directory) / "voice.sqlite3"),
            VOICE_CALENDAR_PROVIDER="fake")
        process = subprocess.Popen([str(ROOT / ".venv/bin/uvicorn"), "scripts.verify_lab_controls:create_verification_app", "--factory",
            "--host", "127.0.0.1", "--port", str(port), "--no-access-log", "--log-level", "error"],
            cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            base = f"http://127.0.0.1:{port}"
            async with httpx.AsyncClient() as client:
                async with asyncio.timeout(20):
                    while True:
                        assert process.poll() is None, "No inicio el backend temporal"
                        try:
                            if (await client.get(base + "/lab")).status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        await asyncio.sleep(.1)
            async with async_playwright() as playwright:
                browser = (
                    await playwright.chromium.connect_over_cdp(cdp_url)
                    if cdp_url
                    else await playwright.chromium.launch(
                        executable_path="/usr/bin/chromium",
                        headless=True,
                        args=["--mute-audio", "--autoplay-policy=no-user-gesture-required",
                              "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
                              f"--use-file-for-fake-audio-capture={ROOT / 'assets/voice-availability-sample.wav'}"],
                    )
                )
                try:
                    page = await browser.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(type(error).__name__))
                    await page.goto(base + "/lab")
                    assert await page.locator("#token").count() == 0
                    assert await page.locator("#check").count() == 0
                    assert await page.locator("#connect").inner_text() == "Conectar e iniciar llamada"
                    await page.locator("#source").select_option("tone")
                    await page.locator("#connect").click()
                    await wait_state(page, lambda state: state.get("metrics", {}).get("voice_turn_count", 0) >= 1 and
                                     state.get("metrics", {}).get("voice_state") == "listening")
                    failed_once = [False]

                    async def lose_first_reply(route):
                        response = await route.fetch()
                        if not failed_once[0]:
                            failed_once[0] = True
                            await route.fulfill(status=503, json={"detail": "Respuesta de prueba perdida"})
                        else:
                            await route.fulfill(response=response)

                    await page.route("**/lab/messages", lose_first_reply)
                    await page.locator("#chat-text").fill("Mensaje durante la llamada")
                    await page.locator("#send-text").click()
                    await page.wait_for_function("document.getElementById('text-result').textContent.includes('reintentar')")
                    await page.locator("#send-text").click()
                    await page.wait_for_function("document.getElementById('text-result').textContent.includes('Respuesta de texto')")
                    await page.wait_for_function("!document.getElementById('send-text').disabled && document.getElementById('shared-history').textContent.length > 0")
                    history = json.loads(await page.locator("#shared-history").inner_text())["history"]
                    self_text = [item for item in history if item["role"] == "user" and item["channel"] == "text"]
                    assert len(self_text) == 1
                    assert any(item["channel"] == "voice" and item["emitted_ms"] > 0 for item in history)
                    await page.locator("#hangup").click()
                    await wait_state(page, lambda state: state.get("state") == "ended")
                    await page.locator("#chat-text").fill("Continuar despues de colgar")
                    await page.locator("#send-text").click()
                    await page.wait_for_function("document.getElementById('text-result').textContent.includes('Contexto compartido')")
                    await page.wait_for_function("!document.getElementById('send-text').disabled")

                    # Reproduce getUserMedia con un microfono Chromium simulado y
                    # exige audio entrante, no solo que el servidor acepte HTTP.
                    await page.locator("#source").select_option("microphone")
                    await page.locator("#connect").click()
                    try:
                        microphone_state = await wait_state(page, lambda state:
                            state.get("state") in {"failed", "ended"} or (
                                state.get("metrics", {}).get("voice_turn_count", 0) >= 1
                                and state.get("metrics", {}).get("non_silent_frames", 0) > 0
                            ), timeout=25)
                    except TimeoutError:
                        return {
                            "passed": False,
                            "stage": "microphone_webrtc_timeout",
                            "status_text": (await page.locator("#status").inner_text())[:300],
                            "browser_connectivity": json.loads(await page.locator("#network").inner_text()),
                            "backend": safe_backend_state(directory),
                            "javascript_errors": errors,
                        }
                    if microphone_state.get("state") in {"failed", "ended"}:
                        return {
                            "passed": False,
                            "stage": "microphone_webrtc_failed",
                            "status_text": (await page.locator("#status").inner_text())[:300],
                            "browser_connectivity": json.loads(await page.locator("#network").inner_text()),
                            "backend": safe_backend_state(directory),
                            "javascript_errors": errors,
                        }
                    await page.wait_for_function(
                        "network.connection === 'connected' && network.audio_sent_packets > 0",
                        timeout=10000,
                    )
                    assert microphone_state["state"] not in {"failed", "interrupted"}
                    microphone_network = json.loads(await page.locator("#network").inner_text())
                    assert microphone_network["audio_sent_packets"] > 0
                    assert microphone_network["audio_received_packets"] > 0
                    await page.locator("#hangup").click()
                    await wait_state(page, lambda state: state.get("state") == "ended")
                    assert not errors
                    return {"passed": True,
                        "mode": "mac_chromium_cdp_fake_microphone" if cdp_url else "chromium_real_webrtc_fake_realtime",
                        "javascript_errors": errors,
                        "token_free_connection": True, "voice_text_shared_history": True, "lost_response_retry_without_duplicate": True,
                        "text_after_hangup_restores_context": True, "microphone_get_user_media_and_rtp": True,
                        "microphone_voice_turns": microphone_state["metrics"]["voice_turn_count"],
                        "microphone_non_silent_frames": microphone_state["metrics"]["non_silent_frames"],
                        "microphone_connectivity": microphone_network,
                        "external_api_calls": 0}
                finally:
                    await browser.close()
        finally:
            process.terminate()
            await asyncio.to_thread(process.wait, 10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdp-url")
    parser.add_argument("--port", type=int, default=0)
    arguments = parser.parse_args()
    print(json.dumps(asyncio.run(verify(cdp_url=arguments.cdp_url, port=arguments.port)), indent=2))
