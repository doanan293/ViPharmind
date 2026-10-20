from collections import Counter

import pytest

from pharma_lab.evaluation.dev_test_split import (
    build_report,
    choose,
    split_queries,
)


def groups(**sizes: int) -> dict[str, str]:
    return {
        f"{group}-{index}": group
        for group, size in sizes.items()
        for index in range(size)
    }


def test_split_is_stratified_and_deterministic() -> None:
    queries = groups(a=5, b=1)

    split = split_queries(queries, seed=0)

    in_a = Counter(half for query, half in split.items() if queries[query] == "a")
    in_b = Counter(half for query, half in split.items() if queries[query] == "b")
    assert in_a == {"dev": 2, "test": 3}
    assert in_b == {"test": 1}
    assert split_queries(queries, seed=0) == split
    dev_a = {query for query, half in split.items() if half == "dev" and "a-" in query}
    other = split_queries(queries, seed=1)
    assert {q for q, half in other.items() if half == "dev" and "a-" in q} != dev_a


def test_every_query_is_in_exactly_one_half() -> None:
    queries = groups(a=7, b=4, c=3)

    split = split_queries(queries, seed=3)

    assert split.keys() == queries.keys()
    assert set(split.values()) == {"dev", "test"}


def test_choose_takes_the_highest_mean_on_the_given_ids() -> None:
    options = {
        "x": {"q1": 1.0, "q2": 0.0, "q3": 0.0},
        "y": {"q1": 0.0, "q2": 1.0, "q3": 1.0},
    }

    assert choose(options, ["q1"]) == "x"
    assert choose(options, ["q1", "q2", "q3"]) == "y"


def test_choose_keeps_the_first_option_on_a_tie() -> None:
    options = {"x": {"q1": 1.0}, "y": {"q1": 1.0}}

    assert choose(options, ["q1"]) == "x"


def test_choose_rejects_an_empty_id_set() -> None:
    with pytest.raises(ValueError, match="no queries"):
        choose({"x": {"q1": 1.0}}, [])


def metrics(hit: dict[str, float]) -> dict[str, dict[str, float]]:
    return {"hit@10": hit, "mrr@10": hit, "ndcg@10": hit, "mrr": hit}


def test_the_report_chooses_on_dev_and_reports_on_test() -> None:
    queries = groups(a=4)
    split = split_queries(queries, seed=0)
    dev = sorted(q for q, half in split.items() if half == "dev")
    test = sorted(q for q, half in split.items() if half == "test")
    # rrf2 wins on dev; rrf60 wins on test, so the chosen row is not the test winner.
    rrf2 = {**dict.fromkeys(dev, 1.0), **dict.fromkeys(test, 0.0)}
    rrf60 = {**dict.fromkeys(dev, 0.0), **dict.fromkeys(test, 1.0)}
    pilot_ids = [dev[0], test[0]]
    instruction = {
        "without": {pilot_ids[0]: 0.1, pilot_ids[1]: 0.9},
        "with": {pilot_ids[0]: 0.5, pilot_ids[1]: 0.1},
    }

    report = build_report(
        queries,
        split,
        k_runs={"rrf2": metrics(rrf2), "rrf60": metrics(rrf60)},
        rerank_rrf2=None,
        instruction=instruction,
        seed=0,
    )

    assert report["seed"] == 0
    assert report["counts"] == {"a": {"dev": 2, "test": 2}}
    k = report["fusion_constant"]
    assert k["chosen"] == "rrf2"
    assert k["dev_means"] == {"rrf2": 1.0, "rrf60": 0.0}
    assert k["test"]["rrf2"]["hit@10"] == 0.0
    assert k["test"]["rrf60"]["hit@10"] == 1.0
    assert k["test_size"] == 2
    ins = report["rerank_instruction"]
    assert ins["chosen"] == "with"
    assert ins["dev_size"] == 1
    assert ins["dev_means"] == {"without": 0.1, "with": 0.5}
    assert ins["test_means"] == {"without": 0.9, "with": 0.1}
    assert ins["test_size"] == 1
    assert "rerank_rrf2" not in report


def test_the_report_includes_the_reranked_rrf2_row_on_test_when_given() -> None:
    queries = groups(a=4)
    split = split_queries(queries, seed=0)
    ones = dict.fromkeys(queries, 1.0)

    report = build_report(
        queries,
        split,
        k_runs={"rrf2": metrics(ones), "rrf60": metrics(ones)},
        rerank_rrf2=metrics(ones),
        instruction={"without": {}, "with": {}},
        seed=0,
    )

    assert report["rerank_rrf2"]["test"]["hit@10"] == 1.0
    assert report["rerank_instruction"]["dev_size"] == 0
