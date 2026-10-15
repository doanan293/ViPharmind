import pytest

from pharma_lab.runtime.catalog import RERANKER_MODELS, require_model
from pharma_lab.runtime.model_profiles import (
    EmbeddingRuntimeProfile,
    EmbeddingWorkloadProfile,
    RerankContract,
)


def test_rerank_contract_rejects_other_protocols():
    with pytest.raises(ValueError, match="unsupported rerank protocol"):
        RerankContract(protocol="completion_logprobs")


def test_embedding_profile_separates_query_and_corpus_workloads():
    profile = require_model("qwen3-embedding:4b-q8_0").embedding_runtime

    assert isinstance(profile, EmbeddingRuntimeProfile)
    assert isinstance(profile.query, EmbeddingWorkloadProfile)
    assert isinstance(profile.corpus, EmbeddingWorkloadProfile)
    assert profile.query is not profile.corpus
    assert profile.query.production_batch_size > 0
    assert profile.corpus.production_batch_size > 0


def test_embedding_slots_hold_the_longest_chunk():
    # Packed chunks reach about 3,200 Qwen3 tokens; one slot must embed one whole.
    spec = require_model("qwen3-embedding:4b-q8_0")
    assert spec.embedding_runtime is not None
    assert spec.embedding_runtime.context_per_slot == 4096
    assert spec.embedding_search_space is not None
    assert {
        c.context_per_slot for c in spec.embedding_search_space.corpus.candidates
    } == {4096}


def test_embedding_model_exposes_separate_runtime_search_spaces():
    search_space = require_model("qwen3-embedding:4b-q8_0").embedding_search_space

    assert search_space is not None
    assert search_space.query != search_space.corpus
    assert all(
        candidate.request_batch_size > 0 for candidate in search_space.query.candidates
    )


@pytest.mark.parametrize(
    ("model", "levels"),
    [
        ("qwen3-reranker:0.6b-q8_0", ((8, 4096, 4), (16, 4096, 4), (16, 4096, 8))),
        (
            "qwen3-reranker:4b-q8_0",
            ((4, 4096, 4), (8, 4096, 4), (8, 4096, 8), (12, 4096, 8)),
        ),
        ("qwen3-reranker:8b-q8_0", ((2, 4096, 2), (4, 4096, 4), (6, 4096, 4))),
        ("bge-reranker-v2-m3:q8_0", ((8, 4096, 4), (16, 4096, 4), (16, 4096, 8))),
    ],
)
def test_kaggle_rerank_search_space_pairs_slots_with_the_ubatch(
    model: str, levels: tuple[tuple[int, int, int], ...]
):
    spec = require_model(model)
    space = spec.rerank_search_space

    assert space is not None
    assert (
        tuple(
            (item.server_slots, item.physical_batch_size, item.concurrency)
            for item in space.candidates
        )
        == levels
    )
    for item in space.candidates:
        assert (item.request_batch_size, item.threads) == (20, None)
        assert item.context_per_slot == item.physical_batch_size
        assert item.logical_batch_size == item.physical_batch_size
    slots, ubatch, _concurrency = levels[0]
    assert (
        spec.kaggle_parallel,
        spec.kaggle_context_per_slot,
        spec.kaggle_physical_batch_size,
    ) == (slots, ubatch, ubatch)


@pytest.mark.parametrize("model", sorted(RERANKER_MODELS))
def test_local_rerank_search_space_sweeps_levels_and_threads(model: str):
    space = require_model(model).local_rerank_search_space

    assert space is not None
    assert [
        (item.server_slots, item.physical_batch_size, item.threads)
        for item in space.candidates
    ] == [(4, 4096, 8), (4, 4096, 12)]
    for item in space.candidates:
        assert (item.request_batch_size, item.concurrency) == (15, 1)
        assert item.context_per_slot == item.physical_batch_size
        assert item.logical_batch_size == item.physical_batch_size
