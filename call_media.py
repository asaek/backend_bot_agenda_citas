"""Transporte WebRTC opcional del laboratorio; audio PCM temporal y Opus en red."""

import asyncio
import math
import wave
from collections import deque
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from aiortc import (
    AudioStreamTrack,
    RTCConfiguration,
    RTCPeerConnection,
    RTCRtpSender,
    RTCSessionDescription,
)
from aiortc.mediastreams import MediaStreamError


def validate_greeting(path: Path) -> None:
    with wave.open(str(path), "rb") as source:
        if (
            source.getnchannels() != 1
            or source.getsampwidth() != 2
            or source.getframerate() not in {16000, 48000}
            or source.getcomptype() != "NONE"
            or not 0 < source.getnframes() <= source.getframerate() * 30
        ):
            raise ValueError("El saludo debe ser WAV PCM16 mono, 16/48 kHz y hasta 30 segundos")
        if len(source.readframes(source.getnframes())) != source.getnframes() * 2:
            raise ValueError("El archivo del saludo esta truncado")


class _GreetingTrack(AudioStreamTrack):
    def __init__(self, path: Path, ready: asyncio.Event, emit) -> None:
        super().__init__()
        self._source = wave.open(str(path), "rb")
        self._rate = self._source.getframerate()
        self._frame_samples = self._rate // 50
        self._ready = ready
        self._emit = emit
        self._started_at = None
        self._position = 0
        self._drain_frames = 0
        self._complete = False
        self.sent_samples = 0
        self.sent_frames = 0

    async def recv(self) -> av.AudioFrame:
        await self._ready.wait()
        if self.readyState != "live":
            raise MediaStreamError
        loop = asyncio.get_running_loop()
        if self._started_at is None:
            self._started_at = loop.time()
            self._emit("greeting_playing")
        await asyncio.sleep(max(0, self._started_at + self._position / self._rate - loop.time()))
        raw = self._source.readframes(self._frame_samples)
        pcm = np.zeros((1, self._frame_samples), dtype=np.int16)
        if raw:
            values = np.frombuffer(raw, dtype="<i2")
            pcm[0, :len(values)] = values
            self.sent_samples += len(values)
            self.sent_frames += 1
        elif not self._complete:
            # Los paquetes de silencio permiten drenar el encoder y el jitter remoto.
            self._drain_frames += 1
            if self._drain_frames >= 15:
                self._complete = True
                self._emit("greeting_completed")
        frame = av.AudioFrame.from_ndarray(pcm, format="s16", layout="mono")
        frame.sample_rate = self._rate
        frame.pts = self._position
        frame.time_base = Fraction(1, self._rate)
        self._position += self._frame_samples
        return frame

    def stop(self) -> None:
        self._source.close()
        super().stop()

    @property
    def sent_seconds(self) -> float:
        return self.sent_samples / self._rate


