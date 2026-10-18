import json
from types import SimpleNamespace

from pharma_lab.artifacts.manifest import Completion
from pharma_lab.evaluation.query_embedding_cache import QueryEmbeddingCache
from pharma_lab.evaluation.query_embedding_service import (
    KaggleQueryEmbeddingBackend,
    QueryEmbeddingRequest,
)
from pharma_lab.integrations.kaggle import auto_profile
from pharma_lab.integrations.kaggle import service as kaggle_service
from pharma_lab.runtime.catalog import require_model

MODEL = "qwen3-embedding:4b-q8_0"


def test_kaggle_query_embedding_propagates_selected_account(tmp_path, monkeypatch):
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
                profile=SimpleNamespace(selected=selected), action="reuse"
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
            budget_seconds=60,
            request_timeout_seconds=5.0,
            kaggle_account="acc2",
        )
    )

    assert result.incomplete
    assert seen == [("profile", "acc2"), ("stage", "acc2")]


def test_kaggle_query_embedding_sends_only_uncached_questions(tmp_path, monkeypatch):
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
        sent.extend(
            json.loads(line)["query_id"]
            for line in kwargs["input_path"].read_text("utf-8").splitlines()
        )
        return SimpleNamespace(
            artifact_path=None, completion=Completion(1, 0, 1), actions=()
        )

    search_space = spec.embedding_search_space
    assert search_space is not None
    monkeypatch.setattr(
        auto_profile,
        "ensure_runtime_profile",
        lambda **kwargs: SimpleNamespace(
            profile=SimpleNamespace(selected=search_space.query.candidates[0]),
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
        budget_seconds=60,
        request_timeout_seconds=5.0,
    )
    KaggleQueryEmbeddingBackend().run(request)
    assert sent == ["q2"]

    # With every question cached, Kaggle is not called at all.
    cache.set(
        MODEL, "q2", "tác dụng phụ ibuprofen", [0.2] * (spec.vector_dimension or 4)
    )
    sent.clear()
    result = KaggleQueryEmbeddingBackend().run(request)
    assert sent == [] and not result.incomplete and result.subset_sha256
