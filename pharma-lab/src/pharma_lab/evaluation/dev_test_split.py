"""Choose the fusion constant and the rerank instruction on a dev half, report them on a test half.

The benchmark was used both to pick k and the instruction and to report their results; this
splits its queries once (stratified by eval group, fixed seed), repeats each choice on the dev
half only, and reports every candidate on the test half, from the metrics of runs that exist.
"""

from __future__ import annotations

import random
import statistics
from collections import defaultdict
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pharma_lab.artifacts.jsonl import iter_jsonl_objects
from pharma_lab.evaluation.artifact_contracts import write_json
from pharma_lab.evaluation.metric_comparison import load_query_metric

Split = Literal["dev", "test"]
Metrics = Mapping[str, Mapping[str, float]]

REPORT_METRICS = ("hit@10", "mrr@10", "ndcg@10")
# The decision metrics of v1: Hit@10 before reranking for k, MRR@30 for the instruction.
K_DECISION_METRIC = "hit@10"
INSTRUCTION_METRIC = "mrr"
K_RUNS = {
    "rrf2": "hybrid-qwen4b-p50-k30-rrf2",
    "rrf60": "hybrid-qwen4b-p50-k30-rrf60",
}
RERANK_4B_DIR = "qwen3_reranker_4b_fp16"
PILOT_RUN = "hybrid-qwen4b-p50-k30-rrf2-sample1000"
# Directory slug of each pilot variant; the instruction one is no longer in the catalog.
PILOT_VARIANTS = {
    "without": "qwen3_reranker_0_6b_fp16",
    "with": "qwen3_reranker_0_6b_fp16_vimed",
}
REPORT_NAME = "top30-window3"
BASELINE_DIR = Path("reports") / "baseline" / REPORT_NAME


def split_queries(groups: Mapping[str, str], *, seed: int) -> dict[str, Split]:
    """Half of every eval group (rounded down) is dev, the rest test."""
    members: dict[str, list[str]] = defaultdict(list)
    for query_id, group in groups.items():
        members[group].append(query_id)
    split: dict[str, Split] = {}
    for group, query_ids in members.items():
        ordered = sorted(query_ids)
        random.Random(f"{seed}:{group}").shuffle(ordered)
        dev_size = len(ordered) // 2
        for index, query_id in enumerate(ordered):
            split[query_id] = "dev" if index < dev_size else "test"
    return split


def mean_on(values: Mapping[str, float], ids: Collection[str]) -> float:
    return statistics.fmean(values[query_id] for query_id in ids)


def choose(options: Mapping[str, Mapping[str, float]], ids: Collection[str]) -> str:
    """The option with the highest mean over `ids`; the first one on a tie."""
    if not ids:
        raise ValueError("no queries to choose on")
    best: str | None = None
    best_mean = float("-inf")
    for name, values in options.items():
        value = mean_on(values, ids)
        if value > best_mean:
            best, best_mean = name, value
    assert best is not None
    return best


def _ids(split: Mapping[str, Split], half: Split, within: Collection[str]) -> list[str]:
    return sorted(query for query in within if split.get(query) == half)


def _test_row(metrics: Metrics, test_ids: Collection[str]) -> dict[str, float]:
    return {name: mean_on(metrics[name], test_ids) for name in REPORT_METRICS}


def build_report(
    groups: Mapping[str, str],
    split: Mapping[str, Split],
    *,
    k_runs: Mapping[str, Metrics],
    rerank_rrf2: Metrics | None,
    instruction: Mapping[str, Mapping[str, float]],
    seed: int,
) -> dict[str, Any]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"dev": 0, "test": 0})
    for query_id, group in groups.items():
        counts[group][split[query_id]] += 1
    dev_ids = _ids(split, "dev", groups)
    test_ids = _ids(split, "test", groups)

    decision = {name: run[K_DECISION_METRIC] for name, run in k_runs.items()}
    report: dict[str, Any] = {
        "seed": seed,
        "counts": {group: dict(halves) for group, halves in sorted(counts.items())},
        "fusion_constant": {
            "metric": K_DECISION_METRIC,
            "chosen": choose(decision, dev_ids),
            "dev_size": len(dev_ids),
            "dev_means": {name: mean_on(v, dev_ids) for name, v in decision.items()},
            "test_size": len(test_ids),
            "test": {name: _test_row(run, test_ids) for name, run in k_runs.items()},
        },
    }
    if rerank_rrf2 is not None:
        report["rerank_rrf2"] = {
            "test_size": len(test_ids),
            "test": _test_row(rerank_rrf2, test_ids),
        }
    pilot_ids = set.intersection(*(set(v) for v in instruction.values()))
    pilot_dev = _ids(split, "dev", pilot_ids)
    pilot_test = _ids(split, "test", pilot_ids)
    report["rerank_instruction"] = {
        "metric": INSTRUCTION_METRIC,
        "chosen": choose(instruction, pilot_dev) if pilot_dev else None,
        "dev_size": len(pilot_dev),
        "dev_means": {n: mean_on(v, pilot_dev) for n, v in instruction.items()}
        if pilot_dev
        else {},
        "test_size": len(pilot_test),
        "test_means": {n: mean_on(v, pilot_test) for n, v in instruction.items()}
        if pilot_test
        else {},
    }
    return report


