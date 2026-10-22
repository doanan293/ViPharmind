from pathlib import Path

from pharma_lab.e2e.citation_analysis import (
    CitationBreakdown,
    breakdown,
    write_citation_report,
)
from pharma_lab.e2e.judging.code_metrics import alce_citation_recall
from pharma_lab.e2e.records import (
    ANSWERS_FILE,
    JUDGMENTS_FILE,
    AnswerRecord,
    JsonlStore,
    Judgement,
)

CONTEXT = (
    "[1] Paracetamol > Liều dùng\nNgười lớn uống 500 mg.\n\n"
    "[2] Paracetamol > Chống chỉ định\nSuy gan nặng."
)
ANSWER = "\n".join(
    [
        "Người lớn uống 500 mg mỗi lần [1].",
        "Tối đa bốn lần mỗi ngày theo hướng dẫn [1].",
        "Không dùng khi suy gan nặng [9].",
        "Hỏi dược sĩ nếu còn thắc mắc nhiều.",
    ]
)


def answer(item_id: str, text: str) -> AnswerRecord:
    return AnswerRecord(
        item_id=item_id,
        config="full",
        status="completed",
        answer_mode="grounded",
        answer_text=text,
        context_text=CONTEXT,
    )


def judged(item_id: str, support: float | None) -> Judgement:
    return Judgement(
        item_id=item_id, config="full", category="answerable", citation_support=support
    )


def test_breakdown_matches_alce_recall() -> None:
    result = breakdown(ANSWER, CONTEXT, 0.5)

    assert result == CitationBreakdown(
        total=4,
        uncited=1,
        uncited_lead_in=0,
        dangling=1,
        unsupported=1,
        supported=1,
    )
    assert result is not None
    assert result.supported / result.total == alce_citation_recall(ANSWER, CONTEXT, 0.5)


def test_breakdown_without_a_judged_share_counts_no_sentence_as_supported() -> None:
    result = breakdown(ANSWER, CONTEXT, None)

    assert result == CitationBreakdown(
        total=4,
        uncited=1,
        uncited_lead_in=0,
        dangling=1,
        unsupported=2,
        supported=0,
    )


def test_breakdown_counts_uncited_lead_ins_and_labels() -> None:
    text = "\n".join(
        [
            "Liều dùng của thuốc theo tờ hướng dẫn như sau:",
            "* **Người lớn và trẻ em trên 12 tuổi:**",
            "Người lớn uống 500 mg mỗi lần [1].",
            "Hỏi dược sĩ nếu còn thắc mắc nhiều.",
        ]
    )

    result = breakdown(text, CONTEXT, 1.0)

    assert result is not None
    assert result.uncited == 3
    assert result.uncited_lead_in == 2


def test_breakdown_is_none_without_content_sentences() -> None:
    assert breakdown("## Tiêu đề\n---", CONTEXT, 1.0) is None


def test_report_counts_only_graded_grounded_items(tmp_path: Path) -> None:
    config_dir = tmp_path / "full"
    config_dir.mkdir()
    answers = JsonlStore(config_dir / ANSWERS_FILE, AnswerRecord)
    judgments = JsonlStore(config_dir / JUDGMENTS_FILE, Judgement)
    graded = judged("graded", 0.5).model_copy(update={"key_fact_recall": 1.0})
    ungraded = judged("ungraded", 0.5)  # no key facts: not in the e2e recall mean
    for item_id in ("graded", "ungraded"):
        answers.append(answer(item_id, ANSWER))
    judgments.append(graded)
    judgments.append(ungraded)

    report = write_citation_report(config_dir, tmp_path / "reports")

    assert report["items"] == 1
    assert report["sentences"] == 4
    assert report["uncited"]["sentences"] == 1
    assert report["dangling"]["sentences"] == 1
    assert report["unsupported"]["sentences"] == 1
    assert report["supported"]["share"] == 0.25
    assert report["mean_item_recall"] == alce_citation_recall(ANSWER, CONTEXT, 0.5)
    assert (tmp_path / "reports" / "citations.json").is_file()
