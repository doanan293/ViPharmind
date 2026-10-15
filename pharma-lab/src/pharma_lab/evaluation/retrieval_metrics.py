import math
from collections import defaultdict
from collections.abc import Iterable, Mapping

DEFAULT_METRIC_KS = (3, 5, 10, 30)
# Cutoffs of the BEIR/MTEB-style nDCG@k and MRR@k reported next to Hit@k: 5 is what the
# pipeline reads per round (spec v2 §3.0c), 10 is the BEIR convention.
RANKING_KS = (5, 10)


def expected_section_ids(row: Mapping[str, object]) -> list[str]:
    raw = row.get("expected_section_ids")
    if isinstance(raw, list):
        return [str(s) for s in raw if s]
    if isinstance(raw, str):
        return [s for s in raw.split("|") if s]
    primary = row.get("expected_section_id")
    return [str(primary)] if primary else []


def _chunk_id(payload: Mapping[str, object]) -> str:
    return str(payload.get("chunk_id") or "")


def _sections(payload: Mapping[str, object]) -> set[str]:
    raw = payload.get("section_ids")
    return {str(s) for s in raw} if isinstance(raw, list) else set()


def is_hit(
    payload: Mapping[str, object],
    expected: Mapping[str, object],
    accepted_chunk_ids: frozenset[str] = frozenset(),
) -> bool:
    """A chunk answers the row when it holds a gold section or is a judged accepted chunk.

    `accepted_chunk_ids` are chunks outside the gold sections that relevance judgments
    accept for this row (see evaluation/relevance_judgments.py).
    """
    if accepted_chunk_ids and _chunk_id(payload) in accepted_chunk_ids:
        return True
    return bool(_sections(payload) & set(expected_section_ids(expected)))


def evidence_units(query_row: Mapping[str, object]) -> tuple[str, ...]:
    """What a query needs found: every section of a multi-part question, otherwise one
    unit (the expected section, or any of the acceptable ones)."""
    sections = expected_section_ids(query_row)
    if query_row.get("answer_mode") == "multi_required" and sections:
        return tuple(sections)
    return ("answer",)


def satisfied_units(
    payload: Mapping[str, object],
    query_row: Mapping[str, object],
    judged: Mapping[str, frozenset[str]],
) -> set[str]:
    """Every evidence unit a retrieved chunk satisfies; a chunk may hold several sections."""
    units = evidence_units(query_row)
    if units == ("answer",):
        accepted = frozenset().union(*judged.values()) if judged else frozenset()
        return {"answer"} if is_hit(payload, query_row, accepted) else set()
    chunk = _chunk_id(payload)
    held = _sections(payload)
    return {unit for unit in units if unit in held or chunk in judged.get(unit, ())}


def ranking_scores(
    retrieved_payloads: list[dict],
    query_row: Mapping[str, object],
    *,
    judged: Mapping[str, frozenset[str]],
    k: int,
) -> dict[str, float]:
    """nDCG@k with binary gains and MRR@k over evidence units.

    A unit earns gain once, at the first chunk that satisfies it; a chunk that holds
    several gold sections earns their gains at the same rank. The ideal is fixed per
    query, one unit per rank from rank 1 as in BEIR, so every system is scored against
    the same ideal; a chunk that holds several units can beat it, so the score is capped
    at 1. For single-answer queries nDCG@k is 1/log2(rank+1) of the first hit, as in
    known-item retrieval benchmarks.
    """
    units = evidence_units(query_row)
    seen: set[str] = set()
    dcg = 0.0
    first_hit: int | None = None
    for rank, payload in enumerate(retrieved_payloads[:k], start=1):
        fresh = satisfied_units(payload, query_row, judged) - seen
        seen |= fresh
        dcg += len(fresh) / math.log2(rank + 1)
    for rank, payload in enumerate(retrieved_payloads[:k], start=1):
        if satisfied_units(payload, query_row, judged):
            first_hit = rank
            break
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(units), k) + 1))
    return {
        f"ndcg@{k}": min(1.0, dcg / ideal),
        f"mrr@{k}": 0.0 if first_hit is None else 1.0 / first_hit,
    }


def score_ranked_payloads(
    retrieved_payloads: list[dict],
    query_row: Mapping[str, object],
    top_k: int = 10,
    metric_ks: Iterable[int] = DEFAULT_METRIC_KS,
    judgments: Mapping[str, frozenset[str]] | None = None,
) -> dict[str, float]:
    """Hit@k, MRR and multi-section recall of one ranked candidate list.

    `judgments` maps a gold section id to the extra chunk ids accepted for it.
    """
    judged = judgments or {}
    hits: dict[str, float] = {}
    units = evidence_units(query_row)
    satisfied_at = [satisfied_units(p, query_row, judged) for p in retrieved_payloads]

    for k in metric_ks:
        if k > top_k:
            continue
        hits[f"hit@{k}"] = 1 if any(satisfied_at[:k]) else 0
        if query_row.get("answer_mode") == "multi_required":
            found = set().union(*satisfied_at[:k]) if satisfied_at[:k] else set()
            matched = len(found & set(units))
            hits[f"multi_section_recall@{k}"] = matched / (len(units) or 1)
            hits[f"multi_all_hit@{k}"] = 1 if matched == len(units) else 0

    first_hit_rank = next(
        (rank for rank, found in enumerate(satisfied_at, start=1) if found), None
    )
    hits["mrr"] = 1.0 / first_hit_rank if first_hit_rank else 0.0
    for k in RANKING_KS:
        if k <= top_k:
            hits.update(
                ranking_scores(retrieved_payloads, query_row, judged=judged, k=k)
            )
    return hits


def new_metric_bucket() -> defaultdict[str, float]:
    return defaultdict(float)


def accumulate_metrics(
    target: defaultdict[str, float], hits: dict[str, float], query_row: dict
) -> None:
    target["count"] += 1
    for key, value in hits.items():
        target[key] += value
    if query_row.get("answer_mode") == "multi_required":
        target["multi_count"] += 1
