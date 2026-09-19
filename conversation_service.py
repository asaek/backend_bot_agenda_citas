from dataclasses import dataclass
from datetime import datetime, timezone

from llm_provider import (
    ChatMessage,
    DEFAULT_LLM_MAX_HISTORY_MESSAGES,
    LLMProvider,
)
from persistence import SQLiteDatabase
from repositories import (
    ConversationRepository,
    MessageRecord,
    MessageRepository,
    PatientRepository,
)


SYSTEM_PROMPT = "\n".join(
    (
        "Responder en español.",
        "Ser breve y claro.",
        "No inventar citas, horarios o datos.",
        "No afirmar que realizó acciones externas.",
        "No proporcionar diagnósticos médicos.",
        "Pedir aclaración cuando falte información.",
        "Responder únicamente con texto normal.",
    )
)


@dataclass(frozen=True, slots=True)
class IncomingTextMessage:
    sender: str
    message_id: str
    message_type: str
    text: str


@dataclass(frozen=True, slots=True)
class ConversationContext:
    patient_id: int
    conversation_id: int
    incoming_message_id: int
    reply_status: str | None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationService:
    def __init__(
        self,
        database: SQLiteDatabase,
        llm_provider: LLMProvider | None = None,
        max_history_messages: int = DEFAULT_LLM_MAX_HISTORY_MESSAGES,
    ) -> None:
        self.database = database
        self.llm_provider = llm_provider
        self.max_history_messages = max_history_messages
        self.patients = PatientRepository()
        self.conversations = ConversationRepository()
        self.messages = MessageRepository()

    def receive_message(self, message: IncomingTextMessage) -> ConversationContext:
        now = utc_now()
        with self.database.transaction() as connection:
            existing = self.messages.get_by_provider_id(
                connection,
                direction="incoming",
                provider_message_id=message.message_id,
            )
            if existing is not None:
                conversation = self.conversations.get_by_id(
                    connection,
                    existing.conversation_id,
                )
                if conversation is None:
                    raise RuntimeError("El mensaje existente no tiene conversacion")
                reply = self.messages.get_reply(connection, existing.id)
                return ConversationContext(
                    patient_id=conversation.patient_id,
                    conversation_id=conversation.id,
                    incoming_message_id=existing.id,
                    reply_status=reply.status if reply else None,
                )

            patient = self.patients.get_or_create(connection, message.sender, now)
            conversation = self.conversations.get_or_create_active(
                connection,
                patient_id=patient.id,
                now=now,
            )
            incoming = self.messages.create_incoming(
                connection,
                conversation_id=conversation.id,
                provider_message_id=message.message_id,
                text=message.text,
                message_type=message.message_type,
                now=now,
            )
            self.conversations.mark_active(connection, conversation.id, now)

            return ConversationContext(
                patient_id=patient.id,
                conversation_id=conversation.id,
                incoming_message_id=incoming.id,
                reply_status=None,
            )

    async def build_reply(self, context: ConversationContext) -> str:
        if self.llm_provider is None:
            raise RuntimeError("ConversationService requiere un proveedor LLM")
        messages = self.build_chat_messages(context)
        return await self.llm_provider.generate(messages)

    def build_chat_messages(
        self,
        context: ConversationContext,
        max_history_messages: int | None = None,
    ) -> list[ChatMessage]:
        """Construye el contexto del LLM con el historial más reciente."""
        history_limit = (
            self.max_history_messages
            if max_history_messages is None
            else max_history_messages
        )
        if history_limit <= 0:
            raise ValueError("max_history_messages debe ser positivo")

        history = self.get_history(context.conversation_id)
        recent_history = history[-history_limit:]
        messages = [ChatMessage(role="system", content=SYSTEM_PROMPT)]

        for message in recent_history:
            if message.direction == "incoming":
                role = "user"
            elif message.direction == "outgoing" and message.status == "sent":
                role = "assistant"
            else:
                continue
            messages.append(ChatMessage(role=role, content=message.text))

        return messages

    def record_reply_sent(
        self,
        context: ConversationContext,
        body: str,
        provider_message_id: str | None,
    ) -> MessageRecord:
        return self._record_reply(
            context=context,
            body=body,
            status="sent",
            provider_message_id=provider_message_id,
        )

    def record_reply_failed(
        self,
        context: ConversationContext,
        body: str,
    ) -> MessageRecord:
        return self._record_reply(
            context=context,
            body=body,
            status="failed",
            provider_message_id=None,
        )

    def _record_reply(
        self,
        context: ConversationContext,
        body: str,
        status: str,
        provider_message_id: str | None,
    ) -> MessageRecord:
        with self.database.transaction() as connection:
            return self.messages.save_reply(
                connection,
                incoming_message_id=context.incoming_message_id,
                conversation_id=context.conversation_id,
                text=body,
                status=status,
                provider_message_id=provider_message_id,
                now=utc_now(),
            )

    def get_history(self, conversation_id: int) -> list[MessageRecord]:
        with self.database.transaction() as connection:
            return self.messages.list_for_conversation(connection, conversation_id)
