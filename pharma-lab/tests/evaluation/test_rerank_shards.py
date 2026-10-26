from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from tests.integrations.kaggle.factories import cloud_artifact, stage_job
from tests.integrations.kaggle.test_scheduler import contexts

from pharma_lab.artifacts.manifest import Completion
from pharma_lab.evaluation.rerank_cache_checkpoint import RerankCacheCheckpoint
from pharma_lab.evaluation.rerank_score_cache import RerankScoreCache
from pharma_lab.evaluation.rerank_shards import RerankShardAdapter
from pharma_lab.evaluation.retrieval_candidate_artifact import (
    CandidateArtifactReader,
    build_candidate_artifact,
)
from pharma_lab.evaluation.retrieval_types import RetrievalCandidate
from pharma_lab.integrations.kaggle.job_registry import ShardRecord
from pharma_lab.integrations.kaggle.models import PipelineResult, StageName
from pharma_lab.integrations.kaggle.quota import AccountQuota
from pharma_lab.integrations.kaggle.sessions import ReservedAccount
from pharma_lab.integrations.kaggle.shards import Shard, WorkUnit
from pharma_lab.runtime.catalog import require_model
from pharma_lab.runtime.runtime_profiles import RuntimeCandidate

MODEL = "qwen3-reranker:0.6b-q8_0"
QUERIES = ["q1", "q2", "q3"]


class Retriever:
    """Two candidates for the first query, one for each other query."""

    def __init__(self) -> None:
        self.count = 0

    def search(self, query: str, *, limit: int):
        del limit
        wide = query.endswith("1")
        return [
            RetrievalCandidate(
                chunk_id=f"chunk-{index}",
                score=1.0 / index,
                rank=index,
                source="test",
                payload={"chunk_id": f"chunk-{index}", "section_ids": []},
                document_text=f"document {index}",
            )
            for index in range(1, 3 if wide else 2)
        ]


def build_candidates(root: Path):
    return build_candidate_artifact(
        rows=[{"query_id": q, "query": f"question {q}"} for q in QUERIES],
        retriever=Retriever(),
        output_path=root / "candidates" / "candidates.jsonl",
        identity={"evaluation_sha256": "e" * 64},
        candidate_k=2,
    )


def score_cache(path: Path) -> RerankScoreCache:
    spec = require_model(MODEL)
    assert spec.rerank_contract is not None
    return RerankScoreCache(
        path,
        model_sha256=spec.sha256,
        request_contract_sha256=spec.rerank_contract.sha256,
    )


def score_query(
    cache: RerankScoreCache,
    artifact_path: Path,
    query_id: str,
    only: str | None = None,
) -> None:
    for row in CandidateArtifactReader.from_data_path(artifact_path):
        if row["query_id"] != query_id:
            continue
        for item in row["candidates"]:
            if only is not None and item["chunk_id"] != only:
                continue
            candidate = RetrievalCandidate(
                chunk_id=item["chunk_id"],
                score=float(item["retrieval_score"]),
                rank=int(item["retrieval_rank"]),
                source=str(item["source"]),
                payload=dict(item["payload"]),
                document_text=str(item["document_text"]),
                document_hash=str(item["document_hash"]),
            )
            cache.set(
                MODEL,
                {"query_id": row["query_id"], "query": row["query"]},
                candidate,
                0.5,
            )


class Runner:
    def __init__(self, root: Path) -> None:
        self.calls: list[dict] = []
        self.job = stage_job(root / "runner", stage=StageName.RERANK)

    def __call__(self, **kwargs) -> PipelineResult:
        self.calls.append(kwargs)
        return PipelineResult(self.job, Completion(1, 1, 0), (), None, 1)


def reserved(profile: str = "acc1") -> ReservedAccount:
    quota = AccountQuota(profile, f"user-{profile}", 20.0, 30.0, None)
    return ReservedAccount(contexts(profile)[0], quota, 7200)


def selected_level() -> RuntimeCandidate:
    search_space = require_model(MODEL).rerank_search_space
    assert search_space is not None
    return search_space.candidates[0]


def make(tmp_path: Path, runner: Runner | None = None, **kwargs):
    artifact = build_candidates(tmp_path / "run")
    merged: list[Path] = []
    cache_path = tmp_path / "scores.jsonl"
    adapter = RerankShardAdapter(
        model=MODEL,
        candidates=artifact.data_path,
        cache_path=cache_path,
        work_dir=tmp_path / "work",
        remote_dir=tmp_path / "remote",
        stage_runner=runner or Runner(tmp_path),
        runtime_profile=selected_level(),
        seconds_per_pair=2.0,
        merge_scores=merged.append,
        force=kwargs.get("force", False),
    )
    return adapter, artifact, cache_path, merged


