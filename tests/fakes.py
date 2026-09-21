from collections.abc import Sequence

from llm_provider import ChatMessage, LLMProviderError, LLMResponse


GENERATED_REPLY = "Respuesta generada por el proveedor."


class FakeLLMProvider:
    """Proveedor local que registra las solicitudes sin acceder a una API."""

    def __init__(
        self,
        reply: LLMResponse = GENERATED_REPLY,
        error: LLMProviderError | None = None,
        replies: Sequence[LLMResponse] | None = None,
    ) -> None:
        self.reply = reply
        self.error = error
        self.replies = tuple(replies or ())
        self.received_messages: list[list[ChatMessage]] = []

    @property
    def call_count(self) -> int:
        return len(self.received_messages)

    async def generate(self, messages: Sequence[ChatMessage]) -> LLMResponse:
        self.received_messages.append(list(messages))
        if self.error is not None:
            raise self.error
        if self.replies:
            reply_index = min(len(self.received_messages) - 1, len(self.replies) - 1)
            return self.replies[reply_index]
        return self.reply
