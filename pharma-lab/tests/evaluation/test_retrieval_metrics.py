import math

import pytest

from pharma_lab.evaluation.retrieval_metrics import (
    is_hit,
    ranking_scores,
    satisfied_units,
    score_ranked_payloads,
)

LEAFLET_CHUNK = "leaflet:thuoc-tri-tieu-duong:acarbose-a:chunk-001"


def _payload(chunk_id: str, *sections: str) -> dict:
    document, _, _ordinal = chunk_id.rpartition(":chunk-")
    return {
        "chunk_id": chunk_id,
        "document_id": document,
        "section_ids": list(sections),
    }


def _ranked(*sections: str) -> list[dict]:
    return [
        _payload(f"{section.rsplit(':', 1)[0]}:chunk-{index:03d}", section)
        for index, section in enumerate(sections, start=1)
    ]


def _section_row(section: str = "drug:a:lieu") -> dict:
    return {
        "query_id": "q",
        "answer_mode": "single",
        "expected_section_id": section,
        "expected_section_ids": [section],
    }


def test_hit_when_any_section_of_the_chunk_is_gold() -> None:
    row = _section_row("drug:a:lieu-dung")
    assert is_hit(
        _payload("drug:a:chunk-001", "drug:a:chi-dinh", "drug:a:lieu-dung"), row
    )
    assert not is_hit(_payload("drug:a:chunk-001", "drug:a:chi-dinh"), row)


def test_one_chunk_satisfies_several_units() -> None:
    gold = ["drug:a:chi-dinh", "drug:a:lieu-dung"]
    row = {
        "query_id": "q",
        "answer_mode": "multi_required",
        "expected_section_id": gold[0],
        "expected_section_ids": gold,
    }
    chunk = _payload("drug:a:chunk-001", *gold)

    assert satisfied_units(chunk, row, {}) == set(gold)
    scores = ranking_scores([chunk], row, judged={})
    assert scores["ndcg@10"] == 1.0 and scores["mrr@10"] == 1.0


def test_accepted_chunk_counts_as_hit() -> None:
    row = _section_row("drug:a:lieu-dung")
    judged = {"drug:a:lieu-dung": frozenset({LEAFLET_CHUNK})}
    payload = _payload(
        LEAFLET_CHUNK, "leaflet:thuoc-tri-tieu-duong:acarbose-a:03-cach-dung"
    )

    assert satisfied_units(payload, row, judged) == {"answer"}
    assert satisfied_units(payload, row, {}) == set()


def test_an_accepted_leaflet_chunk_counts_as_a_hit_for_its_section() -> None:
    row = _section_row("drug:acarbose:lieu-luong-va-cach-dung")
    payloads = [
        _payload(LEAFLET_CHUNK, "leaflet:thuoc-tri-tieu-duong:acarbose-a:03-cach-dung"),
        _payload("drug:acarbose:chunk-002", "drug:acarbose:lieu-luong-va-cach-dung"),
    ]
    judgments = {"drug:acarbose:lieu-luong-va-cach-dung": frozenset({LEAFLET_CHUNK})}

    judged = score_ranked_payloads(payloads, row, top_k=3, judgments=judgments)
    unjudged = score_ranked_payloads(payloads, row, top_k=3)

    assert (judged["hit@3"], judged["mrr"]) == (1, 1.0)
    assert (unjudged["hit@3"], unjudged["mrr"]) == (1, 0.5)


def test_an_accepted_leaflet_chunk_satisfies_its_intent_of_a_multi_query() -> None:
    row = {
        "query_id": "q",
        "answer_mode": "multi_required",
        "expected_section_id": "drug:acarbose:chi-dinh",
        "expected_section_ids": [
            "drug:acarbose:chi-dinh",
            "drug:acarbose:lieu-luong-va-cach-dung",
        ],
    }
    payloads = [
        _payload(LEAFLET_CHUNK, "leaflet:thuoc-tri-tieu-duong:acarbose-a:02-cong-dung"),
        _payload("drug:acarbose:chunk-002", "drug:acarbose:lieu-luong-va-cach-dung"),
        _payload("drug:metformin:chunk-001", "drug:metformin:chi-dinh"),
    ]
    judgments = {"drug:acarbose:chi-dinh": frozenset({LEAFLET_CHUNK})}

    judged = score_ranked_payloads(payloads, row, top_k=3, judgments=judgments)
    unjudged = score_ranked_payloads(payloads, row, top_k=3)

    assert judged["multi_section_recall@3"] == 1.0
    assert judged["multi_all_hit@3"] == 1
    assert judged["mrr"] == 1.0
    assert unjudged["multi_section_recall@3"] == 0.5
    assert unjudged["multi_all_hit@3"] == 0
    assert unjudged["mrr"] == 0.5


def test_ndcg_and_mrr_at_10_for_a_single_answer_query() -> None:
    payloads = _ranked("x:y", "x:z", "drug:a:lieu", "drug:a:lieu", *["x:w"] * 10)

    scores = score_ranked_payloads(payloads, _section_row(), top_k=30)

    # First hit at rank 3; a second chunk of the same section adds no gain.
    assert scores["ndcg@10"] == pytest.approx(1 / math.log2(4))
    assert scores["mrr@10"] == pytest.approx(1 / 3)
    assert scores["mrr"] == pytest.approx(1 / 3)


def test_hits_after_rank_10_count_for_mrr_at_30_only() -> None:
    payloads = _ranked(*["x:z"] * 11, "drug:a:lieu")

    scores = score_ranked_payloads(payloads, _section_row(), top_k=30)

    assert scores["ndcg@10"] == 0.0
    assert scores["mrr@10"] == 0.0
    assert scores["mrr"] == pytest.approx(1 / 12)


def test_ndcg_of_a_multi_part_query_needs_every_section() -> None:
    row = {
        "query_id": "q",
        "answer_mode": "multi_required",
        "expected_section_id": "drug:a:lieu",
        "expected_section_ids": ["drug:a:lieu", "drug:a:chong-chi-dinh"],
    }
    ideal = 1 + 1 / math.log2(3)

    one = score_ranked_payloads(_ranked("drug:a:lieu", "x:y"), row, top_k=10)
    both = score_ranked_payloads(
        _ranked("drug:a:lieu", "drug:a:chong-chi-dinh"), row, top_k=10
    )

    assert one["ndcg@10"] == pytest.approx(1 / ideal)
    assert both["ndcg@10"] == pytest.approx(1.0)


def test_an_accepted_chunk_satisfies_its_multi_part_unit() -> None:
    row = {
        "query_id": "q",
        "answer_mode": "multi_required",
        "expected_section_id": "drug:a:lieu",
        "expected_section_ids": ["drug:a:lieu", "drug:a:chong-chi-dinh"],
    }
    judgments = {"drug:a:chong-chi-dinh": frozenset({LEAFLET_CHUNK})}
    payloads = [
        _payload(LEAFLET_CHUNK, "leaflet:thuoc-tri-tieu-duong:acarbose-a:04-chong"),
        *_ranked("drug:a:lieu"),
    ]

    scores = score_ranked_payloads(payloads, row, top_k=10, judgments=judgments)

    assert scores["ndcg@10"] == pytest.approx(1.0)


def test_ranking_scores_need_a_cutoff_of_at_least_10() -> None:
    assert "ndcg@10" not in score_ranked_payloads(
        _ranked("x:y"), _section_row(), top_k=5
    )