def test_missing_queries_come_from_the_score_cache(tmp_path: Path) -> None:
    adapter, artifact, cache_path, _ = make(tmp_path)

    first = {unit.key: unit for unit in adapter.missing()}
    assert list(first) == QUERIES
    assert [first[q].seconds for q in QUERIES] == [4.0, 2.0, 2.0]  # pairs x 2 s

    cache = score_cache(cache_path)
    score_query(cache, artifact.data_path, "q2")
    again = {unit.key for unit in adapter.missing()}
    assert again == {"q1", "q3"}


def test_shard_input_is_a_subset_with_a_consistent_manifest(tmp_path: Path) -> None:
    runner = Runner(tmp_path)
    adapter, _, _, _ = make(tmp_path, runner)
    shard = Shard("abc", (WorkUnit("q3", 2.0), WorkUnit("q1", 4.0)), "")

    adapter.run_shard(shard, reserved("acc2"))

    call = runner.calls[0]
    subset = Path(call["input_path"])
    assert subset.parent.name == "shard-abc"
    rows = list(
        CandidateArtifactReader.from_data_path(subset)
    )  # validates the manifest
    assert [row["query_id"] for row in rows] == [
        "q1",
        "q3",
    ]  # file order, not shard order
    manifest = json.loads(subset.with_name("manifest.json").read_text())
    assert manifest["record_count"] == 2
    assert manifest["identity"]["pair_count"] == 3
    assert call["stage"] is StageName.RERANK
    assert call["model"] == MODEL
    assert call["kaggle_account"] == "acc2"
    assert call["budget_seconds"] == 7200
    assert call["max_runs"] == 1
    assert (call["force"], call["resume_remote"]) == (False, True)
    assert isinstance(call["local_checkpoint"], RerankCacheCheckpoint)


def test_shard_input_holds_only_the_pairs_the_cache_lacks(tmp_path: Path) -> None:
    # A query with one missing pair must not send all its candidates: the kernel scores
    # every pair it receives, so a whole query per missing pair multiplies the GPU time.
    runner = Runner(tmp_path)
    adapter, artifact, cache_path, _ = make(tmp_path, runner)
    score_query(score_cache(cache_path), artifact.data_path, "q1", only="chunk-1")
    shard = Shard("abc", (WorkUnit("q1", 2.0), WorkUnit("q3", 2.0)), "")

    adapter.run_shard(shard, reserved("acc2"))

    subset = Path(runner.calls[0]["input_path"])
    rows = list(CandidateArtifactReader.from_data_path(subset))
    assert [
        (r["query_id"], [c["chunk_id"] for c in r["candidates"]]) for r in rows
    ] == [
        ("q1", ["chunk-2"]),
        ("q3", ["chunk-1"]),
    ]
    manifest = json.loads(subset.with_name("manifest.json").read_text())
    assert manifest["identity"]["pair_count"] == 2


def test_subset_files_are_deterministic_so_a_relaunch_attaches(tmp_path: Path) -> None:
    runner = Runner(tmp_path)
    adapter, _, _, _ = make(tmp_path, runner)
    shard = Shard("abc", (WorkUnit("q1", 4.0), WorkUnit("q3", 2.0)), "")

    adapter.run_shard(shard, reserved())
    first = {
        name: (Path(runner.calls[0]["input_path"]).parent / name).read_bytes()
        for name in ("candidates.jsonl", "manifest.json")
    }
    adapter.run_shard(shard, reserved())
    second = {
        name: (Path(runner.calls[1]["input_path"]).parent / name).read_bytes()
        for name in ("candidates.jsonl", "manifest.json")
    }

    assert first == second


def test_checkpoint_source_counts_only_the_shard_pairs(tmp_path: Path) -> None:
    runner = Runner(tmp_path)
    adapter, artifact, cache_path, _ = make(tmp_path, runner)
    shard = Shard("abc", (WorkUnit("q2", 2.0), WorkUnit("q3", 2.0)), "")
    adapter.run_shard(shard, reserved())
    subset = Path(runner.calls[0]["input_path"])
    # The kernel's scores arrive in the cache, along with pairs of other queries.
    cache = score_cache(cache_path)
    for query in QUERIES:
        score_query(cache, artifact.data_path, query)
    job = stage_job(subset.parent, stage=StageName.RERANK, model=MODEL)
    job = replace(job, input_bundle=_bundle(subset), expected_total=2)

    state = runner.calls[0]["local_checkpoint"].inspect(
        job, download_root=tmp_path / "ckpt"
    )

    assert state.completion.complete == 2  # not the 4 pairs the whole cache holds


def _bundle(subset: Path):
    from pharma_lab.integrations.kaggle.models import InputBundle, InputFile

    return InputBundle.create(
        (
            InputFile.create("candidates", subset),
            InputFile.create("candidate_manifest", subset.with_name("manifest.json")),
        )
    )


