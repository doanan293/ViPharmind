from uuid import UUID

from pydantic import BaseModel, Field

from pharma_agent.domain.retrieval.models import Hit
from pharma_agent.domain.shared.text import make_snippet


class Evidence(BaseModel):
    """One chunk the agent may cite; its text is the chunk as stored (spec v2 §3.0c)."""

    ref: str
    hit: Hit
    superseded: bool = False

    @property
    def score(self) -> float:
        return self.hit.score

    def text(self) -> str:
        return self.hit.chunk_text

    def char_count(self) -> int:
        return len(self.hit.chunk_text)


class EvidenceSet(BaseModel):
    items: list[Evidence] = Field(default_factory=list)

    def active(self) -> list[Evidence]:
        return sorted(
            (e for e in self.items if not e.superseded),
            key=lambda e: e.score,
            reverse=True,
        )

    def rerank_scores(self) -> dict[UUID, float]:
        """Rerank scores already computed in this run, superseded evidence included."""
        return {
            e.hit.chunk_version_id: e.hit.rerank_score
            for e in self.items
            if e.hit.rerank_score is not None
        }

    def supersede_all(self) -> None:
        for evidence in self.items:
            evidence.superseded = True

    def merge(self, retrieved: list[Hit]) -> list[Evidence]:
        by_chunk = {e.hit.chunk_version_id: e for e in self.items}
        for hit in retrieved:
            existing = by_chunk.get(hit.chunk_version_id)
            if existing is None:
                evidence = Evidence(ref=f"E{len(self.items) + 1}", hit=hit)
                self.items.append(evidence)
                by_chunk[hit.chunk_version_id] = evidence
                continue
            merged_queries = list(existing.hit.matched_queries)
            merged_queries.extend(
                q for q in hit.matched_queries if q not in merged_queries
            )
            existing.hit = hit.model_copy(
                update={
                    "rerank_score": _max_optional(
                        existing.hit.rerank_score, hit.rerank_score
                    ),
                    "fusion_score": max(existing.hit.fusion_score, hit.fusion_score),
                    "matched_queries": merged_queries,
                }
            )
            existing.superseded = False
        return self.active()

    def pack(self, max_chars: int) -> list[Evidence]:
        """Whole chunks by score; once one does not fit, it and every lower one are
        dropped, so the budget cuts the weakest evidence, never truncates a chunk."""
        packed: list[Evidence] = []
        remaining = max_chars
        for evidence in self.active():
            if evidence.char_count() > remaining:
                break
            packed.append(evidence)
            remaining -= evidence.char_count()
        return packed

    def summary_view(self, snippet_chars: int = 300) -> str:
        lines: list[str] = []
        for evidence in self.active():
            hit = evidence.hit
            parts = [
                evidence.ref,
                hit.context_header,
                hit.page_label,
                make_snippet(hit.chunk_text, snippet_chars),
            ]
            line = " | ".join(part for part in parts if part)
            hints = hit.term_hints()
            if hints:
                line += f" | gợi ý thuật ngữ: {', '.join(hints[:6])}"
            lines.append(line)
        return "\n".join(lines) if lines else "(không có evidence)"

    def context_view(
        self, packed: list[Evidence]
    ) -> tuple[str, list[tuple[int, Evidence]]]:
        numbered: list[tuple[int, Evidence]] = []
        blocks: list[str] = []
        for index, evidence in enumerate(packed, start=1):
            numbered.append((index, evidence))
            hit = evidence.hit
            label = f" ({hit.page_label})" if hit.page_label else ""
            blocks.append(f"[{index}] {hit.context_header}{label}\n{evidence.text()}")
        return "\n\n".join(blocks), numbered


def _max_optional(a: float | None, b: float | None) -> float | None:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)
