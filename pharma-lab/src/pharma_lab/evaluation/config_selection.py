"""The rule that picks the agent's retriever and reranker (spec v2 §3.4).

Configurations are listed cheapest first. In each stage the leader is the configuration
with the highest mean of a metric (the cheaper one on equal means); it beats another
configuration when the paired bootstrap 95% interval of leader minus other lies above 0
and the paired sign-flip p, Holm-adjusted over the stage's comparisons, is below 0.05.
Configurations the leader does not beat are tied with it. A single leader on the primary
metric is chosen; otherwise the tied ones go through the secondary metric the same way;
a tie that remains goes to the cheapest.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from pharma_lab.artifacts.bundle import load_bundle
from pharma_lab.artifacts.manifest import (
    ArtifactContractError,
    iter_jsonl_objects,
    sha256_file,
)
from pharma_lab.evaluation.metrics_artifacts import report_dir
from pharma_lab.evaluation.relevance_judgments import judgments_path
from pharma_lab.evaluation.statistics import holm, paired_test

ALPHA = 0.05


@dataclass(frozen=True)
class ConfigReport:
    label: str
    run_root: Path
    model: str | None  # None: the run's baseline report (no reranker)


@dataclass(frozen=True)
class PairRow:
    leader: str
    other: str
    mean_difference: float
    ci_low: float
    ci_high: float
    p_value: float
    p_holm: float
    beaten: bool


@dataclass(frozen=True)
class StageResult:
    metric: str
    leader: str
    means: dict[str, float]
    rows: tuple[PairRow, ...]
    tied: tuple[str, ...]  # the leader and every configuration it does not beat


@dataclass(frozen=True)
class Selection:
    chosen: str
    reason: Literal["primary", "secondary", "cheapest_of_tie"]
    primary: StageResult
    secondary: StageResult | None
    query_count: int
    excluded_groups: tuple[str, ...]


def load_query_metric(
    report: Path, metric: str
) -> tuple[dict[str, Any], dict[str, float]]:
    bundle = load_bundle(report, expected_type="metrics_report", require_complete=True)
    values: dict[str, float] = {}
    for row in iter_jsonl_objects(bundle.data_path):
        if metric not in row:
            raise ArtifactContractError(
                f"Metric {metric} is missing for query {row.get('query_id')} "
                f"in {bundle.data_path}"
            )
        values[str(row["query_id"])] = float(row[metric])
    return dict(bundle.manifest.identity), values


def _groups(evaluation_path: Path) -> dict[str, str]:
    return {
        str(row["query_id"]): str(row.get("eval_group") or "")
        for row in iter_jsonl_objects(evaluation_path)
    }


def _stage(
    metric: str,
    pool: Sequence[str],
    values: Mapping[str, Mapping[str, float]],
    queries: Sequence[str],
) -> StageResult:
    means = {
        label: sum(values[label][q] for q in queries) / len(queries) for label in pool
    }
    # max() keeps the first of equal means, and the pool is in cost order.
    leader = max(pool, key=lambda label: means[label])
    others = [label for label in pool if label != leader]
    tests = [
        paired_test([values[leader][q] - values[other][q] for q in queries])
        for other in others
    ]
    adjusted = holm([test.p_value for test in tests])
    rows = tuple(
        PairRow(
            leader,
            other,
            test.summary.mean,
            test.summary.ci_low,
            test.summary.ci_high,
            test.p_value,
            p_holm,
            test.summary.ci_low > 0 and p_holm < ALPHA,
        )
        for other, test, p_holm in zip(others, tests, adjusted, strict=True)
    )
    beaten = {row.other for row in rows if row.beaten}
    tied = tuple(label for label in pool if label not in beaten)
    return StageResult(metric, leader, means, rows, tied)


def _check_reports(
    configs: Sequence[ConfigReport],
    identities: Mapping[str, Mapping[str, Any]],
    evaluation_path: Path,
) -> None:
    evaluation_sha256 = sha256_file(evaluation_path)
    judgments = judgments_path(evaluation_path)
    current = sha256_file(judgments) if judgments.is_file() else None
    for config in configs:
        identity = identities[config.label]
        if identity.get("evaluation_sha256") != evaluation_sha256:
            raise ArtifactContractError(
                f"{config.label} was scored on another evaluation file than "
                f"{evaluation_path}"
            )
        if identity.get("judgments_sha256") != current:
            raise ArtifactContractError(
                f"{config.label} was scored with other relevance judgments than "
                f"{judgments}; run `pharma-lab metrics --run {config.run_root.name} "
                "--force`"
            )


def select_config(
    configs: Sequence[ConfigReport],
    *,
    primary: str,
    secondary: str,
    top_k: int,
    evaluation_path: Path,
    exclude_groups: Sequence[str] = (),
) -> Selection:
    """Apply the §3.4 rule to `configs`, listed cheapest first."""
    if len(configs) < 2:
        raise ValueError("selection needs at least two configurations")
    labels = [config.label for config in configs]
    if len(set(labels)) != len(labels):
        raise ValueError("a configuration label is given twice")
    groups = _groups(Path(evaluation_path))
    unknown = sorted(set(exclude_groups) - set(groups.values()))
    if unknown:
        raise ValueError(
            f"excluded group(s) {', '.join(unknown)} are not in {evaluation_path}"
        )
    values: dict[str, dict[str, dict[str, float]]] = {}
    identities: dict[str, dict[str, Any]] = {}
    for config in configs:
        report = report_dir(config.run_root, top_k=top_k, model=config.model)
        values[config.label] = {}
        for metric in (primary, secondary):
            identity, by_query = load_query_metric(report, metric)
            values[config.label][metric] = by_query
            identities[config.label] = identity
    _check_reports(configs, identities, Path(evaluation_path))
    query_sets = {frozenset(values[label][primary]) for label in labels}
    if len(query_sets) != 1:
        raise ArtifactContractError("the reports cover different queries")
    excluded = set(exclude_groups)
    queries = sorted(q for q in next(iter(query_sets)) if groups.get(q) not in excluded)
    if not queries:
        raise ValueError("no query is left after excluding groups")

    def by_metric(metric: str) -> dict[str, dict[str, float]]:
        return {label: values[label][metric] for label in labels}

    first = _stage(primary, labels, by_metric(primary), queries)
    if len(first.tied) == 1:
        return Selection(
            first.leader, "primary", first, None, len(queries), tuple(exclude_groups)
        )
    second = _stage(secondary, first.tied, by_metric(secondary), queries)
    if len(second.tied) == 1:
        return Selection(
            second.leader,
            "secondary",
            first,
            second,
            len(queries),
            tuple(exclude_groups),
        )
    return Selection(
        second.tied[0],
        "cheapest_of_tie",
        first,
        second,
        len(queries),
        tuple(exclude_groups),
    )


def selection_details(selection: Selection) -> dict[str, Any]:
    """The selection as JSON-ready details for the CLI."""
    return asdict(selection)
