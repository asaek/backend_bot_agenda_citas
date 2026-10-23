import json
import asyncio
import logging
import os
import sqlite3
from collections.abc import Mapping
from contextlib import asynccontextmanager
from datetime import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from appointment_reason_evaluation import StructuredAppointmentReasonEvaluator
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
    LLMHTTPError,
    LLMProviderError,
    LLMProvider,
    ToolCall,
    create_llm_provider,
    load_llm_settings,
)
from notification_trigger import DoctorNotificationTrigger
from notification_composer import DEFAULT_NOTIFICATION_MAX_HISTORY_MESSAGES
from debug_reporting import format_debug_fallback_reply
from notification_domain import AppointmentNotificationEvent
from persistence import DEFAULT_DATABASE_PATH, SQLiteDatabase
from reply_delivery import ReplyDeliveryService, patient_turn
from persistent_calendar_provider import PersistentCalendarProvider
from tool_executor import ToolExecutor
from tool_validation import BusinessHours, TimeWindow
from whatsapp_client import WhatsAppClient, WhatsAppConfigurationError


load_dotenv(Path(__file__).with_name(".env"))

@asynccontextmanager
async def application_lifespan(application: FastAPI):
    if not hasattr(application.state, "tool_executor"):
        application.state.calendar_provider = create_calendar_provider()
        application.state.availability_provider = create_availability_provider(application.state.calendar_provider)
        application.state.tool_executor = create_tool_executor(
            application.state.calendar_provider,
            availability_provider=application.state.availability_provider,
        )
    notifications = create_chat_notification_worker()
    statuses = create_meta_status_worker()
    application.state.doctor_notifications = notifications
    application.state.meta_status_worker = statuses
    if notifications:
        notifications.start()
    if statuses:
        statuses.start()
    try:
        yield
    finally:
        if notifications:
            await notifications.close()
        if statuses:
            await statuses.close()


app = FastAPI(title="WhatsApp Chatbot", lifespan=application_lifespan)
logger = logging.getLogger(__name__)


DEFAULT_CALENDAR_TIMEZONE = "UTC"
DEFAULT_BUSINESS_WORKDAYS = "0,1,2,3,4"
DEFAULT_BUSINESS_HOURS_START = "09:00"
DEFAULT_BUSINESS_HOURS_END = "17:00"
DEFAULT_LLM_REASON_EVALUATION_ENABLED = True


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
    conversation_timezone = (
        resolved_tool_executor.default_timezone
        if resolved_tool_executor is not None
        else DEFAULT_CALENDAR_TIMEZONE
    )
    conversation_now = (
        resolved_tool_executor.current_time
        if resolved_tool_executor is not None
        else None
    )
    try:
        settings = load_llm_settings()
        llm_provider = create_llm_provider(settings)
    except LLMConfigurationError as error:
        return ConversationService(
            database,
            llm_configuration_error=error,
            tool_executor=resolved_tool_executor,
            timezone_name=conversation_timezone,
            now=conversation_now,
        )
    reason_evaluator = (
        StructuredAppointmentReasonEvaluator(llm_provider)
        if _environment_flag(
            os.getenv("LLM_REASON_EVALUATION_ENABLED"),
            default=DEFAULT_LLM_REASON_EVALUATION_ENABLED,
        )
        else None
    )
    return ConversationService(
        database,
        llm_provider=llm_provider,
        max_history_messages=settings.max_history_messages,
        max_tool_iterations=settings.max_tool_iterations,
        tool_executor=resolved_tool_executor,
        timezone_name=conversation_timezone,
        now=conversation_now,
        reason_evaluator=reason_evaluator,
    )


