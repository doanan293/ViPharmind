import json
from types import SimpleNamespace

import pytest
from tests.integrations.kaggle.test_scheduler import contexts

from pharma_lab.artifacts.manifest import Completion
from pharma_lab.evaluation import query_embedding_service
from pharma_lab.evaluation.query_embedding_cache import QueryEmbeddingCache
from pharma_lab.evaluation.query_embedding_service import (
    KaggleQueryEmbeddingBackend,
    QueryEmbeddingRequest,
)
from pharma_lab.integrations.kaggle import auto_profile, sessions
from pharma_lab.integrations.kaggle import service as kaggle_service
from pharma_lab.integrations.kaggle.quota import AccountQuota
from pharma_lab.runtime.catalog import require_model

MODEL = "qwen3-embedding:4b-q8_0"
DIMS = require_model(MODEL).vector_dimension or 4


@pytest.fixture
def kaggle_sessions(monkeypatch, tmp_path):
    """Fake Kaggle accounts with quota; records what the backend asked to resolve."""
    asked: list[str | None] = []

    def resolve(account):
        asked.append(account)
        names = (
            ("acc1", "acc2") if account in (None, "auto") else tuple(account.split(","))
        )
        return contexts(*names)

    def read_quota(context):
        assert context.profile is not None
        return AccountQuota(
            context.profile.name, context.profile.username, 25.0, 30.0, None
        )

    monkeypatch.setattr(kaggle_service, "resolve_session_contexts", resolve)
    monkeypatch.setattr(sessions, "read_account_quota", read_quota)
    monkeypatch.setattr(query_embedding_service, "WORK_DIR", tmp_path / "work")
    return asked


def test_kaggle_query_embedding_propagates_selected_account(
    tmp_path, monkeypatch, kaggle_sessions
):
    seen = []
    search_space = require_model(MODEL).embedding_search_space
    assert search_space is not None
    selected = search_space.query.candidates[0]
    input_path = tmp_path / "evaluation.jsonl"
    input_path.write_text(
        '{"query_id": "q1", "query": "liều paracetamol"}\n', encoding="utf-8"
    )
    monkeypatch.setattr(
        auto_profile,
        "ensure_runtime_profile",
        lambda **kwargs: (
            seen.append(("profile", kwargs["kaggle_account"]))
            or SimpleNamespace(
                profile=SimpleNamespace(selected=selected, measurements=()),
                action="reuse",
            )
        ),
    )
    monkeypatch.setattr(
        kaggle_service,
        "run_kaggle_stage",
        lambda **kwargs: (
            seen.append(("stage", kwargs["kaggle_account"]))
            or SimpleNamespace(
                artifact_path=None,
                completion=Completion(1, 0, 1),
                actions=(),
            )
        ),
    )

    result = KaggleQueryEmbeddingBackend().run(
        QueryEmbeddingRequest(
            evaluation_path=input_path,
            model=MODEL,
            output_dir=tmp_path / "cache.jsonl",
            force=False,
            dry_run=False,
            budget_seconds=21_600,
            request_timeout_seconds=5.0,
            kaggle_account="acc2",
        )
    )

    assert result.incomplete
    # A session that completes nothing is retried once, then the shard is stuck.
    assert seen[0] == ("profile", "acc2")
    assert set(seen[1:]) == {("stage", "acc2")}


def test_kaggle_query_embedding_sends_only_uncached_questions(
    tmp_path, monkeypatch, kaggle_sessions
):
    spec = require_model(MODEL)
    cache_path = tmp_path / "cache.jsonl"
    cache = QueryEmbeddingCache(
        cache_path, vector_dim=spec.vector_dimension, model_sha256=spec.sha256
    )
    cache.set(MODEL, "q1", "liều paracetamol", [0.1] * (spec.vector_dimension or 4))
    input_path = tmp_path / "evaluation.jsonl"
    input_path.write_text(
        '{"query_id": "q1", "query": "liều paracetamol"}\n'
        '{"query_id": "q2", "query": "tác dụng phụ ibuprofen"}\n',
        encoding="utf-8",
    )
    sent: list[str] = []

    def stage(**kwargs):
        rows = [
            json.loads(line)
            for line in kwargs["input_path"].read_text("utf-8").splitlines()
        ]
        sent.extend(row["query_id"] for row in rows)
        remote = QueryEmbeddingCache(
            tmp_path / "remote" / "q.jsonl",
            vector_dim=spec.vector_dimension,
            model_sha256=spec.sha256,
        )
        for row in rows:
            remote.set(MODEL, row["query_id"], row["query"], [0.2] * DIMS)
        return SimpleNamespace(
            artifact_path=remote.path,
            completion=Completion(len(rows), len(rows), 0),
            actions=(),
        )

    search_space = spec.embedding_search_space
    assert search_space is not None
    monkeypatch.setattr(
        auto_profile,
        "ensure_runtime_profile",
        lambda **kwargs: SimpleNamespace(
            profile=SimpleNamespace(
                selected=search_space.query.candidates[0], measurements=()
            ),
            action="reuse",
        ),
    )
    monkeypatch.setattr(kaggle_service, "run_kaggle_stage", stage)
    request = QueryEmbeddingRequest(
        evaluation_path=input_path,
        model=MODEL,
        output_dir=cache_path,
        force=False,
        dry_run=False,
        budget_seconds=21_600,
        request_timeout_seconds=5.0,
    )
    KaggleQueryEmbeddingBackend().run(request)
    assert sent == ["q2"]

    # With every question cached, Kaggle is not called at all.
    sent.clear()
    result = KaggleQueryEmbeddingBackend().run(request)
    assert sent == [] and not result.incomplete and result.subset_sha256


