from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from tests.integrations.kaggle.factories import cloud_artifact, stage_job
from tests.integrations.kaggle.test_scheduler import contexts

from pharma_lab.artifacts.manifest import Completion
from pharma_lab.evaluation.query_embedding_cache import QueryEmbeddingCache
from pharma_lab.evaluation.query_embedding_shards import QueryEmbeddingShardAdapter
from pharma_lab.integrations.kaggle.job_registry import ShardRecord
from pharma_lab.integrations.kaggle.models import PipelineResult, StageName
from pharma_lab.integrations.kaggle.quota import AccountQuota
from pharma_lab.integrations.kaggle.scheduler import shard_margin_seconds
from pharma_lab.integrations.kaggle.sessions import ReservedAccount
from pharma_lab.integrations.kaggle.shards import Shard, WorkUnit, plan_shards
from pharma_lab.runtime.catalog import require_model
from pharma_lab.runtime.runtime_profiles import RuntimeCandidate

MODEL = "qwen3-embedding:4b-q8_0"
SPEC = require_model(MODEL)
DIMS = SPEC.vector_dimension or 4
QUERIES = {
    "q1": "liều paracetamol",
    "q2": "tác dụng phụ ibuprofen",
    "q3": "chống chỉ định",
}


def vector(seed: float) -> list[float]:
    return [seed] * DIMS


def cache_at(path: Path) -> QueryEmbeddingCache:
    return QueryEmbeddingCache(path, vector_dim=DIMS, model_sha256=SPEC.sha256)


class Runner:
    """Stands in for `run_kaggle_stage`: embeds the shard's rows into a remote cache."""

    def __init__(self, root: Path, seed: float = 0.25) -> None:
        self.calls: list[dict] = []
        self.root = root
        self.seed = seed
        self.job = stage_job(root / "runner", stage=StageName.QUERY_EMBED)

    def __call__(self, **kwargs) -> PipelineResult:
        self.calls.append(kwargs)
        rows = [
            json.loads(line)
            for line in Path(kwargs["input_path"]).read_text().splitlines()
        ]
        remote = cache_at(self.root / f"remote-{len(self.calls)}" / "q.jsonl")
        for row in rows:
            remote.set(MODEL, row["query_id"], row["query"], vector(self.seed))
        return PipelineResult(
            self.job, Completion(len(rows), len(rows), 0), (), remote.path, 1
        )


def profile() -> RuntimeCandidate:
    space = SPEC.embedding_search_space
    assert space is not None
    return space.query.candidates[0]


def reserved(name: str = "acc1") -> ReservedAccount:
    quota = AccountQuota(name, f"user-{name}", 20.0, 30.0, None)
    return ReservedAccount(contexts(name)[0], quota, 7200)


def make(tmp_path: Path, *, cached=(), runner: Runner | None = None, force=False):
    evaluation = tmp_path / "evaluation.jsonl"
    evaluation.write_text(
        "".join(
            json.dumps({"query_id": q, "query": text}, ensure_ascii=False) + "\n"
            for q, text in QUERIES.items()
        ),
        encoding="utf-8",
    )
    cache_path = tmp_path / "cache.jsonl"
    cache = cache_at(cache_path)
    for query_id in cached:
        cache.set(MODEL, query_id, QUERIES[query_id], vector(0.5))
    runner = runner or Runner(tmp_path)
    adapter = QueryEmbeddingShardAdapter(
        model=MODEL,
        evaluation_path=evaluation,
        cache_path=cache_path,
        work_dir=tmp_path / "work",
        remote_dir=tmp_path / "remote",
        stage_runner=runner,
        runtime_profile=profile(),
        seconds_per_character=0.01,
        force=force,
    )
    return adapter, runner, cache_path


def test_cached_queries_are_never_resent(tmp_path: Path) -> None:
    adapter, runner, _ = make(tmp_path, cached=("q1",))

    assert {unit.key for unit in adapter.missing()} == {"q2", "q3"}
    shard = Shard("abc", tuple(WorkUnit(k, 1.0) for k in ("q3", "q2")), "")
    adapter.run_shard(shard, reserved("acc2"))

    call = runner.calls[0]
    sent = [
        json.loads(line)["query_id"]
        for line in Path(call["input_path"]).read_text().splitlines()
    ]
    assert sent == ["q2", "q3"]  # file order
    assert Path(call["input_path"]).name.endswith(".shard-abc.jsonl")
    assert call["stage"] is StageName.QUERY_EMBED
    assert (call["kaggle_account"], call["budget_seconds"], call["max_runs"]) == (
        "acc2",
        7200,
        1,
    )
    assert (call["force"], call["resume_remote"]) == (False, True)


