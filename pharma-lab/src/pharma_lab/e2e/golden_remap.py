"""Carry authored golden items over to a corpus whose leaflets are split by heading.

A golden item cites a leaflet page by its key. After the split the page key names a
document, and its text lives in one section per heading. Each key fact is moved to the
subsection whose text holds its evidence quote, the gold chunks are the chunks of those
subsections that hold a quote, and the "(phần ...)" hint is dropped from the question.
Items whose quotes sit in several subsections are kept with every candidate and reported
in the notes, so an author picks the right one by hand.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from pharma_lab.e2e.corpus_text import CorpusText, normalize_space
from pharma_lab.e2e.golden import GoldenItem

GROUP_RENAMES = {"patient_natural": "leaflet_short", "noisy_confuser": "noisy"}
# "(phần <label>)" at the end of a question; the label may hold one nested "(...)".
_HINT = re.compile(r"\s*\(phần\s(?:[^()]|\([^()]*\))*\)\s*$", re.IGNORECASE)
ChunkLookup = Callable[[Iterable[str]], dict[str, str]]


@dataclass(frozen=True)
class RemapResult:
    item: GoldenItem
    notes: list[str]


def strip_hint(text: str) -> str:
    return _HINT.sub("", text).strip()


def _candidates(corpus: CorpusText, key: str) -> list[str]:
    if key in corpus.sections:
        return [key]
    if key.startswith("leaflet:") and key.count(":") > 2:
        # A subsection key from an earlier split: search its whole page.
        key = ":".join(key.split(":")[:3])
    return sorted(
        section
        for section, document in corpus.section_documents.items()
        if document == key
    )


def _holders(corpus: CorpusText, candidates: list[str], quote: str) -> list[str]:
    needle = normalize_space(quote)
    return [
        key for key in candidates if needle in (corpus.normalized_section(key) or "")
    ]


def remap_item(
    item: GoldenItem, corpus: CorpusText, chunks: ChunkLookup
) -> RemapResult:
    notes: list[str] = []
    data = item.model_dump(mode="json")
    group = data.get("eval_group")
    if group in GROUP_RENAMES:
        data["eval_group"] = GROUP_RENAMES[group]
    if data["turns"]:
        last = data["turns"][-1]["text"]
        stripped = strip_hint(last)
        if stripped != last:
            data["turns"][-1]["text"] = stripped
            notes.append(f"{item.item_id}: hint removed from question")
    facts = data["reference"]["key_facts"]
    moved = False
    gold: list[str] = []
    for fact in facts:
        holders = _holders(
            corpus, _candidates(corpus, fact["section_id"]), fact["evidence_quote"]
        )
        if not holders:
            notes.append(
                f"{item.item_id}: quote not found: {fact['evidence_quote'][:60]}"
            )
            gold.extend(s for s in [fact["section_id"]] if s not in gold)
            continue
        if len(holders) > 1:
            notes.append(f"{item.item_id}: ambiguous quote in {holders}")
        else:
            moved = moved or holders[0] != fact["section_id"]
            fact["section_id"] = holders[0]
        gold.extend(s for s in holders if s not in gold)
    if facts and gold != data["gold_section_ids"]:
        data["gold_section_ids"] = gold
        quotes = [normalize_space(fact["evidence_quote"]) for fact in facts]
        data["gold_chunk_ids"] = sorted(
            label
            for label, text in chunks(gold).items()
            if any(quote in normalize_space(text) for quote in quotes)
        )
    elif moved:
        notes.append(f"{item.item_id}: key facts moved within the gold sections")
    return RemapResult(GoldenItem.model_validate(data), notes)


def remap_files(
    paths: Iterable[Path], corpus: CorpusText, chunks: ChunkLookup, todo: Path
) -> int:
    """Rewrite each authored batch in place; return how many items changed."""
    notes: list[str] = []
    changed = 0
    for path in paths:
        lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        out: list[str] = []
        for line in lines:
            original = GoldenItem.model_validate(json.loads(line))
            result = remap_item(original, corpus, chunks)
            notes.extend(result.notes)
            changed += result.item != original
            out.append(
                json.dumps(result.item.model_dump(mode="json"), ensure_ascii=False)
            )
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
    todo.write_text(
        "# Golden remap notes\n\n" + "".join(f"- {note}\n" for note in notes),
        encoding="utf-8",
    )
    return changed
