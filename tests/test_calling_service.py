import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from calling_repository import CallCapacityError, CallingRepository
from calling_service import CallMediaPersistenceError, CallPersistenceError, CallSetupError, CallingService


class FakeMedia:
    def __init__(self) -> None:
        self.events = asyncio.Queue()
        self.metrics = {"received_frames": 0, "non_silent_frames": 0}
        self.last_received_at = None
        self.closed = False

    async def negotiate(self, sdp: str) -> str:
        return "laboratory-answer"

    async def close(self) -> None:
        self.closed = True


class CallingSessionTests(unittest.IsolatedAsyncioTestCase):
    async def make_service(self, factory=FakeMedia, **limits):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        repository = CallingRepository(Path(directory) / "laboratory.sqlite3")
        service = CallingService(repository, factory, **limits)
        await service.start()
        self.addAsyncCleanup(service.shutdown)
        return service

    async def wait_terminal(self, service, session_id):
        for _ in range(100):
            row = service.get(session_id)
            if row["state"] in {"ended", "failed", "interrupted"}:
                return row
            await asyncio.sleep(0.005)
        self.fail("La sesion no termino")

    async def test_session_preserves_result_and_releases_capacity_after_repeated_hangup(self) -> None:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        repository = CallingRepository(Path(directory) / "laboratory.sqlite3")
        media = []

        def make_media():
            item = FakeMedia()
            media.append(item)
            return item

        service = CallingService(repository, make_media)
        await service.start()
        self.addAsyncCleanup(service.shutdown)
        session, answer = await service.create("test-offer")
        self.assertEqual(answer, "laboratory-answer")
        self.assertEqual(session["state"], "negotiating")
        await media[0].events.put("connected")
        await media[0].events.put("greeting_playing")
        await media[0].events.put("greeting_completed")
        for _ in range(20):
            await asyncio.sleep(0.005)
            if service.get(session["session_id"])["greeting_state"] == "completed":
                break
        active = service.get(session["session_id"])
        self.assertEqual(active["state"], "active")
        self.assertEqual(active["greeting_state"], "completed")
        ended = await service.finish(session["session_id"])
        self.assertEqual(ended["state"], "ended")
        self.assertEqual(ended["greeting_state"], "completed")
        self.assertEqual(await service.finish(session["session_id"]), ended)
        self.assertTrue(media[0].closed)
        next_session, _ = await service.create("next-offer")
        self.assertNotEqual(next_session["session_id"], session["session_id"])

    async def test_second_call_does_not_replace_first_and_shutdown_interrupts_greeting(self):
        media = FakeMedia()
        service = await self.make_service(lambda: media)
        session, _ = await service.create("first-offer")
        with self.assertRaises(CallCapacityError):
            await service.create("second-offer")
        await media.events.put("connected")
        await media.events.put("greeting_playing")
        await asyncio.sleep(0.025)
        await service.shutdown()
        row = service.get(session["session_id"])
        self.assertEqual(row["state"], "ended")
        self.assertEqual(row["reason"], "server_shutdown")
        self.assertEqual(row["greeting_state"], "interrupted")
        self.assertTrue(row["resources_released"])
        self.assertTrue(media.closed)
        with self.assertRaises(CallCapacityError):
            await service.create("late-offer")

    async def test_negotiation_timeout_cancels_work_and_allows_another_call(self):
        class BlockedMedia(FakeMedia):
            async def negotiate(self, sdp):
                await asyncio.Future()

        media = BlockedMedia()
        service = await self.make_service(lambda: media, negotiation_seconds=0.025)
        with self.assertRaises(CallSetupError):
            await asyncio.wait_for(service.create("offer"), timeout=1)
        self.assertTrue(media.closed)
        service.media_factory = FakeMedia
        next_session, _ = await service.create("next")
        self.assertEqual(next_session["state"], "negotiating")

    async def test_audio_timeout_and_disconnect_release_resources_without_late_reactivation(self):
        for event, expected in ((None, "audio_timeout"), ("disconnected", "disconnected")):
            with self.subTest(event=event):
                media = FakeMedia()
                service = await self.make_service(lambda: media, inactivity_seconds=0.025)
                session, _ = await service.create("offer")
                await media.events.put("connected")
                await media.events.put("greeting_playing")
                if event:
                    await media.events.put(event)
                result = await self.wait_terminal(service, session["session_id"])
                self.assertEqual(result["reason"], expected)
                self.assertTrue(result["resources_released"])
                await media.events.put("connected")
                await media.events.put("greeting_completed")
                self.assertEqual(service.get(session["session_id"]), result)

    async def test_concurrent_hangups_close_once(self):
        class CountedMedia(FakeMedia):
            closes = 0

            async def close(self):
                self.closes += 1
                await asyncio.sleep(0.01)
                await super().close()

        media = CountedMedia()
        service = await self.make_service(lambda: media)
        session, _ = await service.create("offer")
        results = await asyncio.gather(*(service.finish(session["session_id"]) for _ in range(4)))
        self.assertTrue(all(row == results[0] for row in results))
        self.assertEqual(media.closes, 1)

    async def test_media_history_finalization_can_retry_after_resources_are_released(self):
        class PendingHistoryMedia(FakeMedia):
            history_available = False
            releases = 0

            async def close(self):
                if not self.closed:
                    self.releases += 1
                    self.closed = True
                if not self.history_available:
                    raise CallMediaPersistenceError(resources_released=True)

        media = PendingHistoryMedia()
        service = await self.make_service(lambda: media)
        session, _ = await service.create("offer")
        with self.assertRaises(CallPersistenceError):
            await service.finish(session["session_id"])
        pending = service.get(session["session_id"])
        self.assertTrue(pending["resources_released"])
        self.assertEqual(pending["persistence_status"], "pending")
        with self.assertRaises(CallCapacityError):
            await service.create("must-wait")
        media.history_available = True
        self.assertEqual((await service.finish(session["session_id"]))["state"], "ended")
        self.assertEqual(media.releases, 1)
        await service.create("next")

    async def test_database_write_failure_still_closes_audio_and_finalization_can_be_retried(self):
        class CountedMedia(FakeMedia):
            closes = 0

            async def close(self):
                self.closes += 1
                await super().close()

        media = CountedMedia()
        service = await self.make_service(lambda: media)
        session, _ = await service.create("offer")
        with closing(sqlite3.connect(service.repository.path)) as competing_writer:
            competing_writer.execute("BEGIN IMMEDIATE")
            with self.assertRaises(CallPersistenceError):
                await service.finish(session["session_id"])
            self.assertTrue(media.closed)
            pending = service.get(session["session_id"])
            self.assertTrue(pending["resources_released"])
            self.assertEqual(pending["state"], "ending")
            self.assertEqual(pending["persistence_status"], "pending")
            with self.assertRaises(CallCapacityError):
                await service.create("blocked-until-result-is-durable")
        finalized = await service.finish(session["session_id"])
        self.assertEqual(finalized["state"], "ended")
        self.assertTrue(finalized["resources_released"])
        self.assertEqual(media.closes, 1)
        self.assertEqual(await service.finish(session["session_id"]), finalized)
        await service.create("next-offer")

    async def test_storage_failure_after_media_allocation_does_not_leave_audio_running(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        repository = CallingRepository(Path(directory) / "lab.sqlite3")
        media = FakeMedia()
        writer = None

        def allocate_media():
            writer.execute("BEGIN IMMEDIATE")
            return media

        service = CallingService(repository, allocate_media)
        await service.start()
        self.addAsyncCleanup(service.shutdown)
        writer = self.enterContext(closing(sqlite3.connect(repository.path)))
        with self.assertRaises(CallPersistenceError):
            await service.create("offer")
        self.assertTrue(media.closed)
        writer.rollback()
        await service.shutdown()

    async def test_restart_marks_stale_call_interrupted_and_database_cannot_be_shared(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        path = Path(directory) / "lab.sqlite3"
        repository = CallingRepository(path)
        repository.start()
        session = repository.claim()
        competing = CallingRepository(path)
        with self.assertRaises(BlockingIOError):
            competing.start()
        repository.close()
        service = CallingService(CallingRepository(path), FakeMedia)
        await service.start()
        self.addAsyncCleanup(service.shutdown)
        recovered = service.get(session["session_id"])
        self.assertEqual(recovered["state"], "interrupted")
        self.assertEqual(recovered["reason"], "process_restart")
        self.assertTrue(recovered["resources_released"])
        await service.create("new-offer")
