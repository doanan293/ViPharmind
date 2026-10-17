"""LLM drafts of the golden set's multi-hop items and answerable probes (spec §3.0b),
for review.

Candidates come from `golden hard-candidates` (benchmark questions one retrieval round
answers only in part) and `golden generate` (two-drug and brand questions built from the
corpus). A draft is the reference answer and key facts with verbatim quotes from every
gold section, plus the question in a user's words for generated candidates; it is checked
with the golden rules, sent back once with its problems, and replaced by the next
candidate of its kind when it still fails. Drafts are written as *.draft.jsonl: the
reviewer corrects them before they become *.authored.jsonl. Drafting tops the set up to
the per-kind quotas, so it can run again after a review rejected some items.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pharma_agent.domain.llm.models import ChatMessage, LlmRole, system, user
from pharma_agent.domain.llm.port import LlmError, LlmPort
from pydantic import BaseModel, Field

from pharma_lab.e2e.corpus_text import CorpusText
from pharma_lab.e2e.golden import (
    ID_PREFIX,
    MULTI_HOP_QUOTAS,
    PROBE_QUOTAS,
    Category,
    ExpectedBehavior,
    GoldenItem,
    KeyFact,
    Reference,
    Turn,
    validate_items,
)

# The model the plan names for drafts (phase D Task 7b), on the backend LLM endpoint.
DRAFT_MODEL = "gemini-3.1-flash-lite"


@dataclass(frozen=True)
class Family:
    """A group of drafted items with its own batches, quotas and item ids: the
    multi-hop items, and the answerable probes of the retrieval-side components."""

    batch: str
    category: Category
    quotas: Mapping[str, int]
    id_prefix: str

    @property
    def candidate_files(self) -> tuple[str, str]:
        return (f"{self.batch}.todo.jsonl", f"{self.batch}.generated.jsonl")


MULTI_HOP = Family(
    "multi-hop", Category.MULTI_HOP, MULTI_HOP_QUOTAS, ID_PREFIX[Category.MULTI_HOP]
)
PROBE = Family(
    "probe", Category.ANSWERABLE, PROBE_QUOTAS, f"{ID_PREFIX[Category.ANSWERABLE]}p"
)
FAMILIES = {family.batch: family for family in (MULTI_HOP, PROBE)}

DRAFT_SYSTEM = """Bạn soạn đáp án mẫu cho bộ đánh giá hệ thống tra cứu thuốc tiếng Việt.
Cho một câu hỏi và các mục tài liệu (mỗi mục có id), hãy trả về:
- answer: câu trả lời mẫu tiếng Việt, 1 đến 4 câu, trả lời thẳng vào câu hỏi, chỉ dùng thông tin trong các mục, không thêm câu khuyên hỏi ý kiến bác sĩ.
- key_facts: 2 đến 6 ý nguyên tử mà câu trả lời đúng phải nêu, chỉ gồm những ý trả lời đúng điều được hỏi. Mỗi mục tài liệu phải có ít nhất một key fact.
Mỗi key fact có:
- fact: ý đó, viết ngắn.
- evidence_quote: chép nguyên văn một đoạn 5 đến 30 từ của đúng mục đó, giữ nguyên dấu và ký hiệu markdown. Chọn đoạn văn thường, tránh ranh giới ô bảng. Văn bản có chỗ xuống dòng giữa câu do lấy từ PDF; quote được phép đi qua chỗ xuống dòng, hãy lấy trọn cụm từ thay vì dừng ở cuối dòng.
- section_id: id của mục chứa quote, đúng như được cho.
- question: chỉ khi đề bài yêu cầu viết lại câu hỏi; nếu không, để trống."""

REWRITE_QUESTION = (
    "Câu hỏi trên được ghép theo mẫu. Hãy viết lại thành một câu hỏi tự nhiên như "
    "người dùng tự hỏi (question), giữ nguyên tên thuốc {names} và đúng các ý được "
    "hỏi, không thêm ý mới."
)


class DraftFact(BaseModel):
    fact: str
    evidence_quote: str
    section_id: str


class DraftFailure(BaseModel):
    """A candidate whose draft still broke the golden rules after one retry."""

    query_id: str
    kind: str
    problems: list[str]


class DraftReference(BaseModel):
    answer: str
    key_facts: list[DraftFact] = Field(default_factory=list)
    question: str | None = None


def needed_counts(
    authored: Mapping[str, int], family: Family = MULTI_HOP
) -> dict[str, int]:
    """Items still to draft per kind: the quota less the authored items of that kind."""
    return {
        kind: max(quota - authored.get(kind, 0), 0)
        for kind, quota in family.quotas.items()
    }


def load_candidates(
    authoring_dir: Path, family: Family = MULTI_HOP
) -> list[dict[str, object]]:
    """Rows of every candidate file of `family` that exists (the benchmark candidates
    and the generated ones)."""
    rows: list[dict[str, object]] = []
    for name in family.candidate_files:
        path = Path(authoring_dir) / name
        if path.exists():
            rows += [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
    return rows


def select_candidates(
    candidates: Sequence[Mapping[str, object]],
    *,
    exclude: set[str],
    seed: int,
    exclude_sections: Iterable[frozenset[str]] = (),
    family: Family = MULTI_HOP,
) -> dict[str, list[Mapping[str, object]]]:
    """Candidates by kind in a seeded order, without questions the set already uses
    and without the gold section sets of `exclude_sections` (generated candidate ids
    are positional, so an authored item is recognised by its sections)."""
    by_kind: dict[str, list[Mapping[str, object]]] = {
        kind: [] for kind in family.quotas
    }
    # The benchmark asks the same section pair in both orders; one item is enough.
    seen_sections: set[frozenset[str]] = set(exclude_sections)
    for row in sorted(candidates, key=lambda row: str(row["query_id"])):
        sections = frozenset(_gold(row))
        if str(row["query_id"]) in exclude or sections in seen_sections:
            continue
        seen_sections.add(sections)
        by_kind[str(row["kind"])].append(row)
    rng = random.Random(seed)
    for rows in by_kind.values():
        rows.sort(key=lambda row: str(row["query_id"]))
        rng.shuffle(rows)
    return by_kind


def _batches(authoring_dir: Path, pattern: str) -> list[Path]:
    return sorted(Path(authoring_dir).glob(pattern))


def _lines(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def used_query_ids(authoring_dir: Path) -> set[str]:
    """Questions the authored batches use, and candidates already drafted (a draft the
    review rejected is not drafted again)."""
    used: set[str] = set()
    for pattern in ("*.authored.jsonl", "*-[0-9][0-9].draft.jsonl"):
        for path in _batches(authoring_dir, pattern):
            for line in _lines(path):
                if query_id := line.get("source_query_id"):
                    used.add(str(query_id))
    return used


def authored_state(
    authoring_dir: Path, family: Family = MULTI_HOP
) -> tuple[Counter[str], int]:
    """Authored items of `family` per kind, and the highest item number of the family
    used by any authored or draft batch."""
    counts: Counter[str] = Counter()
    highest = 0
    prefix = family.id_prefix
    batch = family.batch
    for pattern in (f"{batch}-*.authored.jsonl", f"{batch}-*.draft.jsonl"):
        for path in _batches(authoring_dir, pattern):
            for line in _lines(path):
                item_id = str(line.get("item_id", ""))
                if item_id.startswith(prefix) and item_id[len(prefix) :].isdigit():
                    highest = max(highest, int(item_id[len(prefix) :]))
                tags = line.get("tags")
                if pattern.endswith("authored.jsonl") and isinstance(tags, list):
                    counts.update(tag for tag in tags if tag in family.quotas)
    return counts, highest


def authored_sections(
    authoring_dir: Path, family: Family = MULTI_HOP
) -> list[frozenset[str]]:
    """Gold section sets of the authored and drafted items of `family`."""
    sets: list[frozenset[str]] = []
    batch = family.batch
    for pattern in (f"{batch}-*.authored.jsonl", f"{batch}-*.draft.jsonl"):
        for path in _batches(authoring_dir, pattern):
            for line in _lines(path):
                sections = line.get("gold_section_ids")
                if isinstance(sections, list) and sections:
                    sets.append(frozenset(str(section) for section in sections))
    return sets


def authored_documents(authoring_dir: Path, kind: str) -> list[str]:
    """Documents whose sections the authored items of `kind` already use, so generated
    candidates of that kind pick other drugs."""
    documents: set[str] = set()
    for path in _batches(authoring_dir, "multi-hop-*.authored.jsonl"):
        for line in _lines(path):
            tags = line.get("tags")
            sections = line.get("gold_section_ids")
            if isinstance(tags, list) and kind in tags and isinstance(sections, list):
                documents.update(_document(str(section)) for section in sections)
    return sorted(documents)


def _document(section_id: str) -> str:
    parts = section_id.split(":")
    return ":".join(parts[:3] if parts[0] == "leaflet" else parts[:2])


def write_drafts(
    authoring_dir: Path,
    items: Sequence[GoldenItem],
    failures: Sequence[DraftFailure],
    *,
    batch_size: int = 25,
    family: Family = MULTI_HOP,
) -> list[Path]:
    """<batch>-NN.draft.jsonl batches numbered after the existing ones, and
    <batch>.failed.jsonl."""
    directory = Path(authoring_dir)
    batch = family.batch
    existing = [
        int(match.group(1))
        for path in _batches(directory, f"{batch}-*.draft.jsonl")
        if (match := re.fullmatch(rf"{batch}-(\d+)\.draft\.jsonl", path.name))
    ]
    first = max(existing, default=0) + 1
    paths: list[Path] = []
    for index, start in enumerate(range(0, len(items), batch_size)):
        path = directory / f"{batch}-{first + index:02d}.draft.jsonl"
        path.write_text(
            "".join(
                item.model_dump_json(exclude_none=True) + "\n"
                for item in items[start : start + batch_size]
            ),
            encoding="utf-8",
        )
        paths.append(path)
    failed = directory / f"{batch}.failed.jsonl"
    failed.write_text(
        "".join(failure.model_dump_json() + "\n" for failure in failures),
        encoding="utf-8",
    )
    return [*paths, failed]


def draft_messages(
    row: Mapping[str, object], corpus: CorpusText, problems: Sequence[str] = ()
) -> list[ChatMessage]:
    sections = "\n\n".join(
        f"### {section_id}\n{corpus.sections[section_id]}" for section_id in _gold(row)
    )
    prompt = f"Câu hỏi:\n{row['query']}\n\nCác mục tài liệu:\n{sections}"
    if row.get("generated"):
        prompt += "\n\n" + REWRITE_QUESTION.format(names=", ".join(_subjects(row)))
    if problems:
        prompt += "\n\nBản trước có các lỗi sau, hãy sửa:\n" + "\n".join(
            f"- {problem}" for problem in problems
        )
    return [system(DRAFT_SYSTEM), user(prompt)]


def to_item(
    row: Mapping[str, object],
    draft: DraftReference,
    item_id: str,
    family: Family = MULTI_HOP,
) -> GoldenItem:
    question = draft.question if row.get("generated") and draft.question else None
    return GoldenItem(
        item_id=item_id,
        category=family.category,
        source_query_id=str(row["query_id"]),
        turns=[Turn(role="user", text=(question or str(row["query"])).strip())],
        expected_behavior=ExpectedBehavior.GROUNDED,
        gold_section_ids=_gold(row),
        reference=Reference(
            answer=draft.answer.strip(),
            key_facts=[
                KeyFact(
                    fact=fact.fact.strip(),
                    evidence_quote=fact.evidence_quote.strip(),
                    section_id=fact.section_id.strip(),
                )
                for fact in draft.key_facts
            ],
        ),
        tags=[str(row["kind"])],
    )


def draft_problems(
    item: GoldenItem, corpus: CorpusText, subjects: Sequence[str] = ()
) -> list[str]:
    """The golden rules, plus a quote from every gold section (a multi-hop item must
    need every section, including the ones the first round missed), plus every drug
    name a rewritten question must keep."""
    problems = validate_items([item], corpus, complete=False)
    quoted = {fact.section_id for fact in item.reference.key_facts}
    problems += [
        f"{item.item_id}: section {section_id} has no key fact"
        for section_id in item.gold_section_ids
        if section_id not in quoted
    ]
    question = item.question.casefold()
    problems += [
        f"{item.item_id}: question no longer names {name}"
        for name in subjects
        if name.casefold() not in question
    ]
    return problems


async def draft_multi_hop(
    llm: LlmPort,
    candidates: Mapping[str, Sequence[Mapping[str, object]]],
    counts: Mapping[str, int],
    corpus: CorpusText,
    *,
    concurrency: int = 8,
    first_number: int = 1,
    family: Family = MULTI_HOP,
) -> tuple[list[GoldenItem], list[DraftFailure]]:
    """Drafts `counts[kind]` items per kind of `family`; item ids run across kinds in
    kind order from `first_number`."""
    gate = asyncio.Semaphore(concurrency)
    drafted: list[tuple[Mapping[str, object], DraftReference]] = []
    failures: list[DraftFailure] = []
    for kind in family.quotas:
        need = counts.get(kind, 0)
        queue = list(candidates.get(kind, ()))
        done: list[tuple[Mapping[str, object], DraftReference]] = []
        while len(done) < need and queue:
            wave, queue = queue[: need - len(done)], queue[need - len(done) :]
            results = await asyncio.gather(
                *(_draft_one(llm, row, corpus, gate, family) for row in wave)
            )
            for row, (draft, problems) in zip(wave, results, strict=True):
                if draft is None:
                    failures.append(
                        DraftFailure(
                            query_id=str(row["query_id"]), kind=kind, problems=problems
                        )
                    )
                else:
                    done.append((row, draft))
        drafted += done
    items = [
        to_item(row, draft, f"{family.id_prefix}{number:04d}", family)
        for number, (row, draft) in enumerate(drafted, start=first_number)
    ]
    return items, failures


async def _draft_one(
    llm: LlmPort,
    row: Mapping[str, object],
    corpus: CorpusText,
    gate: asyncio.Semaphore,
    family: Family,
) -> tuple[DraftReference | None, list[str]]:
    problems: list[str] = []
    for _attempt in range(2):
        try:
            async with gate:
                draft, _usage = await llm.structured(
                    LlmRole.ANSWER,
                    draft_messages(row, corpus, problems),
                    DraftReference,
                )
        except LlmError as exc:
            return None, [f"{type(exc).__name__}: {exc}"]
        problems = draft_problems(
            to_item(row, draft, f"{family.id_prefix}draft", family),
            corpus,
            _subjects(row),
        )
        if not problems:
            return draft, []
    return None, problems


def _gold(row: Mapping[str, object]) -> list[str]:
    sections = row["expected_section_ids"]
    if not isinstance(sections, list):
        raise TypeError(f"{row['query_id']}: expected_section_ids is not a list")
    return [str(section) for section in sections]


def _subjects(row: Mapping[str, object]) -> list[str]:
    subjects = row.get("subjects", [])
    if not isinstance(subjects, list):
        raise TypeError(f"{row['query_id']}: subjects is not a list")
    return [str(subject) for subject in subjects]
