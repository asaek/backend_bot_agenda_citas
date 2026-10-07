import asyncio
import json
import unittest

import httpx

from llm_provider import (
    ChatMessage,
    LLMConfigurationError,
    LLMHTTPError,
    LLMProviderError,
    LLMResponseError,
    LLMResponseTooLongError,
    LLMSettings,
    LLMTimeoutError,
    OpenAICompatibleLLMProvider,
    ToolCall,
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
                "LLM_MAX_RESPONSE_CHARACTERS": "1000",
            }
        )

        self.assertEqual(settings.provider, "groq")
        self.assertEqual(settings.api_key, "test-key")
        self.assertEqual(settings.model, "test-model")
        self.assertEqual(settings.base_url, "https://example.test")
        self.assertEqual(settings.timeout_seconds, 12.5)
        self.assertEqual(settings.max_history_messages, 10)
        self.assertEqual(settings.max_output_tokens, 250)
        self.assertEqual(settings.max_response_characters, 1000)

    def test_uses_safe_defaults_for_optional_limits(self) -> None:
        settings = load_llm_settings(
            {"LLM_API_KEY": "test-key", "LLM_MODEL": "test-model"}
        )

        self.assertEqual(settings.timeout_seconds, 20.0)
        self.assertEqual(settings.max_history_messages, 30)
        self.assertEqual(settings.max_output_tokens, 500)
        self.assertEqual(settings.max_response_characters, 4000)
        self.assertEqual(settings.max_tool_iterations, 3)

    def test_uses_openrouter_default_base_url(self) -> None:
        settings = load_llm_settings(
            {
                "LLM_PROVIDER": "openrouter",
                "LLM_API_KEY": "test-key",
                "LLM_MODEL": "test-model",
            }
        )

        self.assertEqual(settings.base_url, "https://openrouter.ai/api/v1")

    def test_provider_selector_uses_selected_credentials_and_model(self) -> None:
        environment = {
            "LLM_API_KEY": "legacy-active-provider-key",
            "LLM_MODEL": "legacy-active-provider-model",
            "LLM_BASE_URL": "https://legacy-groq.test/openai/v1",
            "GROQ_API_KEY": "groq-key",
            "GROQ_MODEL": "groq-model",
            "OPENAI_API_KEY": "openai-key",
            "OPENAI_MODEL": "gpt-4.1-mini",
        }

        groq_settings = load_llm_settings(
            {**environment, "LLM_PROVIDER": "groq"}
        )
        openai_settings = load_llm_settings(
            {**environment, "LLM_PROVIDER": "openai"}
        )

        self.assertEqual(
            (groq_settings.api_key, groq_settings.model),
            ("groq-key", "groq-model"),
        )
        self.assertEqual(
            (openai_settings.api_key, openai_settings.model),
            ("openai-key", "gpt-4.1-mini"),
        )
        self.assertEqual(
            openai_settings.base_url,
            "https://api.openai.com/v1",
        )

    def test_openai_uses_generic_credentials_for_the_selected_provider(self) -> None:
        settings = load_llm_settings(
            {
                "LLM_PROVIDER": "openai",
                "LLM_API_KEY": "openai-key",
                "LLM_MODEL": "gpt-4.1-mini",
                "LLM_BASE_URL": "https://legacy-groq.test/openai/v1",
            }
        )

        self.assertEqual(settings.api_key, "openai-key")
        self.assertEqual(settings.model, "gpt-4.1-mini")
        self.assertEqual(settings.base_url, "https://api.openai.com/v1")

    def test_uses_provider_specific_openai_base_url_when_configured(self) -> None:
        settings = load_llm_settings(
            {
                "LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "openai-key",
                "OPENAI_MODEL": "gpt-4.1-mini",
                "OPENAI_BASE_URL": "https://openai-proxy.test/v1/",
            }
        )

        self.assertEqual(settings.base_url, "https://openai-proxy.test/v1")

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
        with self.assertRaises(LLMConfigurationError):
            load_llm_settings(
                {
                    "LLM_API_KEY": "test-key",
                    "LLM_MODEL": "test-model",
                    "LLM_MAX_RESPONSE_CHARACTERS": "0",
                }
            )

    def test_factory_creates_the_same_adapter_for_supported_providers(self) -> None:
        for provider in ("groq", "openai", "openrouter"):
            settings = LLMSettings(
                provider=provider,
                api_key="test-key",
                model="test-model",
                base_url="https://example.test",
                timeout_seconds=20.0,
                max_history_messages=20,
                max_output_tokens=500,
            )

            self.assertIsInstance(
                create_llm_provider(settings),
                OpenAICompatibleLLMProvider,
            )

    def test_factory_rejects_unsupported_provider(self) -> None:
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


