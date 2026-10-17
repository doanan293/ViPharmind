"""Answerable probes of the retrieval-side components (spec §3.0b).

A probe is a benchmark question whose one-round coverage one component decides, so the
ablation of that component changes it. With the full retriever (hybrid search reranked,
top five) covering the gold section:

- `rerank_probe`: the hybrid order without reranking misses it in the top five;
- `lexical_probe`: dense search misses it in its whole candidate list, so the BM25 half
  of hybrid search found it;
- `semantic_probe`: BM25 misses it in its whole candidate list, so the dense half found it.

Only single-section questions phrased as questions are kept, so a probe is answerable
from one section and tests retrieval rather than planning.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pharma_lab.e2e.corpus_text import CorpusText
from pharma_lab.e2e.one_round import coverage, informative
from pharma_lab.evaluation.retrieval_metrics import expected_section_ids

PROBE_DEPTH = 5


@dataclass(frozen=True)
class ProbeRuns:
    """One-round coverage of every benchmark question under each configuration."""

    rows: dict[str, dict]
    full: dict[str, bool]
    no_rerank: dict[str, bool]
    bm25_depth: dict[str, bool]
    dense_depth: dict[str, bool]


def probe_kind(query_id: str, runs: ProbeRuns) -> str | None:
    """The probe kind of one benchmark question, or None. A question can fit more than
    one kind; the rarer component wins, in the order reranking, lexical, semantic."""
    if not runs.full.get(query_id, False):
        return None
    if not runs.no_rerank.get(query_id, True):
        return "rerank_probe"
    if not runs.dense_depth.get(query_id, True):
        return "lexical_probe"
    if not runs.bm25_depth.get(query_id, True):
        return "semantic_probe"
    return None


def probe_candidates(runs: ProbeRuns, corpus: CorpusText) -> list[dict[str, object]]:
    """Probe rows in the candidate format of `golden draft`."""
    out: list[dict[str, object]] = []
    for query_id in sorted(runs.full):
        row = runs.rows[query_id]
        kind = probe_kind(query_id, runs)
        sections = expected_section_ids(dict(row))
        if kind is None or len(sections) != 1 or not informative(row, corpus):
            continue
        out.append(
            {
                "query_id": query_id,
                "query": row["query"],
                "kind": kind,
                "eval_group": row.get("eval_group"),
                "expected_section_ids": sections,
                "missing": [],
            }
        )
    return out


def _coverage_by_query(
    run_root: Path, *, model: str | None, top_k: int
) -> tuple[dict[str, dict], dict[str, bool]]:
    from pharma_lab.evaluation.metrics_service import (
        MetricsRequest,
        load_and_validate_metric_inputs,
        ranked_payloads,
    )

    inputs = load_and_validate_metric_inputs(
        MetricsRequest(run_root=run_root, top_k=top_k, model=model)
    )
    rerank = inputs.rerank_variants[0] if model else None
    covered: dict[str, bool] = {}
    for record in inputs.candidates:
        query_id = str(record["query_id"])
        row = inputs.evaluation_rows[query_id]
        result = coverage(
            ranked_payloads(record, row, rerank),
            row,
            inputs.judgments.for_query(query_id),
            top_k=top_k,
        )
        covered[query_id] = not result.missing
    return inputs.evaluation_rows, covered


def load_probe_runs(
    hybrid: Path,
    bm25: Path,
    dense: Path,
    *,
    model: str,
    depth: int,
) -> ProbeRuns:
    """Coverage of the full retriever and its three ablations from finished runs;
    `depth` is the candidate depth of the BM25 and dense runs."""
    rows, full = _coverage_by_query(hybrid, model=model, top_k=PROBE_DEPTH)
    _, no_rerank = _coverage_by_query(hybrid, model=None, top_k=PROBE_DEPTH)
    _, bm25_depth = _coverage_by_query(bm25, model=None, top_k=depth)
    _, dense_depth = _coverage_by_query(dense, model=None, top_k=depth)
    return ProbeRuns(rows, full, no_rerank, bm25_depth, dense_depth)
