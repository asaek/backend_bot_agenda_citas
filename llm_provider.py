import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx


DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_LLM_PROVIDER = "groq"
DEFAULT_LLM_TIMEOUT_SECONDS = 20.0
DEFAULT_LLM_MAX_HISTORY_MESSAGES = 30
DEFAULT_LLM_MAX_OUTPUT_TOKENS = 500


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class LLMSettings:
    provider: str
    api_key: str
    model: str
    base_url: str
    timeout_seconds: float
    max_history_messages: int
    max_output_tokens: int


class LLMProviderError(RuntimeError):
    """Indica que el proveedor no pudo generar una respuesta."""


class LLMConfigurationError(LLMProviderError):
    """Indica que falta o es invalida la configuracion del LLM."""


class LLMProvider(Protocol):
    async def generate(self, messages: Sequence[ChatMessage]) -> str:
        """Genera una respuesta de texto usando los mensajes recibidos."""


def load_llm_settings(environment: Mapping[str, str] | None = None) -> LLMSettings:
    values = os.environ if environment is None else environment

    provider = values.get("LLM_PROVIDER", DEFAULT_LLM_PROVIDER).strip().lower()
    api_key = values.get("LLM_API_KEY", "").strip()
    model = values.get("LLM_MODEL", "").strip()
    base_url = values.get("LLM_BASE_URL", DEFAULT_GROQ_BASE_URL).strip()

    if not api_key:
        raise LLMConfigurationError("LLM_API_KEY no esta configurado")
    if not model:
        raise LLMConfigurationError("LLM_MODEL no esta configurado")
    if not base_url:
        raise LLMConfigurationError("LLM_BASE_URL no puede estar vacio")

    timeout_seconds = _positive_float(
        values.get("LLM_TIMEOUT_SECONDS"),
        name="LLM_TIMEOUT_SECONDS",
        default=DEFAULT_LLM_TIMEOUT_SECONDS,
    )
    max_history_messages = _positive_int(
        values.get("LLM_MAX_HISTORY_MESSAGES"),
        name="LLM_MAX_HISTORY_MESSAGES",
        default=DEFAULT_LLM_MAX_HISTORY_MESSAGES,
    )
    max_output_tokens = _positive_int(
        values.get("LLM_MAX_OUTPUT_TOKENS"),
        name="LLM_MAX_OUTPUT_TOKENS",
        default=DEFAULT_LLM_MAX_OUTPUT_TOKENS,
    )

    return LLMSettings(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url.rstrip("/"),
        timeout_seconds=timeout_seconds,
        max_history_messages=max_history_messages,
        max_output_tokens=max_output_tokens,
    )


def create_llm_provider(settings: LLMSettings | None = None) -> LLMProvider:
    resolved_settings = settings or load_llm_settings()
    if resolved_settings.provider != "groq":
        raise LLMConfigurationError(
            f"LLM_PROVIDER no soportado: {resolved_settings.provider}"
        )
    return GroqLLMProvider(resolved_settings)


class GroqLLMProvider:
    def __init__(
        self,
        settings: LLMSettings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.http_client = http_client

    async def generate(self, messages: Sequence[ChatMessage]) -> str:
        if not messages:
            raise LLMProviderError("El LLM requiere al menos un mensaje")

        payload = {
            "model": self.settings.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "max_tokens": self.settings.max_output_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }

        try:
            if self.http_client is not None:
                response = await self.http_client.post(
                    f"{self.settings.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            else:
                async with httpx.AsyncClient(
                    timeout=self.settings.timeout_seconds
                ) as client:
                    response = await client.post(
                        f"{self.settings.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
        except httpx.HTTPError as error:
            raise LLMProviderError("Groq no pudo generar la respuesta") from error
        except (TypeError, ValueError) as error:
            raise LLMProviderError("Groq devolvio una respuesta invalida") from error

        try:
            choices = data["choices"]
            content = choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise LLMProviderError("Groq devolvio una respuesta sin contenido") from error

        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError("Groq devolvio una respuesta vacia")
        return content.strip()


def _positive_float(value: str | None, name: str, default: float) -> float:
    try:
        parsed = default if value is None else float(value)
    except ValueError as error:
        raise LLMConfigurationError(f"{name} debe ser un numero positivo") from error
    if parsed <= 0:
        raise LLMConfigurationError(f"{name} debe ser un numero positivo")
    return parsed


def _positive_int(value: str | None, name: str, default: int) -> int:
    try:
        parsed = default if value is None else int(value)
    except ValueError as error:
        raise LLMConfigurationError(f"{name} debe ser un entero positivo") from error
    if parsed <= 0:
        raise LLMConfigurationError(f"{name} debe ser un entero positivo")
    return parsed
