import uuid
from datetime import UTC, datetime

from pharma_agent.domain.agent.budget import BudgetLimits
from pharma_agent.domain.agent.run import AgentRun
from pharma_agent.domain.conversation.models import Citation
from pharma_agent.domain.retrieval.models import (
    Hit,
)
from pharma_agent.domain.retrieval.service import SearchResult

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
TEST_NAMESPACE = uuid.UUID("5f0c7a52-3d4e-4b8a-9c21-6e7f8a9b0c1d")
RELEASE_ID = uuid.uuid5(TEST_NAMESPACE, "release")
COLLECTION_ID = uuid.uuid5(TEST_NAMESPACE, "collection")
SECTION_KEY = "drug:paracetamol:lieu-luong-va-cach-dung"
SOURCE = "Dược thư Quốc gia Việt Nam"


def chunk_uuid(label: str) -> uuid.UUID:
    """Stable chunk version id for a readable test label."""
    return uuid.uuid5(TEST_NAMESPACE, f"chunk:{label}")


def make_hit(
    label: str,
    *,
    document_key: str = "drug:paracetamol",
    ordinal: int = 1,
    section_keys: list[str] | None = None,
    headings: list[str] | None = None,
    fusion: float = 0.5,
    rerank: float | None = None,
    text: str = "paracetamol 500 mg",
    title: str = "Paracetamol",
    section: str = "Liều dùng",
    start_page: int | None = 10,
    end_page: int | None = 11,
) -> Hit:
    keys = [SECTION_KEY] if section_keys is None else section_keys
    names = [section] if headings is None else headings
    return Hit(
        chunk_version_id=chunk_uuid(label),
        release_id=RELEASE_ID,
        collection_id=COLLECTION_ID,
        document_key=document_key,
        ordinal=ordinal,
        section_keys=keys,
        headings=names,
        source=SOURCE,
        title=title,
        start_page=start_page,
        end_page=end_page,
        context_header=f"{title} > {'; '.join(names)}",
        chunk_text=text,
        embedding_text=f"{title} > {'; '.join(names)}\n\n{text}",
        fusion_score=fusion,
        rerank_score=rerank,
        matched_queries=["q1"],
    )


def make_citation(label: str, *, index: int = 1) -> Citation:
    return Citation(
        index=index,
        chunk_version_id=chunk_uuid(label),
        release_id=RELEASE_ID,
        source=SOURCE,
        title="Paracetamol",
        section="Liều dùng",
        start_page=10,
        end_page=11,
        snippet="paracetamol 500 mg",
    )


def search_result(*labels: str, error: str | None = None) -> SearchResult:
    return SearchResult(
        items=[make_hit(label, rerank=0.8) for label in labels], error=error
    )


def make_run(
    query: str = "Paracetamol liều người lớn?",
    *,
    max_llm_calls: int = 10,
    max_search_rounds: int = 3,
    max_tokens: int = 40_000,
) -> AgentRun:
    return AgentRun.start(
        user_id="u1",
        original_query=query,
        limits=BudgetLimits(
            max_llm_calls=max_llm_calls,
            max_search_rounds=max_search_rounds,
            max_tokens=max_tokens,
        ),
        now=NOW,
        run_id="run-1",
    )