class OpenAICompatibleLLMProviderTests(unittest.TestCase):
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
                provider = OpenAICompatibleLLMProvider(
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
        payload = json.loads(requests[0].content)
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(
            payload["messages"],
            [
                {"role": "system", "content": "Responde en espanol."},
                {"role": "user", "content": "Hola"},
            ],
        )
        self.assertEqual(payload["max_tokens"], 500)
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertEqual(
            [tool["function"]["name"] for tool in payload["tools"]],
            [
                "check_availability",
                "create_appointment",
                "list_appointments",
                "reschedule_appointment",
                "cancel_appointment",
            ],
        )
        check_availability = payload["tools"][0]["function"]
        self.assertEqual(
            check_availability["parameters"]["additionalProperties"],
            False,
        )
        list_appointments = payload["tools"][2]["function"]
        self.assertEqual(
            set(list_appointments["parameters"]["properties"]),
            {"start_at", "end_at"},
        )
        self.assertNotIn("required", list_appointments["parameters"])

    def test_generate_text_does_not_publish_or_accept_tools(self) -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Resumen seguro"}}]},
            )

        async def run_test() -> str:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http_client:
                provider = OpenAICompatibleLLMProvider(
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
                return await provider.generate_text(
                    [ChatMessage(role="user", content="Resume")]
                )

        self.assertEqual(asyncio.run(run_test()), "Resumen seguro")
        payload = json.loads(requests[0].content)
        self.assertNotIn("tools", payload)
        self.assertNotIn("tool_choice", payload)

    def test_reuses_adapter_with_openrouter_configuration(self) -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Respuesta"}}]},
            )

        async def run_test() -> str:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http_client:
                provider = OpenAICompatibleLLMProvider(
                    LLMSettings(
                        provider="openrouter",
                        api_key="test-key",
                        model="openai/test-model",
                        base_url="https://openrouter.test/api/v1",
                        timeout_seconds=20.0,
                        max_history_messages=20,
                        max_output_tokens=500,
                    ),
                    http_client=http_client,
                )
                return await provider.generate(
                    [ChatMessage(role="user", content="Hola")]
                )

        self.assertEqual(asyncio.run(run_test()), "Respuesta")
        self.assertEqual(
            str(requests[0].url),
            "https://openrouter.test/api/v1/chat/completions",
        )

    def test_openai_uses_responses_api_and_parses_text_output(self) -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "output": [
                        {
                            "id": "msg-openai-1",
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "  Hola desde OpenAI  ",
                                    "annotations": [],
                                }
                            ],
                        }
                    ]
                },
            )

        async def run_test() -> str:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http_client:
                settings = load_llm_settings(
                    {
                        "LLM_PROVIDER": "openai",
                        "OPENAI_API_KEY": "openai-key",
                        "OPENAI_MODEL": "gpt-oss-20b",
                    }
                )
                provider = OpenAICompatibleLLMProvider(
                    settings,
                    http_client=http_client,
                )
                return await provider.generate(
                    [
                        ChatMessage(role="system", content="Responde en espanol."),
                        ChatMessage(role="user", content="Hola"),
                    ]
                )

        self.assertEqual(asyncio.run(run_test()), "Hola desde OpenAI")
        self.assertEqual(
            str(requests[0].url),
            "https://api.openai.com/v1/responses",
        )
        self.assertEqual(requests[0].headers["Authorization"], "Bearer openai-key")
        payload = json.loads(requests[0].content)
        self.assertEqual(payload["model"], "gpt-oss-20b")
        self.assertEqual(
            payload["input"],
            [
                {"role": "system", "content": "Responde en espanol."},
                {"role": "user", "content": "Hola"},
            ],
        )
        self.assertEqual(payload["max_output_tokens"], 500)
        self.assertFalse(payload["store"])
        self.assertNotIn("temperature", payload)
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertFalse(payload["parallel_tool_calls"])
        self.assertEqual(payload["tools"][0]["type"], "function")
        self.assertEqual(payload["tools"][0]["name"], "check_availability")
        self.assertNotIn("function", payload["tools"][0])

    def test_responses_tool_call_replays_reasoning_and_function_output(self) -> None:
        requests: list[httpx.Request] = []
        response_items = [
            {"id": "rs_1", "type": "reasoning", "summary": []},
            {
                "id": "fc_1",
                "call_id": "call_1",
                "type": "function_call",
                "name": "check_availability",
                "arguments": json.dumps(
                    {
                        "start_at": "2026-10-06T09:00:00",
                        "end_at": "2026-10-06T17:00:00",
                    }
                ),
            },
        ]

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(200, json={"output": response_items})
            return httpx.Response(
                200,
                json={
                    "output": [
                        {
                            "id": "msg_2",
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {"type": "output_text", "text": "Hay horarios."}
                            ],
                        }
                    ]
                },
            )

        async def run_test() -> str:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http_client:
                provider = OpenAICompatibleLLMProvider(
                    load_llm_settings(
                        {
                            "LLM_PROVIDER": "openai",
                            "OPENAI_API_KEY": "openai-key",
                            "OPENAI_MODEL": "gpt-oss-20b",
                        }
                    ),
                    http_client=http_client,
                )
                tool_call = await provider.generate(
                    [ChatMessage(role="user", content="Que horarios hay?")]
                )
                self.assertIsInstance(tool_call, ToolCall)
                return await provider.generate(
                    [
                        ChatMessage(role="user", content="Que horarios hay?"),
                        ChatMessage(
                            role="assistant",
                            content=None,
                            tool_calls=(tool_call,),
                        ),
                        ChatMessage(
                            role="tool",
                            content='{"ok":true}',
                            tool_call_id=tool_call.call_id,
                        ),
                    ]
                )

        self.assertEqual(asyncio.run(run_test()), "Hay horarios.")
        follow_up_payload = json.loads(requests[1].content)
        self.assertEqual(
            follow_up_payload["input"],
            [
                {"role": "user", "content": "Que horarios hay?"},
                *response_items,
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": '{"ok":true}',
                },
            ],
        )

    def test_openai_generate_text_does_not_publish_tools(self) -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "output": [
                        {
                            "id": "msg_1",
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {"type": "output_text", "text": "Resumen"}
                            ],
                        }
                    ]
                },
            )

        async def run_test() -> str:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http_client:
                provider = OpenAICompatibleLLMProvider(
                    load_llm_settings(
                        {
                            "LLM_PROVIDER": "openai",
                            "OPENAI_API_KEY": "openai-key",
                            "OPENAI_MODEL": "gpt-oss-20b",
                        }
                    ),
                    http_client=http_client,
                )
                return await provider.generate_text(
                    [ChatMessage(role="user", content="Resume")]
                )

        self.assertEqual(asyncio.run(run_test()), "Resumen")
        payload = json.loads(requests[0].content)
        self.assertNotIn("tools", payload)
        self.assertNotIn("tool_choice", payload)

    def test_parses_native_openai_tool_call_response(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {
                                            "name": "check_availability",
                                            "arguments": json.dumps(
                                                {
                                                    "start_at": "2026-09-21T10:00:00",
                                                    "end_at": "2026-09-21T17:00:00",
                                                }
                                            ),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                },
            )

        async def run_test() -> ToolCall:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http_client:
                provider = OpenAICompatibleLLMProvider(
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
                response = await provider.generate(
                    [ChatMessage(role="user", content="Que horarios hay?")]
                )

            self.assertIsInstance(response, ToolCall)
            return response

        response = asyncio.run(run_test())

        self.assertEqual(response.name, "check_availability")
        self.assertEqual(
            response.arguments,
            {
                "start_at": "2026-09-21T10:00:00",
                "end_at": "2026-09-21T17:00:00",
            },
        )

    def test_parses_normalized_tool_call_response(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "tool_call": {
                                    "name": "list_appointments",
                                    "arguments": {},
                                }
                            }
                        }
                    ]
                },
            )

        async def run_test() -> ToolCall:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http_client:
                provider = OpenAICompatibleLLMProvider(
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
                response = await provider.generate(
                    [ChatMessage(role="user", content="Que citas tengo?")]
                )

            self.assertIsInstance(response, ToolCall)
            return response

        response = asyncio.run(run_test())

        self.assertEqual(response, ToolCall(name="list_appointments", arguments={}))

    def test_serializes_tool_call_and_tool_result_messages(self) -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "Respuesta final"}}]},
            )

        async def run_test() -> str:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http_client:
                provider = OpenAICompatibleLLMProvider(
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
                        ChatMessage(
                            role="assistant",
                            content=None,
                            tool_calls=(
                                ToolCall(
                                    name="list_appointments",
                                    arguments={},
                                    call_id="call-1",
                                ),
                            ),
                        ),
                        ChatMessage(
                            role="tool",
                            content='{"ok": true}',
                            tool_call_id="call-1",
                        ),
                    ]
                )

        self.assertEqual(asyncio.run(run_test()), "Respuesta final")
        self.assertEqual(
            json.loads(requests[0].content)["messages"],
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "list_appointments",
                                "arguments": "{}",
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "content": '{"ok": true}',
                    "tool_call_id": "call-1",
                },
            ],
        )

    def test_rejects_invalid_tool_call_arguments(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "type": "function",
                                        "function": {
                                            "name": "check_availability",
                                            "arguments": "[]",
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                },
            )

        async def run_test() -> None:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http_client:
                provider = OpenAICompatibleLLMProvider(
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
                with self.assertRaises(LLMResponseError):
                    await provider.generate([ChatMessage(role="user", content="Hola")])

        asyncio.run(run_test())

    def test_translates_http_errors_to_provider_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": {"message": "rate limit"}})

        async def run_test() -> None:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http_client:
                provider = OpenAICompatibleLLMProvider(
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
                with self.assertRaises(LLMHTTPError) as raised:
                    await provider.generate([ChatMessage(role="user", content="Hola")])

                self.assertEqual(raised.exception.status_code, 429)

        asyncio.run(run_test())

    def test_translates_http_5xx_to_provider_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"error": {"message": "unavailable"}})

        async def run_test() -> None:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http_client:
                provider = OpenAICompatibleLLMProvider(
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
                with self.assertRaises(LLMHTTPError) as raised:
                    await provider.generate([ChatMessage(role="user", content="Hola")])

                self.assertEqual(raised.exception.status_code, 503)

        asyncio.run(run_test())

    def test_translates_timeout_to_provider_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timeout de prueba", request=request)

        async def run_test() -> None:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http_client:
                provider = OpenAICompatibleLLMProvider(
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
                with self.assertRaises(LLMTimeoutError):
                    await provider.generate([ChatMessage(role="user", content="Hola")])

        asyncio.run(run_test())

    def test_rejects_empty_provider_response(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "   "}}]},
            )

        async def run_test() -> None:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http_client:
                provider = OpenAICompatibleLLMProvider(
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
                with self.assertRaises(LLMResponseError):
                    await provider.generate([ChatMessage(role="user", content="Hola")])

        asyncio.run(run_test())

    def test_rejects_response_that_is_too_long(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "abcd"}}]},
            )

        async def run_test() -> None:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http_client:
                provider = OpenAICompatibleLLMProvider(
                    LLMSettings(
                        provider="groq",
                        api_key="test-key",
                        model="test-model",
                        base_url="https://api.groq.test/openai/v1",
                        timeout_seconds=20.0,
                        max_history_messages=20,
                        max_output_tokens=500,
                        max_response_characters=3,
                    ),
                    http_client=http_client,
                )
                with self.assertRaises(LLMResponseTooLongError):
                    await provider.generate([ChatMessage(role="user", content="Hola")])

        asyncio.run(run_test())

    def test_rejects_empty_message_list(self) -> None:
        provider = OpenAICompatibleLLMProvider(
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
