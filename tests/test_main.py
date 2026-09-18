import asyncio
import json
import os
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from main import FIXED_REPLY, app, normalize_recipient_number
from whatsapp_client import GRAPH_API_VERSION, WhatsAppClient


class FakeWhatsAppClient:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, str]] = []

    async def send_text(self, to: str, body: str) -> dict[str, str]:
        self.sent_messages.append((to, body))
        return {"status": "sent"}


class WebhookTests(unittest.TestCase):
    def test_normalizes_mexico_recipient_number_for_sending(self) -> None:
        self.assertEqual(
            normalize_recipient_number("5217531363338"),
            "527531363338",
        )

    def test_keeps_other_country_formats_unchanged(self) -> None:
        self.assertEqual(
            normalize_recipient_number("5491100000000"),
            "5491100000000",
        )

    def test_verification_uses_whatsapp_path(self) -> None:
        with patch.dict(os.environ, {"WHATSAPP_VERIFY_TOKEN": "test-token"}):
            with TestClient(app) as client:
                response = client.get(
                    "/webhook/whatsapp",
                    params={
                        "hub.mode": "subscribe",
                        "hub.verify_token": "test-token",
                        "hub.challenge": "challenge-123",
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "challenge-123")

    def test_text_message_is_parsed_and_answered(self) -> None:
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "5491100000000",
                                        "id": "wamid.test",
                                        "type": "text",
                                        "text": {"body": "Hola"},
                                    },
                                    {
                                        "from": "5491100000000",
                                        "id": "media.test",
                                        "type": "image",
                                        "image": {"id": "media-id"},
                                    },
                                ]
                            }
                        }
                    ]
                }
            ],
        }
        fake_client = FakeWhatsAppClient()

        with patch("main.WhatsAppClient", return_value=fake_client):
            with TestClient(app) as client:
                response = client.post("/webhook/whatsapp", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(fake_client.sent_messages, [("5491100000000", FIXED_REPLY)])

    def test_non_text_event_is_ignored_without_cloud_api_credentials(self) -> None:
        payload = {
            "entry": [{"changes": [{"value": {"statuses": [{"status": "read"}]}}]}]
        }

        with patch.dict(os.environ, {}, clear=True):
            with TestClient(app) as client:
                response = client.post("/webhook/whatsapp", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class WhatsAppClientTests(unittest.TestCase):
    def test_builds_cloud_api_text_request(self) -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"messages": [{"id": "wamid.reply"}]})

        async def run_test() -> None:
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as http_client:
                client = WhatsAppClient(
                    access_token="access-token",
                    phone_number_id="phone-id",
                    http_client=http_client,
                )
                result = await client.send_text("5491100000000", FIXED_REPLY)

            self.assertEqual(result, {"messages": [{"id": "wamid.reply"}]})

        asyncio.run(run_test())

        self.assertEqual(
            str(requests[0].url),
            f"https://graph.facebook.com/{GRAPH_API_VERSION}/phone-id/messages",
        )
        self.assertEqual(requests[0].headers["Authorization"], "Bearer access-token")
        self.assertEqual(
            json.loads(requests[0].content),
            {
                "messaging_product": "whatsapp",
                "to": "5491100000000",
                "type": "text",
                "text": {"body": FIXED_REPLY},
            },
        )
