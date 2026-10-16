"""Measure Jev's token count for a judge state of a given size (spec v2 §2.1, first step)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pharma_agent.domain.corpus.bundle import KnowledgeBundle
from pharma_agent.domain.llm.decision import DecisionPort, NoulQuestion
from pharma_agent.domain.llm.models import LlmRole

from pharma_lab.bundle.chunks import iter_document_chunks

# Tokens the evidence may take of the 32k state budget (spec v2 §2.1).
TOKEN_CEILING = 24_000


@dataclass(frozen=True)
class ProbeResult:
    input_tokens: int
    chars: int
    chars_per_token: float
    seconds: float
    model: str


def longest_chunk_texts(bundle: KnowledgeBundle) -> list[str]:
    """The text the judge reads for every chunk of the bundle, longest first."""
    texts = [
        draft.chunk_text
        for document in iter_document_chunks(bundle)
        for draft in document.drafts
    ]
    return sorted(texts, key=len, reverse=True)


def probe_state(chunks: Sequence[str], chars: int) -> dict[str, object]:
    evidence: list[dict[str, object]] = []
    remaining = chars
    for index, text in enumerate(chunks, start=1):
        if remaining <= 0:
            break
        piece = text[:remaining]
        evidence.append({"id": index, "source": f"probe {index}", "text": piece})
        remaining -= len(piece)
    if remaining > 0:
        raise ValueError(
            f"chunks hold {chars - remaining} characters, fewer than {chars}"
        )
    return {
        "user_question": "probe",
        "standalone_query": "probe",
        "asked_intents": [],
        "evidence": evidence,
    }


async def run_probe(decision: DecisionPort, state: dict[str, object]) -> ProbeResult:
    result = await decision.decide(
        LlmRole.JUDGE,
        state,
        {"warmup": NoulQuestion(instructions="Is `evidence` empty?")},
    )
    evidence = state["evidence"]
    assert isinstance(evidence, list)
    chars = sum(len(str(item["text"])) for item in evidence)
    return ProbeResult(
        result.input_tokens,
        chars,
        chars / max(1, result.input_tokens),
        result.seconds,
        result.model,
    )


def recommended_evidence_chars(result: ProbeResult, current: int = 60_000) -> int:
    if result.input_tokens <= TOKEN_CEILING:
        return current
    return int(current * TOKEN_CEILING / result.input_tokens // 1_000) * 1_000
