from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    # The answer to one tool call (ReAct agent, spec v2 §2.4).
    TOOL = "tool"


class ToolCall(BaseModel):
    """One tool call a model requested; `arguments` is its raw JSON text."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    arguments: str


class ChatMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: ChatRole
    content: str
    # Set on an assistant message that called tools.
    tool_calls: tuple[ToolCall, ...] = ()
    # Set on a tool message: the call it answers.
    tool_call_id: str | None = None


# "none" keeps the declared tools (a history with tool calls needs them) but forbids calls.
ToolChoice = Literal["auto", "none"]


class ToolSpec(BaseModel):
    """A tool offered to the model: its name, purpose and JSON-schema arguments."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    parameters: dict[str, object]


class ToolTurn(BaseModel):
    """One tool-calling model response: text, the calls it requested, why it stopped."""

    model_config = ConfigDict(frozen=True)

    text: str
    tool_calls: tuple[ToolCall, ...]
    finish_reason: str


class LlmUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    prompt_tokens: int = 0
    completion_tokens: int = 0
    # Reasoning tokens inside completion_tokens, when the server reports them.
    reasoning_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: "LlmUsage") -> "LlmUsage":
        return LlmUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
        )


class LlmRole(StrEnum):
    GUARDRAIL = "guardrail"
    REPHRASE = "rephrase"
    JUDGE = "judge"
    REFINE = "refine"
    ANSWER = "answer"
    SUMMARIZER = "summarizer"
    # The ReAct agent's model calls (spec v2 §2.4).
    AGENT = "agent"


class StreamDelta(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str = ""
    usage: LlmUsage | None = None


def system(content: str) -> ChatMessage:
    return ChatMessage(role=ChatRole.SYSTEM, content=content)


def user(content: str) -> ChatMessage:
    return ChatMessage(role=ChatRole.USER, content=content)
