"""The pharmacist's review of the whole golden set (spec v2 appendix C.2).

Every item gets one review row keyed by a digest of its content, so a pack rebuilt after
the golden set changes keeps the verdicts of items that did not change and asks again
for the others. The score is the share of items the pharmacist had to fix or reject, per
golden tier, which the paper reports.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence

from pharma_lab.bundle.corpus_text import CorpusText
from pharma_lab.e2e.golden import SLICE_KINDS, Category, GoldenItem
from pharma_lab.evaluation.statistics import Summary, wilson

TIERS = ("natural", "slice", "multi_hop", "multi_turn", "safety")
VERDICTS = ("pass", "fixed", "fail")
PACK_SIZE = 50


def item_tier(item: GoldenItem) -> str:
    if item.category is Category.ANSWERABLE:
        return "slice" if set(item.tags) & set(SLICE_KINDS) else "natural"
    if item.category is Category.MULTI_HOP:
        return "multi_hop"
    if item.category is Category.MULTI_TURN:
        return "multi_turn"
    return "safety"


def item_digest(item: GoldenItem) -> str:
    payload = json.dumps(item.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def row_is_current(row: Mapping[str, str], digest: str) -> bool:
    """A verdict stands for the item it was given on, and a `fixed` verdict also for
    the item as the pharmacist's fix left it."""
    return bool(digest) and digest in (row.get("digest"), row.get("fixed_digest"))


def review_rows(
    items: Sequence[GoldenItem], previous: Mapping[str, Mapping[str, str]]
) -> list[dict[str, str]]:
    """One row per item, sorted by tier then item id. A row keeps its verdict while the
    item is unchanged. A `fixed` verdict also survives the one rebuild that brings the
    pharmacist's own edit into the set: the new digest is recorded as `fixed_digest`,
    and any later change asks for review again."""
    rows: list[dict[str, str]] = []
    for item in sorted(items, key=lambda i: (TIERS.index(item_tier(i)), i.item_id)):
        digest = item_digest(item)
        old = previous.get(item.item_id, {})
        fixed = old.get("fixed_digest", "")
        if old.get("verdict") == "fixed" and not fixed and old.get("digest") != digest:
            fixed = digest
        kept = row_is_current(
            {"digest": old.get("digest", ""), "fixed_digest": fixed}, digest
        )
        rows.append(
            {
                "item_id": item.item_id,
                "tier": item_tier(item),
                "digest": old["digest"] if kept else digest,
                "fixed_digest": fixed if kept else "",
                "verdict": old.get("verdict", "") if kept else "",
                "reason": old.get("reason", "") if kept else "",
            }
        )
    return rows


def review_score(rows: Sequence[Mapping[str, str]]) -> dict[str, Summary]:
    """Share of `fixed` or `fail` verdicts per tier, with a Wilson interval."""
    missing = [row["item_id"] for row in rows if row.get("verdict") not in VERDICTS]
    if missing:
        raise ValueError(f"items without a verdict: {', '.join(missing)}")
    by_tier: defaultdict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_tier[row["tier"]].append(float(row["verdict"] != "pass"))
    return {tier: wilson(values) for tier, values in by_tier.items()}


def render_pack(name: str, items: Sequence[GoldenItem], corpus: CorpusText) -> str:
    """A review file: every item, then each gold section's text once."""
    parts = [
        f"# Review package: {name} ({len(items)} items)\n\n"
        "Section texts are in the appendix at the end, once per section. Line breaks "
        "inside a sentence come from the PDF source.\n"
    ]
    used: dict[str, None] = {}
    for item in items:
        parts.append(
            f"\n---\n\n## {item.item_id}  (tier: {item_tier(item)}; "
            f"tags: {', '.join(item.tags) or '-'}; source: {item.source_query_id})\n"
        )
        for turn in item.turns[:-1]:
            speaker = "User" if turn.role == "user" else "Assistant (fixed)"
            parts.append(f"\n> {speaker}: {turn.text}\n")
        parts.append(f"\n**Question:** {item.turns[-1].text}\n")
        parts.append(f"\n**Expected behaviour:** {item.expected_behavior.value}\n")
        if item.gold_section_ids:
            parts.append(f"\n**Gold sections:** {', '.join(item.gold_section_ids)}\n")
        if item.reference.answer or item.reference.key_facts:
            parts.append(f"\n**Answer:** {item.reference.answer}\n\n**Key facts:**\n")
            for n, fact in enumerate(item.reference.key_facts, start=1):
                parts.append(
                    f"{n}. fact: {fact.fact}\n   quote: «{fact.evidence_quote}»\n"
                    f"   section: {fact.section_id}\n"
                )
        used.update(dict.fromkeys(item.gold_section_ids))
    parts.append("\n---\n\n# Appendix: gold section texts\n")
    for section_id in used:
        title = corpus.titles.get(corpus.section_documents.get(section_id, ""), "")
        text = corpus.sections.get(section_id, "(missing from the bundle)")
        parts.append(f"\n## {section_id} ({title})\n\n{text}\n")
    return "".join(parts)
