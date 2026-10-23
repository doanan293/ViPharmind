import shutil
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.integrations.kaggle.factories import job_identity, stage_job

from pharma_lab.artifacts.manifest import Completion
from pharma_lab.cache.jsonl_records import append_record
from pharma_lab.cache.paths import rerank_log_path
from pharma_lab.evaluation import rerank_service
from pharma_lab.evaluation.local_rerank_benchmark import LocalRerankBenchmarkResult
from pharma_lab.evaluation.rerank_cache_checkpoint import RerankCacheCheckpoint
from pharma_lab.evaluation.rerank_score_cache import RerankScoreCache
from pharma_lab.evaluation.rerank_service import (
    KaggleRerankBackend,
    LocalRerankBackend,
    RerankRequest,
)
from pharma_lab.evaluation.run_workspace import load_run_record
from pharma_lab.integrations.kaggle import auto_profile, kernel_service, sessions
from pharma_lab.integrations.kaggle import service as kaggle_service
from pharma_lab.integrations.kaggle.api import KaggleCommandRunner
from pharma_lab.integrations.kaggle.config import (
    KaggleAccountProfile,
    OwnerConfiguration,
)
from pharma_lab.integrations.kaggle.models import (
    ActionVerb,
    CloudArtifact,
    KernelPresence,
    KernelRemoteState,
    KernelStatus,
    ReconcileAction,
)
from pharma_lab.integrations.kaggle.quota import AccountQuota
from pharma_lab.integrations.kaggle.service import KaggleExecutionContext
from pharma_lab.integrations.kaggle.workers.runtime import write_artifact_manifest
from pharma_lab.runtime.benchmarking import BenchmarkMeasurement
from pharma_lab.runtime.catalog import LOCAL_RERANK_SEARCH_SPACE, require_model
from pharma_lab.runtime.runtime_profiles import (
    RuntimeProfile,
    RuntimeProfileIdentity,
)


@pytest.fixture(autouse=True)
def isolated_rerank_cache(tmp_path, monkeypatch):
    from pharma_lab.config import paths

    monkeypatch.setattr(paths, "RERANK_SCORE_CACHE_DIR", tmp_path / "rerank-cache")


class FakeReranker:
    def rerank(self, query, candidates):
        del query
        return [
            candidate.with_rerank_score(float(index), index)
            for index, candidate in enumerate(candidates, start=1)
        ]


def request(run_root, model, *, force=False, dry_run=False):
    return RerankRequest(
        run_root=run_root,
        model=model,
        force=force,
        dry_run=dry_run,
        budget_seconds=60,
        request_timeout_seconds=5.0,
    )


def fake_local_backend():
    return LocalRerankBackend(reranker_factory=lambda _spec, _timeout: FakeReranker())


MODEL = "qwen3-reranker:0.6b-q8_0"


def _session_contexts(*names: str) -> tuple[KaggleExecutionContext, ...]:
    return tuple(
        KaggleExecutionContext(
            KaggleAccountProfile(name, f"user-{name}", f"token-{name}"),
            OwnerConfiguration(f"user-{name}", "user-acc1", f"user-{name}"),
            KaggleCommandRunner(environment={}),
        )
        for name in names
    )


def _scores_artifact(cache: RerankScoreCache) -> CloudArtifact:
    return CloudArtifact(
        cache.path,
        cache.path.with_name("manifest.json"),
        job_identity(),
        Completion(1, 1, 0),
    )


