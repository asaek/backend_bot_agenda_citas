import os
from typing import Any

import httpx


GRAPH_API_VERSION = "v23.0"
GRAPH_API_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


class WhatsAppConfigurationError(RuntimeError):
    """Indica que falta una credencial necesaria para WhatsApp Cloud API."""


class WhatsAppClient:
    def __init__(
        self,
        access_token: str | None = None,
        phone_number_id: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.access_token = access_token or os.getenv("WHATSAPP_ACCESS_TOKEN")
        self.phone_number_id = phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        self.http_client = http_client

    async def send_text(self, to: str, body: str) -> dict[str, Any]:
        if not self.access_token:
            raise WhatsAppConfigurationError("WHATSAPP_ACCESS_TOKEN no esta configurado")
        if not self.phone_number_id:
            raise WhatsAppConfigurationError("WHATSAPP_PHONE_NUMBER_ID no esta configurado")

        url = f"{GRAPH_API_BASE_URL}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }

        if self.http_client is not None:
            response = await self.http_client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