@dataclass(frozen=True)
class DevTestRequest:
    runs_root: Path
    evaluation_path: Path
    output_dir: Path
    seed: int = 0


def _load(report: Path, names: Collection[str]) -> dict[str, dict[str, float]]:
    return {name: load_query_metric(report, name)[1] for name in names}


def run_dev_test(request: DevTestRequest) -> dict[str, Any]:
    groups = {
        str(row["query_id"]): str(row["eval_group"])
        for row in iter_jsonl_objects(request.evaluation_path)
    }
    split = split_queries(groups, seed=request.seed)
    names = (*REPORT_METRICS, K_DECISION_METRIC)
    k_runs = {
        name: _load(request.runs_root / run / BASELINE_DIR, names)
        for name, run in K_RUNS.items()
    }
    rerank_dir = (
        request.runs_root / K_RUNS["rrf2"] / "reports" / "rerank" / RERANK_4B_DIR
    )
    instruction = {
        name: load_query_metric(
            request.runs_root / PILOT_RUN / "reports" / "rerank" / slug / REPORT_NAME,
            INSTRUCTION_METRIC,
        )[1]
        for name, slug in PILOT_VARIANTS.items()
    }
    report = build_report(
        groups,
        split,
        k_runs=k_runs,
        rerank_rrf2=_load(rerank_dir / REPORT_NAME, REPORT_METRICS),
        instruction=instruction,
        seed=request.seed,
    )
    request.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(request.output_dir / "report.json", report)
    (request.output_dir / "report.md").write_text(markdown(report), encoding="utf-8")
    return report


def markdown(report: Mapping[str, Any]) -> str:
    k = report["fusion_constant"]
    lines = [
        f"# Dev/test check (seed {report['seed']})",
        "",
        "## Fusion constant",
        "",
        f"Chosen on dev by {k['metric']} ({k['dev_size']} queries): **{k['chosen']}**.",
        "",
        "| Option | dev "
        + k["metric"]
        + " | test Hit@10 | test MRR@10 | test nDCG@10 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, row in k["test"].items():
        lines.append(
            f"| {name} | {k['dev_means'][name]:.4f} | {row['hit@10']:.4f} "
            f"| {row['mrr@10']:.4f} | {row['ndcg@10']:.4f} |"
        )
    if "rerank_rrf2" in report:
        row = report["rerank_rrf2"]["test"]
        lines += [
            "",
            f"rrf2 reranked by Qwen3-Reranker-4B on test ({k['test_size']} queries): "
            f"Hit@10 {row['hit@10']:.4f}, MRR@10 {row['mrr@10']:.4f}, "
            f"nDCG@10 {row['ndcg@10']:.4f}.",
        ]
    ins = report["rerank_instruction"]
    lines += [
        "",
        "## Rerank instruction (Qwen3-Reranker-0.6B pilot)",
        "",
        f"Pilot queries on dev: {ins['dev_size']}; on test: {ins['test_size']}. "
        f"Chosen on dev by {ins['metric']}: **{ins['chosen']}**.",
        "",
        "| Option | dev MRR@30 | test MRR@30 |",
        "| --- | ---: | ---: |",
    ]
    for name in ins["dev_means"]:
        test = ins["test_means"].get(name)
        shown = "-" if test is None else f"{test:.4f}"
        lines.append(f"| {name} | {ins['dev_means'][name]:.4f} | {shown} |")
    return "\n".join(lines) + "\n"
