"""Control de sesiones de laboratorio, sin dependencias de audio ni Meta."""

import asyncio
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from calling_repository import CallCapacityError, CallingRepository, VoiceSessionQuotaExceededError


class CallSetupError(RuntimeError):
    pass


class CallPersistenceError(RuntimeError):
    def __init__(self, session_id: str) -> None:
        super().__init__("Falta persistir el resultado del cierre")
        self.session_id = session_id


class CallMediaPersistenceError(RuntimeError):
    """Medios cerrados, finalizacion de su historial pendiente de reintento."""

    def __init__(self, *, resources_released: bool):
        super().__init__("Falta persistir el cierre de medios")
        self.resources_released = resources_released


class CallMedia(Protocol):
    events: asyncio.Queue[str]
    last_received_at: float | None

    @property
    def metrics(self) -> dict: ...

    async def negotiate(self, offer_sdp: str) -> str: ...

    async def close(self) -> None: ...


@dataclass
class _Session:
    media: CallMedia | None
    started_at: float
    record: dict
    connected_at: float | None = None
    negotiation: asyncio.Task | None = None
    watcher: asyncio.Task | None = None
    closing: asyncio.Task | None = None
    cleanup_complete: bool = False
    media_finalization_pending: bool = False
    persistence_pending: bool = False
    final_reason: str | None = None
    final_failed: bool = False


