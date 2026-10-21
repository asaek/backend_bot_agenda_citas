"""Verifica navegador real -> Pi -> OpenAI -> Pi -> navegador con muestra de voz.

Ejecutar en la Pi. --cdp-url permite usar Chrome de otra computadora por SSH.
La prueba usa una sesion de pago, sin microfono fisico ni transcripciones en logs.
"""

import argparse
import asyncio
import json
import os
import socket
import sqlite3
import subprocess
import tempfile
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

from verify_lab_browser import wait_state

ROOT = Path(__file__).resolve().parents[1]


def safe_row(row):
    metrics = row.get("metrics", {})
    keys = ("voice_state", "voice_failure_type", "voice_failure_code", "voice_error_code", "voice_turn_count",
            "voice_tool_calls", "voice_usage", "voice_performance", "voice_cost", "non_silent_frames", "playback_peak_queued_ms")
    return {"state": row.get("state"), "reason": row.get("reason"),
            "metrics": {key: metrics.get(key) for key in keys},
            "transcript_roles": [item.get("role") for item in metrics.get("voice_history", [])]}


def safe_backend_state(directory):
    path = Path(directory) / "calls.sqlite3"
    if not path.exists():
        return {}
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT state,reason,metrics_json FROM lab_call_sessions ORDER BY created_at DESC LIMIT 1").fetchone()
    if not row:
        return {}
    return safe_row({"state": row[0], "reason": row[1], "metrics": json.loads(row[2])})


