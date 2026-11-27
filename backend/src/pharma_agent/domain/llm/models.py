from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ChatRole(StrEnum):
    """Author of a chat message."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    """One chat message sent to a model."""

    model_config = ConfigDict(frozen=True)

    role: ChatRole
    content: str


class LlmUsage(BaseModel):
    """Tokens one or more LLM calls used."""

    model_config = ConfigDict(frozen=True)

    prompt_tokens: int = 0
    completion_tokens: int = 0
    # Reasoning tokens inside completion_tokens, when the server reports them.
    reasoning_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """Prompt plus completion tokens."""
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: "LlmUsage") -> "LlmUsage":
        """Field-wise sum of two usages."""
        return LlmUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
        )


class LlmRole(StrEnum):
    """Which step a model call serves; each role can be configured separately."""

    GUARDRAIL = "guardrail"
    REPHRASE = "rephrase"
    JUDGE = "judge"
    REFINE = "refine"
    ANSWER = "answer"
    SUMMARIZER = "summarizer"
    # The ReAct agent's model calls (spec v2 §2.4).
    AGENT = "agent"


class StreamDelta(BaseModel):
    """A piece of a streamed answer; the final piece carries the usage."""

    model_config = ConfigDict(frozen=True)

    text: str = ""
    usage: LlmUsage | None = None


def system(content: str) -> ChatMessage:
    """A system message with `content`."""
    return ChatMessage(role=ChatRole.SYSTEM, content=content)


def user(content: str) -> ChatMessage:
    """A user message with `content`."""
    return ChatMessage(role=ChatRole.USER, content=content)
