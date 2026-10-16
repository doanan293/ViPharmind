"""Fakes shared by the E2E tests."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import TypeVar

from pharma_agent.domain.llm.decision import Decision, NoulQuestion
from pharma_agent.domain.llm.models import ChatMessage, LlmRole, LlmUsage, StreamDelta
from pharma_agent.domain.retrieval.models import Hit, Query, ReleaseScope
from pharma_agent.domain.retrieval.service import RetrievalConfig, RetrievalService
from pharma_agent.infrastructure.retrieval.llama_cpp_reranker import NoopReranker
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ScriptedLlm:
    """Returns scripted structured results per role and a fixed streamed answer."""

    def __init__(
        self, answer: str = "Trả lời [1].", stream_error: Exception | None = None
    ) -> None:
        self.answer = answer
        self.stream_error = stream_error
        self.scripts: dict[LlmRole, list[BaseModel | Exception]] = {}
        self.calls: list[tuple[LlmRole, list[ChatMessage]]] = []

    def script(self, role: LlmRole, *responses: BaseModel | Exception) -> None:
        self.scripts.setdefault(role, []).extend(responses)

    async def structured(
        self, role: LlmRole, messages: Sequence[ChatMessage], schema: type[T]
    ) -> tuple[T, LlmUsage]:
        self.calls.append((role, list(messages)))
        response = self.scripts[role].pop(0)
        if isinstance(response, Exception):
            raise response
        assert isinstance(response, schema)
        return response, LlmUsage(prompt_tokens=10, completion_tokens=2)

    async def stream(
        self, role: LlmRole, messages: Sequence[ChatMessage]
    ) -> AsyncIterator[StreamDelta]:
        self.calls.append((role, list(messages)))
        if self.stream_error is not None:
            raise self.stream_error
        yield StreamDelta(text=self.answer)
        yield StreamDelta(usage=LlmUsage(prompt_tokens=100, completion_tokens=20))


NAMESPACE = uuid.UUID("0f5c1d0e-7a8b-4c3d-9e2f-1a2b3c4d5e6f")
RELEASE = uuid.uuid5(NAMESPACE, "release")


def make_hit(
    label: str, section_key: str, *, ordinal: int = 1, score: float = 0.5
) -> Hit:
    return Hit(
        chunk_version_id=uuid.uuid5(NAMESPACE, label),
        release_id=RELEASE,
        collection_id=uuid.uuid5(NAMESPACE, "collection"),
        document_key="drug:paracetamol",
        ordinal=ordinal,
        section_keys=[section_key],
        headings=["Liều dùng"],
        source="Dược thư Quốc gia Việt Nam",
        title="Paracetamol",
        start_page=1,
        end_page=1,
        context_header="Paracetamol > Liều dùng",
        chunk_text=f"text of {label}",
        embedding_text=f"text of {label}",
        fusion_score=score,
    )


class FakeRetriever:
    def __init__(self, hits: list[Hit]) -> None:
        self.hits = hits
        self.queries: list[list[str]] = []

    async def search_many(
        self, queries: Sequence[Query], top_k: int, scope: ReleaseScope | None = None
    ) -> list[list[Hit]]:
        # Evaluation runs have no user, so the harness never passes a scope.
        assert scope is None
        self.queries.append([query.text for query in queries])
        return [list(self.hits[:top_k]) for _ in queries]


def retrieval_service(retriever: FakeRetriever) -> RetrievalService:
    return RetrievalService(
        retriever, NoopReranker(), RetrievalConfig(candidate_k=5, rerank_top_n=3)
    )


class FakeDecision:
    """Scripted decision model: returns the given answers or raises the given error."""

    def __init__(self, answers: dict[str, float] | Exception) -> None:
        self.answers = answers
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
        if isinstance(self.answers, Exception):
            raise self.answers
        return Decision(
            answers=self.answers,
            model="jev-1.13.0",
            input_tokens=300,
            seconds=0.2,
            raw={"answers": {}},
        )
