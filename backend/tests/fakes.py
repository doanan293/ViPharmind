import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, TypeVar

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage, ToolCall, UsageMetadata
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from pharma_agent.application.chat.context import TurnDeps
from pharma_agent.domain.guardrail.service import GuardrailService
from pharma_agent.domain.llm.decision import Decision, DecisionPort, NoulQuestion
from pharma_agent.domain.llm.models import (
    ChatMessage,
    LlmRole,
    LlmUsage,
    StreamDelta,
)
from pharma_agent.domain.llm.port import LlmError
from pharma_agent.domain.retrieval.models import (
    Hit,
    Query,
    ReleaseScope,
)
from pharma_agent.domain.retrieval.ports import Reranker, RetrievalError
from pharma_agent.domain.retrieval.service import RetrievalConfig, RetrievalService
from pharma_agent.domain.shared.clock import FixedClock

T = TypeVar("T", bound=BaseModel)

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


class FakeLlm:
    """Scripted LLM: one queue of structured responses per role, one streamed answer."""

    def __init__(self) -> None:
        self.structured_responses: dict[LlmRole, list[BaseModel | Exception]] = {}
        self.stream_text = (
            "Paracetamol người lớn 500 mg mỗi 4-6 giờ [1], tối đa 4 g/ngày [1]."
        )
        self.stream_error: Exception | None = None
        self.stream_delay: float = 0.0
        self.calls: list[tuple[LlmRole, list[ChatMessage]]] = []

    def script(self, role: LlmRole, *responses: BaseModel | Exception) -> None:
        self.structured_responses.setdefault(role, []).extend(responses)

    async def structured(
        self, role: LlmRole, messages: Sequence[ChatMessage], schema: type[T]
    ) -> tuple[T, LlmUsage]:
        self.calls.append((role, list(messages)))
        queue = self.structured_responses.get(role) or []
        if not queue:
            raise AssertionError(f"no scripted response for role {role.value}")
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        assert isinstance(item, schema), (
            f"scripted {type(item).__name__} but node asked for {schema.__name__}"
        )
        return item, LlmUsage(prompt_tokens=100, completion_tokens=10)

    async def stream(
        self, role: LlmRole, messages: Sequence[ChatMessage]
    ) -> AsyncIterator[StreamDelta]:
        self.calls.append((role, list(messages)))
        if self.stream_delay:
            await asyncio.sleep(self.stream_delay)
        if self.stream_error is not None:
            raise self.stream_error
        text = self.stream_text
        for start in range(0, len(text), 7):
            yield StreamDelta(text=text[start : start + 7])
        yield StreamDelta(usage=LlmUsage(prompt_tokens=800, completion_tokens=60))

    def calls_for(self, role: LlmRole) -> list[list[ChatMessage]]:
        return [messages for r, messages in self.calls if r is role]


class FakeChatModel(BaseChatModel):
    """Scripted LangChain chat model for the ReAct agent: each call returns the next
    scripted AIMessage (or raises the next scripted error). `bind_tools` returns the
    model itself and records what each call was bound with."""

    responses: list[AIMessage | Exception] = Field(default_factory=list)
    # One entry per model call: the messages it saw, its tool names and tool_choice.
    seen: list[list[BaseMessage]] = Field(default_factory=list)
    bound_tools: list[list[str]] = Field(default_factory=list)
    tool_choices: list[str | None] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake-chat"

    def script(self, *responses: AIMessage | Exception) -> None:
        self.responses.extend(responses)

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        self.bound_tools.append(
            [t.name if isinstance(t, BaseTool) else str(t) for t in tools]
        )
        self.tool_choices.append(tool_choice)
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.seen.append(list(messages))
        if not self.responses:
            raise AssertionError("no scripted agent response")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return ChatResult(generations=[ChatGeneration(message=response)])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop)


AGENT_USAGE = UsageMetadata(input_tokens=200, output_tokens=20, total_tokens=220)


def searching(*queries: tuple[str, str]) -> AIMessage:
    """A response that calls search_corpus once per (call id, query), in order."""
    return AIMessage(
        content="",
        tool_calls=[
            ToolCall(name="search_corpus", args={"query": q}, id=cid, type="tool_call")
            for cid, q in queries
        ],
        usage_metadata=AGENT_USAGE,
        response_metadata={"finish_reason": "tool_calls"},
    )


def answering(text: str, *, finish_reason: str = "stop") -> AIMessage:
    return AIMessage(
        content=text,
        usage_metadata=AGENT_USAGE,
        response_metadata={"finish_reason": finish_reason},
    )