def test_default_account_is_auto(tmp_path, monkeypatch, kaggle_sessions):
    search_space = require_model(MODEL).embedding_search_space
    assert search_space is not None
    input_path = tmp_path / "evaluation.jsonl"
    input_path.write_text('{"query_id": "q1", "query": "liều"}\n', encoding="utf-8")
    monkeypatch.setattr(
        auto_profile,
        "ensure_runtime_profile",
        lambda **kwargs: SimpleNamespace(
            profile=SimpleNamespace(
                selected=search_space.query.candidates[0], measurements=()
            ),
            action="reuse",
        ),
    )
    monkeypatch.setattr(
        kaggle_service,
        "run_kaggle_stage",
        lambda **kwargs: SimpleNamespace(
            artifact_path=None, completion=Completion(1, 0, 1), actions=()
        ),
    )

    KaggleQueryEmbeddingBackend().run(
        QueryEmbeddingRequest(
            evaluation_path=input_path,
            model=MODEL,
            output_dir=tmp_path / "cache.jsonl",
            force=False,
            dry_run=False,
            budget_seconds=21_600,
            request_timeout_seconds=5.0,
        )
    )

    assert kaggle_sessions == ["auto"]


def test_dry_run_plans_shards_without_touching_kaggle(
    tmp_path, monkeypatch, kaggle_sessions
):
    search_space = require_model(MODEL).embedding_search_space
    assert search_space is not None
    input_path = tmp_path / "evaluation.jsonl"
    input_path.write_text('{"query_id": "q1", "query": "liều"}\n', encoding="utf-8")
    monkeypatch.setattr(
        auto_profile,
        "ensure_runtime_profile",
        lambda **kwargs: SimpleNamespace(
            profile=SimpleNamespace(
                selected=search_space.query.candidates[0], measurements=()
            ),
            action="reuse",
        ),
    )
    monkeypatch.setattr(
        kaggle_service,
        "run_kaggle_stage",
        lambda **kwargs: pytest.fail("a dry run starts no session"),
    )

    result = KaggleQueryEmbeddingBackend().run(
        QueryEmbeddingRequest(
            evaluation_path=input_path,
            model=MODEL,
            output_dir=tmp_path / "cache.jsonl",
            force=False,
            dry_run=True,
            budget_seconds=21_600,
            request_timeout_seconds=5.0,
        )
    )

    assert result.incomplete
    assert any(action.startswith("planned_shards=1") for action in result.actions)


def test_a_list_of_accounts_profiles_the_runtime_on_the_first_one(
    tmp_path, monkeypatch, kaggle_sessions
):
    search_space = require_model(MODEL).embedding_search_space
    assert search_space is not None
    input_path = tmp_path / "evaluation.jsonl"
    input_path.write_text('{"query_id": "q1", "query": "liều"}\n', encoding="utf-8")
    profiled: list[str | None] = []

    def ensure(**kwargs):
        profiled.append(kwargs["kaggle_account"])
        return SimpleNamespace(
            profile=SimpleNamespace(
                selected=search_space.query.candidates[0], measurements=()
            ),
            action="reuse",
        )

    monkeypatch.setattr(auto_profile, "ensure_runtime_profile", ensure)

    KaggleQueryEmbeddingBackend().run(
        QueryEmbeddingRequest(
            evaluation_path=input_path,
            model=MODEL,
            output_dir=tmp_path / "cache.jsonl",
            force=False,
            dry_run=True,
            budget_seconds=21_600,
            request_timeout_seconds=5.0,
            kaggle_account="acc1,acc2",
        )
    )

    assert profiled == ["acc1"]