def _environment_flag(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_chat_notification_worker():
    if not _environment_flag(os.getenv("DOCTOR_NOTIFICATIONS_ENABLED"), default=False):
        return None
    from chat_notifications import ChatDoctorNotifications

    def trigger_factory(database):
        provider = None
        limit = DEFAULT_NOTIFICATION_MAX_HISTORY_MESSAGES
        try:
            settings = load_llm_settings()
            provider = create_llm_provider(settings)
            limit = settings.max_history_messages
        except LLMConfigurationError:
            pass
        return DoctorNotificationTrigger(database, provider, max_history_messages=limit)

    return ChatDoctorNotifications(os.getenv("DATABASE_PATH", DEFAULT_DATABASE_PATH), trigger_factory)


def create_meta_status_service():
    from notification_statuses import MetaDeliveryStatusService
    chat_path = os.getenv("DATABASE_PATH", DEFAULT_DATABASE_PATH)
    lab_path = Path(os.getenv("LAB_DATABASE_PATH", "data/calling-lab.sqlite3"))
    voice_path = os.getenv("VOICE_DATABASE_PATH", str(lab_path.with_name(lab_path.stem + "-voice.sqlite3")))
    return MetaDeliveryStatusService(chat_path, {"chat": chat_path, "voice": voice_path})


def create_meta_status_worker():
    from notification_statuses import MetaDeliveryStatusWorker
    return MetaDeliveryStatusWorker(create_meta_status_service())


async def deliver_doctor_notifications(
    conversation_service: ConversationService,
    whatsapp_client: WhatsAppClient,
    events: list[AppointmentNotificationEvent],
) -> bool:
    """Entrega eventos ya confirmados sin propagar fallos al paciente."""
    if not events:
        return True

    try:
        trigger = DoctorNotificationTrigger(conversation_service.database, conversation_service.llm_provider,
            whatsapp_client=whatsapp_client, max_history_messages=conversation_service.max_history_messages)
    except Exception as error:
        logger.warning(
            "No se pudo configurar la entrega al doctor: %s",
            type(error).__name__,
        )
        return False

    if not trigger.enabled:
        return True
    completed = True
    for event in events:
        notified = await trigger.notify(event)
        completed = notified and completed
    return completed


def create_lab_app(
    *,
    enabled: bool | None = None,
    repository=None,
    media_factory=None,
    audio_mode: str | None = None,
    realtime_provider_factory=None,
    voice_settings=None,
    voice_database_path: str | Path | None = None,
    doctor_notification_trigger_factory=None,
) -> FastAPI:
    """Crea solo el laboratorio: `uvicorn main:create_lab_app --factory`."""
    import asyncio
    import sqlite3
    from fastapi.responses import HTMLResponse, JSONResponse
    from starlette.background import BackgroundTask

    from calling_repository import (
        CallCapacityError,
        CallNotFoundError,
        CallingRepository,
        VoiceSessionQuotaExceededError,
    )
    from calling_service import CallMediaPersistenceError, CallPersistenceError, CallSetupError, CallingService
    from openai_realtime_provider import RealtimeError
    from voice_session import voice_calendar_provider_name

    audio_mode = audio_mode or os.getenv("LAB_AUDIO_MODE", "greeting")
    if audio_mode not in {"greeting", "realtime"}:
        raise ValueError("LAB_AUDIO_MODE debe ser greeting o realtime")
    calendar_provider_name = voice_calendar_provider_name()

    if enabled is None:
        enabled = _environment_flag(os.getenv("LAB_CALLS_ENABLED"), default=False)
    if not enabled:
        raise ValueError("LAB_CALLS_ENABLED debe habilitarse para iniciar el laboratorio")
    database_path = Path(os.getenv("LAB_DATABASE_PATH", "data/calling-lab.sqlite3"))
    if repository is None:
        if database_path.resolve() == Path(os.getenv("DATABASE_PATH", DEFAULT_DATABASE_PATH)).resolve():
            raise ValueError("LAB_DATABASE_PATH debe ser diferente de la base de pacientes")
        repository = CallingRepository(database_path)

    @asynccontextmanager
    async def lifespan(laboratory: FastAPI):
        factory = media_factory
        session_factory = None
        voice_repository = None
        doctor_notifications = None
        text_conversation = None
        maximum_seconds = float(os.getenv("LAB_MAXIMUM_SECONDS", "600"))
        if audio_mode == "realtime":
            from openai_realtime_provider import OpenAIRealtimeProvider, RealtimeSettings
            from voice_repository import VoiceRepository
            from voice_session import VoiceSession
            from lab_text_conversation import LaboratoryTextConversation
            from voice_notifications import VoiceDoctorNotifications

            settings = voice_settings or RealtimeSettings.from_environment()
            voice_path = Path(voice_database_path or os.getenv("VOICE_DATABASE_PATH", str(repository.path.with_name(repository.path.stem + "-voice.sqlite3"))))
            if voice_path.resolve() in {repository.path.resolve(), Path(os.getenv("DATABASE_PATH", DEFAULT_DATABASE_PATH)).resolve()}:
                raise ValueError("VOICE_DATABASE_PATH requiere una base separada de llamadas y pacientes")
            voice_repository = VoiceRepository(voice_path)
            if doctor_notification_trigger_factory is not None:
                trigger = doctor_notification_trigger_factory(voice_repository)
            else:
                summary_provider = None
                summary_history_limit = DEFAULT_NOTIFICATION_MAX_HISTORY_MESSAGES
                try:
                    summary_settings = load_llm_settings()
                    summary_provider = create_llm_provider(summary_settings)
                    summary_history_limit = summary_settings.max_history_messages
                except LLMConfigurationError:
                    logger.warning("No hay proveedor LLM configurado para los avisos de voz al doctor")
                trigger = DoctorNotificationTrigger(voice_repository, summary_provider,
                    max_history_messages=summary_history_limit)
            doctor_notifications = VoiceDoctorNotifications(voice_repository, trigger)
            hours = create_business_hours()
            profile = os.getenv("VOICE_LAB_PROFILE", "developer").strip()
            if not profile or len(profile) > 100:
                raise ValueError("VOICE_LAB_PROFILE debe identificar el perfil de prueba del servidor")
            if factory is None:
                from call_media import AiortcCallMedia
                factory = AiortcCallMedia
            session_factory = lambda session_id: VoiceSession(
                session_id=session_id, media=factory(),
                provider=realtime_provider_factory() if realtime_provider_factory else OpenAIRealtimeProvider(settings),
                repository=voice_repository, settings=settings, business_hours=hours, profile=profile,
                calendar_provider_name=calendar_provider_name,
                notifications=doctor_notifications,
            )
            text_conversation = LaboratoryTextConversation(repository=voice_repository, settings=settings,
                provider_factory=realtime_provider_factory or (lambda: OpenAIRealtimeProvider(settings)),
                business_hours=hours, profile=profile, calendar_provider_name=calendar_provider_name,
                notifications=doctor_notifications)
            maximum_seconds = min(maximum_seconds, settings.maximum_seconds)
        elif factory is None:
            from call_media import AiortcCallMedia, validate_greeting

            greeting = Path(os.getenv("LAB_GREETING_PATH", str(Path(__file__).parent / "assets/lab-greeting.wav")))
            validate_greeting(greeting)
            factory = lambda: AiortcCallMedia(greeting)
        service = CallingService(
            repository, factory,
            session_media_factory=session_factory,
            negotiation_seconds=float(os.getenv("LAB_NEGOTIATION_SECONDS", "20")),
            inactivity_seconds=float(os.getenv("LAB_INACTIVITY_SECONDS", "60")),
            maximum_seconds=maximum_seconds,
        )
        try:
            if voice_repository:
                voice_repository.start()
            if doctor_notifications:
                doctor_notifications.start()
            await service.start()
            laboratory.state.calling_service = service
            laboratory.state.conversation_lock = asyncio.Lock()
            laboratory.state.text_conversation = text_conversation
            laboratory.state.voice_repository = voice_repository
            laboratory.state.doctor_notifications = doctor_notifications
            laboratory.state.pending_text_results = {}
            yield
        finally:
            try:
                try:
                    if text_conversation:
                        await text_conversation.close()
                finally:
                    await service.shutdown()
            finally:
                if doctor_notifications:
                    await doctor_notifications.close()
                if voice_repository:
                    voice_repository.close()

    laboratory = FastAPI(title="Laboratorio de audio", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @laboratory.middleware("http")
    async def laboratory_response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @laboratory.get("/lab", response_class=HTMLResponse)
    async def laboratory_client():
        return (
            (Path(__file__).parent / "assets/lab-client.html")
            .read_text()
            .replace('data-audio-mode="greeting"', f'data-audio-mode="{audio_mode}"')
            .replace('data-calendar-provider="fake"', f'data-calendar-provider="{calendar_provider_name}"')
        )

    @laboratory.get("/lab/health")
    async def laboratory_health():
        return {
            "status": "ok",
            "mode": "laboratory",
            "audio_mode": audio_mode,
            "calendar_provider": calendar_provider_name,
        }

    @laboratory.post("/lab/calls", status_code=201)
    async def create_laboratory_call(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 131072:
                raise HTTPException(status_code=413, detail="Oferta demasiado grande")
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeError):
            raise HTTPException(status_code=400, detail="Se requiere JSON valido") from None
        if (
            not isinstance(payload, dict)
            or payload.get("type") != "offer"
            or not isinstance(payload.get("sdp"), str)
            or not payload["sdp"].strip()
        ):
            raise HTTPException(status_code=400, detail="Se requiere una oferta SDP")
        try:
            async with laboratory.state.conversation_lock:
                if laboratory.state.text_conversation:
                    await laboratory.state.text_conversation.close()
                session, answer = await laboratory.state.calling_service.create(payload["sdp"])
        except VoiceSessionQuotaExceededError as error:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"El perfil de laboratorio alcanzó su límite de sesiones "
                    f"({error.used}/{error.maximum}). Reiniciar no restablece el "
                    "contador; revisa el consumo antes de ampliar la cuota."
                ),
            ) from None
        except CallCapacityError:
            raise HTTPException(status_code=409, detail="Laboratorio ocupado o cerrando") from None
        except CallSetupError:
            raise HTTPException(status_code=422, detail="No se pudo establecer el audio") from None
        except CallMediaPersistenceError:
            raise HTTPException(status_code=503, detail="Reintenta iniciar la llamada tras finalizar el historial de texto") from None
        except CallPersistenceError as error:
            return JSONResponse(
                {"detail": "Reintenta finalizar la sesion", "session_id": error.session_id},
                status_code=503,
            )
        except sqlite3.Error:
            raise HTTPException(status_code=503, detail="No se pudo persistir el resultado de la sesion") from None
        return {
            "session_id": session["session_id"],
            "type": "answer",
            "sdp": answer,
            "mode": "laboratory",
            "audio_mode": audio_mode,
            "calendar_provider": calendar_provider_name,
        }

    @laboratory.get("/lab/history")
    async def laboratory_history():
        manager = laboratory.state.text_conversation
        if manager is None:
            raise HTTPException(status_code=409, detail="El historial compartido requiere modo realtime")
        try:
            history = await asyncio.to_thread(manager.repository.profile_history, manager.profile)
            return {"profile": manager.profile, "history": history, "mode": "laboratory"}
        except sqlite3.Error:
            raise HTTPException(status_code=503, detail="Historial no disponible") from None

    @laboratory.post("/lab/messages")
    async def laboratory_text(request: Request):
        manager = laboratory.state.text_conversation
        if manager is None:
            raise HTTPException(status_code=409, detail="Los mensajes requieren modo realtime")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 16384:
                raise HTTPException(status_code=413, detail="Mensaje demasiado grande")
        try:
            value = json.loads(body)
        except (ValueError, UnicodeError):
            raise HTTPException(status_code=400, detail="Se requiere JSON valido") from None
        if (not isinstance(value, dict) or set(value) != {"message_id", "text"}
            or not isinstance(value["message_id"], str) or not 1 <= len(value["message_id"]) <= 100
            or not isinstance(value["text"], str) or not 1 <= len(value["text"].strip()) <= 2000):
            raise HTTPException(status_code=400, detail="Se requiere message_id y texto de hasta 2000 caracteres")
        async with laboratory.state.conversation_lock:
            claimed = False
            try:
                pending = laboratory.state.pending_text_results.get(value["message_id"])
                if pending:
                    if pending["text"] != value["text"]:
                        raise ValueError("message_id reutilizado")
                    await store_text_result(manager, value, pending["result"])
                    return text_response(manager, pending["result"])
                fresh, previous = await asyncio.to_thread(manager.repository.claim_text, manager.profile, value["message_id"], value["text"])
                if not fresh:
                    return text_response(manager, previous)
                claimed = True
                media = laboratory.state.calling_service.active_media()
                session = media if media is not None and not media.closed else await manager.ensure_session()
                result = await session.submit_text(value["text"])
                await store_text_result(manager, value, result)
                return text_response(manager, result)
            except sqlite3.Error:
                raise HTTPException(status_code=503, detail="No se pudo persistir el mensaje") from None
            except ValueError:
                if claimed:
                    await store_text_result(manager, value, {
                        "state": "failed", "reply": "Perfil o cuota no disponibles; revisa el estado antes de enviar otro mensaje.",
                    })
                raise HTTPException(status_code=409, detail="Perfil, cuota o mensaje no disponibles; revisa el estado del laboratorio") from None
            except RealtimeError:
                if claimed:
                    await store_text_result(manager, value, {
                        "state": "failed", "reply": "La conexion Realtime fallo; consulta el historial antes de reintentar.",
                    })
                raise HTTPException(status_code=502, detail="No se pudo completar la conexion Realtime") from None
            except CallMediaPersistenceError:
                raise HTTPException(status_code=503, detail="Reintenta cuando se recupere el historial del laboratorio") from None
            except TimeoutError:
                result = {"state": "interrupted", "reply": "La respuesta expiro; revisa el historial antes de iniciar otro mensaje."}
                await store_text_result(manager, value, result)
                return text_response(manager, result)
            except asyncio.CancelledError:
                if claimed:
                    await store_text_result(manager, value, {
                        "state": "interrupted", "reply": "La entrega se interrumpio; consulta el historial antes de iniciar otro mensaje.",
                    })
                raise

    async def store_text_result(manager, value, result):
        pending = laboratory.state.pending_text_results
        pending[value["message_id"]] = {"text": value["text"], "result": result}
        try:
            await asyncio.to_thread(manager.repository.finish_text, manager.profile, value["message_id"], result)
        except sqlite3.Error:
            raise HTTPException(status_code=503, detail="Respuesta conservada; reintenta el mismo mensaje para finalizarla sin repetir acciones") from None
        pending.pop(value["message_id"], None)

    def text_response(manager, result):
        session = next((candidate for candidate in (laboratory.state.calling_service.active_media(), manager.session)
                        if candidate is not None and candidate.session_id == result.get("session_id") and not candidate.closed), None)

        async def published():
            if session is not None and isinstance(result.get("turn_id"), int):
                try:
                    await session.publish_text(result["turn_id"])
                except sqlite3.Error:
                    # Permiso sigue deshabilitado; reenviar el resultado puede
                    # reintentar la publicacion sin volver a ejecutar el modelo.
                    pass

        return JSONResponse(result, background=BackgroundTask(published))

    @laboratory.get("/lab/calls/{session_id}")
    async def get_laboratory_call(session_id: str):
        try:
            return laboratory.state.calling_service.get(session_id)
        except CallNotFoundError:
            raise HTTPException(status_code=404, detail="Sesion no encontrada") from None
        except sqlite3.Error:
            raise HTTPException(status_code=503, detail="Estado de sesion temporalmente no disponible") from None

    @laboratory.delete("/lab/calls/{session_id}")
    async def end_laboratory_call(session_id: str):
        try:
            return await laboratory.state.calling_service.finish(session_id)
        except CallNotFoundError:
            raise HTTPException(status_code=404, detail="Sesion no encontrada") from None
        except (CallPersistenceError, sqlite3.Error):
            raise HTTPException(status_code=503, detail="Reintenta finalizar la sesion") from None

    return laboratory


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


