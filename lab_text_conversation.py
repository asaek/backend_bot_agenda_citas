"""Texto del paciente ficticio en la misma conversacion Realtime del laboratorio."""

import asyncio
from uuid import uuid4

from voice_session import VoiceSession


class TextMedia:
    """Una sesion de texto no crea WebRTC ni dispositivos de audio."""

    def __init__(self):
        self.events = asyncio.Queue()
        self.input_audio = asyncio.Queue()
        self.output_events = asyncio.Queue()
        self.last_received_at = None
        self.metrics = {"received_frames": 0, "non_silent_frames": 0}

    async def negotiate(self, offer):
        return ""

    def interrupt_output(self):
        return {}

    def output_audio(self, item_id, pcm):
        raise ValueError("La sesion de texto no admite salida de audio")

    def output_done(self, item_id):
        pass

    async def close(self):
        pass


class LaboratoryTextConversation:
    def __init__(self, *, repository, settings, provider_factory, business_hours, profile):
        self.repository, self.settings = repository, settings
        self.provider_factory, self.business_hours, self.profile = provider_factory, business_hours, profile
        self.session = None
        self._watcher = None

    async def ensure_session(self):
        if self.session is not None and not self.session.closed:
            return self.session
        await self.close()
        session = VoiceSession(session_id="text-" + uuid4().hex, media=TextMedia(), provider=self.provider_factory(),
            repository=self.repository, settings=self.settings, business_hours=self.business_hours, profile=self.profile)
        self.session = session
        try:
            await session.negotiate("")
        except BaseException:
            await session.close()
            raise
        self._watcher = asyncio.create_task(self._watch(session))
        return session

    async def _watch(self, session):
        try:
            async with asyncio.timeout(self.settings.maximum_seconds):
                while True:
                    event = await session.events.get()
                    if event in {"disconnected", "media_failed", "input_ended"}:
                        return
        except TimeoutError:
            pass
        finally:
            await session.close()

    async def close(self):
        watcher, self._watcher = self._watcher, None
        if watcher:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
        if self.session:
            await self.session.close()
            self.session = None
