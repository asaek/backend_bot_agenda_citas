from collections.abc import Sequence

from llm_provider import ChatMessage, LLMProviderError


GENERATED_REPLY = "Respuesta generada por el proveedor."


class FakeLLMProvider:
    """Proveedor local que registra las solicitudes sin acceder a una API."""

    def __init__(
        self,
        reply: str = GENERATED_REPLY,
        error: LLMProviderError | None = None,
    ) -> None:
        self.reply = reply
        self.error = error
        self.received_messages: list[list[ChatMessage]] = []

    @property
    def call_count(self) -> int:
        return len(self.received_messages)

    async def generate(self, messages: Sequence[ChatMessage]) -> str:
        self.received_messages.append(list(messages))
        if self.error is not None:
            raise self.error
        return self.reply
