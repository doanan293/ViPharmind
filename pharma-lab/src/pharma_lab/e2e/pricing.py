"""List prices of every model a run may use (spec v2 §2.5).

USD per million tokens, read on the date given. Costs in the paper are list prices times
tokens, for self-hosted models too (Qwen3.5-9B at its OpenRouter price), never GPU hours.
Retrieval is priced per reranked candidate and per query token.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pharma_lab.e2e.records import AnswerRecord


class UnpricedModel(ValueError):
    pass


@dataclass(frozen=True)
class ModelPrice:
    usd_per_1m_prompt: float
    usd_per_1m_completion: float
    source: str
    date: str


_GOOGLE = "https://ai.google.dev/gemini-api/docs/pricing"
_OPENROUTER_QWEN = "https://openrouter.ai/qwen/qwen3.5-9b (DeepInfra bf16)"
# OpenRouter serves the retrieval models only through /api/v1/embeddings and
# /api/v1/rerank and lists no price for them (checked 2026-10-16). Until the price of the
# pair the agent uses is read (phase 0 plan, Task 4 Step 3b), each carries Qwen3.5-9B's
# input price, an upper bound for models of that size or smaller.
_UPPER_BOUND = "upper bound: " + _OPENROUTER_QWEN

PRICES: dict[str, ModelPrice] = {
    "gemini-3.8-flash-high": ModelPrice(0.75, 3.75, _GOOGLE, "2026-10-14"),
    "gemini-3.1-flash-lite": ModelPrice(0.25, 1.50, _GOOGLE, "2026-10-14"),
    "claude-opus-5-5": ModelPrice(
        4.0, 20.0, "https://claude.com/pricing", "2026-10-14"
    ),
    # The self-hosted name and the OpenRouter id are the same model at the same price.
    "qwen3.5:9b-q8_0": ModelPrice(0.10, 0.15, _OPENROUTER_QWEN, "2026-10-14"),
    "qwen/qwen3.5-9b": ModelPrice(0.10, 0.15, _OPENROUTER_QWEN, "2026-10-14"),
    "~typesafe/jev-latest": ModelPrice(
        0.042, 0.0, "https://docs.typesafe.ai/models.md", "2026-10-14"
    ),
    **{
        name: ModelPrice(0.10, 0.0, _UPPER_BOUND, "2026-10-16")
        for name in (
            "qwen3-embedding:0.6b-q8_0",
            "qwen3-embedding:4b-q8_0",
            "qwen3-embedding:8b-q8_0",
            "bge-m3:567m-q8_0",
            "embeddinggemma:300m-q8_0",
            "qwen3-reranker:0.6b-q8_0",
            "qwen3-reranker:4b-q8_0",
            "qwen3-reranker:8b-q8_0",
            "bge-reranker-v2-m3:q8_0",
        )
    },
}


@dataclass(frozen=True)
class RetrievalPricing:
    # Mean Qwen3 tokens of a chunk's embedding text, measured on the formulary bundle
    # (13,408 chunks, 2026-10-15, spec v2 §3.0c); the reranker reads one chunk per
    # candidate.
    candidate_tokens_mean: int = 1_001
    # Vietnamese characters per token (spec v2 §2.1), for the short query embeddings.
    chars_per_token: float = 3.1


RETRIEVAL = RetrievalPricing()


def price_of(model: str) -> ModelPrice:
    try:
        return PRICES[model]
    except KeyError as exc:
        raise UnpricedModel(
            f"no list price for model {model!r}; add it to pricing.PRICES"
        ) from exc


def turn_cost_usd(
    record: AnswerRecord, role_models: Mapping[str, Mapping[str, object]]
) -> float:
    """USD of the LLM and decision-model calls of one turn."""
    total = 0.0
    for role, usage in record.usage_by_role.items():
        price = price_of(str(role_models[role]["model"]))
        total += usage.prompt_tokens * price.usd_per_1m_prompt / 1e6
        total += usage.completion_tokens * price.usd_per_1m_completion / 1e6
    return total


def retrieval_cost_usd(
    record: AnswerRecord,
    embedding_model: str,
    reranker_model: str | None,
    pricing: RetrievalPricing = RETRIEVAL,
) -> float:
    """USD of embedding every search query and reranking every scored candidate; the
    models come from the run's identity (`retrieval.embedding_model`, `rerank.model`)."""
    reranker = (
        0.0 if reranker_model is None else price_of(reranker_model).usd_per_1m_prompt
    )
    embedding = price_of(embedding_model).usd_per_1m_prompt
    query_tokens = sum(
        len(query) / pricing.chars_per_token
        for queries in record.search_queries
        for query in queries
    )
    reranked_tokens = record.rerank_scored * pricing.candidate_tokens_mean
    return (reranked_tokens * reranker + query_tokens * embedding) / 1e6
