"""What one retrieval round finds for each benchmark question.

The golden set's multi-hop split is chosen from data: a question is a multi-hop candidate
when one round of retrieval (hybrid search and rerank, the top `k` chunks the pipeline
reads) misses part of its gold evidence, and the answerable items it drops to make room
are the ones that round already covers.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pharma_lab.e2e.corpus_text import CorpusText, section_slug
from pharma_lab.e2e.golden import GoldenItem
from pharma_lab.evaluation.retrieval_metrics import (
    evidence_units,
    expected_section_ids,
    satisfied_units,
)


@dataclass(frozen=True)
class OneRoundCoverage:
    query_id: str
    units: tuple[str, ...]
    missing: tuple[str, ...]


def coverage(
    ranked: Sequence[Mapping[str, object]],
    query_row: Mapping[str, object],
    judged: Mapping[str, frozenset[str]],
    *,
    top_k: int,
) -> OneRoundCoverage:
    units = evidence_units(dict(query_row))
    found: set[str] = set()
    for payload in ranked[:top_k]:
        found |= satisfied_units(dict(payload), dict(query_row), judged)
    return OneRoundCoverage(
        str(query_row["query_id"]),
        units,
        tuple(unit for unit in units if unit not in found),
    )


# Sections that do not answer a question on their own: trade-name lists, regulatory notes,
# incompatibility lines, the formulary's front matter and a leaflet's closing notes. Most
# first-round misses of the benchmark sit there, and a single-section item (retrieval
# miss or noisy retry) must be answerable from its gold section, so those kinds keep only
# questions whose every gold section is informative and long enough to quote, and which
# are questions, not template fragments or open requests.
UNINFORMATIVE_SLUGS = frozenset(
    {"ten-thuong-mai", "thong-tin-qui-che", "tuong-ky", "noi-dung", "thong-tin-them"}
)
MIN_SECTION_TOKENS = 30


def informative(query_row: Mapping[str, object], corpus: CorpusText) -> bool:
    if "?" not in str(query_row["query"]):
        return False
    for section_id in expected_section_ids(dict(query_row)):
        text = corpus.sections.get(section_id, "")
        if (
            section_slug(section_id) in UNINFORMATIVE_SLUGS
            or len(text.split()) < MIN_SECTION_TOKENS
        ):
            return False
    return True


def multi_hop_kind(
    query_row: Mapping[str, object], result: OneRoundCoverage
) -> str | None:
    """The multi-hop kind of a benchmark question one round misses, or None.

    The two-drug and brand-to-ingredient kinds are generated from the corpus
    (`golden_generate`): the benchmark has no question whose evidence sits in two
    different drugs' documents, only the same product at another strength.
    """
    if not result.missing:
        return None
    if query_row.get("answer_mode") == "multi_required":
        return "three_intent"
    if query_row.get("eval_group") == "noisy":
        return "noisy_retry"
    return "retrieval_miss"


def trim_covered(
    items: Sequence[GoldenItem],
    coverage_by_query: Mapping[str, OneRoundCoverage],
    *,
    keep_per_group: int,
) -> list[str]:
    """Ids of answerable items to drop so each group keeps `keep_per_group`.

    Only items whose gold one round fully covers are dropped, in id order.
    """
    by_group: dict[str, list[GoldenItem]] = defaultdict(list)
    for item in items:
        # Probes have no group and are never trimmed.
        if item.eval_group is not None:
            by_group[item.eval_group].append(item)
    dropped: list[str] = []
    problems: list[str] = []
    for group, members in sorted(by_group.items()):
        excess = len(members) - keep_per_group
        if excess <= 0:
            continue
        covered = sorted(
            item.item_id
            for item in members
            if (result := coverage_by_query.get(str(item.source_query_id)))
            and not result.missing
        )
        if len(covered) < excess:
            problems.append(f"{group}: {len(covered)} covered items, need {excess}")
            continue
        dropped.extend(covered[:excess])
    if problems:
        raise ValueError("cannot trim the golden set:\n" + "\n".join(problems))
    return dropped


@dataclass(frozen=True)
class OneRoundRun:
    rows: dict[str, dict]
    judged: dict[str, dict[str, frozenset[str]]]
    coverage: dict[str, OneRoundCoverage]

    def hard_candidates(self, corpus: CorpusText) -> list[dict[str, object]]:
        """Benchmark questions one round misses that fit a multi-hop kind."""
        out: list[dict[str, object]] = []
        for query_id, result in sorted(self.coverage.items()):
            row = self.rows[query_id]
            kind = multi_hop_kind(row, result)
            single = kind in {"retrieval_miss", "noisy_retry"}
            if kind is None or (single and not informative(row, corpus)):
                continue
            out.append(
                {
                    "query_id": query_id,
                    "query": row["query"],
                    "kind": kind,
                    "eval_group": row.get("eval_group"),
                    "expected_section_ids": expected_section_ids(row),
                    "missing": list(result.missing),
                }
            )
        return out


def load_one_round(run_root: Path, *, model: str, top_k: int) -> OneRoundRun:
    """Coverage of every question of a retrieval run after reranking with `model`."""
    from pharma_lab.evaluation.metrics_service import (
        MetricsRequest,
        load_and_validate_metric_inputs,
        ranked_payloads,
    )

    inputs = load_and_validate_metric_inputs(
        MetricsRequest(run_root=run_root, top_k=top_k, model=model)
    )
    (rerank,) = inputs.rerank_variants
    judged: dict[str, dict[str, frozenset[str]]] = {}
    found: dict[str, OneRoundCoverage] = {}
    for record in inputs.candidates:
        query_id = str(record["query_id"])
        row = inputs.evaluation_rows[query_id]
        judged[query_id] = inputs.judgments.for_query(query_id)
        found[query_id] = coverage(
            ranked_payloads(record, row, rerank), row, judged[query_id], top_k=top_k
        )
    return OneRoundRun(inputs.evaluation_rows, judged, found)
