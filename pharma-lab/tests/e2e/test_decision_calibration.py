import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from pharma_agent.domain.agent.decisions import judge_state
from pharma_agent.domain.corpus.bundle import read_bundle
from pharma_agent.domain.llm.models import LlmRole
from pharma_agent.domain.retrieval.evidence import Evidence
from pharma_agent.domain.retrieval.models import Hit
from pydantic import BaseModel
from tests.e2e.factories import ScriptedLlm

from pharma_lab.artifacts.bundle import load_bundle
from pharma_lab.bundle.chunks import gold_chunk_label, iter_document_chunks
from pharma_lab.bundle.export import ExportRequest, export_bundle
from pharma_lab.e2e.decision_calibration import (
    ATTACK_KINDS,
    NON_ATTACK_KINDS,
    SMALLTALK_KINDS,
    TEMPLATES,
    GuardTurn,
    _guard_plan,
    build_judge_set,
    draft_guard_set,
)
from pharma_lab.evaluation.artifact_contracts import sha256_file
from pharma_lab.evaluation.relevance_judgments import judgments_path, write_judgments
from pharma_lab.evaluation.rerank_artifacts import finalize_run_rerank_bundle
from pharma_lab.evaluation.rerank_score_cache import RerankScoreCache
from pharma_lab.evaluation.retrieval_candidate_artifact import (
    CandidateArtifactReader,
    build_candidate_artifact,
)
from pharma_lab.evaluation.retrieval_types import RetrievalCandidate
from pharma_lab.evaluation.run_workspace import RunIdentity, RunWorkspace
from pharma_lab.evaluation.variant_identity import RerankVariantIdentity
from pharma_lab.runtime.catalog import require_model

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "rag_final_small"
MODEL = "qwen3-reranker:0.6b-q8_0"
GROUPS = {"q-hit": "formulary", "q-miss": "leaflet", "q-golden": "formulary"}


class Retriever:
    """The same two chunks for every query: first the gold chunk, then a distractor."""

    def __init__(self, labels: list[str], sections: dict[str, list[str]]) -> None:
        self.labels, self.sections = labels, sections

    def search(self, query: str, *, limit: int) -> list[RetrievalCandidate]:
        del query, limit
        return [
            RetrievalCandidate(
                chunk_id=label,
                score=1.0 - rank / 10,
                rank=rank,
                source="hybrid",
                payload={
                    "chunk_id": label,
                    "document_id": label.split(":chunk-")[0],
                    "section_ids": self.sections[label],
                },
                document_text=f"embedding of {label}",
            )
            for rank, label in enumerate(self.labels, start=1)
        ]


@pytest.fixture
def world(tmp_path: Path) -> dict[str, Any]:
    export_bundle(
        ExportRequest(
            rag_final_dir=FIXTURE,
            glossary_path=FIXTURE / "term_glossary.json",
            mappings_path=FIXTURE / "colloquial_mappings.json",
            output_dir=tmp_path / "bundle",
        )
    )
    bundle = read_bundle(tmp_path / "bundle")
    drafts = [d for item in iter_document_chunks(bundle) for d in item.drafts][:2]
    labels = [gold_chunk_label(d.document_key, d.ordinal) for d in drafts]
    sections = {
        label: list(d.section_keys) for label, d in zip(labels, drafts, strict=True)
    }
    gold = drafts[0].section_keys[0]
    rows = [
        {
            "query_id": query_id,
            "query": f"{query_id} hỏi gì",
            "eval_group": group,
            "intent_category": "dosage",
            "answer_mode": "single",
            "expected_section_id": expected,
            "expected_section_ids": [expected],
        }
        for query_id, group, expected in (
            ("q-hit", "formulary", gold),
            ("q-miss", "leaflet", "drug:absent:lieu"),
            ("q-golden", "formulary", gold),
        )
    ]
    evaluation = tmp_path / "evaluation.jsonl"
    evaluation.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    write_judgments(
        [], evaluation_path=evaluation, output_path=judgments_path(evaluation)
    )
    identity = RunIdentity(
        evaluation_path=str(evaluation),
        evaluation_sha256=sha256_file(evaluation),
        collection_name="collection",
        embedding_model="embeddinggemma:300m-q8_0",
        query_embeddings_sha256="query-cache",
        retriever="hybrid",
        candidate_k=5,
        rrf_k=2,
        limit=None,
        prefetch_k=5,
    )
    root = tmp_path / "run-x"
    workspace = RunWorkspace.open_or_create(root, identity)
    artifact = build_candidate_artifact(
        rows=rows,
        retriever=Retriever(labels, sections),
        output_path=root / "candidates" / "candidates.jsonl",
        identity={"evaluation_sha256": identity.evaluation_sha256},
        candidate_k=5,
    )
    workspace.record_candidates(artifact)
    candidate_bundle = load_bundle(
        root / "candidates",
        expected_type="retrieval_candidates",
        require_complete=True,
    )
    spec = require_model(MODEL)
    assert spec.rerank_contract is not None
    cache = RerankScoreCache(
        tmp_path / "rerank-cache.jsonl",
        model_sha256=spec.sha256,
        request_contract_sha256=spec.rerank_contract.sha256,
    )
    for record in CandidateArtifactReader.from_data_path(candidate_bundle.data_path):
        for item in record["candidates"]:
            candidate = RetrievalCandidate(
                chunk_id=item["chunk_id"],
                score=float(item["retrieval_score"]),
                rank=int(item["retrieval_rank"]),
                source=str(item["source"]),
                payload=dict(item["payload"]),
                document_text=str(item["document_text"]),
                document_hash=str(item["document_hash"]),
            )
            # The reranker prefers the second retrieved chunk, so the order flips.
            score = 2.0 if item["chunk_id"] == labels[1] else -1.0
            cache.set(
                MODEL,
                {"query_id": record["query_id"], "query": record["query"]},
                candidate,
                score,
                protocol=spec.reranker_protocol,
            )
    finalize_run_rerank_bundle(
        workspace=workspace,
        candidate_bundle=candidate_bundle,
        cache_path=cache.path,
        identity=RerankVariantIdentity.create(
            candidate_bundle.manifest.data_sha256, MODEL
        ),
    )
    return {
        "root": root,
        "bundle": tmp_path / "bundle",
        "drafts": drafts,
        "labels": labels,
        "tmp": tmp_path,
    }


