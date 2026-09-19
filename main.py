import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from conversation_service import (
    ConversationContext,
    ConversationService,
    IncomingTextMessage,
)
from llm_provider import (
    LLMConfigurationError,
    LLMProviderError,
    create_llm_provider,
    load_llm_settings,
)
from persistence import DEFAULT_DATABASE_PATH, SQLiteDatabase
from whatsapp_client import WhatsAppClient, WhatsAppConfigurationError


load_dotenv(Path(__file__).with_name(".env"))

app = FastAPI(title="WhatsApp Chatbot")


def create_conversation_service() -> ConversationService:
    database_path = os.getenv("DATABASE_PATH", DEFAULT_DATABASE_PATH)
    settings = load_llm_settings()
    return ConversationService(
        SQLiteDatabase(database_path),
        llm_provider=create_llm_provider(settings),
        max_history_messages=settings.max_history_messages,
    )


def extract_provider_message_id(result: dict[str, Any]) -> str | None:
    messages = result.get("messages")
    if not isinstance(messages, list) or not messages:
        return None
    first_message = messages[0]
    if not isinstance(first_message, dict):
        return None
    message_id = first_message.get("id")
    return message_id if isinstance(message_id, str) else None


def normalize_recipient_number(phone_number: str) -> str:
    """Adapta el identificador mexicano de WhatsApp al formato de envio."""
    if phone_number.startswith("521") and len(phone_number) == 13:
        return "52" + phone_number[3:]
    return phone_number


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
    """Procesa mensajes de texto, conserva la conversacion y responde."""
    try:
        payload = await request.json()
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="El cuerpo debe ser JSON valido") from error

    messages = extract_text_messages(payload)
    if not messages:
        return {"status": "ok"}

    try:
        conversation_service = create_conversation_service()
    except LLMConfigurationError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    whatsapp_client = WhatsAppClient()
    for message in messages:
        context: ConversationContext = conversation_service.receive_message(message)
        print(json.dumps(asdict(message), ensure_ascii=False), flush=True)
        if context.reply_status == "sent":
            continue

        try:
            reply = await conversation_service.build_reply(context)
        except LLMProviderError as error:
            conversation_service.record_reply_failed(context, body="")
            raise HTTPException(
                status_code=502,
                detail="No se pudo generar la respuesta del asistente",
            ) from error
        try:
            result = await whatsapp_client.send_text(
                to=normalize_recipient_number(message.sender),
                body=reply,
            )
        except WhatsAppConfigurationError as error:
            conversation_service.record_reply_failed(context, reply)
            raise HTTPException(status_code=500, detail=str(error)) from error
        except httpx.HTTPError as error:
            conversation_service.record_reply_failed(context, reply)
            raise HTTPException(
                status_code=502,
                detail="No se pudo enviar la respuesta mediante WhatsApp Cloud API",
            ) from error

        conversation_service.record_reply_sent(
            context,
            body=reply,
            provider_message_id=extract_provider_message_id(result),
        )

    return {"status": "ok"}
