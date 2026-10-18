from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: ChatRole
    content: str


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
