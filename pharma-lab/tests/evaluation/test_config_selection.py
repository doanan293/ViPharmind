import json
from pathlib import Path

import pytest

from pharma_lab.artifacts.manifest import ArtifactContractError, sha256_file
from pharma_lab.evaluation.config_selection import (
    ConfigReport,
    Selection,
    select_config,
)
from pharma_lab.evaluation.metrics_artifacts import publish_metrics_artifact
from pharma_lab.evaluation.variant_identity import MetricsArtifactIdentity

TOP_K = 20
QUERIES = [f"q{index:03d}" for index in range(80)]


def _gold(tmp_path: Path, groups: dict[str, str] | None = None) -> Path:
    gold = tmp_path / "gold" / "section_retrieval_eval.jsonl"
    gold.parent.mkdir(parents=True, exist_ok=True)
    groups = groups or {}
    gold.write_text(
        "".join(
            json.dumps({"query_id": q, "eval_group": groups.get(q, "formulary")}) + "\n"
            for q in QUERIES
        ),
        encoding="utf-8",
    )
    judgments = gold.with_name("section_retrieval_eval.judgments.jsonl")
    judgments.write_text("{}\n", encoding="utf-8")
    return gold


def _publish(
    tmp_path: Path,
    gold: Path,
    label: str,
    hits: dict[str, list[int]],
    *,
    judgments_sha256: str | None = None,
    queries: list[str] = QUERIES,
) -> ConfigReport:
    run = tmp_path / "runs" / label
    rows = [
        {"query_id": q, **{metric: values[i] for metric, values in hits.items()}}
        for i, q in enumerate(queries)
    ]
    judgments = gold.with_name("section_retrieval_eval.judgments.jsonl")
    publish_metrics_artifact(
        run,
        MetricsArtifactIdentity.create(
            evaluation_sha256=sha256_file(gold),
            candidate_data_sha256=f"{label}".ljust(64, "c"),
            top_k=TOP_K,
            judgments_sha256=judgments_sha256 or sha256_file(judgments),
        ),
        {"count": len(rows), "mrr": 0.0},
        {"eval_group": {}},
        rows,
        top_k=TOP_K,
    )
    return ConfigReport(label, run, None)


def _select(
    configs: list[ConfigReport],
    gold: Path,
    exclude_groups: tuple[str, ...] = (),
) -> Selection:
    return select_config(
        configs,
        primary="hit@20",
        secondary="hit@5",
        top_k=TOP_K,
        evaluation_path=gold,
        exclude_groups=exclude_groups,
    )


ONES = [1] * 80
HALF = [1, 0] * 40


def test_a_clear_primary_winner_is_chosen(tmp_path: Path) -> None:
    gold = _gold(tmp_path)
    configs = [
        _publish(tmp_path, gold, "b", {"hit@20": HALF, "hit@5": HALF}),
        _publish(tmp_path, gold, "c", {"hit@20": HALF, "hit@5": HALF}),
        _publish(tmp_path, gold, "a", {"hit@20": ONES, "hit@5": ONES}),
    ]

    selection = _select(configs, gold)

    assert (selection.chosen, selection.reason) == ("a", "primary")
    assert selection.primary.leader == "a"
    assert all(row.beaten for row in selection.primary.rows)
    assert selection.secondary is None
    assert selection.query_count == 80


def test_a_primary_tie_goes_to_the_secondary_metric(tmp_path: Path) -> None:
    gold = _gold(tmp_path)
    configs = [
        _publish(tmp_path, gold, "b", {"hit@20": ONES, "hit@5": HALF}),
        _publish(tmp_path, gold, "a", {"hit@20": ONES, "hit@5": ONES}),
    ]

    selection = _select(configs, gold)

    assert selection.primary.tied == ("b", "a")
    assert (selection.chosen, selection.reason) == ("a", "secondary")


def test_a_full_tie_takes_the_cheapest(tmp_path: Path) -> None:
    gold = _gold(tmp_path)
    configs = [
        _publish(tmp_path, gold, "cheap", {"hit@20": HALF, "hit@5": HALF}),
        _publish(tmp_path, gold, "dear", {"hit@20": HALF[::-1], "hit@5": HALF[::-1]}),
    ]

    selection = _select(configs, gold)

    assert (selection.chosen, selection.reason) == ("cheap", "cheapest_of_tie")