def test_recomputed_vector_does_not_replace_the_cached_one(tmp_path: Path) -> None:
    adapter, _, cache_path = make(
        tmp_path, cached=("q1",), runner=Runner(tmp_path, 0.7)
    )
    stale = cache_at(tmp_path / "stale" / "q.jsonl")
    stale.set(MODEL, "q1", QUERIES["q1"], vector(0.5000001))  # last digits differ
    stale.set(MODEL, "q2", QUERIES["q2"], vector(0.25))
    shard = Shard("abc", (WorkUnit("q2", 1.0),), "")
    result = PipelineResult(
        stage_job(tmp_path / "j", stage=StageName.QUERY_EMBED),
        Completion(2, 2, 0),
        (),
        stale.path,
        1,
    )

    adapter.merge(shard, result)

    merged = cache_at(cache_path)
    assert merged.get(MODEL, "q1", QUERIES["q1"]) == vector(0.5)  # the cached one stays
    assert merged.get(MODEL, "q2", QUERIES["q2"]) == vector(0.25)


def test_shards_partition_the_missing_queries(tmp_path: Path) -> None:
    adapter, _, _ = make(tmp_path, cached=("q1",))
    units = adapter.missing()
    shards = plan_shards(
        [WorkUnit(u.key, 4000.0, u.group) for u in units],
        setup_seconds=adapter.setup_seconds(),
        budget_seconds=21_600,
        margin_seconds=shard_margin_seconds(21_600),
        slots=4,
    )

    covered = [unit.key for shard in shards for unit in shard.units]

    assert len(shards) == 2
    assert sorted(covered) == ["q2", "q3"]


def test_merge_reports_the_units_done_and_is_idempotent(tmp_path: Path) -> None:
    adapter, _, cache_path = make(tmp_path)
    shard = Shard("abc", (WorkUnit("q1", 1.0), WorkUnit("q2", 1.0)), "")
    result = adapter.run_shard(shard, reserved())

    assert adapter.merge(shard, result) == 2
    assert adapter.merge(shard, result) == 2
    assert len(cache_path.read_text().splitlines()) == 2
    assert {u.key for u in adapter.missing()} == {"q3"}


def test_partial_artifacts_are_merged_as_they_arrive(tmp_path: Path) -> None:
    partial = cache_at(tmp_path / "partial" / "q.jsonl")
    partial.set(MODEL, "q1", QUERIES["q1"], vector(0.9))

    class Sinking(Runner):
        def __call__(self, **kwargs) -> PipelineResult:
            artifact = replace(
                cloud_artifact(Completion(2, 1, 1)), data_path=partial.path
            )
            kwargs["artifact_sink"](self.job, artifact)
            return PipelineResult(self.job, Completion(2, 1, 1), (), None, 1)

    adapter, _, cache_path = make(tmp_path, runner=Sinking(tmp_path))
    shard = Shard("abc", (WorkUnit("q1", 1.0), WorkUnit("q2", 1.0)), "")

    result = adapter.run_shard(shard, reserved())

    assert adapter.merge(shard, result) == 1
    assert cache_at(cache_path).get(MODEL, "q1", QUERIES["q1"]) == vector(0.9)


def test_force_clears_the_cached_vectors_so_every_query_is_recomputed(
    tmp_path: Path,
) -> None:
    adapter, _, cache_path = make(tmp_path, cached=("q1", "q2"), force=True)

    assert {unit.key for unit in adapter.missing()} == {"q1", "q2", "q3"}
    assert cache_at(cache_path).get(MODEL, "q1", QUERIES["q1"]) is None


def test_a_recorded_kernel_makes_the_shard_attach_even_when_forced(
    tmp_path: Path,
) -> None:
    adapter, runner, _ = make(tmp_path, force=True)
    shard = Shard("abc", (WorkUnit("q1", 1.0),), "")
    record = ShardRecord(
        "abc", "query-embed", "acc3", ("q1",), "2026-10-23T00:00:00+00:00", 60
    )

    adapter.run_shard(shard, reserved())
    assert adapter.preferred_profile(shard, record) == "acc3"
    adapter.run_shard(shard, reserved())

    assert [c["resume_remote"] for c in runner.calls] == [False, True]


def test_cost_is_a_per_query_overhead_plus_the_characters(tmp_path: Path) -> None:
    adapter, _, _ = make(tmp_path)

    seconds = {unit.key: unit.seconds for unit in adapter.missing()}

    assert seconds["q1"] == pytest.approx(0.01 + len(QUERIES["q1"]) * 0.01)
