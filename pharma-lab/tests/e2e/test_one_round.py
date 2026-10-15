import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from pharma_lab.cli.app import app
from pharma_lab.cli.commands import e2e as e2e_commands
from pharma_lab.e2e.golden import GoldenItem
from pharma_lab.e2e.one_round import (
    OneRoundCoverage,
    OneRoundRun,
    coverage,
    multi_hop_kind,
    trim_covered,
)


def row(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "query_id": "q1",
        "query": "Liều paracetamol?",
        "eval_group": "formulary",
        "answer_mode": "single",
        "retrieval_granularity": "section",
        "expected_section_id": "drug:paracetamol:lieu-dung",
        "expected_section_ids": ["drug:paracetamol:lieu-dung"],
    }
    data.update(changes)
    return data


def payload(section: str, index: int = 1) -> dict[str, Any]:
    return {"chunk_id": f"{section}:chunk-{index:03d}", "section_id": section}


def test_single_answer_is_covered_when_a_gold_chunk_is_in_the_top_k() -> None:
    ranked = [payload("drug:a:x")] * 2 + [payload("drug:paracetamol:lieu-dung")]
    assert coverage(ranked, row(), {}, top_k=3).missing == ()
    assert coverage(ranked, row(), {}, top_k=2).missing == ("answer",)


def test_multi_required_lists_each_missing_section() -> None:
    sections = ["drug:a:chi-dinh", "drug:a:lieu-dung", "drug:a:tac-dung-phu"]
    query = row(
        answer_mode="multi_required",
        expected_section_id=sections[0],
        expected_section_ids=sections,
    )
    result = coverage([payload(sections[0]), payload(sections[2])], query, {}, top_k=8)
    assert result == OneRoundCoverage("q1", tuple(sections), (sections[1],))


def test_judged_chunks_outside_gold_count_as_found() -> None:
    accepted = {"drug:paracetamol:lieu-dung": frozenset({"drug:b:x:chunk-001"})}
    ranked = [payload("drug:b:x")]
    assert coverage(ranked, row(), accepted, top_k=8).missing == ()


@pytest.mark.parametrize(
    ("changes", "judged", "kind"),
    [
        (
            {
                "answer_mode": "multi_required",
                "expected_section_ids": ["drug:a:tuong-tac", "drug:b:tuong-tac"],
            },
            {},
            "two_drug",
        ),
        (
            {
                "answer_mode": "multi_required",
                "expected_section_ids": ["drug:a:chi-dinh", "drug:a:lieu-dung"],
            },
            {},
            "three_intent",
        ),
        ({"eval_group": "noisy"}, {}, "noisy_retry"),
        (
            {
                "eval_group": "leaflet",
                "expected_section_id": "leaflet:t:brand:05-luu-y",
                "expected_section_ids": ["leaflet:t:brand:05-luu-y"],
            },
            {"leaflet:t:brand:05-luu-y": frozenset({"drug:a:than-trong:chunk-001"})},
            "brand_to_ingredient",
        ),
        ({}, {}, None),
    ],
)
def test_missed_rows_get_a_multi_hop_kind(
    changes: dict[str, Any], judged: dict[str, frozenset[str]], kind: str | None
) -> None:
    query = row(**changes)
    missed = OneRoundCoverage("q1", ("answer",), ("answer",))
    assert multi_hop_kind(query, missed, judged) == kind
    covered = OneRoundCoverage("q1", ("answer",), ())
    assert multi_hop_kind(query, covered, judged) is None


def item(item_id: str, group: str, source: str) -> GoldenItem:
    return GoldenItem.model_validate(
        {
            "item_id": item_id,
            "category": "answerable",
            "source_query_id": source,
            "turns": [{"role": "user", "text": "Câu hỏi?"}],
            "expected_behavior": "grounded",
            "gold_section_ids": ["drug:a:x"],
            "reference": {
                "key_facts": [
                    {"fact": "f", "evidence_quote": "q", "section_id": "drug:a:x"}
                ]
            },
            "eval_group": group,
        }
    )


def test_trim_drops_covered_items_evenly_per_group() -> None:
    items = [item(f"e2e-ans-{g}{i}", g, f"{g}{i}") for g in "ab" for i in range(4)]
    covered = {
        f"{g}{i}": OneRoundCoverage(f"{g}{i}", ("answer",), ())
        for g in "ab"
        for i in range(4)
    }
    covered["a0"] = OneRoundCoverage("a0", ("answer",), ("answer",))
    dropped = trim_covered(items, covered, keep_per_group=2)
    assert dropped == ["e2e-ans-a1", "e2e-ans-a2", "e2e-ans-b0", "e2e-ans-b1"]


def test_trim_fails_when_a_group_has_too_few_covered_items() -> None:
    items = [item(f"e2e-ans-a{i}", "a", f"a{i}") for i in range(3)]
    missed = {
        f"a{i}": OneRoundCoverage(f"a{i}", ("answer",), ("answer",)) for i in range(3)
    }
    with pytest.raises(ValueError, match="a: 0 covered items, need 1"):
        trim_covered(items, missed, keep_per_group=2)


def _fake_run(coverage_by_query: dict[str, OneRoundCoverage], rows: dict[str, dict]):
    return OneRoundRun(rows, {key: {} for key in rows}, coverage_by_query)


def test_cli_trim_rewrites_authored_batches(tmp_path: Path, monkeypatch) -> None:
    items = [item(f"e2e-ans-a{i}", "a", f"a{i}") for i in range(3)]
    batch = tmp_path / "answerable-01.authored.jsonl"
    batch.write_text(
        "".join(
            json.dumps(i.model_dump(mode="json"), ensure_ascii=False) + "\n"
            for i in items
        ),
        encoding="utf-8",
    )
    covered = {f"a{i}": OneRoundCoverage(f"a{i}", ("answer",), ()) for i in range(3)}
    monkeypatch.setattr(
        e2e_commands, "load_one_round", lambda *a, **k: _fake_run(covered, {})
    )
    result = CliRunner().invoke(
        app,
        [
            "e2e",
            "golden",
            "trim",
            "--run",
            "r",
            "--per-group",
            "2",
            "--authoring-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    kept = [
        json.loads(line)["item_id"] for line in batch.read_text("utf-8").splitlines()
    ]
    assert kept == ["e2e-ans-a1", "e2e-ans-a2"]


def test_cli_hard_candidates_writes_the_todo(tmp_path: Path, monkeypatch) -> None:
    rows = {"q1": row(eval_group="noisy"), "q2": row(query_id="q2")}
    found = {
        "q1": OneRoundCoverage("q1", ("answer",), ("answer",)),
        "q2": OneRoundCoverage("q2", ("answer",), ()),
    }
    monkeypatch.setattr(
        e2e_commands, "load_one_round", lambda *a, **k: _fake_run(found, rows)
    )
    result = CliRunner().invoke(
        app,
        [
            "e2e",
            "golden",
            "hard-candidates",
            "--run",
            "r",
            "--authoring-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    todo = [
        json.loads(line)
        for line in (tmp_path / "multi-hop.todo.jsonl").read_text("utf-8").splitlines()
    ]
    assert [(t["query_id"], t["kind"], t["missing"]) for t in todo] == [
        ("q1", "noisy_retry", ["answer"])
    ]
