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
    scores = ranking_scores([chunk], row, judged={}, k=10)
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


def test_finding_both_units_in_one_earlier_chunk_never_scores_lower() -> None:
    gold = ["drug:a:lieu", "drug:a:chong-chi-dinh"]
    row = {
        "query_id": "q",
        "answer_mode": "multi_required",
        "expected_section_id": gold[0],
        "expected_section_ids": gold,
    }
    filler = [_payload(f"x:y:chunk-{i:03d}", "x:y") for i in range(1, 3)]
    together = [*filler, _payload("drug:a:chunk-001", *gold)]
    apart = [*filler, *_ranked(*gold)]
    only_first = _ranked("drug:a:lieu")

    def ndcg(ranked: list[dict]) -> float:
        return score_ranked_payloads(ranked, row, top_k=5)["ndcg@5"]

    # The ideal is fixed per query: one unit per rank from rank 1.
    assert ndcg(together) == pytest.approx(1 / (1 + 1 / math.log2(3)))
    assert ndcg(together) > ndcg(apart)
    assert ndcg(_ranked(*gold)) == 1.0
    assert ndcg([_payload("drug:a:chunk-001", *gold)]) == 1.0
    assert ndcg(only_first) < 1.0


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


def test_ranking_scores_at_5_and_10() -> None:
    payloads = _ranked(*["x:z"] * 5, "drug:a:lieu")

    scores = score_ranked_payloads(payloads, _section_row(), top_k=10)

    assert (scores["ndcg@5"], scores["mrr@5"]) == (0.0, 0.0)
    assert scores["mrr@10"] == pytest.approx(1 / 6)
    assert scores["ndcg@10"] == pytest.approx(1 / math.log2(7))


def test_a_cutoff_of_5_reports_only_the_scores_at_5() -> None:
    scores = score_ranked_payloads(_ranked("drug:a:lieu"), _section_row(), top_k=5)

    assert (scores["ndcg@5"], scores["mrr@5"]) == (1.0, 1.0)
    assert "ndcg@10" not in scores


def test_a_run_reports_hit_at_its_own_depth_and_nothing_deeper() -> None:
    payloads = _ranked(*["x:z"] * 15, "drug:a:lieu")

    scores = score_ranked_payloads(payloads, _section_row(), top_k=20)

    assert scores["hit@10"] == 0 and scores["hit@20"] == 1
    assert "hit@30" not in scores