def _hit(draft: Any, bundle: Any) -> Hit:
    document = next(d for d in bundle.documents if d.key == draft.document_key)
    return Hit(
        chunk_version_id=draft.chunk_version_id,
        release_id=uuid.UUID(int=0),
        collection_id=uuid.UUID(int=0),
        document_key=draft.document_key,
        ordinal=draft.ordinal,
        section_keys=list(draft.section_keys),
        headings=list(draft.headings),
        source=document.source.title,
        title=document.title,
        start_page=draft.start_page,
        end_page=draft.end_page,
        context_header=draft.context_header,
        chunk_text=draft.chunk_text,
        embedding_text=draft.embedding_text,
    )


def _build(world: dict[str, Any], **changes: Any) -> list[dict[str, Any]]:
    arguments: dict[str, Any] = {
        "output": world["tmp"] / "judge_set.jsonl",
        "reranker": MODEL,
        "size": 2,
        "seed": 0,
        "golden_sources": {"q-golden"},
    }
    arguments.update(changes)
    path = build_judge_set(world["root"], world["bundle"], **arguments)
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def test_judge_set_excludes_golden_sources_and_labels_by_gold_coverage(
    world: dict[str, Any],
) -> None:
    rows = _build(world)
    assert {r["query_id"] for r in rows} == {"q-hit", "q-miss"}
    assert {r["query_id"]: r["sufficient"] for r in rows} == {"q-hit": 1, "q-miss": 0}
    miss = next(r for r in rows if r["query_id"] == "q-miss")
    assert miss["units_missing"] == ["answer"]


def test_judge_set_records_the_run_and_reranker_and_no_asked_intents(
    world: dict[str, Any],
) -> None:
    for row in _build(world):
        assert row["run"] == "run-x" and row["reranker"] == MODEL
        assert "asked_intents" not in row
        assert row["benchmark_intent"] == "dosage"


def test_evidence_is_what_judge_state_emits_for_the_reranked_hits(
    world: dict[str, Any],
) -> None:
    bundle = read_bundle(world["bundle"])
    first, second = world["drafts"]
    row = next(r for r in _build(world) if r["query_id"] == "q-hit")
    expected = judge_state(
        "q",
        "q",
        [],
        [
            Evidence(ref="1", hit=_hit(second, bundle)),
            Evidence(ref="2", hit=_hit(first, bundle)),
        ],
    )["evidence"]
    assert row["evidence"] == expected
    assert row["evidence"][0].keys() == {"id", "source", "text"}


def test_judge_set_fails_when_the_pool_is_smaller_than_the_size(
    world: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="only 1"):
        _build(world, golden_sources={"q-golden", "q-miss"})


def test_every_kind_has_ten_templates() -> None:
    assert len(ATTACK_KINDS) == 7 and len(NON_ATTACK_KINDS) == 5
    assert SMALLTALK_KINDS == ("chitchat",)
    for kind in (*ATTACK_KINDS, *NON_ATTACK_KINDS):
        assert len(TEMPLATES[kind]) == 10


def test_the_documented_count_of_100_fits_the_templates() -> None:
    plan = _guard_plan(100, 0)
    labels = [label for label, _, _ in plan]
    assert len(plan) == 100
    assert labels.count("attack") == 50
    assert labels.count("out_of_scope") == 40 and labels.count("smalltalk") == 10
    assert {k for label, k, _ in plan if label == "smalltalk"} == {"chitchat"}
    assert len({template for _, _, template in plan}) == 100


def test_guard_draft_writes_a_todo_with_half_attacks(tmp_path: Path) -> None:
    llm = ScriptedLlm()
    llm.script(LlmRole.JUDGE, *[GuardTurn(turn=f"lượt {i}") for i in range(20)])
    output = tmp_path / "guard_set.todo.jsonl"
    path = asyncio.run(draft_guard_set(llm, output, count=20, seed=0))
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    assert path.name == "guard_set.todo.jsonl" and len(rows) == 20
    assert [r["label"] for r in rows].count("attack") == 10
    assert {r["label"] for r in rows} == {"attack", "out_of_scope", "smalltalk"}
    assert {r["kind"] for r in rows if r["label"] == "smalltalk"} == {"chitchat"}
    assert {r["kind"] for r in rows if r["label"] == "attack"} <= set(ATTACK_KINDS)
    assert all(r["conversation_so_far"] == [] for r in rows)
    assert len({r["guard_id"] for r in rows}) == 20
    assert all(r["latest_user_turn"].startswith("lượt") for r in rows)


def test_guard_draft_rejects_a_count_the_templates_cannot_cover(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="templates"):
        asyncio.run(draft_guard_set(ScriptedLlm(), tmp_path / "x", count=1000))


def test_guard_turn_is_a_model() -> None:
    assert issubclass(GuardTurn, BaseModel)