class _StreamingTrack(AudioStreamTrack):
    """Reloj de salida PCM24k; el proveedor puede generar mas rapido que la llamada."""

    def __init__(self, drained, maximum_seconds: int = 30, *, started=None):
        super().__init__()
        self._drained = drained
        self._started = started
        self._queue = deque()
        self._queued_bytes = 0
        self._maximum_bytes = maximum_seconds * 24000 * 2
        self.peak_queued_ms = 0
        self._ended = set()
        self._deadlines = {}
        self.sent_samples = {}
        self._started_at = None
        self._position = 0

    @property
    def queued_ms(self):
        return round(self._queued_bytes / 48)

    def enqueue(self, item_id: str, pcm: bytes):
        if len(pcm) % 2 or self._queued_bytes + len(pcm) > self._maximum_bytes:
            raise ValueError("Buffer de reproduccion excedido o PCM invalido")
        if pcm:
            self._queue.append((item_id, bytearray(pcm)))
            self._queued_bytes += len(pcm)
            self.peak_queued_ms = max(self.peak_queued_ms, self.queued_ms)
            self._deadlines.pop(item_id, None)

    def complete(self, item_id: str):
        self._ended.add(item_id)

    def interrupt(self) -> dict[str, int]:
        emitted = {key: samples // 24 for key, samples in self.sent_samples.items()}
        self._queue.clear()
        self._queued_bytes = 0
        self._ended.clear()
        self._deadlines.clear()
        return emitted

    async def recv(self):
        if self.readyState != "live":
            raise MediaStreamError
        loop = asyncio.get_running_loop()
        if self._started_at is None:
            self._started_at = loop.time()
        await asyncio.sleep(max(0, self._started_at + self._position / 24000 - loop.time()))
        data = bytearray()
        while self._queue and len(data) < 960:
            item_id, pending = self._queue[0]
            count = min(960 - len(data), len(pending))
            data.extend(pending[:count])
            del pending[:count]
            self._queued_bytes -= count
            if item_id not in self.sent_samples and self._started:
                self._started(item_id, loop.time())
            self.sent_samples[item_id] = self.sent_samples.get(item_id, 0) + count // 2
            if not pending:
                self._queue.popleft()
        queued_items = {item_id for item_id, _ in self._queue}
        for item_id in list(self._ended):
            if item_id not in queued_items:
                deadline = self._deadlines.setdefault(item_id, loop.time() + .3)
                if loop.time() >= deadline:
                    self._ended.remove(item_id)
                    self._deadlines.pop(item_id, None)
                    self._drained(item_id, self.sent_samples.get(item_id, 0) // 24)
        data.extend(bytes(960 - len(data)))
        frame = av.AudioFrame.from_ndarray(np.frombuffer(data, dtype="<i2").reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate, frame.pts, frame.time_base = 24000, self._position, Fraction(1, 24000)
        self._position += 480
        return frame

    def stop(self):
        self.interrupt()
        super().stop()


class AiortcCallMedia:
    def __init__(self, greeting_path: Path | None = None) -> None:
        if greeting_path is not None:
            validate_greeting(greeting_path)
        self.events: asyncio.Queue[str] = asyncio.Queue(maxsize=16)
        self.last_received_at: float | None = None
        self._closed = False
        self._close_lock = asyncio.Lock()
        self._signal = asyncio.Event()
        self._received_frames = self._non_silent_frames = self._received_samples = 0
        self._received_seconds = self._sum_squares = self._peak = 0.0
        self._tasks: set[asyncio.Task] = set()
        self.input_audio: asyncio.Queue[bytes] = asyncio.Queue(maxsize=50)
        self.output_events: asyncio.Queue[tuple[str, int]] = asyncio.Queue(maxsize=32)
        self.output_started: asyncio.Queue[tuple[str, float]] = asyncio.Queue(maxsize=32)
        self._resampler = av.AudioResampler(format="s16", layout="mono", rate=24000)
        self._greeting = _GreetingTrack(greeting_path, self._signal, self._emit) if greeting_path is not None else None
        self._streaming = _StreamingTrack(self._output_drained, started=self._output_started) if self._greeting is None else None
        self._peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        self._peer.addTrack(self._greeting or self._streaming)
        opus = [c for c in RTCRtpSender.getCapabilities("audio").codecs if c.mimeType.lower() == "audio/opus"]
        self._peer.getTransceivers()[0].setCodecPreferences(opus)

        @self._peer.on("connectionstatechange")
        def connection_changed():
            state = self._peer.connectionState
            if state == "connected":
                self._emit("connected")
            elif state == "failed":
                self._emit("media_failed")
            elif state == "closed":
                self._emit("disconnected")

        @self._peer.on("iceconnectionstatechange")
        def ice_changed():
            if self._peer.iceConnectionState in {"disconnected", "failed"}:
                self._emit("disconnected")

        @self._peer.on("track")
        def incoming_track(track):
            if track.kind != "audio":
                self._emit("media_failed")
                return
            task = asyncio.create_task(self._receive(track))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    def _emit(self, event: str) -> None:
        if not self._closed and not self.events.full():
            self.events.put_nowait(event)

    def _output_drained(self, item_id: str, emitted_ms: int):
        if not self.output_events.full():
            self.output_events.put_nowait((item_id, emitted_ms))
        else:
            self._emit("media_failed")

    def _output_started(self, item_id: str, started_at: float):
        if not self.output_started.full():
            self.output_started.put_nowait((item_id, started_at))
        else:
            self._emit("media_failed")

    def output_audio(self, item_id: str, pcm: bytes):
        self._streaming.enqueue(item_id, pcm)

    def output_done(self, item_id: str):
        self._streaming.complete(item_id)

    def interrupt_output(self) -> dict[str, int]:
        return self._streaming.interrupt()

    async def negotiate(self, offer_sdp: str) -> str:
        await self._peer.setRemoteDescription(RTCSessionDescription(sdp=offer_sdp, type="offer"))
        transceivers = self._peer.getTransceivers()
        if len(transceivers) != 1 or transceivers[0].kind != "audio":
            raise ValueError("El laboratorio admite una pista de audio bidireccional")
        await self._peer.setLocalDescription(await self._peer.createAnswer())
        if transceivers[0].currentDirection != "sendrecv":
            raise ValueError("Se requiere audio en ambos sentidos")
        return self._peer.localDescription.sdp

    async def _receive(self, track) -> None:
        try:
            while True:
                frame = await track.recv()
                pcm = frame.to_ndarray().astype(np.float64).reshape(-1)
                peak = float(np.max(np.abs(pcm)))
                self._received_frames += 1
                self._received_samples += pcm.size
                self._received_seconds += frame.samples / frame.sample_rate
                self._sum_squares += float(np.dot(pcm, pcm))
                self._peak = max(self._peak, peak)
                self.last_received_at = asyncio.get_running_loop().time()
                if peak > 500:
                    self._non_silent_frames += 1
                    self._signal.set()
                if self._streaming is not None:
                    for converted in self._resampler.resample(frame):
                        self.input_audio.put_nowait(converted.to_ndarray().tobytes())
        except MediaStreamError:
            self._emit("input_ended")
        except asyncio.CancelledError:
            raise
        except Exception:
            self._emit("media_failed")

    @property
    def metrics(self) -> dict:
        return {
            "codec": "opus",
            "received_frames": self._received_frames,
            "non_silent_frames": self._non_silent_frames,
            "received_audio_seconds": round(self._received_seconds, 3),
            "received_rms_pcm16": round(math.sqrt(self._sum_squares / max(1, self._received_samples)), 1),
            "received_peak_pcm16": self._peak,
            "input_queued_frames": self.input_audio.qsize(),
            "greeting_sent_frames": self._greeting.sent_frames if self._greeting else 0,
            "greeting_sent_seconds": round(self._greeting.sent_seconds, 3) if self._greeting else 0,
            **({"playback_queued_ms": self._streaming.queued_ms,
                "playback_peak_queued_ms": self._streaming.peak_queued_ms} if self._streaming else {}),
        }

    async def close(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            self._closed = True
            (self._greeting or self._streaming).stop()
            tasks = list(self._tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._tasks.clear()
            await self._peer.close()
