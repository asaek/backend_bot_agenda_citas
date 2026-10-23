"""Conexion Realtime GA de servidor: audio nativo y herramientas, sin agente de texto."""

import asyncio
import base64
import json
import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlencode


class RealtimeError(RuntimeError):
    """Error seguro: nunca incluye cuerpos de proveedor ni credenciales."""


@dataclass(frozen=True)
class RealtimeSettings:
    api_key: str = field(repr=False)
    model: str = "gpt-realtime-2.1"
    voice: str = "marin"
    transcription_model: str = "gpt-4o-mini-transcribe"
    maximum_seconds: float = 300
    idle_seconds: float = 30
    maximum_sessions: int | None = 5

    def __post_init__(self):
        if not self.api_key or self.api_key.startswith("replace-"):
            raise ValueError("Configura OPENAI_REALTIME_API_KEY u OPENAI_API_KEY")
        if not all(isinstance(v, str) and v.strip() for v in (self.model, self.voice, self.transcription_model)):
            raise ValueError("Modelo, voz y transcripcion deben configurarse")
        if any(not math.isfinite(v) or not 0 < v <= 600 for v in (self.maximum_seconds, self.idle_seconds)):
            raise ValueError("Los plazos de voz deben estar entre 0 y 600 segundos")
        if self.maximum_sessions is not None and (
            not isinstance(self.maximum_sessions, int)
            or isinstance(self.maximum_sessions, bool)
            or not 1 <= self.maximum_sessions <= 100
        ):
            raise ValueError("VOICE_MAX_SESSIONS debe ser unlimited o un numero entre 1 y 100")

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None):
        values = os.environ if environment is None else environment
        maximum_sessions_value = values.get("VOICE_MAX_SESSIONS", "5").strip().lower()
        maximum_sessions = (
            None if maximum_sessions_value == "unlimited" else int(maximum_sessions_value)
        )
        return cls(
            api_key=values.get("OPENAI_REALTIME_API_KEY") or values.get("OPENAI_API_KEY", ""),
            model=values.get("VOICE_MODEL", "gpt-realtime-2.1"),
            voice=values.get("VOICE_VOICE", "marin"),
            transcription_model=values.get("VOICE_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe"),
            maximum_seconds=float(values.get("VOICE_MAXIMUM_SECONDS", "300")),
            idle_seconds=float(values.get("VOICE_IDLE_SECONDS", "30")),
            maximum_sessions=maximum_sessions,
        )


class RealtimeProvider(Protocol):
    async def connect(self, instructions: str, tools: list[dict], history: list[dict]) -> None: ...
    async def send(self, event: dict) -> None: ...
    async def receive(self) -> dict: ...
    async def close(self) -> None: ...


def greeting_response(metadata: dict[str, str]) -> dict:
    """Saludo fuera de la conversacion: no recibe historial ni herramientas."""
    return {
        "metadata": metadata,
        "conversation": "none",
        "input": [],
        "output_modalities": ["audio"],
        "tools": [],
        "tool_choice": "none",
        "instructions": (
            "Habla español de Mexico, con voz natural. Di unicamente: "
            "Hola, soy el asistente virtual del consultorio. ¿En qué puedo ayudarte hoy?"
        ),
    }


class OpenAIRealtimeProvider:
    def __init__(self, settings: RealtimeSettings, *, connector=None):
        self.settings = settings
        self._connector = connector
        self._socket = None
        self._send_lock = asyncio.Lock()
        self.error_code = None

    async def connect(self, instructions: str, tools: list[dict], history: list[dict]) -> None:
        from websockets.asyncio.client import connect

        connector = self._connector or connect
        try:
            self._socket = await connector(
                "wss://api.openai.com/v1/realtime?" + urlencode({"model": self.settings.model}),
                additional_headers={"Authorization": "Bearer " + self.settings.api_key},
                open_timeout=10, close_timeout=2, max_size=2**20, max_queue=16,
            )
            async with asyncio.timeout(10):
                await self._wait_for("session.created")
                await self.send({"type": "session.update", "session": {
                    "type": "realtime", "model": self.settings.model,
                    "instructions": instructions, "output_modalities": ["audio"],
                    "max_output_tokens": 512,
                    "audio": {
                        "input": {
                            "format": {"type": "audio/pcm", "rate": 24000},
                            "transcription": {"model": self.settings.transcription_model, "language": "es"},
                            "turn_detection": {"type": "server_vad", "silence_duration_ms": 500,
                                               "create_response": False, "interrupt_response": False},
                        },
                        "output": {"format": {"type": "audio/pcm", "rate": 24000}, "voice": self.settings.voice},
                    },
                    "tools": tools, "tool_choice": "auto",
                }})
                await self._wait_for("session.updated")
                for item in history:
                    await self.send({"type": "conversation.item.create", "item": item})
        except BaseException as error:
            await self.close()
            if isinstance(error, asyncio.CancelledError):
                raise
            raise RealtimeError("No se pudo iniciar OpenAI Realtime") from None

    async def _wait_for(self, kind):
        for _ in range(32):
            event = await self.receive()
            if event.get("type") == kind:
                return
            if event.get("type") == "error":
                break
        raise RealtimeError("Configuracion Realtime rechazada")

    async def send(self, event: dict) -> None:
        try:
            async with self._send_lock:
                async with asyncio.timeout(5):
                    await self._socket.send(json.dumps(event))
        except asyncio.CancelledError:
            raise
        except Exception:
            raise RealtimeError("Fallo al enviar un evento Realtime") from None

    async def send_audio(self, pcm: bytes) -> None:
        await self.send({"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm).decode("ascii")})

    async def receive(self) -> dict:
        try:
            event = json.loads(await self._socket.recv())
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                raise ValueError
            if event["type"] == "error":
                code = event.get("error", {}).get("code", "")
                self.error_code = code if isinstance(code, str) and re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", code) else "provider_error"
            return event
        except asyncio.CancelledError:
            raise
        except Exception:
            raise RealtimeError("Conexion Realtime cerrada o evento invalido") from None

    async def close(self) -> None:
        socket, self._socket = self._socket, None
        if socket is not None:
            await socket.close()
