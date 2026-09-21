import json
import os
from collections.abc import Mapping
from dataclasses import asdict
from datetime import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from calendar_domain import CalendarProvider
from conversation_service import (
    CONTROLLED_FALLBACK_REPLY,
    ConversationContext,
    ConversationService,
    IncomingTextMessage,
)
from fake_calendar_provider import FakeCalendarProvider
from google_calendar_provider import (
    create_google_calendar_provider_from_environment,
)
from llm_provider import (
    LLMConfigurationError,
    LLMProviderError,
    ToolCall,
    create_llm_provider,
    load_llm_settings,
)
from persistence import DEFAULT_DATABASE_PATH, SQLiteDatabase
from persistent_calendar_provider import PersistentCalendarProvider
from tool_executor import ToolExecutor
from tool_validation import BusinessHours, TimeWindow
from whatsapp_client import WhatsAppClient, WhatsAppConfigurationError


load_dotenv(Path(__file__).with_name(".env"))

app = FastAPI(title="WhatsApp Chatbot")


DEFAULT_CALENDAR_TIMEZONE = "UTC"
DEFAULT_BUSINESS_WORKDAYS = "0,1,2,3,4"
DEFAULT_BUSINESS_HOURS_START = "09:00"
DEFAULT_BUSINESS_HOURS_END = "17:00"


def create_calendar_provider(
    environment: Mapping[str, str] | None = None,
) -> CalendarProvider:
    """Crea el proveedor seleccionado por configuracion del backend."""
    values = os.environ if environment is None else environment
    provider_name = values.get("CALENDAR_PROVIDER", "fake").strip().lower()
    if provider_name == "fake":
        return FakeCalendarProvider()
    if provider_name == "google":
        return PersistentCalendarProvider(
            create_google_calendar_provider_from_environment(values),
            SQLiteDatabase(values.get("DATABASE_PATH", DEFAULT_DATABASE_PATH)),
        )
    raise ValueError("CALENDAR_PROVIDER debe ser fake o google")


def create_availability_provider(
    primary_provider: CalendarProvider,
    environment: Mapping[str, str] | None = None,
) -> CalendarProvider:
    """Selecciona el proveedor exclusivo de `check_availability`."""
    values = os.environ if environment is None else environment
    provider_name = values.get(
        "CALENDAR_AVAILABILITY_PROVIDER",
        "primary",
    ).strip().lower()
    if provider_name in {"", "primary"}:
        return primary_provider
    if provider_name == "fake":
        return FakeCalendarProvider()
    if provider_name == "google":
        return create_google_calendar_provider_from_environment(values)
    raise ValueError(
        "CALENDAR_AVAILABILITY_PROVIDER debe ser primary, fake o google"
    )


def create_business_hours(
    environment: Mapping[str, str] | None = None,
) -> BusinessHours:
    """Configura el horario laboral desde el entorno del backend."""
    values = os.environ if environment is None else environment
    timezone_name = values.get(
        "GOOGLE_CALENDAR_TIMEZONE",
        DEFAULT_CALENDAR_TIMEZONE,
    ).strip() or DEFAULT_CALENDAR_TIMEZONE
    weekdays = _parse_business_weekdays(
        values.get("BUSINESS_WORKDAYS", DEFAULT_BUSINESS_WORKDAYS)
    )
    start_at = _parse_business_time(
        values.get("BUSINESS_HOURS_START", DEFAULT_BUSINESS_HOURS_START),
        "BUSINESS_HOURS_START",
    )
    end_at = _parse_business_time(
        values.get("BUSINESS_HOURS_END", DEFAULT_BUSINESS_HOURS_END),
        "BUSINESS_HOURS_END",
    )
    return BusinessHours(
        timezone_name=timezone_name,
        windows_by_weekday={
            weekday: (TimeWindow(start_at, end_at),)
            for weekday in weekdays
        },
    )


def _parse_business_weekdays(value: str) -> tuple[int, ...]:
    try:
        weekdays = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as error:
        raise ValueError(
            "BUSINESS_WORKDAYS debe contener numeros entre 0 y 6 separados por comas"
        ) from error
    if not weekdays or any(weekday not in range(7) for weekday in weekdays):
        raise ValueError(
            "BUSINESS_WORKDAYS debe contener al menos un dia entre 0 y 6"
        )
    if len(set(weekdays)) != len(weekdays):
        raise ValueError("BUSINESS_WORKDAYS no puede repetir dias")
    return weekdays


def _parse_business_time(value: str, name: str) -> time:
    try:
        parsed = time.fromisoformat(value.strip())
    except ValueError as error:
        raise ValueError(f"{name} debe usar el formato HH:MM") from error
    if parsed.tzinfo is not None:
        raise ValueError(f"{name} no debe incluir zona horaria")
    return parsed


def create_tool_executor(
    provider: CalendarProvider | None = None,
    environment: Mapping[str, str] | None = None,
    availability_provider: CalendarProvider | None = None,
) -> ToolExecutor:
    """Compone el ejecutor con el proveedor y las reglas del backend."""
    values = os.environ if environment is None else environment
    resolved_provider = (
        provider if provider is not None else create_calendar_provider(values)
    )
    resolved_availability_provider = (
        availability_provider
        if availability_provider is not None
        else (
            create_availability_provider(resolved_provider, values)
            if provider is None
            else resolved_provider
        )
    )
    business_hours = create_business_hours(values)
    return ToolExecutor(
        provider=resolved_provider,
        business_hours=business_hours,
        default_timezone=business_hours.timezone_name,
        availability_provider=resolved_availability_provider,
    )


def create_conversation_service(
    tool_executor: ToolExecutor | None = None,
) -> ConversationService:
    resolved_tool_executor = (
        tool_executor
        if tool_executor is not None
        else getattr(app.state, "tool_executor", None)
    )
    database_path = os.getenv("DATABASE_PATH", DEFAULT_DATABASE_PATH)
    database = SQLiteDatabase(database_path)
    try:
        settings = load_llm_settings()
        llm_provider = create_llm_provider(settings)
    except LLMConfigurationError as error:
        return ConversationService(
            database,
            llm_configuration_error=error,
            tool_executor=resolved_tool_executor,
        )
    return ConversationService(
        database,
        llm_provider=llm_provider,
        max_history_messages=settings.max_history_messages,
        max_tool_iterations=settings.max_tool_iterations,
        tool_executor=resolved_tool_executor,
    )


app.state.calendar_provider = create_calendar_provider()
app.state.availability_provider = create_availability_provider(
    app.state.calendar_provider,
)
app.state.tool_executor = create_tool_executor(
    app.state.calendar_provider,
    availability_provider=app.state.availability_provider,
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

    conversation_service = create_conversation_service()
    whatsapp_client = WhatsAppClient()
    for message in messages:
        context: ConversationContext = conversation_service.receive_message(message)
        print(json.dumps(asdict(message), ensure_ascii=False), flush=True)
        if context.reply_status == "sent":
            continue

        try:
            reply = await conversation_service.build_reply(context)
        except LLMProviderError as error:
            conversation_service.record_llm_failure(
                context,
                error_type=type(error).__name__,
            )
            reply = CONTROLLED_FALLBACK_REPLY
        if isinstance(reply, ToolCall):
            conversation_service.record_llm_failure(
                context,
                error_type="UnsupportedToolCall",
            )
            reply = CONTROLLED_FALLBACK_REPLY
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
