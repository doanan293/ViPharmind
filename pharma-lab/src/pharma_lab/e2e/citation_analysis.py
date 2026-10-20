"""Where citation recall is lost: sentences without a citation, with a citation to a passage
the prompt never held, or with a citation the cited passages do not support.

The judge stores one supported share per answer, not a verdict per sentence, so unsupported
cited sentences are counted from that share, as the ALCE recall of the report does.
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pharma_lab.e2e.judging.code_metrics import (
    alce_citation_recall,
    cited_sentences,
    content_sentences,
    context_blocks,
)
from pharma_lab.e2e.records import (
    ANSWERS_FILE,
    JUDGMENTS_FILE,
    AnswerRecord,
    JsonlStore,
    Judgement,
)

REPORT_FILE = "citations.json"
# Markdown emphasis and list markers around a sentence, ignored when reading its end.
_MARKUP = re.compile(r"[*_#>`]")


@dataclass(frozen=True)
class CitationBreakdown:
    """Content sentences of one answer, by what happened to their citation."""

    total: int
    uncited: int
    # Uncited sentences that end in a colon: headings, item labels and lead-ins
    # such as "as follows:", which state no fact of their own.
    uncited_lead_in: int
    dangling: int
    unsupported: int
    supported: int


def breakdown(
    answer_text: str, context_text: str, supported_share: float | None
) -> CitationBreakdown | None:
    """The ALCE citation-recall numerator split in its parts; None without content."""
    total = len(content_sentences(answer_text))
    if not total:
        return None
    blocks = context_blocks(context_text)
    cited = cited_sentences(answer_text)
    cited_text = {sentence for sentence, _ in cited}
    uncited = [s for s in content_sentences(answer_text) if s.strip() not in cited_text]
    valid = sum(1 for _, numbers in cited if set(numbers) & set(blocks))
    supported = (
        0 if supported_share is None else min(total, round(supported_share * valid))
    )
    return CitationBreakdown(
        total=total,
        uncited=max(0, total - len(cited)),
        uncited_lead_in=sum(
            1 for sentence in uncited if _MARKUP.sub("", sentence).strip().endswith(":")
        ),
        dangling=len(cited) - valid,
        unsupported=valid - supported,
        supported=supported,
    )


def _graded(
    answers: Mapping[str, AnswerRecord], judgments: Mapping[str, Judgement]
) -> dict[str, tuple[AnswerRecord, Judgement]]:
    """The items that count toward citation recall in the e2e report."""
    return {
        item_id: (answers[item_id], judgement)
        for item_id, judgement in judgments.items()
        if item_id in answers
        and judgement.error is None
        and answers[item_id].answer_mode == "grounded"
        and judgement.key_fact_recall is not None
    }


def write_citation_report(config_dir: Path, reports_dir: Path) -> dict[str, Any]:
    """Write citations.json: where the content sentences of the graded answers lose support."""
    answers = JsonlStore(config_dir / ANSWERS_FILE, AnswerRecord).latest()
    judgments = JsonlStore(config_dir / JUDGMENTS_FILE, Judgement).latest()
    graded = _graded(answers, judgments)
    totals: Counter[str] = Counter()
    recalls: list[float] = []
    for record, judgement in graded.values():
        result = breakdown(
            record.answer_text, record.context_text, judgement.citation_support
        )
        if result is None:
            continue
        totals.update(asdict(result))
        recalls.append(
            alce_citation_recall(
                record.answer_text, record.context_text, judgement.citation_support
            )
            or 0.0
        )
    sentences = totals["total"]
    report: dict[str, Any] = {
        "config": config_dir.name,
        "items": len(recalls),
        "sentences": sentences,
        "mean_item_recall": statistics.fmean(recalls) if recalls else None,
        **{
            name: {
                "sentences": totals[name],
                "share": totals[name] / sentences if sentences else None,
            }
            for name in (
                "uncited",
                "uncited_lead_in",
                "dangling",
                "unsupported",
                "supported",
            )
        },
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / REPORT_FILE).write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report