async def verify(cdp_url=None, port=0, expected_peer=None):
    with tempfile.TemporaryDirectory(prefix="realtime-browser-") as directory:
        with socket.socket() as reservation:
            reservation.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            reservation.bind(("127.0.0.1", port))
            port = reservation.getsockname()[1]
        environment = dict(os.environ, LAB_CALLS_ENABLED="true", LAB_AUDIO_MODE="realtime",
            LAB_DATABASE_PATH=str(Path(directory) / "calls.sqlite3"), VOICE_DATABASE_PATH=str(Path(directory) / "voice.sqlite3"),
            VOICE_CALENDAR_PROVIDER="fake", VOICE_MAXIMUM_SECONDS="90", VOICE_IDLE_SECONDS="30", VOICE_MAX_SESSIONS="2")
        server = subprocess.Popen([str(ROOT / ".venv/bin/uvicorn"), "main:create_lab_app", "--factory", "--host", "127.0.0.1", "--port", str(port), "--no-access-log", "--log-level", "error"],
                                  cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            base = f"http://127.0.0.1:{port}"
            async with httpx.AsyncClient(timeout=5) as client:
                async with asyncio.timeout(20):
                    while True:
                        if server.poll() is not None:
                            raise RuntimeError("No se pudo iniciar el laboratorio Realtime")
                        try:
                            if (await client.get(base + "/lab")).status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        await asyncio.sleep(.1)
            async with async_playwright() as playwright:
                browser = await playwright.chromium.connect_over_cdp(cdp_url) if cdp_url else await playwright.chromium.launch(
                    executable_path="/usr/bin/chromium", headless=True,
                    args=["--mute-audio", "--autoplay-policy=no-user-gesture-required"])
                page = await browser.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(type(error).__name__))
                try:
                    await page.goto(base + "/lab")
                    assert await page.locator("#source").input_value() == "microphone"
                    await page.locator("#source").select_option("sample")
                    await page.locator("#sample").set_input_files(ROOT / "assets/voice-availability-sample.wav")
                    await page.locator("#connect").click()
                    try:
                        row = await wait_state(page, lambda state: state.get("state") in {"failed", "ended"} or (
                            state.get("metrics", {}).get("voice_turn_count", 0) >= 1 and
                            state.get("metrics", {}).get("voice_tool_calls", 0) >= 1 and
                            state.get("metrics", {}).get("voice_state") == "listening" and
                            sum(item["role"] == "assistant" for item in state.get("metrics", {}).get("voice_history", [])) >= 2), timeout=70)
                        failed = row.get("state") in {"failed", "ended"}
                    except TimeoutError:
                        failed = True
                    if failed:
                        backend = safe_backend_state(directory)
                        session_id = await page.evaluate("current?.id || null")
                        if session_id:
                            async with httpx.AsyncClient(timeout=5) as client:
                                response = await client.get(base + "/lab/calls/" + session_id)
                                if response.status_code == 200:
                                    backend = safe_row(response.json())
                        browser_state = await page.evaluate("""() => ({
                            peer: current?.peer?.connectionState, sample_started: !!current?.sampleStarted,
                            context_state: current?.context?.state, secure_context: window.isSecureContext,
                            audio_mode: document.documentElement.dataset.audioMode,
                        })""")
                        return {"passed": False, "stage": "browser_conversation", "backend": backend,
                                "browser": browser_state, "javascript_errors": errors}
                    playback = await page.evaluate("""async () => {
                        const stats = await current.peer.getStats();
                        const inbound = [...stats.values()].find(item => item.type === 'inbound-rtp' && item.kind === 'audio');
                        const transport = [...stats.values()].find(item => item.type === 'transport' && item.selectedCandidatePairId);
                        const pair = stats.get(transport.selectedCandidatePairId);
                        const audio = document.getElementById('audio');
                        return {packets_received: inbound.packetsReceived, bytes_received: inbound.bytesReceived,
                            sample_end_to_browser_playback_signal_ms: network.sample_end_to_browser_playback_signal_ms,
                            remote_candidate_type: stats.get(pair.remoteCandidateId).candidateType,
                            remote_address: stats.get(pair.remoteCandidateId).address,
                            paused: audio.paused, current_time: audio.currentTime};
                    }""")
                    assert not playback["paused"] and playback["packets_received"] > 100
                    peer_address = playback.pop("remote_address", None)
                    peer_verified = peer_address in expected_peer.split(",") if expected_peer else None
                    if expected_peer:
                        if not peer_verified:
                            async with httpx.AsyncClient(timeout=10) as client:
                                ended = await client.delete(base + "/lab/calls/" + row["session_id"])
                            return {"passed": False, "stage": "peer_verification", "expected_peer_verified": False,
                                    "backend": safe_row(ended.json()), "javascript_errors": errors,
                                    "physical_microphone_and_listening": "not_performed"}
                    await page.locator("#chat-text").fill("¿Qué te pregunté por voz?")
                    async with page.expect_response("**/lab/messages") as text_response:
                        await page.locator("#send-text").click()
                    first_text = await (await text_response.value).json()
                    assert first_text["state"] == "completed" and first_text["reply"]
                    await page.wait_for_function("!document.getElementById('send-text').disabled")
                    await page.locator("#hangup").click()
                    final = await wait_state(page, lambda state: state.get("state") == "ended")
                    assert final["resources_released"] and not errors
                    await page.locator("#chat-text").fill("¿Recuerdas que pregunté por horarios?")
                    async with page.expect_response("**/lab/messages") as text_response:
                        await page.locator("#send-text").click()
                    following_text = await (await text_response.value).json()
                    assert following_text["state"] == "completed" and following_text["reply"]
                    await page.wait_for_function("!document.getElementById('send-text').disabled")
                    return {"passed": True, "mode": "mac_browser_pi_openai" if cdp_url else "pi_browser_pi_openai",
                        "browser_version": browser.version, "model": row["metrics"]["voice_model"],
                        "expected_peer_verified": peer_verified,
                        "voice_turns": row["metrics"]["voice_turn_count"], "tool_calls": row["metrics"]["voice_tool_calls"],
                        "usage": row["metrics"]["voice_usage"], "playback": playback,
                        "performance": final["metrics"].get("voice_performance"),
                        "estimated_cost": final["metrics"].get("voice_cost"),
                        "resources_released": final["resources_released"], "javascript_errors": errors,
                        "voice_to_text_during_call": True, "text_after_hangup_restores_context": True,
                        "text_session_usage": following_text["usage"], "voice_and_text_usage": first_text["usage"],
                        "physical_microphone_and_listening": "not_performed"}
                finally:
                    await page.close()
                    await browser.close()
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    await asyncio.to_thread(server.wait, 10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    await asyncio.to_thread(server.wait)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdp-url")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--expected-peer", help="Direcciones verificadas de la Pi, separadas por comas")
    args = parser.parse_args()
    result = asyncio.run(verify(args.cdp_url, args.port, args.expected_peer))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
