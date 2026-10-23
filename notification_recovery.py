"""Ciclo comun de recuperacion de avisos registrados, independiente de la agenda."""

import asyncio
import logging
from dataclasses import dataclass

from notification_domain import AppointmentNotificationEvent
from notification_trigger import DoctorNotificationContext


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotificationBatch:
    source_id: str | int
    events: tuple[AppointmentNotificationEvent, ...]
    context: DoctorNotificationContext | None = None


class NotificationRecoveryWorker:
    def __init__(self, trigger, load_pending, complete, *, retry_seconds=60, trigger_factory=None):
        self.trigger = trigger
        self.trigger_factory = trigger_factory
        self.load_pending, self.complete = load_pending, complete
        self.retry_seconds = retry_seconds
        self._wake = asyncio.Event()
        self._lock = asyncio.Lock()
        self._task = None

    @property
    def enabled(self):
        return self.trigger is not None and self.trigger.enabled

    def wake(self):
        self._wake.set()

    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def flush(self):
        async with self._lock:
            if self.trigger_factory:
                self.trigger = self.trigger_factory()
            if not self.enabled:
                return
            batches = await asyncio.to_thread(self.load_pending)
            seen = set()
            for batch in batches:
                try:
                    completed = True
                    for event in batch.events:
                        seen.add(event.event_key)
                        sent = await self.trigger.notify(event, context=batch.context)
                        completed = sent and completed
                    if completed:
                        await asyncio.to_thread(self.complete, batch.source_id)
                except Exception as error:
                    logger.warning("No se pudo recuperar un aviso: %s", type(error).__name__)
            await self.trigger.recover_pending(exclude=seen)

    async def _run(self):
        while True:
            self._wake.clear()
            try:
                await self.flush()
            except Exception as error:
                logger.warning("No se pudo procesar la bandeja de avisos: %s", type(error).__name__)
            try:
                await asyncio.wait_for(self._wake.wait(), self.retry_seconds)
            except TimeoutError:
                pass

    async def close(self):
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