class CallingService:
    def __init__(
        self,
        repository: CallingRepository,
        media_factory: Callable[[], CallMedia],
        *,
        session_media_factory: Callable[[str], CallMedia] | None = None,
        negotiation_seconds: float = 20,
        inactivity_seconds: float = 60,
        maximum_seconds: float = 600,
    ) -> None:
        if any(not math.isfinite(value) or value <= 0 for value in (negotiation_seconds, inactivity_seconds, maximum_seconds)):
            raise ValueError("Los plazos deben ser positivos")
        self.repository = repository
        self.media_factory = media_factory
        self.session_media_factory = session_media_factory
        self.negotiation_seconds = negotiation_seconds
        self.inactivity_seconds = inactivity_seconds
        self.maximum_seconds = maximum_seconds
        self._sessions: dict[str, _Session] = {}
        self._stopping = True

    async def start(self) -> None:
        self.repository.start()
        self._stopping = False

    async def create(self, offer_sdp: str) -> tuple[dict, str]:
        if self._stopping or any(item.persistence_pending for item in self._sessions.values()):
            raise CallCapacityError("El laboratorio no admite sesiones")
        row = self.repository.claim()
        session_id = row["session_id"]
        runtime = _Session(None, asyncio.get_running_loop().time(), row)
        self._sessions[session_id] = runtime
        try:
            media = runtime.media = self.session_media_factory(session_id) if self.session_media_factory else self.media_factory()
            self.repository.transition(session_id, "negotiating")
            runtime.record["state"] = "negotiating"
            runtime.negotiation = asyncio.create_task(media.negotiate(offer_sdp))
            runtime.watcher = asyncio.create_task(self._watch(session_id, runtime))
            answer = await asyncio.shield(runtime.negotiation)
            if runtime.closing is not None:
                await runtime.closing
                raise CallSetupError("La sesion termino durante la negociacion")
            return self.get(session_id), answer
        except asyncio.CancelledError:
            await self.finish(session_id, reason="request_cancelled")
            if asyncio.current_task().cancelling():
                raise
            raise CallSetupError("Negociacion interrumpida") from None
        except VoiceSessionQuotaExceededError:
            await self.finish(session_id, reason="session_quota_reached", failed=True)
            raise
        except Exception:
            reason = "media_setup_failed" if runtime.media is None else "negotiation_failed"
            await self.finish(session_id, reason=reason, failed=True)
            raise CallSetupError("No se pudo negociar el audio") from None

    def get(self, session_id: str) -> dict:
        runtime = self._sessions.get(session_id)
        if runtime is not None and runtime.persistence_pending:
            result = dict(runtime.record)
            result.update(state="ending", resources_released=runtime.cleanup_complete, persistence_status="pending")
        else:
            result = self.repository.get(session_id)
            if runtime is not None:
                runtime.record = dict(result)
        if runtime is not None and runtime.media is not None:
            result["metrics"] = dict(runtime.media.metrics)
        return result

    def active_media(self):
        """Medios del unico interlocutor activo, elegidos por el servidor."""
        return next((item.media for item in self._sessions.values()
                     if item.media is not None and item.closing is None), None)

    async def _watch(self, session_id: str, runtime: _Session) -> None:
        assert runtime.media is not None
        try:
            while True:
                now = asyncio.get_running_loop().time()
                if runtime.connected_at is None:
                    deadline = runtime.started_at + self.negotiation_seconds
                    reason = "negotiation_timeout"
                else:
                    deadline = (runtime.media.last_received_at or runtime.connected_at) + self.inactivity_seconds
                    reason = "audio_timeout"
                maximum = runtime.started_at + self.maximum_seconds
                if maximum < deadline:
                    deadline, reason = maximum, "duration_limit"
                if now >= deadline:
                    await self.finish(session_id, reason=reason, failed=reason != "duration_limit")
                    return
                try:
                    event = await asyncio.wait_for(runtime.media.events.get(), min(0.25, deadline - now))
                except TimeoutError:
                    continue
                if event == "connected" and runtime.connected_at is None:
                    runtime.connected_at = asyncio.get_running_loop().time()
                    runtime.record["state"] = "active"
                    self.repository.transition(session_id, "active")
                elif event in {"greeting_playing", "greeting_completed"}:
                    runtime.record["greeting_state"] = event.removeprefix("greeting_")
                    self.repository.greeting(session_id, event.removeprefix("greeting_"))
                elif event in {"disconnected", "input_ended", "media_failed"}:
                    await self.finish(session_id, reason=event, failed=event == "media_failed")
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.finish(session_id, reason="supervision_failed", failed=True)

    async def finish(self, session_id: str, *, reason: str = "hangup", failed: bool = False) -> dict:
        runtime = self._sessions.get(session_id)
        if runtime is None:
            return self.get(session_id)
        if runtime.closing is not None and runtime.closing.done() and runtime.persistence_pending:
            runtime.closing = None
        if runtime.closing is None:
            runtime.closing = asyncio.create_task(self._close(session_id, runtime, reason, failed))
            runtime.closing.add_done_callback(lambda task: None if task.cancelled() else task.exception())
        await asyncio.shield(runtime.closing)
        return self.get(session_id)

    async def _close(self, session_id: str, runtime: _Session, reason: str, failed: bool) -> None:
        if runtime.final_reason is None:
            runtime.final_reason, runtime.final_failed = reason, failed
        runtime.persistence_pending = True
        try:
            self.repository.transition(session_id, "ending")
        except Exception:
            # La durabilidad puede recuperarse; el audio debe cerrarse igualmente.
            pass
        tasks = [task for task in (runtime.negotiation, runtime.watcher) if task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if not runtime.cleanup_complete or runtime.media_finalization_pending:
            try:
                if runtime.media is not None:
                    await asyncio.wait_for(runtime.media.close(), timeout=5)
                runtime.cleanup_complete = True
                runtime.media_finalization_pending = False
            except CallMediaPersistenceError as error:
                runtime.cleanup_complete = error.resources_released
                runtime.media_finalization_pending = True
                raise CallPersistenceError(session_id) from None
            except Exception:
                runtime.final_reason, runtime.final_failed = "media_close_failed", True
                self._stopping = True
        if runtime.record["greeting_state"] == "playing":
            runtime.record["greeting_state"] = "failed" if runtime.final_failed else "interrupted"
        try:
            self.repository.end(
                session_id, "failed" if runtime.final_failed else "ended", runtime.final_reason,
                dict(runtime.media.metrics) if runtime.media is not None else {}, runtime.cleanup_complete,
                runtime.record["greeting_state"],
            )
        except Exception:
            raise CallPersistenceError(session_id) from None
        runtime.persistence_pending = False
        self._sessions.pop(session_id, None)

    async def shutdown(self) -> None:
        self._stopping = True
        try:
            await asyncio.gather(*(
                self.finish(session_id, reason="server_shutdown")
                for session_id in list(self._sessions)
            ))
        finally:
            self.repository.close()
