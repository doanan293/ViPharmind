from collections.abc import AsyncIterator, Sequence
from typing import Protocol, TypeVar

from pydantic import BaseModel

from pharma_agent.domain.llm.models import (
    ChatMessage,
    LlmRole,
    LlmUsage,
    StreamDelta,
    ToolSpec,
    ToolTurn,
)
from pharma_agent.domain.shared.errors import DomainError

T = TypeVar("T", bound=BaseModel)


class LlmError(DomainError):
    code = "LLM_ERROR"


class LlmPort(Protocol):
    async def structured(
        self, role: LlmRole, messages: Sequence[ChatMessage], schema: type[T]
    ) -> tuple[T, LlmUsage]:
        """Return a validated instance of `schema` plus token usage. Raises LlmError."""
        ...

    def stream(
        self, role: LlmRole, messages: Sequence[ChatMessage]
    ) -> AsyncIterator[StreamDelta]:
        """Yield text deltas; the final delta carries `usage`. Raises LlmError."""
        ...

    async def tool_call(
        self, role: LlmRole, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]
    ) -> tuple[ToolTurn, LlmUsage]:
        """One model call that may request tools; empty `tools` forbids tool calls.
        Raises LlmError."""
        ...
