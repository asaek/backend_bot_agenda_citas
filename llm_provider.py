import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

import httpx

from tool_contracts import llm_tool_definitions


DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_LLM_PROVIDER = "groq"
DEFAULT_LLM_TIMEOUT_SECONDS = 20.0
DEFAULT_LLM_MAX_HISTORY_MESSAGES = 30
DEFAULT_LLM_MAX_OUTPUT_TOKENS = 500
DEFAULT_LLM_MAX_RESPONSE_CHARACTERS = 4000
DEFAULT_LLM_MAX_TOOL_ITERATIONS = 3
SUPPORTED_LLM_PROVIDERS = frozenset({"groq", "openrouter"})
DEFAULT_BASE_URLS = {
    "groq": DEFAULT_GROQ_BASE_URL,
    "openrouter": DEFAULT_OPENROUTER_BASE_URL,
}


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Solicitud no confiable de una herramienta propuesta por el LLM."""

    name: str
    arguments: Mapping[str, object]
    call_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("El nombre de la herramienta no puede estar vacio")
        if not isinstance(self.arguments, Mapping):
            raise ValueError("Los argumentos de la herramienta deben ser un objeto")
        if self.call_id is not None and (
            not isinstance(self.call_id, str) or not self.call_id.strip()
        ):
            raise ValueError("El identificador de la herramienta no es valido")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))
        if self.call_id is not None:
            object.__setattr__(self, "call_id", self.call_id.strip())


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str | None
    tool_calls: Sequence[ToolCall] = ()
    tool_call_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))


LLMResponse = str | ToolCall


@dataclass(frozen=True, slots=True)
class LLMSettings:
    provider: str
    api_key: str
    model: str
    base_url: str
    timeout_seconds: float
    max_history_messages: int
    max_output_tokens: int
    max_response_characters: int = DEFAULT_LLM_MAX_RESPONSE_CHARACTERS
    max_tool_iterations: int = DEFAULT_LLM_MAX_TOOL_ITERATIONS


class LLMProviderError(RuntimeError):
    """Indica que el proveedor no pudo generar una respuesta."""


class LLMConfigurationError(LLMProviderError):
    """Indica que falta o es invalida la configuracion del LLM."""


class LLMTimeoutError(LLMProviderError):
    """Indica que el proveedor excedio el tiempo de espera."""


class LLMNetworkError(LLMProviderError):
    """Indica que no se pudo conectar con el proveedor."""


class LLMHTTPError(LLMProviderError):
    """Indica que el proveedor devolvio un error HTTP."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"El proveedor LLM devolvio HTTP {status_code}")


class LLMResponseError(LLMProviderError):
    """Indica que el proveedor devolvio una respuesta invalida o vacia."""


class LLMResponseTooLongError(LLMProviderError):
    """Indica que la respuesta supera el limite permitido."""


class LLMProvider(Protocol):
    async def generate(self, messages: Sequence[ChatMessage]) -> LLMResponse:
        """Genera texto o una solicitud de herramienta usando los mensajes."""


def load_llm_settings(environment: Mapping[str, str] | None = None) -> LLMSettings:
    values = os.environ if environment is None else environment

    provider = values.get("LLM_PROVIDER", DEFAULT_LLM_PROVIDER).strip().lower()
    api_key = values.get("LLM_API_KEY", "").strip()
    model = values.get("LLM_MODEL", "").strip()
    base_url = values.get(
        "LLM_BASE_URL",
        DEFAULT_BASE_URLS.get(provider, DEFAULT_GROQ_BASE_URL),
    ).strip()

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
    max_response_characters = _positive_int(
        values.get("LLM_MAX_RESPONSE_CHARACTERS"),
        name="LLM_MAX_RESPONSE_CHARACTERS",
        default=DEFAULT_LLM_MAX_RESPONSE_CHARACTERS,
    )
    max_tool_iterations = _positive_int(
        values.get("LLM_MAX_TOOL_ITERATIONS"),
        name="LLM_MAX_TOOL_ITERATIONS",
        default=DEFAULT_LLM_MAX_TOOL_ITERATIONS,
    )

    return LLMSettings(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url.rstrip("/"),
        timeout_seconds=timeout_seconds,
        max_history_messages=max_history_messages,
        max_output_tokens=max_output_tokens,
        max_response_characters=max_response_characters,
        max_tool_iterations=max_tool_iterations,
    )


def create_llm_provider(settings: LLMSettings | None = None) -> LLMProvider:
    resolved_settings = settings or load_llm_settings()
    if resolved_settings.provider not in SUPPORTED_LLM_PROVIDERS:
        raise LLMConfigurationError(
            f"LLM_PROVIDER no soportado: {resolved_settings.provider}"
        )
    return OpenAICompatibleLLMProvider(resolved_settings)


