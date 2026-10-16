import json
from pathlib import Path

import pytest
from tests.e2e.report_fixtures import (
    answer,
    golden,
    judgement,
    rows,
    write_config,
    write_identity,
)

from pharma_lab.e2e.compare import compare_runs
from pharma_lab.e2e.records import AnswerRecord, JsonlStore, Judgement

ITEMS = {golden(n).item_id: golden(n) for n in range(4)}


def judged(
    root: Path, recalls: list[float], judge: str = "gemini-3.1-flash-lite"
) -> Path:
    write_config(root, "full", recalls)
    (root / "full" / "judge.json").write_text(
        json.dumps({"model": judge, "reasoning_effort": "none"}), encoding="utf-8"
    )
    return root


def test_compare_pairs_shared_items_and_marks_judges(tmp_path: Path) -> None:
    a = judged(tmp_path / "a", [1.0, 1.0, 0.0, 1.0])
    b = judged(tmp_path / "b", [0.0, 1.0, 0.0, 0.0])

    result = compare_runs(a, b, "full", ITEMS, None)

    recall = next(r for r in result if r.metric == "nugget_recall")
    assert recall.n == 4
    assert recall.delta == pytest.approx(-0.5)
    assert recall.same_judge is True
    table = {r["metric"]: r for r in rows(b / "reports" / "compare-a-full.csv")}
    assert float(table["nugget_recall"]["delta"]) == pytest.approx(-0.5)
    assert (b / "reports" / "compare-a-full.tex").is_file()


def test_compare_flags_different_judges(tmp_path: Path) -> None:
    a = judged(tmp_path / "a", [1.0, 1.0, 0.0, 1.0])
    b = judged(tmp_path / "b", [1.0, 1.0, 0.0, 1.0], judge="gpt-5-mini")

    result = compare_runs(a, b, "full", ITEMS, None)

    assert all(r.same_judge is False for r in result)


def test_compare_refuses_disjoint_runs(tmp_path: Path) -> None:
    a = judged(tmp_path / "a", [1.0, 1.0])
    b = tmp_path / "b"
    write_identity(b, "full")
    for n in (2, 3):
        JsonlStore(b / "full" / "answers.jsonl", AnswerRecord).append(answer(n, "full"))
        JsonlStore(b / "full" / "judgments.jsonl", Judgement).append(
            judgement(n, "full", 1.0)
        )

    with pytest.raises(ValueError, match="no item in common"):
        compare_runs(a, b, "full", ITEMS, None)
