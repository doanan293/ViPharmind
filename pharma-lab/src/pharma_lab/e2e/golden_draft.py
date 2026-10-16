"""LLM drafts of the golden set's multi-hop items (spec v2 §3.0b), for human review.

Candidates come from `golden hard-candidates`: benchmark questions that one retrieval
round answers only in part. A draft is the reference answer and key facts with verbatim
quotes from every gold section; it is checked with the golden rules, sent back once with
its problems, and replaced by the next candidate of its kind when it still fails. Drafts
are written as *.draft.jsonl: the author and the pharmacist review them before they
become *.authored.jsonl.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Mapping, Sequence
from pathlib import Path

from pharma_agent.domain.llm.models import ChatMessage, LlmRole, system, user
from pharma_agent.domain.llm.port import LlmError, LlmPort
from pydantic import BaseModel, Field

from pharma_lab.e2e.corpus_text import CorpusText
from pharma_lab.e2e.golden import (
    ID_PREFIX,
    MULTI_HOP_KINDS,
    QUOTAS,
    Category,
    ExpectedBehavior,
    GoldenItem,
    KeyFact,
    Reference,
    Turn,
    validate_items,
)

PER_KIND_MAX = 45
# The model the plan names for drafts (phase D Task 7b), on the backend LLM endpoint.
DRAFT_MODEL = "gemini-3.1-flash-lite"

DRAFT_SYSTEM = """Bạn soạn đáp án mẫu cho bộ đánh giá hệ thống tra cứu thuốc tiếng Việt.
Cho một câu hỏi và các mục tài liệu (mỗi mục có id), hãy trả về:
- answer: câu trả lời mẫu tiếng Việt, 1 đến 4 câu, trả lời thẳng vào câu hỏi, chỉ dùng thông tin trong các mục, không thêm câu khuyên hỏi ý kiến bác sĩ.
- key_facts: 2 đến 6 ý nguyên tử mà câu trả lời đúng phải nêu, chỉ gồm những ý trả lời đúng điều được hỏi. Mỗi mục tài liệu phải có ít nhất một key fact.
Mỗi key fact có:
- fact: ý đó, viết ngắn.
- evidence_quote: chép nguyên văn một đoạn 5 đến 30 từ của đúng mục đó, giữ nguyên dấu và ký hiệu markdown. Chọn đoạn văn thường, tránh ranh giới ô bảng.
- section_id: id của mục chứa quote, đúng như được cho."""


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


def allocate(available: Mapping[str, int], total: int, cap: int) -> dict[str, int]:
    """Spread `total` over the kinds as evenly as `available` and `cap` allow; the
    earlier kinds get the remainder."""
    counts = dict.fromkeys(available, 0)
    remaining = total
    while remaining > 0:
        open_kinds = [k for k in available if counts[k] < min(cap, available[k])]
        if not open_kinds:
            break
        share, extra = divmod(remaining, len(open_kinds))
        for index, kind in enumerate(open_kinds):
            want = share + (1 if index < extra else 0)
            take = min(want, min(cap, available[kind]) - counts[kind])
            counts[kind] += take
            remaining -= take
    return counts


def select_candidates(
    candidates: Sequence[Mapping[str, object]], *, exclude: set[str], seed: int
) -> dict[str, list[Mapping[str, object]]]:
    """Candidates by kind in a seeded order, without questions the set already uses."""
    by_kind: dict[str, list[Mapping[str, object]]] = {
        kind: [] for kind in MULTI_HOP_KINDS
    }
    for row in candidates:
        if str(row["query_id"]) not in exclude:
            by_kind[str(row["kind"])].append(row)
    rng = random.Random(seed)
    for rows in by_kind.values():
        rows.sort(key=lambda row: str(row["query_id"]))
        rng.shuffle(rows)
    return by_kind


def used_query_ids(authoring_dir: Path) -> set[str]:
    """Benchmark questions the authored batches already use."""
    used: set[str] = set()
    for path in sorted(Path(authoring_dir).glob("*.authored.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and (query_id := json.loads(line).get("source_query_id")):
                used.add(str(query_id))
    return used


def write_drafts(
    authoring_dir: Path,
    items: Sequence[GoldenItem],
    failures: Sequence[DraftFailure],
    *,
    batch_size: int = 25,
) -> list[Path]:
    """multi-hop-NN.draft.jsonl batches for review, and multi-hop.failed.jsonl."""
    directory = Path(authoring_dir)
    paths: list[Path] = []
    for start in range(0, len(items), batch_size):
        path = directory / f"multi-hop-{start // batch_size + 1:02d}.draft.jsonl"
        path.write_text(
            "".join(
                item.model_dump_json(exclude_none=True) + "\n"
                for item in items[start : start + batch_size]
            ),
            encoding="utf-8",
        )
        paths.append(path)
    failed = directory / "multi-hop.failed.jsonl"
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
    if problems:
        prompt += "\n\nBản trước có các lỗi sau, hãy sửa:\n" + "\n".join(
            f"- {problem}" for problem in problems
        )
    return [system(DRAFT_SYSTEM), user(prompt)]


def to_item(
    row: Mapping[str, object], draft: DraftReference, item_id: str
) -> GoldenItem:
    return GoldenItem(
        item_id=item_id,
        category=Category.MULTI_HOP,
        source_query_id=str(row["query_id"]),
        turns=[Turn(role="user", text=str(row["query"]))],
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


def draft_problems(item: GoldenItem, corpus: CorpusText) -> list[str]:
    """The golden rules, plus a quote from every gold section (a multi-hop item must
    need every section, including the ones the first round missed)."""
    problems = validate_items([item], corpus, complete=False)
    quoted = {fact.section_id for fact in item.reference.key_facts}
    problems += [
        f"{item.item_id}: section {section_id} has no key fact"
        for section_id in item.gold_section_ids
        if section_id not in quoted
    ]
    return problems


async def draft_multi_hop(
    llm: LlmPort,
    candidates: Mapping[str, Sequence[Mapping[str, object]]],
    counts: Mapping[str, int],
    corpus: CorpusText,
    *,
    concurrency: int = 8,
) -> tuple[list[GoldenItem], list[DraftFailure]]:
    """Drafts `counts[kind]` items per kind; item ids run across kinds in kind order."""
    gate = asyncio.Semaphore(concurrency)
    drafted: list[tuple[Mapping[str, object], DraftReference]] = []
    failures: list[DraftFailure] = []
    for kind in MULTI_HOP_KINDS:
        need = counts.get(kind, 0)
        queue = list(candidates.get(kind, ()))
        done: list[tuple[Mapping[str, object], DraftReference]] = []
        while len(done) < need and queue:
            wave, queue = queue[: need - len(done)], queue[need - len(done) :]
            results = await asyncio.gather(
                *(_draft_one(llm, row, corpus, gate) for row in wave)
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
    prefix = ID_PREFIX[Category.MULTI_HOP]
    items = [
        to_item(row, draft, f"{prefix}{number:04d}")
        for number, (row, draft) in enumerate(drafted, start=1)
    ]
    return items, failures


async def _draft_one(
    llm: LlmPort,
    row: Mapping[str, object],
    corpus: CorpusText,
    gate: asyncio.Semaphore,
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
        problems = draft_problems(to_item(row, draft, _CHECK_ID), corpus)
        if not problems:
            return draft, []
    return None, problems


_CHECK_ID = f"{ID_PREFIX[Category.MULTI_HOP]}draft"
TOTAL = QUOTAS[Category.MULTI_HOP]


def _gold(row: Mapping[str, object]) -> list[str]:
    sections = row["expected_section_ids"]
    if not isinstance(sections, list):
        raise TypeError(f"{row['query_id']}: expected_section_ids is not a list")
    return [str(section) for section in sections]