def test_merge_is_idempotent_and_reports_the_units_it_completed(
    tmp_path: Path,
) -> None:
    adapter, artifact, cache_path, merged = make(tmp_path)
    cache = score_cache(cache_path)
    shard = Shard("abc", (WorkUnit("q1", 4.0), WorkUnit("q2", 2.0)), "")
    score_query(cache, artifact.data_path, "q1")
    result = PipelineResult(stage_job(tmp_path / "j"), Completion(2, 1, 1), (), None, 1)

    first = adapter.merge(shard, result)
    second = adapter.merge(shard, result)

    assert first == second == 1  # q1 is scored locally, q2 is not
    assert merged == []  # nothing to merge without a finished artifact


def test_a_finished_artifact_is_merged_through_the_service_callback(
    tmp_path: Path,
) -> None:
    adapter, _, _, merged = make(tmp_path)
    shard = Shard("abc", (WorkUnit("q1", 4.0),), "")
    data = tmp_path / "remote" / "job" / "rerank_scores.jsonl"
    data.parent.mkdir(parents=True)
    data.write_text("", encoding="utf-8")
    result = PipelineResult(stage_job(tmp_path / "j"), Completion(1, 1, 0), (), data, 1)

    adapter.merge(shard, result)

    assert merged == [data]


def test_the_sink_merges_partial_artifacts_as_they_arrive(tmp_path: Path) -> None:
    sunk: list[Path] = []

    class Sinking(Runner):
        def __call__(self, **kwargs) -> PipelineResult:
            artifact = cloud_artifact(Completion(2, 1, 1), root=tmp_path / "partial")
            kwargs["artifact_sink"](self.job, artifact)
            sunk.append(artifact.data_path)
            return super().__call__(**kwargs)

    adapter, _, _, merged = make(tmp_path, Sinking(tmp_path))
    adapter.run_shard(Shard("abc", (WorkUnit("q1", 4.0),), ""), reserved())

    assert merged == sunk


def test_a_recorded_kernel_makes_the_shard_attach_even_when_forced(
    tmp_path: Path,
) -> None:
    runner = Runner(tmp_path)
    adapter, _, _, _ = make(tmp_path, runner, force=True)
    shard = Shard("abc", (WorkUnit("q1", 4.0),), "")
    record = ShardRecord(
        "abc", "rerank", "acc2", ("q1",), "2026-10-23T00:00:00+00:00", 60
    )

    adapter.run_shard(shard, reserved())
    assert adapter.preferred_profile(shard, record) == "acc2"
    adapter.run_shard(shard, reserved())

    assert [c["resume_remote"] for c in runner.calls] == [False, True]


def test_cost_estimate_uses_the_profile_measurements() -> None:
    from pharma_lab.evaluation.rerank_shards import seconds_per_pair

    selected = {"concurrency": 4, "server_slots": 4}
    measurements = (
        {
            "candidate": {"concurrency": 1, "server_slots": 1},
            "status": "ok",
            "items": 100,
            "elapsed_seconds": 500.0,
        },
        {"candidate": selected, "status": "ok", "items": 640, "elapsed_seconds": 320.0},
    )

    assert seconds_per_pair(selected, measurements) == pytest.approx(0.5)
    assert seconds_per_pair(selected, ()) == pytest.approx(1.0)


def test_a_merged_complete_artifact_directory_is_removed(tmp_path: Path) -> None:
    adapter, _, _, merged = make(tmp_path)
    shard = Shard("abc", (WorkUnit("q1", 4.0),), "")
    job_dir = tmp_path / "remote" / "rerank" / "model" / "abc123"
    job_dir.mkdir(parents=True)
    data = job_dir / "rerank_scores.jsonl"
    data.write_text("", encoding="utf-8")
    sibling = tmp_path / "remote" / "rerank" / "model" / "other"
    sibling.mkdir()
    result = PipelineResult(stage_job(tmp_path / "j"), Completion(1, 1, 0), (), data, 1)

    adapter.merge(shard, result)

    assert merged == [data]
    assert not job_dir.exists()
    assert sibling.exists()


def test_an_artifact_outside_the_staging_root_is_refused(tmp_path: Path) -> None:
    adapter, _, _, _ = make(tmp_path)
    shard = Shard("abc", (WorkUnit("q1", 4.0),), "")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    data = outside / "rerank_scores.jsonl"
    data.write_text("", encoding="utf-8")
    result = PipelineResult(stage_job(tmp_path / "j"), Completion(1, 1, 0), (), data, 1)

    with pytest.raises(ValueError, match="outside"):
        adapter.merge(shard, result)
    assert outside.exists()