@pytest.fixture
def kaggle_sessions(monkeypatch, tmp_path) -> dict[str, float]:
    """Fake Kaggle: GPU hours left per profile and a reusable runtime profile."""
    spec = require_model(MODEL)
    assert spec.rerank_search_space is not None
    selected = spec.rerank_search_space.candidates[0]
    quotas = {"acc1": 27.58, "acc2": 29.61}

    def read_quota(context: KaggleExecutionContext) -> AccountQuota:
        assert context.profile is not None
        return AccountQuota(
            context.profile.name,
            context.profile.username,
            quotas[context.profile.name],
            30.0,
            datetime(2026, 9, 19),
        )

    monkeypatch.setattr(rerank_service, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(
        kaggle_service,
        "resolve_session_contexts",
        lambda _account: _session_contexts(*quotas),
    )
    monkeypatch.setattr(
        kaggle_service, "runtime_manifest_sha256", lambda *_args, **_kwargs: "c" * 64
    )
    monkeypatch.setattr(
        auto_profile,
        "ensure_runtime_profile",
        lambda **_kwargs: SimpleNamespace(
            profile=SimpleNamespace(selected=selected, measurements=()), action="reuse"
        ),
    )
    monkeypatch.setattr(sessions, "read_account_quota", read_quota)
    return quotas


def _score_record(*, query_id: str, score: float) -> dict[str, object]:
    return {
        "reranker": "qwen3-reranker:0.6b-q8_0",
        "model_sha256": "model-sha",
        "request_contract_sha256": "contract-sha",
        "query_id": query_id,
        "query_hash": f"query-hash-{query_id}",
        "chunk_id": "chunk-1",
        "document_hash": "document-hash-1",
        "score": score,
    }


def test_remote_rerank_reconciliation_replaces_conflicts_and_keeps_local_only(
    tmp_path,
):
    """A missing replacement would keep conflicting local scores and fail merge."""
    local_path = tmp_path / "local.jsonl"
    remote_path = tmp_path / "remote.jsonl"
    append_record(
        local_path,
        _score_record(query_id="shared", score=0.1),
        schema="rerank-score-v2",
    )
    append_record(
        local_path,
        _score_record(query_id="local-only", score=0.2),
        schema="rerank-score-v2",
    )
    append_record(
        remote_path,
        _score_record(query_id="shared", score=0.9),
        schema="rerank-score-v2",
    )

    remote = RerankScoreCache(
        remote_path,
        model_sha256="model-sha",
        request_contract_sha256="contract-sha",
    )
    rerank_service._merge_remote_rerank_scores(
        local_path,
        remote,
        model_sha256="model-sha",
        request_contract_sha256="contract-sha",
    )

    reconciled = RerankScoreCache(
        local_path,
        model_sha256="model-sha",
        request_contract_sha256="contract-sha",
    )
    scores_by_query = {key.query_id: score for key, score in reconciled.records.items()}
    assert scores_by_query == {"shared": 0.9, "local-only": 0.2}


def test_two_models_register_two_variants_without_mutating_candidates(complete_run):
    candidates_path = complete_run / "candidates" / "candidates.jsonl"
    before = candidates_path.read_bytes()
    backend = fake_local_backend()

    first = backend.run(request(complete_run, "qwen3-reranker:0.6b-q8_0"))
    second = backend.run(request(complete_run, "bge-reranker-v2-m3:q8_0"))

    record = load_run_record(complete_run / "run.json")
    assert len(record.rerank_variants) == 2
    assert first.artifact_dir is not None
    assert second.artifact_dir is not None
    assert first.artifact_dir != second.artifact_dir
    assert candidates_path.read_bytes() == before


def test_local_rerun_reuses_the_same_variant(complete_run):
    backend = fake_local_backend()
    first = backend.run(request(complete_run, "qwen3-reranker:0.6b-q8_0"))
    assert first.artifact_dir is not None
    score_bytes = (first.artifact_dir / "rerank_scores.jsonl").read_bytes()

    second = backend.run(request(complete_run, "qwen3-reranker:0.6b-q8_0"))

    assert second.artifact_dir is not None
    assert second.variant_sha256 == first.variant_sha256
    assert second.artifact_dir == first.artifact_dir
    assert (second.artifact_dir / "rerank_scores.jsonl").read_bytes() == score_bytes


def fake_kaggle_dry_run(**_kwargs):
    return SimpleNamespace(
        artifact_path=None,
        completion=Completion(total=1, complete=0, missing=1),
        actions=(
            ReconcileAction(
                "model", "owner/model", ActionVerb.CREATE, "dataset is missing"
            ),
            ReconcileAction(
                "input", "owner/input", ActionVerb.CREATE, "dataset is missing"
            ),
        ),
    )


def test_kaggle_dry_run_formats_resource_identity_and_does_not_register(
    complete_run, monkeypatch, tmp_path
):
    monkeypatch.setattr(kaggle_service, "run_kaggle_stage", fake_kaggle_dry_run)
    monkeypatch.setattr(
        kaggle_service,
        "resolve_session_contexts",
        lambda _account: _session_contexts("acc1"),
    )
    original_ensure_profile = auto_profile.ensure_runtime_profile

    def isolated_profile(**kwargs):
        return original_ensure_profile(
            **kwargs,
            profile_root=tmp_path / "profiles",
        )

    monkeypatch.setattr(auto_profile, "ensure_runtime_profile", isolated_profile)

    result = KaggleRerankBackend().run(
        request(complete_run, "qwen3-reranker:0.6b-q8_0", dry_run=True)
    )

    assert result.incomplete
    assert "profile=benchmark-required" in result.actions
    assert load_run_record(complete_run / "run.json").rerank_variants == {}


def test_kaggle_rerank_allows_different_models_in_the_same_run(
    complete_run, monkeypatch, tmp_path
):
    from pharma_lab.evaluation import rerank_service

    monkeypatch.setattr(rerank_service, "WORK_DIR", tmp_path / "work")

    first_entered = threading.Event()
    release_first = threading.Event()

    def run_unlocked(rerank_request):
        if rerank_request.model == "qwen3-reranker:0.6b-q8_0":
            first_entered.set()
            assert release_first.wait(2)
        return rerank_request.model

    monkeypatch.setattr(
        KaggleRerankBackend,
        "_run_kaggle_unlocked",
        staticmethod(run_unlocked),
    )
    backend = KaggleRerankBackend()
    first_request = request(complete_run, "qwen3-reranker:0.6b-q8_0")
    second_request = request(complete_run, "bge-reranker-v2-m3:q8_0")

    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(backend.run, first_request)
        assert first_entered.wait(2)
        try:
            second = backend.run(second_request)
        finally:
            release_first.set()

        assert first.result(timeout=2) == first_request.model
    assert second == second_request.model


def test_kaggle_rerank_serializes_same_model_across_runs(tmp_path, monkeypatch):
    from pharma_lab.evaluation import rerank_service

    monkeypatch.setattr(rerank_service, "WORK_DIR", tmp_path / "work")

    first_entered = threading.Event()
    release_first = threading.Event()

    def run_unlocked(_request):
        first_entered.set()
        assert release_first.wait(2)
        return "first"

    monkeypatch.setattr(
        KaggleRerankBackend,
        "_run_kaggle_unlocked",
        staticmethod(run_unlocked),
    )
    backend = KaggleRerankBackend()
    first_request = request(tmp_path / "run-a", "qwen3-reranker:0.6b-q8_0")
    second_request = request(tmp_path / "run-b", "qwen3-reranker:0.6b-q8_0")

    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(backend.run, first_request)
        assert first_entered.wait(2)
        try:
            with pytest.raises(RuntimeError, match="already has an active Kaggle job"):
                backend.run(second_request)
        finally:
            release_first.set()
        assert first.result(timeout=2) == "first"


def test_local_dry_run_reports_target_and_missing_pairs(complete_run):
    result = fake_local_backend().run(
        request(complete_run, "qwen3-reranker:0.6b-q8_0", dry_run=True)
    )

    assert "missing_pairs=1" in result.actions
    assert (
        f"target={complete_run / 'rerank' / 'qwen3_reranker_0_6b_q8_0'}"
        in result.actions
    )
    assert load_run_record(complete_run / "run.json").rerank_variants == {}


def test_forced_rerank_rescores_into_the_same_variant(complete_run):
    backend = fake_local_backend()
    first = backend.run(request(complete_run, "qwen3-reranker:0.6b-q8_0"))

    second = backend.run(request(complete_run, "qwen3-reranker:0.6b-q8_0", force=True))

    assert second.artifact_dir == first.artifact_dir
    assert "scored=1" in second.actions
    assert list(load_run_record(complete_run / "run.json").rerank_variants) == [
        "qwen3_reranker_0_6b_q8_0"
    ]


def test_local_rerank_from_a_complete_cache_starts_no_reranker(
    complete_run, complete_rerank_cache, monkeypatch
):
    monkeypatch.setattr(
        rerank_service,
        "rerank_score_cache_path",
        lambda _model: complete_rerank_cache.path,
    )

    def no_server(_spec, _timeout):
        raise AssertionError("a complete cache must not start a reranker")

    result = LocalRerankBackend(reranker_factory=no_server).run(
        request(complete_run, "qwen3-reranker:0.6b-q8_0")
    )

    assert result.artifact_dir == complete_run / "rerank" / "qwen3_reranker_0_6b_q8_0"
    assert "scored=0" in result.actions


class RecordingReranker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def rerank(self, query, candidates):
        self.calls.append((query, [candidate.chunk_id for candidate in candidates]))
        return [
            candidate.with_rerank_score(float(index), index)
            for index, candidate in enumerate(candidates, start=1)
        ]


def test_local_rerank_scores_each_query_in_one_request(two_candidate_run):
    reranker = RecordingReranker()

    result = LocalRerankBackend(reranker_factory=lambda _spec, _timeout: reranker).run(
        request(two_candidate_run, "qwen3-reranker:0.6b-q8_0")
    )

    assert reranker.calls == [("test query", ["chunk-1", "chunk-2"])]
    assert "scored=2" in result.actions
    assert result.artifact_dir is not None


def test_local_benchmark_reports_the_selected_level_without_registering(
    complete_run,
):
    selected = LOCAL_RERANK_SEARCH_SPACE.candidates[1]
    measurement = BenchmarkMeasurement(
        selected, 90, 1000, 3.0, latency_p50_seconds=0.4, latency_p95_seconds=0.5
    )
    identity = RuntimeProfileIdentity.create(
        workload="rerank",
        model="qwen3-reranker:4b-q8_0",
        model_sha256="a" * 64,
        runtime_sha256="b" * 64,
        inference_cache_policy_sha256="c" * 64,
        machine_shape="cpu",
        topology="cpu_compose",
        search_space=LOCAL_RERANK_SEARCH_SPACE,
    )
    profile = RuntimeProfile.create(
        identity,
        selected,
        sample_count=90,
        measurements=[measurement.to_dict()],
        benchmark_job_sha256="d" * 64,
    )
    report = Path("profiles/rerank/qwen3_reranker_4b_q8_0.json")
    seen = []

    def fake_benchmark(spec, candidate_data_path, timeout):
        seen.append((spec.name, candidate_data_path, timeout))
        return LocalRerankBenchmarkResult(profile, report, (measurement,))

    def no_server(_spec, _timeout):
        raise AssertionError("a benchmark must not score the run")

    result = LocalRerankBackend(
        reranker_factory=no_server, benchmark_runner=fake_benchmark
    ).run(replace(request(complete_run, "qwen3-reranker:4b-q8_0"), benchmark=True))

    assert seen == [
        (
            "qwen3-reranker:4b-q8_0",
            complete_run / "candidates" / "candidates.jsonl",
            5.0,
        )
    ]
    assert result.actions == (
        "selected=server_slots=4 ubatch=4096 threads=12",
        "latency_p95_seconds=0.5",
        "env=LLAMA_RERANKER_CONTEXT_SIZE=20480 LLAMA_RERANKER_PARALLEL=4 "
        "LLAMA_RERANKER_THREADS=12 LLAMA_RERANKER_UBATCH_SIZE=4096",
    )
    assert (result.benchmark_levels, result.benchmark_report) == (1, report)
    assert load_run_record(complete_run / "run.json").rerank_variants == {}


def test_local_reranker_starts_compose_with_the_stored_local_profile(monkeypatch):
    spec = require_model("qwen3-reranker:4b-q8_0")
    selected = LOCAL_RERANK_SEARCH_SPACE.candidates[1]
    ensured = []

    class FakeManager:
        def __init__(self, compose_file):
            self.compose_file = compose_file

        def ensure(self, role, ensured_spec, gguf_root, runtime=None):
            del gguf_root
            ensured.append((role, ensured_spec.name, runtime))
            return "http://127.0.0.1:11435"

    monkeypatch.setattr(
        rerank_service,
        "load_local_rerank_profile",
        lambda _spec: SimpleNamespace(selected=selected),
    )
    monkeypatch.setattr(rerank_service, "LlamaCppComposeManager", FakeManager)

    LocalRerankBackend._default_reranker(spec, 5.0)

    assert ensured == [("reranker", spec.name, selected)]


def test_kaggle_backend_leaves_benchmarks_to_the_runtime_profile(complete_run):
    with pytest.raises(ValueError, match="--backend local"):
        KaggleRerankBackend().run(
            replace(request(complete_run, "qwen3-reranker:0.6b-q8_0"), benchmark=True)
        )


def test_kaggle_rerank_merges_session_scores_and_registers_the_variant(
    complete_run, complete_rerank_cache, kaggle_sessions, monkeypatch, tmp_path
):
    calls: list[dict] = []

    def fake_stage(**kwargs):
        calls.append(kwargs)
        kwargs["artifact_sink"](
            stage_job(tmp_path / "job"), _scores_artifact(complete_rerank_cache)
        )
        return SimpleNamespace(
            completion=Completion(1, 1, 0), actions=(), artifact_path=None
        )

    monkeypatch.setattr(kaggle_service, "run_kaggle_stage", fake_stage)

    result = KaggleRerankBackend().run(
        replace(
            request(complete_run, MODEL), kaggle_account="auto", budget_seconds=21_600
        )
    )

    assert not result.incomplete
    assert result.artifact_dir == complete_run / "rerank" / "qwen3_reranker_0_6b_q8_0"
    assert [
        (
            call["kaggle_account"],
            call["budget_seconds"],
            call["max_runs"],
            call["force"],
            call["resume_remote"],
        )
        for call in calls
    ] == [("acc2", 21_600, 1, False, True)]
    assert isinstance(calls[0]["local_checkpoint"], RerankCacheCheckpoint)
    assert "stop=complete" in result.actions
    log = rerank_log_path(MODEL).read_text(encoding="utf-8")
    assert "quota account=acc1 remaining=27.58h" in log
    assert "1 units, starting" in log
    assert "merged artifact pairs=1;" in log


def test_kaggle_rerank_stops_with_a_quota_table_when_no_account_has_an_hour(
    complete_run, kaggle_sessions, monkeypatch
):
    kaggle_sessions.update(acc1=1.2, acc2=0.4)

    def no_session(**_kwargs):
        raise AssertionError("no Kaggle session may start without quota")

    monkeypatch.setattr(kaggle_service, "run_kaggle_stage", no_session)

    result = KaggleRerankBackend().run(
        replace(
            request(complete_run, MODEL), kaggle_account="auto", budget_seconds=21_600
        )
    )

    assert result.incomplete
    assert "stop=quota-exhausted" in result.actions
    assert "missing_pairs=1" in result.actions
    assert len(result.quota) == 3
    assert "2026-09-19T00:00:00" in result.quota[1]
    assert load_run_record(complete_run / "run.json").rerank_variants == {}


def test_kaggle_rerank_attaches_to_the_account_already_running_the_kernel(
    complete_run, complete_rerank_cache, kaggle_sessions, monkeypatch, tmp_path
):
    from pharma_lab.integrations.kaggle.job_registry import JobRegistry, ShardRecord
    from pharma_lab.integrations.kaggle.shards import shard_id_of

    accounts: list[tuple[str, bool]] = []

    def fake_stage(**kwargs):
        accounts.append((kwargs["kaggle_account"], kwargs["resume_remote"]))
        kwargs["artifact_sink"](
            stage_job(tmp_path / "job"), _scores_artifact(complete_rerank_cache)
        )
        return SimpleNamespace(
            completion=Completion(1, 1, 0), actions=(), artifact_path=None
        )

    monkeypatch.setattr(kaggle_service, "run_kaggle_stage", fake_stage)
    JobRegistry(
        tmp_path
        / "work"
        / "kaggle-rerank-shards"
        / "qwen3_reranker_0_6b_q8_0"
        / "jobs.json"
    ).register(
        ShardRecord(
            shard_id_of(["query-1"]),
            "rerank",
            "acc1",
            ("query-1",),
            datetime.now(UTC).isoformat(),
            21_600,
        )
    )

    KaggleRerankBackend().run(
        replace(
            request(complete_run, MODEL), kaggle_account="auto", budget_seconds=21_600
        )
    )

    assert accounts == [("acc1", True)]


def test_forced_kaggle_rerank_starts_clean_and_does_not_force_the_stage(
    complete_run, complete_rerank_cache, kaggle_sessions, monkeypatch, tmp_path
):
    calls: list[tuple[bool, bool]] = []

    def fake_stage(**kwargs):
        calls.append((kwargs["force"], kwargs["resume_remote"]))
        kwargs["artifact_sink"](
            stage_job(tmp_path / "job"), _scores_artifact(complete_rerank_cache)
        )
        return SimpleNamespace(
            completion=Completion(1, 1, 0), actions=(), artifact_path=None
        )

    monkeypatch.setattr(kaggle_service, "run_kaggle_stage", fake_stage)

    result = KaggleRerankBackend().run(
        replace(
            request(complete_run, MODEL, force=True),
            kaggle_account="auto",
            budget_seconds=21_600,
        )
    )

    assert calls == [(False, False)]
    assert not result.incomplete


def test_kaggle_rerank_dry_run_plans_shards_without_touching_kaggle(
    complete_run, kaggle_sessions, monkeypatch
):
    def no_session(**_kwargs):
        raise AssertionError("a dry run starts no Kaggle session")

    monkeypatch.setattr(kaggle_service, "run_kaggle_stage", no_session)

    result = KaggleRerankBackend().run(
        replace(
            request(complete_run, MODEL, dry_run=True),
            kaggle_account="auto",
            budget_seconds=21_600,
        )
    )

    assert result.incomplete
    assert "missing_pairs=1" in result.actions
    assert any(action.startswith("planned_shards=1") for action in result.actions)


def test_kaggle_rerank_runs_shards_on_two_accounts_and_registers_the_variant(
    three_query_run, kaggle_sessions, monkeypatch, tmp_path
):
    from pharma_lab.evaluation.retrieval_candidate_artifact import (
        CandidateArtifactReader,
    )
    from pharma_lab.evaluation.retrieval_types import RetrievalCandidate

    spec = require_model(MODEL)
    assert spec.rerank_contract is not None
    # A pair takes 5,000 s, so three queries do not fit one session usefully.
    assert spec.rerank_search_space is not None
    selected = spec.rerank_search_space.candidates[0]
    monkeypatch.setattr(
        auto_profile,
        "ensure_runtime_profile",
        lambda **_kwargs: SimpleNamespace(
            profile=SimpleNamespace(
                selected=selected,
                measurements=(
                    {
                        "candidate": selected.to_dict(),
                        "status": "ok",
                        "items": 1,
                        "elapsed_seconds": 5000.0,
                    },
                ),
            ),
            action="reuse",
        ),
    )
    calls: list[tuple[str, list[str]]] = []
    lock = threading.Lock()

    def fake_stage(**kwargs):
        subset = Path(kwargs["input_path"])
        remote = RerankScoreCache(
            tmp_path / f"remote-{subset.parent.name}.jsonl",
            model_sha256=spec.sha256,
            request_contract_sha256=spec.rerank_contract.sha256,
        )
        queries = []
        for row in CandidateArtifactReader.from_data_path(subset):
            queries.append(row["query_id"])
            for item in row["candidates"]:
                remote.set(
                    MODEL,
                    {"query_id": row["query_id"], "query": row["query"]},
                    RetrievalCandidate(
                        chunk_id=item["chunk_id"],
                        score=float(item["retrieval_score"]),
                        rank=int(item["retrieval_rank"]),
                        source=str(item["source"]),
                        payload=dict(item["payload"]),
                        document_text=str(item["document_text"]),
                        document_hash=str(item["document_hash"]),
                    ),
                    0.5,
                )
        with lock:
            calls.append((kwargs["kaggle_account"], queries))
        kwargs["artifact_sink"](stage_job(tmp_path / "job"), _scores_artifact(remote))
        return SimpleNamespace(
            completion=Completion(1, 1, 0), actions=(), artifact_path=None
        )

    monkeypatch.setattr(kaggle_service, "run_kaggle_stage", fake_stage)

    result = KaggleRerankBackend().run(
        replace(
            request(three_query_run, MODEL),
            kaggle_account="auto",
            budget_seconds=21_600,
        )
    )

    assert not result.incomplete
    assert sorted(query for _, queries in calls for query in queries) == [
        "query-1",
        "query-2",
        "query-3",
    ]
    assert {account for account, _ in calls} == {"acc1", "acc2"}
    assert (
        result.artifact_dir == three_query_run / "rerank" / "qwen3_reranker_0_6b_q8_0"
    )


def test_kaggle_rerank_finalizes_a_complete_local_cache_without_kaggle(
    complete_run, complete_rerank_cache, monkeypatch, tmp_path
):
    def no_accounts(_account):
        raise AssertionError("a complete local cache needs no Kaggle account")

    monkeypatch.setattr(rerank_service, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(
        rerank_service,
        "rerank_score_cache_path",
        lambda _model: complete_rerank_cache.path,
    )
    monkeypatch.setattr(kaggle_service, "resolve_session_contexts", no_accounts)

    result = KaggleRerankBackend().run(request(complete_run, MODEL))

    assert result.artifact_dir == complete_run / "rerank" / "qwen3_reranker_0_6b_q8_0"
    assert "reuse=local score cache" in result.actions


KERNEL = "user-acc2/rerank-5f22fcadeede1072"


def _fake_kernel_service(
    status: KernelStatus,
    write_output: Callable[[Path], None],
    seen: list[tuple[str, str]],
):
    class FakeKernelService:
        def __init__(self, runner, owner):
            self.owner = owner

        def inspect_state(self, reference):
            seen.append(("inspect", reference))
            return KernelRemoteState(reference, KernelPresence.EXISTS, status)

        def download_output(self, reference, destination):
            seen.append(("download", self.owner))
            write_output(Path(destination))

    return FakeKernelService


def _kernel_output(cache: RerankScoreCache, *, model: str = MODEL):
    def write_output(destination: Path) -> None:
        artifact_dir = destination / "artifact"
        artifact_dir.mkdir(parents=True)
        data = artifact_dir / "rerank_scores.jsonl"
        shutil.copy2(cache.path, data)
        write_artifact_manifest(
            data,
            artifact_type="rerank_scores",
            identity=job_identity(model=model),
            completion=Completion(300_000, 1, 299_999),
        )

    return write_output


@pytest.fixture
def recovery_accounts(monkeypatch, tmp_path):
    monkeypatch.setattr(rerank_service, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(
        kaggle_service,
        "resolve_profile_execution_contexts",
        lambda: _session_contexts("acc1", "acc2"),
    )


def test_recover_kernel_merges_its_scores_and_registers_a_complete_variant(
    complete_run, complete_rerank_cache, recovery_accounts, monkeypatch
):
    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(
        kernel_service,
        "KernelService",
        _fake_kernel_service(
            KernelStatus.ERROR, _kernel_output(complete_rerank_cache), seen
        ),
    )

    result = KaggleRerankBackend().run(
        replace(request(complete_run, MODEL), recover_kernel=KERNEL)
    )

    assert seen == [("inspect", KERNEL), ("download", "user-acc2")]
    assert "recovered_pairs=1" in result.actions
    assert "missing_pairs=0" in result.actions
    assert result.artifact_dir == complete_run / "rerank" / "qwen3_reranker_0_6b_q8_0"


def test_recover_kernel_refuses_a_running_kernel(
    complete_run, complete_rerank_cache, recovery_accounts, monkeypatch
):
    monkeypatch.setattr(
        kernel_service,
        "KernelService",
        _fake_kernel_service(
            KernelStatus.RUNNING, _kernel_output(complete_rerank_cache), []
        ),
    )

    with pytest.raises(ValueError, match="no finished output"):
        KaggleRerankBackend().run(
            replace(request(complete_run, MODEL), recover_kernel=KERNEL)
        )


def test_recover_kernel_rejects_scores_of_another_model(
    complete_run, complete_rerank_cache, recovery_accounts, monkeypatch
):
    monkeypatch.setattr(
        kernel_service,
        "KernelService",
        _fake_kernel_service(
            KernelStatus.COMPLETE,
            _kernel_output(complete_rerank_cache, model="bge-reranker-v2-m3:q8_0"),
            [],
        ),
    )

    with pytest.raises(ValueError, match="another model"):
        KaggleRerankBackend().run(
            replace(request(complete_run, MODEL), recover_kernel=KERNEL)
        )
    assert load_run_record(complete_run / "run.json").rerank_variants == {}


def test_recover_kernel_needs_a_profile_for_the_kernel_owner(
    complete_run, recovery_accounts
):
    with pytest.raises(ValueError, match="has username stranger"):
        KaggleRerankBackend().run(
            replace(request(complete_run, MODEL), recover_kernel="stranger/rerank-1")
        )


def test_local_backend_rejects_kernel_recovery(complete_run):
    with pytest.raises(ValueError, match="requires --backend kaggle"):
        fake_local_backend().run(
            replace(request(complete_run, MODEL), recover_kernel=KERNEL)
        )


def test_kaggle_rerank_without_an_account_flag_uses_every_account(
    complete_run, kaggle_sessions, monkeypatch
):
    asked: list[str | None] = []

    def resolve(account):
        asked.append(account)
        return _session_contexts("acc1", "acc2")

    monkeypatch.setattr(kaggle_service, "resolve_session_contexts", resolve)
    monkeypatch.setattr(
        kaggle_service,
        "run_kaggle_stage",
        lambda **_kwargs: SimpleNamespace(
            completion=Completion(1, 0, 1), actions=(), artifact_path=None
        ),
    )

    KaggleRerankBackend().run(
        replace(request(complete_run, MODEL, dry_run=True), budget_seconds=21_600)
    )

    assert asked == ["auto"]
