import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from calling_repository import CallingRepository
from main import app, create_lab_app
from openai_realtime_provider import RealtimeSettings
from test_calling_service import FakeMedia
from voice_fakes import FakeRealtimeProvider
from voice_repository import VoiceRepository


class CallingLaboratoryAPITests(unittest.TestCase):
    def test_importing_laboratory_does_not_initialize_calendar_or_load_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ, CALENDAR_PROVIDER="google", GOOGLE_CALENDAR_IDS="", DATABASE_PATH=str(Path(directory) / "patients.sqlite3"))
            result = subprocess.run(
                [sys.executable, "-c", "import sys; from main import create_lab_app; print('audio_loaded', 'aiortc' in sys.modules)"],
                env=environment, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "audio_loaded False")
            self.assertFalse((Path(directory) / "patients.sqlite3").exists())

    def test_token_free_laboratory_lifecycle_is_isolated_from_text_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            media = []

            def make_media():
                item = FakeMedia()
                media.append(item)
                return item

            with patch.dict(os.environ, {"VOICE_CALENDAR_PROVIDER": "fake"}):
                lab = create_lab_app(
                    enabled=True,
                    repository=CallingRepository(Path(directory) / "lab.sqlite3"),
                    media_factory=make_media,
                    audio_mode="greeting",
                )
            with TestClient(lab) as client:
                health = client.get("/lab/health")
                self.assertEqual(health.status_code, 200)
                self.assertEqual(health.json(), {
                    "status": "ok",
                    "mode": "laboratory",
                    "audio_mode": "greeting",
                    "calendar_provider": "fake",
                })
                self.assertEqual(health.headers["Cache-Control"], "no-store")
                self.assertEqual(media, [])
                response = client.post("/lab/calls", json={"sdp": "offer", "type": "offer"})
                self.assertEqual(response.status_code, 201)
                data = response.json()
                session_id = data["session_id"]
                self.assertEqual(data["sdp"], "laboratory-answer")
                self.assertEqual(data["type"], "answer")
                self.assertEqual(client.post("/lab/calls", json={"sdp": "offer", "type": "offer"}).status_code, 409)
                state = client.get(f"/lab/calls/{session_id}").json()
                self.assertEqual(state["mode"], "laboratory")
                ended = client.delete(f"/lab/calls/{session_id}")
                self.assertEqual(ended.status_code, 200)
                self.assertTrue(ended.json()["resources_released"])
                self.assertEqual(client.delete(f"/lab/calls/{session_id}").json(), ended.json())
                self.assertEqual(client.get("/lab/calls/missing").status_code, 404)
                self.assertEqual(client.post("/lab/calls", json={"sdp": "offer", "type": "answer"}).status_code, 400)
                self.assertNotIn("sdp", str(client.get(f"/lab/calls/{session_id}").json()))
            self.assertTrue(media[0].closed)
        with TestClient(app) as client:
            self.assertEqual(client.get("/lab").status_code, 404)
            self.assertEqual(client.get("/lab/health").status_code, 404)
            self.assertEqual(client.post("/lab/calls", json={}).status_code, 404)

    def test_google_calendar_mode_is_visible_in_lab_health_and_html(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"VOICE_CALENDAR_PROVIDER": "google"}):
                lab = create_lab_app(
                    enabled=True,
                    repository=CallingRepository(Path(directory) / "lab.sqlite3"),
                    media_factory=FakeMedia,
                    audio_mode="greeting",
                )
            with TestClient(lab) as client:
                self.assertEqual(
                    client.get("/lab/health").json(),
                    {
                        "status": "ok",
                        "mode": "laboratory",
                        "audio_mode": "greeting",
                        "calendar_provider": "google",
                    },
                )
                page = client.get("/lab").text
                self.assertIn('data-calendar-provider="google"', page)
                self.assertIn("Agenda conectada", page)

    def test_factory_requires_explicit_enablement_but_no_token(self):
        with patch.dict(os.environ, {"LAB_CALLS_ENABLED": "false", "LAB_ACCESS_TOKEN": ""}):
            with self.assertRaisesRegex(ValueError, "LAB_CALLS_ENABLED"):
                create_lab_app()
        with patch.dict(os.environ, {"LAB_CALLS_ENABLED": "true", "LAB_ACCESS_TOKEN": ""}):
            with tempfile.TemporaryDirectory() as directory:
                lab = create_lab_app(repository=CallingRepository(Path(directory) / "lab.sqlite3"),
                    media_factory=FakeMedia, audio_mode="greeting")
                with TestClient(lab) as client:
                    self.assertEqual(client.get("/lab/health").status_code, 200)

    def test_invalid_doctor_configuration_does_not_prevent_voice_laboratory_startup(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "DOCTOR_NOTIFICATIONS_ENABLED": "true", "DOCTOR_WHATSAPP_NUMBERS": "invalid",
            "VOICE_CALENDAR_PROVIDER": "fake",
        }):
            lab = create_lab_app(enabled=True, audio_mode="realtime",
                repository=CallingRepository(Path(directory) / "lab.sqlite3"),
                voice_database_path=Path(directory) / "voice.sqlite3",
                media_factory=FakeMedia, realtime_provider_factory=FakeRealtimeProvider,
                voice_settings=RealtimeSettings(api_key="test-only", maximum_sessions=10))
            with TestClient(lab) as client:
                self.assertEqual(client.get("/lab/health").status_code, 200)

    def test_voice_session_quota_returns_actionable_error_without_increasing_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            voice_path = Path(directory) / "voice.sqlite3"
            repository = VoiceRepository(voice_path)
            repository.start()
            repository.begin("already-used", "quota-test", maximum_sessions=1)
            repository.finish("already-used", "hangup", {})
            repository.close()
            with patch.dict(os.environ, {
                "VOICE_LAB_PROFILE": "quota-test",
                "VOICE_CALENDAR_PROVIDER": "fake",
            }):
                lab = create_lab_app(
                    enabled=True,
                    repository=CallingRepository(Path(directory) / "lab.sqlite3"),
                    media_factory=FakeMedia,
                    audio_mode="realtime",
                    realtime_provider_factory=FakeRealtimeProvider,
                    voice_settings=RealtimeSettings(api_key="test-only", maximum_sessions=1),
                    voice_database_path=voice_path,
                )
                with TestClient(lab) as client:
                    response = client.post("/lab/calls", json={"sdp": "offer", "type": "offer"})

            self.assertEqual(response.status_code, 429)
            self.assertIn("1/1", response.json()["detail"])
            self.assertIn("reiniciar no restablece", response.json()["detail"].lower())
            with sqlite3.connect(voice_path) as database:
                self.assertEqual(database.execute(
                    "SELECT COUNT(*) FROM voice_sessions WHERE profile=?", ("quota-test",)
                ).fetchone()[0], 1)

    def test_failed_creation_exposes_session_id_for_durable_finalization_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = CallingRepository(Path(directory) / "lab.sqlite3")
            media = FakeMedia()
            writer = None

            def allocate_media():
                writer.execute("BEGIN IMMEDIATE")
                return media

            lab = create_lab_app(enabled=True, repository=repository, media_factory=allocate_media, audio_mode="greeting")
            # El escritor se utiliza secuencialmente desde el test y desde TestClient.
            with closing(sqlite3.connect(repository.path, check_same_thread=False)) as connection:
                writer = connection
                with TestClient(lab) as client:
                    try:
                        failed = client.post("/lab/calls", json={"type": "offer", "sdp": "offer"})
                        self.assertEqual(failed.status_code, 503)
                        session_id = failed.json()["session_id"]
                        self.assertTrue(media.closed)
                        pending = client.get(f"/lab/calls/{session_id}").json()
                        self.assertTrue(pending["resources_released"])
                        self.assertEqual(pending["persistence_status"], "pending")
                    finally:
                        connection.rollback()
                    finalized = client.delete(f"/lab/calls/{session_id}")
                    self.assertEqual(finalized.status_code, 200)
                    self.assertEqual(finalized.json()["state"], "failed")
                    self.assertTrue(finalized.json()["resources_released"])
