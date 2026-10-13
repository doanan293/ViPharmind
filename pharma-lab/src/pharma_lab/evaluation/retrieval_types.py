from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RetrievalCandidate:
    chunk_id: str
    score: float
    rank: int
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    rerank_score: float | None = None
    document_text: str | None = None
    document_hash: str | None = None

    @property
    def resolved_chunk_id(self) -> str:
        return self.chunk_id or str(
            self.payload.get("chunk_id") or self.payload.get("chunk_key") or ""
        )

    @property
    def section_id(self) -> str:
        return str(self.payload.get("section_id") or "")

    def with_rerank_score(self, rerank_score: float, rank: int) -> "RetrievalCandidate":
        return RetrievalCandidate(
            chunk_id=self.resolved_chunk_id,
            score=self.score,
            rank=rank,
            source=self.source,
            payload=self.payload,
            rerank_score=rerank_score,
            document_text=self.document_text,
            document_hash=self.document_hash,
        )
