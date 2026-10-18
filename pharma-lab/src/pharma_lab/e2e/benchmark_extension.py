"""The retrieval benchmark: 10,000 questions whose groups prove every layer (spec v2 §3.0b,
§3.1, §4.D), and from which the golden e2e set is drawn.

Six groups are built by rules (`evaluation build`). Five more are added so that each
ablation has questions that need its layer: `colloquial` (a product named only by an alias
absent from its leaflet), `glossary` (a plain-language phrase for a term the formulary
writes only abbreviated), `conversational` (a follow-up turn that inherits a question's
gold sections), `multi_hop` (questions whose evidence sits in two documents or in two
chunks of one) and `safety` (unanswerable, out-of-scope and injection turns, with no gold
section, scored only end to end). The rule-built groups make room: structured,
leaflet_short, noisy and multi_intent stay whole, formulary and leaflet are sampled 2:1 by
intent, and every question the golden set or a conversational row refers to is kept.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Mapping, Sequence

from pharma_lab.e2e.conversational import build_conversational
from pharma_lab.e2e.corpus_text import CorpusText
from pharma_lab.e2e.golden_generate import (
    benchmark_row,
    colloquial_benchmark,
    glossary_benchmark,
)

BENCHMARK_SIZE = 10_000
CONVERSATIONAL_ROWS = 1_500
MULTI_HOP_ROWS = 300
WHOLE_GROUPS = ("structured", "leaflet_short", "noisy", "multi_intent")
SAMPLED_GROUPS = {"formulary": 2, "leaflet": 1}
GENERATED_GROUPS = ("colloquial", "glossary", "conversational", "multi_hop", "safety")
SAFETY_CATEGORIES = ("unanswerable", "out_of_scope", "injection")


def golden_rows(
    items: Sequence[Mapping[str, object]], base_ids: set[str]
) -> tuple[list[dict], list[dict]]:
    """Benchmark rows for the golden items that no rule-built question carries: the
    generated multi-hop questions and the safety turns. Each row's id is the item id."""
    multi_hop: list[dict] = []
    safety: list[dict] = []
    for item in items:
        category = str(item.get("category"))
        turns = item.get("turns")
        if not isinstance(turns, list) or not turns:
            continue
        question = str(turns[-1]["text"])
        tags = item.get("tags")
        kind = str(tags[0]) if isinstance(tags, list) and tags else category
        if category == "multi_hop" and str(item.get("source_query_id")) not in base_ids:
            sections = _strings(item.get("gold_section_ids"))
            multi_hop.append(
                _row(item, question, "multi_hop", kind, sections, "multi_intent")
            )
        elif category in SAFETY_CATEGORIES:
            safety.append(_row(item, question, "safety", kind, [], category))
    return multi_hop, safety


def _row(
    item: Mapping[str, object],
    question: str,
    group: str,
    form: str,
    sections: list[str],
    intent: str,
) -> dict:
    return {
        "query_id": str(item["item_id"]),
        "query": question,
        "eval_group": group,
        "source_family": "golden",
        "query_form": form,
        "intent_category": intent,
        "expected_section_id": sections[0] if sections else None,
        "expected_section_ids": sections,
        "query_intent_count": len(sections),
        "answer_mode": "multi_required" if len(sections) > 1 else "single",
        "eval_tags": [group, form],
    }


