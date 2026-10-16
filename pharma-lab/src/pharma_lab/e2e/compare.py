"""Paired comparison of one configuration across two runs (spec v2 §4.E).

Both runs answer the same golden items, so each metric is compared item by item: the
mean difference with a bootstrap interval, a sign-flip test, and Holm's correction over
the metrics of the table (spec v2 §5).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import astuple, dataclass, fields, replace
from pathlib import Path

from pharma_lab.e2e.golden import GoldenItem
from pharma_lab.e2e.judging.service import JUDGE_FILE
from pharma_lab.e2e.report import (
    METRICS,
    REPORTS_DIR,
    Values,
    load_run,
    values_of,
    write_csv,
    write_tex,
)
from pharma_lab.e2e.statistics import bootstrap_mean, holm, paired_test
from pharma_lab.evaluation.relevance_judgments import LoadedJudgments

SIGNIFICANCE = 0.05


@dataclass(frozen=True)
class CompareRow:
    metric: str
    n: int
    mean_a: float
    mean_b: float
    delta: float
    ci_low: float
    ci_high: float
    p_value: float
    p_holm: float
    # Both configurations were scored by the same judge (judge.json identical).
    same_judge: bool


def _judge(run_root: Path, config: str) -> dict[str, object]:
    path = run_root / config / JUDGE_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _config_values(
    run_root: Path,
    config: str,
    items: Mapping[str, GoldenItem],
    relevance: LoadedJudgments | None,
) -> dict[str, Values]:
    loaded = load_run(run_root)
    if config not in loaded:
        raise ValueError(f"{run_root.name} has no judged {config} configuration")
    answers, judgments, identity = loaded[config]
    return values_of(items, answers, judgments, relevance, identity)


def compare_runs(
    run_a: Path,
    run_b: Path,
    config: str,
    items: Mapping[str, GoldenItem],
    relevance: LoadedJudgments | None,
) -> list[CompareRow]:
    """Run B minus run A for every metric both runs measured on shared items; writes
    `<run_b>/reports/compare-<run_a>-<config>.csv|tex`."""
    values_a = _config_values(run_a, config, items, relevance)
    values_b = _config_values(run_b, config, items, relevance)
    same_judge = _judge(run_a, config) == _judge(run_b, config)
    rows: list[CompareRow] = []
    for metric in METRICS:
        a, b = values_a[metric.name], values_b[metric.name]
        shared = sorted(set(a) & set(b))
        if not shared:
            continue
        differences = [b[key] - a[key] for key in shared]
        interval = bootstrap_mean(differences)
        rows.append(
            CompareRow(
                metric=metric.name,
                n=len(shared),
                mean_a=sum(a[key] for key in shared) / len(shared),
                mean_b=sum(b[key] for key in shared) / len(shared),
                delta=interval.mean,
                ci_low=interval.ci_low,
                ci_high=interval.ci_high,
                p_value=paired_test(differences).p_value,
                p_holm=1.0,
                same_judge=same_judge,
            )
        )
    if not rows:
        raise ValueError(
            f"{run_a.name} and {run_b.name} have no item in common for {config}"
        )
    adjusted = holm([row.p_value for row in rows])
    rows = [replace(row, p_holm=p) for row, p in zip(rows, adjusted, strict=True)]
    _write(run_b, run_a.name, config, rows)
    return rows


def _write(run_b: Path, name_a: str, config: str, rows: list[CompareRow]) -> None:
    directory = run_b / REPORTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"compare-{name_a}-{config}"
    write_csv(
        directory / f"{stem}.csv",
        [field.name for field in fields(CompareRow)],
        [list(astuple(row)) for row in rows],
    )
    primary = {metric.name for metric in METRICS if metric.primary}
    write_tex(
        directory / f"{stem}.tex",
        f"Paired comparison of {config}: {run_b.name} minus {name_a}, mean difference "
        "[95\\% CI]; * marks Holm-adjusted p < 0.05.",
        f"tab:e2e-compare-{config}",
        ["Metric", name_a, run_b.name, "$\\Delta$"],
        [
            [
                r.metric,
                f"{r.mean_a:.3f}",
                f"{r.mean_b:.3f}",
                f"{r.delta:+.3f} [{r.ci_low:+.3f}, {r.ci_high:+.3f}]"
                + ("*" if r.p_holm < SIGNIFICANCE else ""),
            ]
            for r in rows
            if r.metric in primary
        ],
    )
