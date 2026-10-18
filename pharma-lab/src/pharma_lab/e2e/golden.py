"""The E2E golden set: item schema, validation and freezing (spec §3)."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from collections.abc import Sequence, Set
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pharma_lab.artifacts.manifest import sha256_file, write_json
from pharma_lab.e2e.corpus_text import CorpusText, normalize_space

SCHEMA = "e2e-golden-v3"
ANSWERABLE_PER_GROUP = 30
EVAL_GROUPS = (
    "formulary",
    "leaflet",
    "structured",
    "leaflet_short",
    "noisy",
    "multi_intent",
)


class Category(StrEnum):
    ANSWERABLE = "answerable"
    MULTI_HOP = "multi_hop"
    MULTI_TURN = "multi_turn"
    UNANSWERABLE = "unanswerable"
    OUT_OF_SCOPE = "out_of_scope"
    INJECTION = "injection"


class ExpectedBehavior(StrEnum):
    GROUNDED = "grounded"
    ABSTAIN = "abstain"
    REDIRECT = "redirect"
    BLOCKED = "blocked"


# Answerable groups follow the retrieval benchmark's groups: 30 items for each of the six
# rule-built groups, and the two enrichment groups (a product named only by a colloquial
# alias, a plain-language phrase for an abbreviated term). The conversational group is the
# multi_turn category (spec §3.0b, §3.1).
ANSWERABLE_GROUP_QUOTAS: dict[str, int] = {
    **dict.fromkeys(EVAL_GROUPS, ANSWERABLE_PER_GROUP),
    "colloquial": 20,
    "glossary": 10,
}
CONVERSATIONAL_GROUP = "conversational"
# Slice items are answerable items of the rule-built groups drawn at random from one
# construction-defined slice of the benchmark (eval data v3 design §3.4, §4), each the
# questions one layer is built for: the gold section does not name the drug (header
# enrichment), the question shares few words with it (dense half of hybrid search), or
# a sibling product of the same brand has the same section (reranking). A slice is set
# by the question and the corpus, never by a system's result. An item keeps its group.
SLICE_QUOTAS: dict[str, int] = {
    "header_dependent": 20,
    "low_overlap": 20,
    "sibling_products": 20,
}
SLICE_KINDS = tuple(SLICE_QUOTAS)
# Multi-turn items per phenomenon of the benchmark's conversational group.
MULTI_TURN_QUOTAS: dict[str, int] = {
    "pronoun": 7,
    "ellipsis": 7,
    "intent_shift": 6,
    "drug_shift": 6,
    "answer_entity": 6,
    "topic_switch": 6,
    "multi_intent": 6,
    "noisy_followup": 6,
}

QUOTAS: dict[Category, int] = {
    Category.ANSWERABLE: sum(ANSWERABLE_GROUP_QUOTAS.values())
    + sum(SLICE_QUOTAS.values()),
    Category.MULTI_HOP: 150,
    Category.MULTI_TURN: sum(MULTI_TURN_QUOTAS.values()),
    Category.UNANSWERABLE: 10,
    Category.OUT_OF_SCOPE: 10,
    Category.INJECTION: 10,
}
ID_PREFIX: dict[Category, str] = {
    Category.ANSWERABLE: "e2e-ans-",
    Category.MULTI_HOP: "e2e-mhop-",
    Category.MULTI_TURN: "e2e-mt-",
    Category.UNANSWERABLE: "e2e-una-",
    Category.OUT_OF_SCOPE: "e2e-oos-",
    Category.INJECTION: "e2e-inj-",
}
BEHAVIOR: dict[Category, ExpectedBehavior] = {
    Category.ANSWERABLE: ExpectedBehavior.GROUNDED,
    Category.MULTI_HOP: ExpectedBehavior.GROUNDED,
    Category.MULTI_TURN: ExpectedBehavior.GROUNDED,
    Category.UNANSWERABLE: ExpectedBehavior.ABSTAIN,
    Category.OUT_OF_SCOPE: ExpectedBehavior.REDIRECT,
    Category.INJECTION: ExpectedBehavior.BLOCKED,
}

# Questions one retrieval round answers only in part, each kind aimed at one part of the
# harness (spec §3.0b). From the benchmark: a clean question whose gold section the first
# round misses, a noisy or misspelled one that misses, and a three-intent question whose
# sections fall in two chunks. Generated from the corpus: two drugs whose evidence sits in
# two monographs, and a brand whose leaflet lacks the section its ingredient's monograph
# has.
# The two benchmark kinds hold every first-round miss the review kept: one round of
# hybrid search and reranking misses few clean questions, so the generated kinds, which
# need two documents by construction, take the rest of the 150.
MULTI_HOP_QUOTAS: dict[str, int] = {
    "retrieval_miss": 25,
    "noisy_retry": 25,
    "three_intent": 16,
    "two_drug": 48,
    "brand_to_ingredient": 36,
}
MULTI_HOP_KINDS = tuple(MULTI_HOP_QUOTAS)

_STRICT = ConfigDict(extra="forbid", frozen=True)


class Turn(BaseModel):
    model_config = _STRICT

    role: Literal["user", "assistant"]
    text: str = Field(min_length=1)


class KeyFact(BaseModel):
    model_config = _STRICT

    fact: str = Field(min_length=1)
    evidence_quote: str = Field(min_length=1)
    section_id: str


class Reference(BaseModel):
    model_config = _STRICT

    answer: str = ""
    key_facts: list[KeyFact] = Field(default_factory=list)


class GoldenItem(BaseModel):
    model_config = _STRICT

    item_id: str
    category: Category
    source_query_id: str | None = None
    turns: list[Turn]
    expected_behavior: ExpectedBehavior
    gold_section_ids: list[str] = Field(default_factory=list)
    reference: Reference = Field(default_factory=Reference)
    absent_terms: list[str] = Field(default_factory=list)
    eval_group: str | None = None
    tags: list[str] = Field(default_factory=list)

    @property
    def question(self) -> str:
        return self.turns[-1].text

    @property
    def history(self) -> list[tuple[str, str]]:
        """(user, assistant) pairs before the evaluated question."""
        earlier = self.turns[:-1]
        return [
            (earlier[index].text, earlier[index + 1].text)
            for index in range(0, len(earlier) - 1, 2)
        ]


class GoldenManifest(BaseModel):
    model_config = _STRICT

    schema_name: str = Field(default=SCHEMA, alias="schema")
    sha256: str
    counts: dict[str, int]
    answerable_per_group: dict[str, int]
    gold_sha256: str
    bundle_manifest_sha256: str
    created_at: str


def manifest_path(golden_path: Path) -> Path:
    return golden_path.with_name(golden_path.stem + ".manifest.json")


def archive_path(golden_path: Path, sha256: str) -> Path:
    """Where `golden build` keeps the version it replaced, by content hash."""
    return golden_path.with_name(f"{golden_path.stem}.{sha256}.jsonl")


def read_items(path: Path) -> tuple[list[GoldenItem], list[str]]:
    items: list[GoldenItem] = []
    problems: list[str] = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            items.append(GoldenItem.model_validate_json(line))
        except ValidationError as exc:
            problems.append(f"{path}:{line_number}: {exc.errors()[0]['msg']}")
    return items, problems


def load_golden(path: Path) -> list[GoldenItem]:
    items, problems = read_items(path)
    if problems:
        raise ValueError("invalid golden set:\n" + "\n".join(problems))
    if not items:
        raise ValueError(f"golden set is empty: {path}")
    return items


def _turn_problems(item: GoldenItem) -> list[str]:
    roles = [turn.role for turn in item.turns]
    if item.category is Category.MULTI_TURN:
        expected = ["user", "assistant"] * (len(roles) // 2) + ["user"]
        if len(roles) < 3 or roles != expected:
            return [
                f"{item.item_id}: multi_turn needs alternating user/assistant turns "
                "ending with user (at least 3)"
            ]
        return []
    if roles != ["user"]:
        return [f"{item.item_id}: {item.category} needs exactly one user turn"]
    return []


def _item_problems(item: GoldenItem, corpus: CorpusText) -> list[str]:
    problems: list[str] = []
    name = item.item_id
    if not name.startswith(ID_PREFIX[item.category]):
        problems.append(f"{name}: id must start with {ID_PREFIX[item.category]}")
    if item.expected_behavior is not BEHAVIOR[item.category]:
        problems.append(
            f"{name}: {item.category} expects {BEHAVIOR[item.category]}, "
            f"not {item.expected_behavior}"
        )
    problems.extend(_turn_problems(item))
    facts = item.reference.key_facts
    if item.expected_behavior is ExpectedBehavior.GROUNDED:
        if not facts or not item.gold_section_ids:
            problems.append(f"{name}: grounded items need key facts and gold sections")
    elif facts or item.gold_section_ids:
        problems.append(f"{name}: non-grounded items have no key facts or gold ids")
    for section_id in item.gold_section_ids:
        if section_id not in corpus.sections:
            problems.append(f"{name}: gold section {section_id} is not in the bundle")
    for index, fact in enumerate(facts, start=1):
        if fact.section_id not in item.gold_section_ids:
            problems.append(
                f"{name}: key fact {index} cites {fact.section_id}, "
                "which is not a gold section"
            )
            continue
        text = corpus.normalized_section(fact.section_id)
        if text is None or normalize_space(fact.evidence_quote) not in text:
            problems.append(
                f"{name}: key fact {index} quote is not in section {fact.section_id}"
            )
    if item.category is Category.MULTI_HOP:
        kinds = [tag for tag in item.tags if tag in MULTI_HOP_KINDS]
        if len(kinds) != 1:
            problems.append(
                f"{name}: multi_hop items need exactly one kind tag "
                f"({', '.join(MULTI_HOP_KINDS)})"
            )
    if item.category is Category.ANSWERABLE:
        slices = _slice_kinds(item)
        if item.eval_group not in ANSWERABLE_GROUP_QUOTAS:
            problems.append(f"{name}: answerable items need a benchmark eval_group")
        elif len(slices) > 1 or (slices and item.eval_group not in EVAL_GROUPS):
            problems.append(
                f"{name}: a slice item has one slice tag and a rule-built source group"
            )
    if item.category is Category.MULTI_TURN:
        phenomena = [tag for tag in item.tags if tag in MULTI_TURN_QUOTAS]
        if item.eval_group != CONVERSATIONAL_GROUP or len(phenomena) != 1:
            problems.append(
                f"{name}: multi_turn items are in the {CONVERSATIONAL_GROUP} group "
                "with one phenomenon tag"
            )
    if item.category is Category.UNANSWERABLE:
        if not item.absent_terms:
            problems.append(f"{name}: unanswerable items need absent_terms")
        for term in item.absent_terms:
            if corpus.contains(term):
                problems.append(f"{name}: absent term {term!r} occurs in the corpus")
    elif item.absent_terms:
        problems.append(f"{name}: only unanswerable items carry absent_terms")
    return problems


def _count_problems(items: Sequence[GoldenItem]) -> list[str]:
    problems: list[str] = []
    counts = Counter(item.category for item in items)
    for category, quota in QUOTAS.items():
        if counts[category] != quota:
            problems.append(f"{category}: {counts[category]} items, expected {quota}")
    groups = Counter(
        item.eval_group
        for item in items
        if item.category is Category.ANSWERABLE and not _slice_kinds(item)
    )
    for group, quota in ANSWERABLE_GROUP_QUOTAS.items():
        if groups[group] != quota:
            problems.append(
                f"answerable {group}: {groups[group]} items, expected {quota}"
            )
    phenomena = Counter(
        tag
        for item in items
        if item.category is Category.MULTI_TURN
        for tag in item.tags
        if tag in MULTI_TURN_QUOTAS
    )
    for phenomenon, quota in MULTI_TURN_QUOTAS.items():
        if phenomena[phenomenon] != quota:
            problems.append(
                f"multi_turn {phenomenon}: {phenomena[phenomenon]} items, "
                f"expected {quota}"
            )
    kinds = Counter(
        tag
        for item in items
        if item.category is Category.MULTI_HOP
        for tag in item.tags
        if tag in MULTI_HOP_KINDS
    )
    for kind, quota in MULTI_HOP_QUOTAS.items():
        if kinds[kind] != quota:
            problems.append(f"multi_hop {kind}: {kinds[kind]} items, expected {quota}")
    slices = Counter(
        kind
        for item in items
        if item.category is Category.ANSWERABLE
        for kind in _slice_kinds(item)
    )
    for kind, quota in SLICE_QUOTAS.items():
        if slices[kind] != quota:
            problems.append(
                f"answerable {kind}: {slices[kind]} items, expected {quota}"
            )
    return problems


def _slice_kinds(item: GoldenItem) -> list[str]:
    return [tag for tag in item.tags if tag in SLICE_KINDS]


def validate_items(
    items: Sequence[GoldenItem], corpus: CorpusText, *, complete: bool
) -> list[str]:
    problems: list[str] = []
    ids = Counter(item.item_id for item in items)
    problems.extend(f"{name}: duplicate item_id" for name, n in ids.items() if n > 1)
    for item in items:
        problems.extend(_item_problems(item, corpus))
    if complete:
        problems.extend(_count_problems(items))
    return problems


def build_golden(
    sources: Sequence[Path],
    output: Path,
    corpus: CorpusText,
    *,
    bundle_manifest_sha256: str,
    gold_sha256: str,
    benchmark_ids: Set[str] | None = None,
) -> GoldenManifest:
    """Validate authored batches and freeze them into one sorted golden file. With
    `benchmark_ids`, every item must be a row of the benchmark (its source_query_id, or
    its own item id for the rows the golden set adds)."""
    if not sources:
        raise ValueError("no authored batches to build from")
    items: list[GoldenItem] = []
    problems: list[str] = []
    for source in sorted(sources):
        batch, batch_problems = read_items(source)
        items.extend(batch)
        problems.extend(batch_problems)
    problems.extend(validate_items(items, corpus, complete=True))
    if benchmark_ids is not None:
        # A generated multi-hop item or a safety turn is a benchmark row under its own
        # item id; every other item points at its row with source_query_id.
        problems.extend(
            f"{item.item_id}: source {item.source_query_id} is not a benchmark row"
            for item in items
            if item.source_query_id not in benchmark_ids
            and item.item_id not in benchmark_ids
        )
    if problems:
        raise ValueError(
            f"golden set has {len(problems)} problem(s):\n" + "\n".join(problems)
        )
    items.sort(key=lambda item: item.item_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name(f".{output.name}.tmp")
    staging.write_text(
        "".join(
            json.dumps(item.model_dump(mode="json"), ensure_ascii=False) + "\n"
            for item in items
        ),
        encoding="utf-8",
    )
    if output.is_file():
        # Runs made with the replaced version resume against it item by item.
        previous = archive_path(output, sha256_file(output))
        if not previous.is_file():
            shutil.copy2(output, previous)
    staging.replace(output)
    counts = Counter(str(item.category) for item in items)
    groups = Counter(
        str(item.eval_group) for item in items if item.category is Category.ANSWERABLE
    )
    manifest = GoldenManifest.model_validate(
        {
            "schema": SCHEMA,
            "sha256": sha256_file(output),
            "counts": dict(sorted(counts.items())),
            "answerable_per_group": dict(sorted(groups.items())),
            "gold_sha256": gold_sha256,
            "bundle_manifest_sha256": bundle_manifest_sha256,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
    )
    write_json(manifest_path(output), manifest.model_dump(mode="json", by_alias=True))
    return manifest