def assemble_benchmark(
    base: Sequence[dict],
    corpus: CorpusText,
    aliases: Sequence[tuple[str, Sequence[str]]],
    golden: Sequence[Mapping[str, object]],
    extra_multi_hop: Sequence[Mapping[str, object]],
    *,
    covered: Mapping[str, bool] | None,
    seed: int,
    size: int = BENCHMARK_SIZE,
    conversational_rows: int = CONVERSATIONAL_ROWS,
    multi_hop_rows: int = MULTI_HOP_ROWS,
) -> list[dict]:
    """The `size`-row benchmark from the rule-built questions: the five added
    groups in full and the rule-built groups cut to fit. `extra_multi_hop` are generated
    multi-hop candidates that fill the group beyond the golden items."""
    base_ids = {str(row["query_id"]) for row in base}
    conversational = build_conversational(
        base, corpus, total=conversational_rows, seed=seed, covered=covered
    )
    probes = [
        benchmark_row(p)
        for p in (*colloquial_benchmark(corpus, aliases), *glossary_benchmark(corpus))
    ]
    multi_hop, safety = golden_rows(golden, base_ids)
    seen = {frozenset(row["expected_section_ids"]) for row in multi_hop}
    for candidate in extra_multi_hop:
        if len(multi_hop) >= multi_hop_rows:
            break
        sections = _strings(candidate.get("expected_section_ids"))
        if frozenset(sections) in seen:
            continue
        seen.add(frozenset(sections))
        multi_hop.append(
            {
                **_row(
                    {"item_id": f"mhop-gen-{len(multi_hop) + 1:04d}"},
                    str(candidate["query"]),
                    "multi_hop",
                    str(candidate["kind"]),
                    sections,
                    "multi_intent",
                ),
                "source_family": "generated",
            }
        )
    added = [*probes, *conversational, *multi_hop, *safety]
    keep = {
        str(item["source_query_id"])
        for item in golden
        if str(item.get("source_query_id")) in base_ids
    } | {str(row["parent_query_id"]) for row in conversational}
    kept = _cut_rule_groups(base, size - len(added), keep=keep, seed=seed)
    return [*kept, *added]


def _cut_rule_groups(
    base: Sequence[dict], size: int, *, keep: set[str], seed: int
) -> list[dict]:
    """`size` rule-built rows: WHOLE_GROUPS in full, SAMPLED_GROUPS by weight, each
    keeping every row of `keep` and filling the rest by intent in a seeded order; the
    rows stay in file order."""
    by_group: dict[str, list[dict]] = defaultdict(list)
    for row in base:
        by_group[str(row.get("eval_group"))].append(row)
    whole = sum(len(by_group[group]) for group in WHOLE_GROUPS)
    room = size - whole
    total_weight = sum(SAMPLED_GROUPS.values())
    targets = {
        group: room * weight // total_weight for group, weight in SAMPLED_GROUPS.items()
    }
    first = next(iter(SAMPLED_GROUPS))
    targets[first] += room - sum(targets.values())
    chosen: set[str] = {
        str(row["query_id"]) for group in WHOLE_GROUPS for row in by_group[group]
    }
    rng = random.Random(seed)
    for group, target in targets.items():
        rows = by_group[group]
        must = [row for row in rows if str(row["query_id"]) in keep]
        if len(must) > target:
            raise ValueError(f"{group}: {len(must)} rows must stay, room for {target}")
        chosen |= {str(row["query_id"]) for row in must}
        chosen |= _fill_by_intent(
            [row for row in rows if str(row["query_id"]) not in keep],
            target - len(must),
            rng,
        )
    return [row for row in base if str(row["query_id"]) in chosen]


def _fill_by_intent(rows: Sequence[dict], count: int, rng: random.Random) -> set[str]:
    """`count` row ids spread over intents in proportion (largest remainder)."""
    by_intent: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_intent[str(row.get("intent_category"))].append(row)
    total = len(rows)
    shares = {intent: count * len(group) / total for intent, group in by_intent.items()}
    quotas = {intent: int(share) for intent, share in shares.items()}
    leftover = count - sum(quotas.values())
    for intent in sorted(shares, key=lambda i: shares[i] - quotas[i], reverse=True)[
        :leftover
    ]:
        quotas[intent] += 1
    picked: set[str] = set()
    for intent, group in sorted(by_intent.items()):
        order = list(group)
        rng.shuffle(order)
        picked |= {str(row["query_id"]) for row in order[: quotas[intent]]}
    return picked


def _strings(value: object) -> list[str]:
    return [str(entry) for entry in value] if isinstance(value, list) else []
