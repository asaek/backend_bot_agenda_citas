"""Verifica desde la Pi un navegador local o remoto y un backend temporal."""

import argparse
import asyncio
import ipaddress
import json
import os
import socket
import sqlite3
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import httpx
from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]


def process_usage(pid: int) -> tuple[float, float]:
    fields = Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].split()
    cpu = (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")
    status = Path(f"/proc/{pid}/status").read_text().splitlines()
    rss = int(next(line for line in status if line.startswith("VmRSS:")).split()[1]) / 1024
    return cpu, rss


async def wait_state(page, predicate, timeout=15):
    async with asyncio.timeout(timeout):
        while True:
            try:
                state = json.loads(await page.locator("#status").inner_text())
                if predicate(state):
                    return state
            except json.JSONDecodeError:
                pass
            await asyncio.sleep(0.05)


def safe_row(row):
    metrics = row.get("metrics", {})
    keys = (
        "voice_state", "voice_failure_type", "voice_failure_code", "voice_error_code",
        "voice_turn_count", "voice_tool_calls", "non_silent_frames", "received_frames",
    )
    return {
        "state": row.get("state"),
        "reason": row.get("reason"),
        "metrics": {key: metrics.get(key) for key in keys},
    }


def safe_backend_state(directory):
    path = Path(directory) / "calls.sqlite3"
    if not path.exists():
        return {}
    with sqlite3.connect(path) as database:
        row = database.execute(
            "SELECT state,reason,metrics_json FROM lab_call_sessions ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        return {}
    return safe_row({"state": row[0], "reason": row[1], "metrics": json.loads(row[2])})


async def verify(*, cdp_url: str | None = None, port: int = 0, expected_lan: str | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix="calling-lab-") as directory:
        with socket.socket() as reservation:
            reservation.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            reservation.bind(("127.0.0.1", port))
            port = reservation.getsockname()[1]
        environment = dict(
            os.environ,
            LAB_CALLS_ENABLED="true", LAB_AUDIO_MODE="greeting",
            LAB_DATABASE_PATH=str(Path(directory) / "lab.sqlite3"),
            VOICE_CALENDAR_PROVIDER="fake",
            LAB_NEGOTIATION_SECONDS="3", LAB_INACTIVITY_SECONDS="2",
        )
        server = subprocess.Popen(
            [str(ROOT / ".venv/bin/python"), "-m", "uvicorn", "main:create_lab_app", "--factory", "--host", "127.0.0.1", "--port", str(port), "--no-access-log", "--no-proxy-headers", "--log-level", "error"],
            cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        sampler = None
        try:
            base_url = f"http://127.0.0.1:{port}"
            async with httpx.AsyncClient(base_url=base_url, timeout=5) as client:
                async with asyncio.timeout(20):
                    while True:
                        if server.poll() is not None:
                            raise RuntimeError("No se pudo iniciar el backend de laboratorio")
                        try:
                            if (await client.get("/lab")).status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        await asyncio.sleep(0.1)
                assert (await client.post("/lab/calls", json={})).status_code == 400
                assert (await client.get("/lab/health")).status_code == 200
                cpu_start, rss_baseline = process_usage(server.pid)
                peak = [rss_baseline]
                started = time.monotonic()

                async def sample():
                    while True:
                        peak[0] = max(peak[0], process_usage(server.pid)[1])
                        await asyncio.sleep(0.05)

                sampler = asyncio.create_task(sample())
                with wave.open(str(ROOT / "assets/lab-greeting.wav"), "rb") as greeting:
                    greeting_seconds = greeting.getnframes() / greeting.getframerate()
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.connect_over_cdp(cdp_url) if cdp_url else await playwright.chromium.launch(
                        executable_path="/usr/bin/chromium", headless=True,
                        args=["--autoplay-policy=no-user-gesture-required",
                              "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
                    )
                    try:
                        page = await browser.new_page()
                        errors = []
                        page.on("pageerror", lambda error: errors.append(type(error).__name__))
                        await page.goto(base_url + "/lab")
                        assert await page.locator("#token").count() == 0
                        assert await page.locator("#check").count() == 0
                        assert await page.evaluate("current === null")
                        assert not await page.locator("#connect").is_disabled()
                        with sqlite3.connect(environment["LAB_DATABASE_PATH"]) as database:
                            assert database.execute("SELECT COUNT(*) FROM lab_call_sessions").fetchone()[0] == 0

                        # Un HTTP correcto no debe presentarse como medios conectados.
                        async def drop_candidates(route):
                            payload = route.request.post_data_json
                            payload["sdp"] = "\r\n".join(line for line in payload["sdp"].split("\r\n") if not line.startswith("a=candidate:"))
                            response = await route.fetch(post_data=json.dumps(payload))
                            data = await response.json()
                            if route.request.method == "POST" and response.status == 201:
                                data["sdp"] = "\r\n".join(line for line in data["sdp"].split("\r\n") if not line.startswith("a=candidate:"))
                                await route.fulfill(response=response, json=data)
                            else:
                                await route.fulfill(response=response)

                        await page.route("**/lab/calls", drop_candidates)
                        await page.locator("#connect").click()
                        no_media = await wait_state(page, lambda state: state.get("state") == "failed")
                        diagnosis = json.loads(await page.locator("#network").inner_text())
                        assert no_media["resources_released"]
                        assert "HTTP 200" in diagnosis["signaling"]
                        assert diagnosis["audio_received_packets"] == 0
                        assert "WebRTC no conectó" in diagnosis["diagnosis"]
                        await page.unroute("**/lab/calls", drop_candidates)

                        # El microfono Chromium simulado sigue el mismo getUserMedia
                        # y SDP que el dispositivo real, pero no requiere permisos humanos.
                        await page.locator("#source").select_option("microphone")
                        await page.locator("#connect").click()
                        try:
                            microphone_result = await wait_state(page, lambda state:
                                state.get("state") in {"failed", "ended"}
                                or state.get("greeting_state") == "completed", timeout=25)
                        except TimeoutError:
                            return {
                                "passed": False,
                                "stage": "microphone_webrtc_timeout",
                                "status_text": (await page.locator("#status").inner_text())[:300],
                                "browser_connectivity": json.loads(await page.locator("#network").inner_text()),
                                "backend": safe_backend_state(directory),
                                "javascript_errors": errors,
                            }
                        if microphone_result.get("state") in {"failed", "ended"}:
                            return {
                                "passed": False,
                                "stage": "microphone_webrtc_failed",
                                "status_text": (await page.locator("#status").inner_text())[:300],
                                "browser_connectivity": json.loads(await page.locator("#network").inner_text()),
                                "backend": safe_row(microphone_result),
                                "javascript_errors": errors,
                            }
                        completed = microphone_result
                        await page.wait_for_function("minimum => document.getElementById('audio').currentTime >= minimum", arg=greeting_seconds)
                        playback = await page.evaluate("""async () => {
                            const stats = await current.peer.getStats();
                            const inbound = [...stats.values()].find(item => item.type === 'inbound-rtp' && item.kind === 'audio');
                            const audio = document.getElementById('audio');
                            return {current_time: audio.currentTime, paused: audio.paused, packets_received: inbound?.packetsReceived || 0, bytes_received: inbound?.bytesReceived || 0};
                        }""")
                        assert completed["metrics"]["non_silent_frames"] > 20
                        assert playback["packets_received"] > 50 and not playback["paused"]
                        connectivity = json.loads(await page.locator("#network").inner_text())
                        assert connectivity["secure_context"] and connectivity["audio_sent_packets"] > 0
                        assert connectivity["audio_received_packets"] > 50
                        assert connectivity["candidate_pair"] == {"local": "host", "remote": "host", "protocol": "udp"}
                        same_lan = None
                        if expected_lan:
                            addresses = await page.evaluate("""async () => {
                                const stats = await current.peer.getStats();
                                const transport = [...stats.values()].find(item => item.type === 'transport' && item.selectedCandidatePairId);
                                const pair = stats.get(transport.selectedCandidatePairId);
                                return [stats.get(pair.localCandidateId).address, stats.get(pair.remoteCandidateId).address];
                            }""")
                            subnet = ipaddress.ip_network(expected_lan)
                            # Chrome puede ocultar la IP local cuando usa mDNS.
                            same_lan = {
                                "remote": ipaddress.ip_address(addresses[1]) in subnet,
                                "local": ipaddress.ip_address(addresses[0]) in subnet if addresses[0] else "hidden_by_browser",
                            }
                            assert same_lan["remote"] and same_lan["local"] is not False, "El par ICE seleccionado no pertenece a la LAN esperada"
                        await page.evaluate("Promise.all([hangup(), hangup()])")
                        closed = await wait_state(page, lambda state: state.get("state") == "ended")
                        assert closed["resources_released"] and closed["greeting_state"] == "completed"
                        assert not await page.locator("#connect").is_disabled()
                        assert json.loads(await page.locator("#network").inner_text())["playback"] == "Sin audio"

                        # Una respuesta HTTP antigua no pertenece a la nueva llamada.
                        health_started, release_health = asyncio.Event(), asyncio.Event()

                        async def stale_health(route):
                            if not health_started.is_set():
                                health_started.set()
                                await release_health.wait()
                                await route.fulfill(status=401, json={"detail": "Respuesta antigua"})
                            else:
                                await route.continue_()

                        await page.route("**/lab/health", stale_health)
                        await page.locator("#connect").click()
                        await asyncio.wait_for(health_started.wait(), 5)
                        await page.locator("#hangup").click()
                        await page.locator("#connect").click()
                        await wait_state(page, lambda state: state.get("greeting_state") == "playing")
                        async with page.expect_response(lambda response: response.url.endswith("/lab/health") and response.status == 401):
                            release_health.set()
                        await page.wait_for_timeout(100)
                        assert "HTTP 200" in json.loads(await page.locator("#network").inner_text())["signaling"]
                        assert await page.evaluate("document.getElementById('audio').srcObject === current.remoteStream && !!current.remoteStream")
                        await page.unroute("**/lab/health", stale_health)
                        await page.locator("#hangup").click()
                        await wait_state(page, lambda state: state.get("state") == "ended")

                        await page.locator("#connect").click()
                        await wait_state(page, lambda state: state.get("greeting_state") == "playing")
                        failed_once = [False]

                        async def fail_first_delete(route):
                            if route.request.method == "DELETE" and not failed_once[0]:
                                failed_once[0] = True
                                await route.fulfill(status=503, content_type="application/json", body='{"detail":"Reintenta finalizar la sesion"}')
                            else:
                                await route.continue_()

                        await page.route("**/lab/calls/*", fail_first_delete)
                        await page.locator("#hangup").click()
                        await page.wait_for_function("document.getElementById('status').textContent.includes('Pulsa Colgar para reintentar')")
                        assert not await page.locator("#hangup").is_disabled()
                        assert await page.locator("#connect").is_disabled()
                        await page.unroute("**/lab/calls/*", fail_first_delete)
                        await page.locator("#hangup").click()
                        interrupted = await wait_state(page, lambda state: state.get("greeting_state") == "interrupted")
                        assert interrupted["resources_released"]

                        await page.locator("#connect").click()
                        await wait_state(page, lambda state: state.get("greeting_state") == "playing")
                        await page.evaluate("current.peer.close()")
                        disconnected = await wait_state(page, lambda state: state.get("state") in {"failed", "ended"})
                        assert disconnected["resources_released"]

                        # Una adquisicion de microfono tardia no debe tocar otro reproductor.
                        await page.evaluate("""() => {
                            window.originalGetUserMedia = navigator.mediaDevices.getUserMedia;
                            navigator.mediaDevices.getUserMedia = () => new Promise(resolve => { window.resolveStaleMic = resolve; });
                        }""")
                        await page.locator("#source").select_option("microphone")
                        await page.locator("#connect").click()
                        await page.wait_for_function("!!window.resolveStaleMic")
                        await page.locator("#hangup").click()
                        await page.locator("#source").select_option("tone")
                        await page.locator("#connect").click()
                        await wait_state(page, lambda state: state.get("greeting_state") == "playing")
                        await page.evaluate("""async () => {
                            window.resolveStaleMic(new MediaStream());
                            navigator.mediaDevices.getUserMedia = window.originalGetUserMedia;
                            await new Promise(resolve => setTimeout(resolve, 50));
                        }""")
                        assert await page.evaluate("document.getElementById('audio').srcObject === current.remoteStream && !!current.remoteStream")
                        await page.locator("#hangup").click()
                        await wait_state(page, lambda state: state.get("state") == "ended")

                        # HTTP en un origen no confiable permite tono, pero no microfono.
                        insecure = await browser.new_page()
                        try:
                            html = (await client.get("/lab")).text
                            await insecure.route("http://lab.invalid/lab", lambda route: route.fulfill(body=html, content_type="text/html"))
                            await insecure.route("http://lab.invalid/lab/health", lambda route: route.fulfill(json={"status": "ok", "mode": "laboratory"}))
                            await insecure.goto("http://lab.invalid/lab")
                            await insecure.locator("#source").select_option("microphone")
                            await insecure.locator("#connect").click()
                            await insecure.wait_for_function("document.getElementById('status').textContent.includes('El micrófono requiere HTTPS')")
                            assert not await insecure.locator("#connect").is_disabled()
                            assert await insecure.evaluate("current === null")
                        finally:
                            await insecure.close()

                        await page.locator("#connect").click()
                        active = await wait_state(page, lambda state: state.get("greeting_state") == "playing")
                        cpu_end, rss_final = process_usage(server.pid)
                        elapsed = time.monotonic() - started
                        sampler.cancel()
                        await asyncio.gather(sampler, return_exceptions=True)
                        server.terminate()
                        await asyncio.to_thread(server.wait, 10)
                        assert not errors, errors
                        with sqlite3.connect(environment["LAB_DATABASE_PATH"]) as database:
                            shutdown = database.execute(
                                "SELECT state,greeting_state,reason,resources_released FROM lab_call_sessions WHERE session_id=?",
                                (active["session_id"],),
                            ).fetchone()
                        assert shutdown == ("ended", "interrupted", "server_shutdown", 1), shutdown
                        return {
                            "mode": "laboratory_remote_browser" if cdp_url else "laboratory_chromium_same_pi",
                            "browser_version": browser.version,
                            "greeting_seconds": round(greeting_seconds, 3),
                            "browser_playback": playback,
                            "backend_audio_metrics": completed["metrics"],
                            "browser_connectivity": connectivity,
                            "microphone_get_user_media": True,
                            "microphone_non_silent_frames": completed["metrics"]["non_silent_frames"],
                            "microphone_sent_rtp_packets": connectivity["audio_sent_packets"],
                            "selected_pair_in_expected_lan": same_lan,
                            "http_check_without_session": "passed",
                            "connect_and_hangup_without_token": "passed",
                            "http_success_without_media_detected": "passed",
                            "stale_http_response_does_not_replace_new_call_diagnostics": "passed",
                            "hangup_clears_playback_diagnostic": "passed",
                            "insecure_microphone_actionable_error": "passed",
                            "complete_greeting_and_hangup": "passed",
                            "double_hangup_allows_reconnect": "passed",
                            "retry_after_finalization_503": "passed",
                            "hangup_during_greeting": "passed",
                            "disconnect_during_greeting": disconnected["reason"],
                            "shutdown_during_greeting": "passed",
                            "late_microphone_does_not_silence_new_call": "passed",
                            "javascript_errors": errors,
                            "backend_wall_seconds": round(elapsed, 3),
                            "backend_cpu_seconds": round(cpu_end - cpu_start, 3),
                            "backend_cpu_percent_one_core": round((cpu_end - cpu_start) / elapsed * 100, 1),
                            "backend_rss_baseline_mib": round(rss_baseline, 2),
                            "backend_rss_final_mib": round(rss_final, 2),
                            "backend_rss_peak_sampled_mib": round(peak[0], 2),
                            "physical_listening": "pending_human_check",
                        }
                    finally:
                        await page.close()
                        await browser.close()
        finally:
            if sampler is not None:
                sampler.cancel()
                await asyncio.gather(sampler, return_exceptions=True)
            if server.poll() is None:
                server.terminate()
                try:
                    await asyncio.to_thread(server.wait, 10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    await asyncio.to_thread(server.wait)
            server.stderr.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdp-url", help="Chromium remoto accesible por CDP desde la Pi")
    parser.add_argument("--port", type=int, default=0, help="Puerto HTTP fijo para reenviarlo al navegador remoto")
    parser.add_argument("--expected-lan", help="CIDR del candidato remoto y del local si el navegador expone su direccion")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(verify(cdp_url=args.cdp_url, port=args.port, expected_lan=args.expected_lan)), indent=2))
