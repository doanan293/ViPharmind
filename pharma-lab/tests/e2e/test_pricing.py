import pytest

from pharma_lab.e2e.pricing import (
    PRICES,
    UnpricedModel,
    retrieval_cost_usd,
    turn_cost_usd,
)
from pharma_lab.e2e.records import AnswerRecord, TokenUsage


def record(**fields: object) -> AnswerRecord:
    base = {"item_id": "e2e-ans-0001", "config": "full", "status": "completed"}
    return AnswerRecord.model_validate({**base, **fields})


def test_turn_cost_prices_each_role_by_its_model() -> None:
    usage = {
        "guardrail": TokenUsage(calls=1, prompt_tokens=1_000_000),
        "answer": TokenUsage(
            calls=1, prompt_tokens=1_000_000, completion_tokens=1_000_000
        ),
    }
    roles = {
        "guardrail": {"model": "gemini-3.1-flash-lite"},
        "answer": {"model": "gemini-3.8-flash-high"},
    }
    assert turn_cost_usd(record(usage_by_role=usage), roles) == pytest.approx(
        0.25 + 0.75 + 3.75
    )


def test_unpriced_model_is_an_error() -> None:
    usage = {"answer": TokenUsage(calls=1, prompt_tokens=10)}
    with pytest.raises(UnpricedModel, match="gpt-7-nano"):
        turn_cost_usd(record(usage_by_role=usage), {"answer": {"model": "gpt-7-nano"}})


def test_retrieval_cost_counts_reranked_candidates_and_query_tokens() -> None:
    rec = record(rerank_scored=20, search_queries=[["x" * 31]])
    reranker = PRICES["qwen3-reranker:8b-q8_0"].usd_per_1m_prompt
    embedding = PRICES["qwen3-embedding:4b-q8_0"].usd_per_1m_prompt
    expected = (20 * 1_001 * reranker + 10 * embedding) / 1_000_000
    assert retrieval_cost_usd(
        rec, "qwen3-embedding:4b-q8_0", "qwen3-reranker:8b-q8_0"
    ) == pytest.approx(expected)
    assert retrieval_cost_usd(rec, "qwen3-embedding:4b-q8_0", None) == pytest.approx(
        10 * embedding / 1_000_000
    )


def test_every_paper_model_has_a_dated_price() -> None:
    for name in (
        "qwen3.5:9b-q8_0",
        "qwen/qwen3.5-9b",
        "gemini-3.8-flash-high",
        "gemini-3.1-flash-lite",
        "claude-opus-5-5",
        "~typesafe/jev-latest",
    ):
        assert PRICES[name].date and PRICES[name].source
