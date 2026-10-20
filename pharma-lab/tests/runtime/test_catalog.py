import pytest

from pharma_lab.runtime.catalog import (
    MODEL_CATALOG,
    ModelKind,
    ModelTopology,
    require_model,
)

CHAT_MODEL = "qwen3.5:9b-f16"

VIMED_FILES = {
    "qwen3-reranker:0.6b-fp16": (
        "qwen3-reranker-0.6b-f16-vimed.gguf",
        1_197_634_336,
        "fa17b7c742ffeeb6f80529e50c9c35a8179c4369baa4a039ef94381c0665f851",
    ),
    "qwen3-reranker:4b-fp16": (
        "qwen3-reranker-4b-f16-vimed.gguf",
        8_049_922_912,
        "4b428e981efc9a209c674a0af9f1ec527b5570896e0bcc431382c16f1e839c7a",
    ),
    "qwen3-reranker:8b-fp16": (
        "qwen3-reranker-8b-f16-vimed.gguf",
        15_141_207_776,
        "c6516333e32d4f1d8aad8325d5d5bdb8165f9778e892eed4ca8b0eaf3339a810",
    ),
}


@pytest.mark.parametrize(("model", "expected"), sorted(VIMED_FILES.items()))
def test_qwen3_rerankers_serve_the_vietnamese_medical_template(
    model: str, expected: tuple[str, int, str]
) -> None:
    spec = require_model(model)

    assert (spec.canonical_filename, spec.byte_size, spec.sha256) == expected


def test_every_gguf_dataset_slug_fits_the_kaggle_limit() -> None:
    too_long = {
        name: spec.gguf_dataset_slug
        for name, spec in MODEL_CATALOG.items()
        if len(spec.gguf_dataset_slug) > 50
    }

    assert too_long == {}


def test_the_open_weight_chat_model_is_served_sharded_with_a_fixed_runtime() -> None:
    spec = require_model(CHAT_MODEL)

    assert spec.kind is ModelKind.CHAT
    assert spec.topology is ModelTopology.SHARDED_1X2
    assert (spec.canonical_filename, spec.byte_size, spec.sha256) == (
        "qwen3.5-9b-f16.gguf",
        17_920_697_312,
        "863a67e28486f4c3ad7a30c49614a398d5a07caf8d0067a018d0e5f0abf79f2d",
    )
    assert spec.gguf_dataset_slug == "vector-cache-gguf-qwen3-5-9b-f16"
    assert spec.serve_runtime is not None
    assert spec.serve_runtime.context_per_slot >= 16384
    assert spec.rerank_search_space is None and spec.vector_dimension is None


def test_q8_models_point_at_the_published_kaggle_datasets() -> None:
    reranker = require_model("qwen3-reranker:4b-q8_0")
    chat = require_model("qwen3.5:9b-q8_0")

    assert reranker.kind is ModelKind.RERANKER
    assert (reranker.canonical_filename, reranker.byte_size, reranker.sha256) == (
        "qwen3-reranker-4b-q8_0-vimed.gguf",
        4_279_678_912,
        "424c3a97b813b53760ffce9fe266fc85cc092c215a5adfef543200f7bde5e526",
    )
    # Kaggle slugs allow letters, digits and "-" only.
    assert (
        reranker.gguf_dataset_slug == "vector-cache-gguf-qwen3-reranker-4b-q8-0-vimed"
    )
    assert chat.kind is ModelKind.CHAT
    assert chat.topology is ModelTopology.SHARDED_1X2
    assert (chat.canonical_filename, chat.byte_size, chat.sha256) == (
        "qwen3.5-9b-q8_0.gguf",
        9_527_502_048,
        "809626574d0cb43d4becfa56169980da2bb448f2299270f7be443cb89d0a6ae4",
    )
    assert chat.gguf_dataset_slug == "vector-cache-gguf-qwen3-5-9b-q8-0"
    assert chat.serve_runtime == require_model(CHAT_MODEL).serve_runtime


def test_slugs_of_the_v1_models_do_not_change() -> None:
    assert require_model("qwen3-embedding:4b-fp16").gguf_dataset_slug == (
        "vector-cache-gguf-qwen3-embedding-4b-fp16"
    )
    assert require_model("qwen3-reranker:4b-fp16").gguf_dataset_slug == (
        "vector-cache-gguf-qwen3-reranker-4b-f16-vimed"
    )
