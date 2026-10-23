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
        return await self._send({
            "messaging_product": "whatsapp", "to": to,
            "type": "text", "text": {"body": body},
        })

    async def send_template(
        self,
        to: str,
        name: str,
        language_code: str,
        components: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Envia los componentes explicitos de una plantilla sin asumir su estructura."""
        if not name.strip() or not language_code.strip():
            raise WhatsAppConfigurationError("Nombre e idioma de plantilla son obligatorios")
        template: dict[str, Any] = {"name": name, "language": {"code": language_code}}
        if components is not None:
            template["components"] = components
        return await self._send({
            "messaging_product": "whatsapp", "to": to,
            "type": "template", "template": template,
        })

    async def _send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.access_token:
            raise WhatsAppConfigurationError("WHATSAPP_ACCESS_TOKEN no esta configurado")
        if not self.phone_number_id:
            raise WhatsAppConfigurationError("WHATSAPP_PHONE_NUMBER_ID no esta configurado")

        url = f"{GRAPH_API_BASE_URL}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        if self.http_client is not None:
            response = await self.http_client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
