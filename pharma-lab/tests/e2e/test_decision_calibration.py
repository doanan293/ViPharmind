import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from pharma_agent.domain.llm.models import LlmRole
from pydantic import BaseModel
from tests.e2e.factories import ScriptedLlm

from pharma_lab.e2e.decision_calibration import (
    ATTACK_KINDS,
    OUT_OF_SCOPE_KINDS,
    TEMPLATES,
    GuardTurn,
    build_judge_set,
    draft_guard_set,
    load_reranked_top,
)
from pharma_lab.evaluation.relevance_judgments import LoadedJudgments
from pharma_lab.evaluation.retrieval_candidate_artifact import build_candidate_artifact
from pharma_lab.evaluation.retrieval_types import RetrievalCandidate

GROUPS = {"q-hit": "formulary", "q-miss": "leaflet", "q-golden": "formulary"}


def _row(query_id: str, section: str) -> dict[str, Any]:
    return {
        "query_id": query_id,
        "query": f"{query_id} hỏi gì",
        "eval_group": GROUPS[query_id],
        "intent_category": "dosage",
        "answer_mode": "single",
        "expected_section_id": section,
        "expected_section_ids": [section],
    }


class _Retriever:
    """Two candidates per query: the gold chunk (retrieved second) and a distractor."""

    def search(self, query: str, limit: int) -> list[RetrievalCandidate]:
        query_id = query.split(" ")[0]
        gold = RetrievalCandidate(
            chunk_id=f"{query_id}:gold",
            score=0.5,
            rank=2,
            source="hybrid",
            payload={"section_ids": [f"drug:{query_id}:lieu"]},
            document_text=f"gold text of {query_id}",
        )
        other = RetrievalCandidate(
            chunk_id=f"{query_id}:other",
            score=0.9,
            rank=1,
            source="hybrid",
            payload={"section_ids": ["drug:other:x"]},
            document_text=f"other text of {query_id}",
        )
        return [other, gold]


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    evaluation = tmp_path / "eval.jsonl"
    rows = [
        _row("q-hit", "drug:q-hit:lieu"),
        _row("q-miss", "drug:q-miss:absent"),
        _row("q-golden", "drug:q-golden:lieu"),
    ]
    evaluation.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    run = tmp_path / "run"
    build_candidate_artifact(
        rows=rows,
        retriever=_Retriever(),
        output_path=run / "candidates" / "candidates.jsonl",
        identity={},
        candidate_k=2,
    )
    scores = run / "rerank" / "slug" / "rerank_scores.jsonl"
    scores.parent.mkdir(parents=True)
    # The reranker puts the gold chunk first: its score beats the distractor's.
    lines = [
        {"reranker": "rer", "query_id": q, "chunk_id": f"{q}:{kind}", "score": s}
        for q in GROUPS
        for kind, s in (("gold", 2.0), ("other", -1.0))
    ]
    scores.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    return run, evaluation


def test_reranked_top_orders_candidates_by_rerank_score(tmp_path: Path) -> None:
    run, _ = _fixture(tmp_path)
    top = load_reranked_top(run, rerank_slug="slug", reranker="rer", top_k=1)
    assert [c["chunk_id"] for c in top["q-hit"]] == ["q-hit:gold"]


def test_reranked_top_fails_on_a_missing_score(tmp_path: Path) -> None:
    run, _ = _fixture(tmp_path)
    path = run / "rerank" / "slug" / "rerank_scores.jsonl"
    path.write_text(path.read_text("utf-8").splitlines()[0] + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="rerank score"):
        load_reranked_top(run, rerank_slug="slug", reranker="rer", top_k=1)


def test_judge_set_excludes_golden_sources_and_labels_by_gold_coverage(
    tmp_path: Path,
) -> None:
    run, evaluation = _fixture(tmp_path)
    path = build_judge_set(
        run,
        evaluation,
        LoadedJudgments("sha", {}),
        output=tmp_path / "judge_set.jsonl",
        reranker="rer",
        rerank_slug="slug",
        size=2,
        seed=0,
        golden_sources={"q-golden"},
    )
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    assert {r["query_id"] for r in rows} == {"q-hit", "q-miss"}
    assert {r["query_id"]: r["sufficient"] for r in rows} == {"q-hit": 1, "q-miss": 0}
    miss = next(r for r in rows if r["query_id"] == "q-miss")
    assert miss["units_missing"] == ["answer"]
    assert miss["asked_intents"] == ["dosage"]
    assert rows[0]["evidence"][0].keys() == {"id", "source", "text"}
    assert rows[0]["evidence"][0]["id"] == 1


def test_judge_set_fails_when_the_pool_is_smaller_than_the_size(
    tmp_path: Path,
) -> None:
    run, evaluation = _fixture(tmp_path)
    with pytest.raises(ValueError, match="only 1"):
        build_judge_set(
            run,
            evaluation,
            LoadedJudgments("sha", {}),
            output=tmp_path / "judge_set.jsonl",
            reranker="rer",
            rerank_slug="slug",
            size=2,
            golden_sources={"q-golden", "q-miss"},
        )


def test_every_kind_has_ten_templates() -> None:
    assert len(ATTACK_KINDS) == 7 and len(OUT_OF_SCOPE_KINDS) == 4
    for kind in (*ATTACK_KINDS, *OUT_OF_SCOPE_KINDS):
        assert len(TEMPLATES[kind]) == 10


def test_guard_draft_writes_a_todo_with_half_attacks(tmp_path: Path) -> None:
    llm = ScriptedLlm()
    llm.script(LlmRole.JUDGE, *[GuardTurn(turn=f"lượt {i}") for i in range(20)])
    output = tmp_path / "guard_set.todo.jsonl"
    path = asyncio.run(draft_guard_set(llm, output, count=20, seed=0))
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    assert path.name == "guard_set.todo.jsonl" and len(rows) == 20
    assert [r["label"] for r in rows].count("attack") == 10
    assert {r["label"] for r in rows} == {"attack", "out_of_scope"}
    assert {r["kind"] for r in rows if r["label"] == "attack"} <= set(ATTACK_KINDS)
    assert all(r["conversation_so_far"] == [] for r in rows)
    assert len({r["guard_id"] for r in rows}) == 20
    assert all(r["latest_user_turn"].startswith("lượt") for r in rows)
    assert isinstance(llm.calls[0][1][1].content, str)


def test_guard_draft_rejects_a_count_the_templates_cannot_cover(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="templates"):
        asyncio.run(draft_guard_set(ScriptedLlm(), tmp_path / "x", count=1000))


def test_guard_turn_is_a_model() -> None:
    assert issubclass(GuardTurn, BaseModel)
