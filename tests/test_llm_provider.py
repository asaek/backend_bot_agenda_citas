import asyncio
import json
import unittest

import httpx

from llm_provider import (
    ChatMessage,
    GroqLLMProvider,
    LLMConfigurationError,
    LLMProviderError,
    LLMSettings,
    create_llm_provider,
    load_llm_settings,
)


class LLMSettingsTests(unittest.TestCase):
    def test_loads_groq_settings_from_environment_values(self) -> None:
        settings = load_llm_settings(
            {
                "LLM_PROVIDER": "groq",
                "LLM_API_KEY": "test-key",
                "LLM_MODEL": "test-model",
                "LLM_BASE_URL": "https://example.test/",
                "LLM_TIMEOUT_SECONDS": "12.5",
                "LLM_MAX_HISTORY_MESSAGES": "10",
                "LLM_MAX_OUTPUT_TOKENS": "250",
            }
        )

        self.assertEqual(settings.provider, "groq")
        self.assertEqual(settings.api_key, "test-key")
        self.assertEqual(settings.model, "test-model")
        self.assertEqual(settings.base_url, "https://example.test")
        self.assertEqual(settings.timeout_seconds, 12.5)
        self.assertEqual(settings.max_history_messages, 10)
        self.assertEqual(settings.max_output_tokens, 250)

    def test_uses_safe_defaults_for_optional_limits(self) -> None:
        settings = load_llm_settings(
            {"LLM_API_KEY": "test-key", "LLM_MODEL": "test-model"}
        )

        self.assertEqual(settings.timeout_seconds, 20.0)
        self.assertEqual(settings.max_history_messages, 30)
        self.assertEqual(settings.max_output_tokens, 500)

    def test_requires_api_key_and_model(self) -> None:
        with self.assertRaises(LLMConfigurationError):
            load_llm_settings({"LLM_MODEL": "test-model"})
        with self.assertRaises(LLMConfigurationError):
            load_llm_settings({"LLM_API_KEY": "test-key"})

    def test_rejects_invalid_limits(self) -> None:
        with self.assertRaises(LLMConfigurationError):
            load_llm_settings(
                {
                    "LLM_API_KEY": "test-key",
                    "LLM_MODEL": "test-model",
                    "LLM_MAX_OUTPUT_TOKENS": "0",
                }
            )

    def test_factory_only_accepts_supported_provider(self) -> None:
        settings = LLMSettings(
            provider="other",
            api_key="test-key",
            model="test-model",
            base_url="https://example.test",
            timeout_seconds=20.0,
            max_history_messages=20,
            max_output_tokens=500,
        )

        with self.assertRaises(LLMConfigurationError):
            create_llm_provider(settings)


class GroqLLMProviderTests(unittest.TestCase):
    def test_builds_chat_completion_request_and_returns_text(self) -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"role": "assistant", "content": "  Hola  "}}
                    ]
                },
            )

        async def run_test() -> str:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http_client:
                provider = GroqLLMProvider(
                    LLMSettings(
                        provider="groq",
                        api_key="test-key",
                        model="test-model",
                        base_url="https://api.groq.test/openai/v1",
                        timeout_seconds=20.0,
                        max_history_messages=20,
                        max_output_tokens=500,
                    ),
                    http_client=http_client,
                )
                return await provider.generate(
                    [
                        ChatMessage(role="system", content="Responde en espanol."),
                        ChatMessage(role="user", content="Hola"),
                    ]
                )

        result = asyncio.run(run_test())

        self.assertEqual(result, "Hola")
        self.assertEqual(
            str(requests[0].url),
            "https://api.groq.test/openai/v1/chat/completions",
        )
        self.assertEqual(requests[0].headers["Authorization"], "Bearer test-key")
        self.assertEqual(
            json.loads(requests[0].content),
            {
                "model": "test-model",
                "messages": [
                    {"role": "system", "content": "Responde en espanol."},
                    {"role": "user", "content": "Hola"},
                ],
                "max_tokens": 500,
            },
        )

    def test_translates_http_errors_to_provider_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": {"message": "rate limit"}})

        async def run_test() -> None:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http_client:
                provider = GroqLLMProvider(
                    LLMSettings(
                        provider="groq",
                        api_key="test-key",
                        model="test-model",
                        base_url="https://api.groq.test/openai/v1",
                        timeout_seconds=20.0,
                        max_history_messages=20,
                        max_output_tokens=500,
                    ),
                    http_client=http_client,
                )
                with self.assertRaises(LLMProviderError):
                    await provider.generate([ChatMessage(role="user", content="Hola")])

        asyncio.run(run_test())

    def test_rejects_empty_message_list(self) -> None:
        provider = GroqLLMProvider(
            LLMSettings(
                provider="groq",
                api_key="test-key",
                model="test-model",
                base_url="https://api.groq.test/openai/v1",
                timeout_seconds=20.0,
                max_history_messages=20,
                max_output_tokens=500,
            )
        )

        async def run_test() -> None:
            with self.assertRaises(LLMProviderError):
                await provider.generate([])

        asyncio.run(run_test())