def _fallback_reply_for_error(
    recipient_number: str,
    *,
    error_type: str,
    http_status_code: int | None,
    llm_provider: LLMProvider | None,
) -> str:
    settings = getattr(llm_provider, "settings", None)
    provider_name = getattr(settings, "provider", None)
    diagnostic_reply = format_debug_fallback_reply(
        recipient_number,
        error_type=error_type,
        provider_name=provider_name,
        http_status_code=http_status_code,
    )
    return diagnostic_reply or CONTROLLED_FALLBACK_REPLY


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
async def receive_webhook(request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Procesa mensajes de texto, conserva la conversacion y responde."""
    try:
        payload = await request.json()
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="El cuerpo debe ser JSON valido") from error

    from notification_statuses import extract_delivery_statuses
    if extract_delivery_statuses(payload):
        service = create_meta_status_service()
        try:
            await asyncio.to_thread(service.receive, payload, reconcile=False)
        except (sqlite3.Error, OSError) as error:
            logger.warning("No se pudo persistir un callback Meta: %s", type(error).__name__)
            raise HTTPException(status_code=503, detail="No se pudo registrar el estado de entrega") from error
        background_tasks.add_task(service.flush)

    messages = extract_text_messages(payload)
    if not messages:
        return {"status": "ok"}

    conversation_service = create_conversation_service()
    whatsapp_client = WhatsAppClient()
    for message in messages:
        async with patient_turn(conversation_service.database.path, message.sender):
            context = conversation_service.receive_message(message)
            delivery = ReplyDeliveryService(conversation_service.database)
            try:
                await _process_reply(conversation_service, whatsapp_client, delivery, context, message)
            except BaseException:
                delivery.interrupt(context)
                raise

    return {"status": "ok"}


async def _process_reply(
    conversation_service: ConversationService,
    whatsapp_client: WhatsAppClient,
    delivery: ReplyDeliveryService,
    context: ConversationContext,
    message: IncomingTextMessage,
) -> None:
    plan = delivery.begin(context)
    if plan is None:
        return
    appointment_events = list(plan.events)
    reply = plan.body
    if reply is None:
        try:
            reply = await conversation_service.build_reply(
                context, appointment_event_sink=appointment_events.append,
            )
        except LLMProviderError as error:
            http_status_code = (
                error.status_code if isinstance(error, LLMHTTPError) else None
            )
            logger.warning(
                "LLM provider failure: error_type=%s http_status_code=%s",
                type(error).__name__,
                http_status_code,
            )
            conversation_service.record_llm_failure(
                context,
                error_type=type(error).__name__,
                http_status_code=http_status_code,
            )
            reply = _fallback_reply_for_error(
                message.sender,
                error_type=type(error).__name__,
                http_status_code=http_status_code,
                llm_provider=conversation_service.llm_provider,
            )
        if isinstance(reply, ToolCall):
            conversation_service.record_llm_failure(
                context,
                error_type="UnsupportedToolCall",
            )
            reply = _fallback_reply_for_error(
                message.sender,
                error_type="UnsupportedToolCall",
                http_status_code=None,
                llm_provider=conversation_service.llm_provider,
            )
    if plan.send_required:
        delivery.prepare(context, reply, appointment_events)
        attempt_id = delivery.start_send(context)
        try:
            result = await whatsapp_client.send_text(
                to=normalize_recipient_number(message.sender),
                body=reply,
            )
        except WhatsAppConfigurationError as error:
            delivery.record_failed(context, attempt_id, reply, error)
            raise HTTPException(status_code=500, detail=str(error)) from error
        except httpx.HTTPError as error:
            delivery.record_failed(context, attempt_id, reply, error)
            raise HTTPException(
                status_code=502,
                detail="No se pudo enviar la respuesta mediante WhatsApp Cloud API",
            ) from error

        delivery.record_sent(
            context,
            attempt_id=attempt_id,
            body=reply,
            provider_message_id=extract_provider_message_id(result),
        )
    if await deliver_doctor_notifications(conversation_service, whatsapp_client, appointment_events):
        delivery.complete_notifications(context)
