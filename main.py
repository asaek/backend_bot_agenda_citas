import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from whatsapp_client import WhatsAppClient, WhatsAppConfigurationError


load_dotenv(Path(__file__).with_name(".env"))

app = FastAPI(title="WhatsApp Chatbot")
FIXED_REPLY = "Hola, recibimos tu mensaje. Esta es una respuesta de prueba."


@dataclass(frozen=True)
class IncomingTextMessage:
    sender: str
    message_id: str
    message_type: str
    text: str


def extract_text_messages(payload: Any) -> list[IncomingTextMessage]:
    """Extrae mensajes de texto del formato de eventos de WhatsApp Cloud API."""
    if not isinstance(payload, dict):
        return []

    messages: list[IncomingTextMessage] = []
    entries = payload.get("entry", [])
    if not isinstance(entries, list):
        return messages

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes", [])
        if not isinstance(changes, list):
            continue

        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value", {})
            if not isinstance(value, dict):
                continue
            incoming_messages = value.get("messages", [])
            if not isinstance(incoming_messages, list):
                continue

            for message in incoming_messages:
                if not isinstance(message, dict) or message.get("type") != "text":
                    continue
                text_payload = message.get("text", {})
                sender = message.get("from")
                message_id = message.get("id")
                text = text_payload.get("body") if isinstance(text_payload, dict) else None
                if not all(isinstance(value, str) for value in (sender, message_id, text)):
                    continue
                messages.append(
                    IncomingTextMessage(
                        sender=sender,
                        message_id=message_id,
                        message_type="text",
                        text=text,
                    )
                )

    return messages


@app.get("/")
async def health_check() -> dict[str, str]:
    """Confirma que el backend esta funcionando."""
    return {"status": "ok"}


@app.get("/webhook/whatsapp", response_class=PlainTextResponse)
async def verify_webhook(
    mode: str | None = Query(default=None, alias="hub.mode"),
    verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> str:
    """Responde al desafio que Meta envia al registrar el webhook."""
    expected_token = os.getenv("WHATSAPP_VERIFY_TOKEN")

    if not expected_token:
        raise HTTPException(
            status_code=500,
            detail="WHATSAPP_VERIFY_TOKEN no esta configurado",
        )

    if mode == "subscribe" and verify_token == expected_token and challenge:
        return challenge

    raise HTTPException(status_code=403, detail="Verificacion rechazada")


@app.post("/webhook/whatsapp")
async def receive_webhook(request: Request) -> dict[str, str]:
    """Procesa mensajes de texto y envia una respuesta fija de prueba."""
    try:
        payload = await request.json()
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="El cuerpo debe ser JSON valido") from error

    messages = extract_text_messages(payload)
    if not messages:
        return {"status": "ok"}

    whatsapp_client = WhatsAppClient()
    for message in messages:
        print(json.dumps(asdict(message), ensure_ascii=False), flush=True)
        try:
            await whatsapp_client.send_text(to=message.sender, body=FIXED_REPLY)
        except WhatsAppConfigurationError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        except httpx.HTTPError as error:
            raise HTTPException(
                status_code=502,
                detail="No se pudo enviar la respuesta mediante WhatsApp Cloud API",
            ) from error

    return {"status": "ok"}