class OpenAICompatibleLLMProvider:
    def __init__(
        self,
        settings: LLMSettings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.http_client = http_client

    async def generate(self, messages: Sequence[ChatMessage]) -> LLMResponse:
        if not messages:
            raise LLMProviderError("El LLM requiere al menos un mensaje")

        request_messages: list[dict[str, object]] = []
        for index, message in enumerate(messages, start=1):
            request_message: dict[str, object] = {
                "role": message.role,
                "content": message.content,
            }
            if message.tool_calls:
                request_message["tool_calls"] = [
                    {
                        "id": tool_call.call_id or f"tool-call-{index}",
                        "type": "function",
                        "function": {
                            "name": tool_call.name,
                            "arguments": json.dumps(
                                dict(tool_call.arguments),
                                ensure_ascii=False,
                            ),
                        },
                    }
                    for tool_call in message.tool_calls
                ]
            if message.tool_call_id is not None:
                request_message["tool_call_id"] = message.tool_call_id
            request_messages.append(request_message)

        payload = {
            "model": self.settings.model,
            "messages": request_messages,
            "max_tokens": self.settings.max_output_tokens,
            "tools": llm_tool_definitions(),
            "tool_choice": "auto",
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
        except httpx.TimeoutException as error:
            raise LLMTimeoutError(
                f"{self.settings.provider} excedio el tiempo de espera"
            ) from error
        except httpx.HTTPStatusError as error:
            raise LLMHTTPError(error.response.status_code) from error
        except httpx.ConnectError as error:
            raise LLMNetworkError(
                f"{self.settings.provider} no pudo conectarse"
            ) from error
        except httpx.HTTPError as error:
            raise LLMNetworkError(
                f"{self.settings.provider} no pudo comunicarse"
            ) from error
        except (TypeError, ValueError) as error:
            raise LLMResponseError(
                f"{self.settings.provider} devolvio una respuesta invalida"
            ) from error

        return self._parse_response(data)

    def _parse_response(self, data: object) -> LLMResponse:
        try:
            choices = data["choices"]  # type: ignore[index]
            message = choices[0]["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise LLMResponseError(
                f"{self.settings.provider} devolvio una respuesta sin contenido"
            ) from error

        if not isinstance(message, Mapping):
            raise LLMResponseError(
                f"{self.settings.provider} devolvio un mensaje invalido"
            )

        direct_tool_call = message.get("tool_call")
        native_tool_calls = message.get("tool_calls")
        if direct_tool_call is not None and native_tool_calls:
            raise LLMResponseError(
                f"{self.settings.provider} devolvio mas de un tipo de respuesta"
            )
        if direct_tool_call is not None:
            return _parse_tool_call(direct_tool_call)
        if native_tool_calls is not None:
            if not isinstance(native_tool_calls, list):
                raise LLMResponseError(
                    f"{self.settings.provider} devolvio tool_calls invalidos"
                )
            if len(native_tool_calls) > 1:
                raise LLMResponseError(
                    f"{self.settings.provider} devolvio mas de una herramienta"
                )
            if native_tool_calls:
                return _parse_tool_call(native_tool_calls[0], native=True)

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseError(f"{self.settings.provider} devolvio una respuesta vacia")
        content = content.strip()
        if len(content) > self.settings.max_response_characters:
            raise LLMResponseTooLongError(
                f"{self.settings.provider} devolvio una respuesta demasiado larga"
            )
        return content


GroqLLMProvider = OpenAICompatibleLLMProvider


def _parse_tool_call(value: object, *, native: bool = False) -> ToolCall:
    if not isinstance(value, Mapping):
        raise LLMResponseError("La llamada de herramienta debe ser un objeto")

    if native:
        if value.get("type") not in (None, "function"):
            raise LLMResponseError("El tipo de llamada de herramienta no es valido")
        function = value.get("function")
        if not isinstance(function, Mapping):
            raise LLMResponseError("La funcion de la llamada de herramienta no es valida")
        name = function.get("name")
        raw_arguments = function.get("arguments")
    else:
        name = value.get("name")
        raw_arguments = value.get("arguments")
    call_id = value.get("id") if native else value.get("call_id", value.get("id"))
    if call_id is not None and (
        not isinstance(call_id, str) or not call_id.strip()
    ):
        raise LLMResponseError("El identificador de la herramienta no es valido")

    if not isinstance(name, str) or not name.strip():
        raise LLMResponseError("La llamada de herramienta no tiene un nombre valido")

    if isinstance(raw_arguments, str):
        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as error:
            raise LLMResponseError(
                "Los argumentos de la herramienta no son JSON valido"
            ) from error
    else:
        arguments = raw_arguments

    if not isinstance(arguments, Mapping):
        raise LLMResponseError("Los argumentos de la herramienta deben ser un objeto")

    return ToolCall(name=name, arguments=arguments, call_id=call_id)


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