class FakeRetriever:
    def __init__(self, *rounds: list[Hit] | Exception) -> None:
        self.rounds = list(rounds)
        self.calls: list[list[Query]] = []
        self.scopes: list[ReleaseScope | None] = []

    async def search_many(
        self, queries: Sequence[Query], top_k: int, scope: ReleaseScope | None = None
    ) -> list[list[Hit]]:
        self.calls.append(list(queries))
        self.scopes.append(scope)
        if not self.rounds:
            return [[] for _ in queries]
        current = self.rounds.pop(0)
        if isinstance(current, Exception):
            raise current
        return [
            [h.model_copy(update={"matched_queries": [q.text]}) for h in current]
            for q in queries
        ]


class FakeReranker:
    def __init__(self) -> None:
        self.received: list[list[uuid.UUID]] = []
        self.queries: list[str] = []

    async def rerank(self, query: str, hits: Sequence[Hit], top_n: int) -> list[Hit]:
        self.received.append([h.chunk_version_id for h in hits])
        self.queries.append(query)
        ordered = sorted(hits, key=lambda h: h.fusion_score, reverse=True)[:top_n]
        return [
            h.model_copy(update={"rerank_score": round(1.0 - i * 0.1, 2)})
            for i, h in enumerate(ordered)
        ]


FAKE_EMBEDDING_MODEL = "fake-embedding-4d"
FAKE_EMBEDDING_DIMENSION = 4


def fake_vector(text: str) -> list[float]:
    """Deterministic vector from sha256(text).

    Components are k/16 (k in 1..16), so they survive float32 encoding exactly and are never
    all zero.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [(digest[i] % 16 + 1) / 16 for i in range(FAKE_EMBEDDING_DIMENSION)]


class FakeEmbedder:
    """Implements `pharma_agent.domain.corpus.ports.Embedder`; records every batch."""

    def __init__(self, *, fail_on_batch: int | None = None) -> None:
        self.batches: list[list[str]] = []
        self._fail_on_batch = fail_on_batch

    @property
    def model(self) -> str:
        return FAKE_EMBEDDING_MODEL

    @property
    def dimension(self) -> int:
        return FAKE_EMBEDDING_DIMENSION

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        if self._fail_on_batch is not None and len(self.batches) == self._fail_on_batch:
            raise RetrievalError("fake embedding endpoint unavailable")
        return [fake_vector(text) for text in texts]


def build_deps(
    llm: FakeLlm,
    retriever: FakeRetriever,
    reranker: Reranker | None = None,
    decisions: Mapping[LlmRole, DecisionPort] | None = None,
    guard_decision: DecisionPort | None = None,
    agent_model: BaseChatModel | None = None,
) -> TurnDeps:
    return TurnDeps(
        llm=llm,
        guardrail=GuardrailService(llm, decision=guard_decision),
        retrieval=RetrievalService(
            retriever,
            reranker if reranker is not None else FakeReranker(),
            RetrievalConfig(candidate_k=5, rerank_top_n=3),
        ),
        clock=FixedClock(NOW),
        decisions=dict(decisions or {}),
        agent_model=agent_model,
    )


__all__ = [
    "FAKE_EMBEDDING_DIMENSION",
    "FAKE_EMBEDDING_MODEL",
    "FakeChatModel",
    "FakeEmbedder",
    "FakeLlm",
    "FakeReranker",
    "FakeRetriever",
    "LlmError",
    "RetrievalError",
    "answering",
    "build_deps",
    "fake_vector",
    "searching",
]


class FakeDecision:
    """Scripted decision model: returns the given answers or raises the given error.
    A list scripts one response per call; its last entry answers every later call."""

    def __init__(
        self,
        answers: dict[str, float] | Exception | list[dict[str, float] | Exception],
    ) -> None:
        self.responses = list(answers) if isinstance(answers, list) else [answers]
        self.calls: list[
            tuple[LlmRole, dict[str, object], dict[str, NoulQuestion]]
        ] = []

    async def decide(
        self,
        role: LlmRole,
        state: Mapping[str, object],
        questions: Mapping[str, NoulQuestion],
    ) -> Decision:
        self.calls.append((role, dict(state), dict(questions)))
        response = (
            self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        )
        if isinstance(response, Exception):
            raise response
        return Decision(
            answers=response,
            model="jev-1.13.0",
            input_tokens=300,
            seconds=0.2,
            raw={"answers": {}},
        )