def test_equal_means_lead_with_the_cheaper_config(tmp_path: Path) -> None:
    gold = _gold(tmp_path)
    configs = [
        _publish(tmp_path, gold, "first", {"hit@20": HALF[::-1], "hit@5": HALF}),
        _publish(tmp_path, gold, "second", {"hit@20": HALF, "hit@5": HALF}),
    ]

    assert _select(configs, gold).primary.leader == "first"


def test_holm_uses_the_family_size(tmp_path: Path) -> None:
    gold = _gold(tmp_path)
    slightly = [1] * 70 + [0] * 10
    configs = [
        _publish(tmp_path, gold, "b", {"hit@20": HALF, "hit@5": HALF}),
        _publish(tmp_path, gold, "c", {"hit@20": slightly, "hit@5": HALF}),
        _publish(tmp_path, gold, "a", {"hit@20": ONES, "hit@5": ONES}),
    ]

    rows = _select(configs, gold).primary.rows
    smallest = min(rows, key=lambda row: row.p_value)

    assert smallest.p_holm == pytest.approx(min(1.0, 2 * smallest.p_value))


def test_excluded_groups_drop_their_queries(tmp_path: Path) -> None:
    conversational = dict.fromkeys(QUERIES[:40], "conversational")
    gold = _gold(tmp_path, conversational)
    # B beats A only on the conversational queries; A and B are equal elsewhere.
    configs = [
        _publish(tmp_path, gold, "a", {"hit@20": [0] * 40 + [1] * 40, "hit@5": ONES}),
        _publish(tmp_path, gold, "b", {"hit@20": ONES, "hit@5": ONES}),
    ]

    with_all = _select(configs, gold)
    without = _select(configs, gold, exclude_groups=("conversational",))

    assert with_all.chosen == "b"
    assert without.query_count == 40
    assert without.excluded_groups == ("conversational",)
    assert without.reason == "cheapest_of_tie"
    assert without.chosen == "a"


def test_unknown_excluded_group_is_an_error(tmp_path: Path) -> None:
    gold = _gold(tmp_path)
    configs = [
        _publish(tmp_path, gold, "a", {"hit@20": ONES, "hit@5": ONES}),
        _publish(tmp_path, gold, "b", {"hit@20": HALF, "hit@5": HALF}),
    ]

    with pytest.raises(ValueError, match="conversation"):
        _select(configs, gold, exclude_groups=("conversation",))


def test_select_refuses_reports_with_different_judgments(tmp_path: Path) -> None:
    gold = _gold(tmp_path)
    configs = [
        _publish(tmp_path, gold, "a", {"hit@20": ONES, "hit@5": ONES}),
        _publish(
            tmp_path,
            gold,
            "b",
            {"hit@20": HALF, "hit@5": HALF},
            judgments_sha256="k" * 64,
        ),
    ]

    with pytest.raises(ArtifactContractError, match="judgments"):
        _select(configs, gold)


def test_select_refuses_reports_with_stale_judgments(tmp_path: Path) -> None:
    gold = _gold(tmp_path)
    configs = [
        _publish(tmp_path, gold, "a", {"hit@20": ONES, "hit@5": ONES}),
        _publish(tmp_path, gold, "b", {"hit@20": HALF, "hit@5": HALF}),
    ]
    gold.with_name("section_retrieval_eval.judgments.jsonl").write_text(
        '{"changed": true}\n', encoding="utf-8"
    )

    with pytest.raises(ArtifactContractError, match="--force"):
        _select(configs, gold)


def test_reports_over_different_queries_are_refused(tmp_path: Path) -> None:
    gold = _gold(tmp_path)
    configs = [
        _publish(tmp_path, gold, "a", {"hit@20": ONES, "hit@5": ONES}),
        _publish(
            tmp_path,
            gold,
            "b",
            {"hit@20": ONES[:40], "hit@5": ONES[:40]},
            queries=QUERIES[:40],
        ),
    ]

    with pytest.raises(ArtifactContractError, match="different queries"):
        _select(configs, gold)


def test_one_config_or_a_repeated_label_is_refused(tmp_path: Path) -> None:
    gold = _gold(tmp_path)
    a = _publish(tmp_path, gold, "a", {"hit@20": ONES, "hit@5": ONES})

    with pytest.raises(ValueError, match="at least two"):
        _select([a], gold)
    with pytest.raises(ValueError, match="twice"):
        _select([a, a], gold)
