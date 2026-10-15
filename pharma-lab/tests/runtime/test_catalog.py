import re

import pytest

from pharma_lab.config.defaults import DEFAULT_CANDIDATE_K
from pharma_lab.runtime.catalog import (
    KAGGLE_RERANK_REQUEST_BATCH_SIZE,
    MODEL_CATALOG,
    ModelKind,
    require_model,
)

CHAT_MODEL = "qwen3.5:9b-q8_0"

VIMED_FILES = {
    "qwen3-reranker:0.6b-q8_0": (
        "qwen3-reranker-0.6b-q8_0-vimed.gguf",
        639_153_216,
        "ec7dc43df4b778258631125d3366d1b4bc8543d9594fbd02650a0332db95180e",
    ),
    "qwen3-reranker:4b-q8_0": (
        "qwen3-reranker-4b-q8_0-vimed.gguf",
        4_279_678_912,
        "424c3a97b813b53760ffce9fe266fc85cc092c215a5adfef543200f7bde5e526",
    ),
    "qwen3-reranker:8b-q8_0": (
        "qwen3-reranker-8b-q8_0-vimed.gguf",
        8_047_134_176,
        "79011330370fdf760fd2d0bd87688826396e06843e682f58f51f60fc43969aef",
    ),
}


@pytest.mark.parametrize(("model", "expected"), sorted(VIMED_FILES.items()))
def test_qwen3_rerankers_serve_the_vietnamese_medical_template(
    model: str, expected: tuple[str, int, str]
) -> None:
    spec = require_model(model)

    assert (spec.canonical_filename, spec.byte_size, spec.sha256) == expected


def test_every_gguf_dataset_slug_is_a_valid_kaggle_slug() -> None:
    # Kaggle accepts lowercase letters, digits and "-" only, at most 50 characters.
    invalid = {
        name: spec.gguf_dataset_slug
        for name, spec in MODEL_CATALOG.items()
        if len(spec.gguf_dataset_slug) > 50
        or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", spec.gguf_dataset_slug)
    }

    assert invalid == {}


def test_the_open_weight_chat_model_is_the_published_q8_0_with_a_fixed_runtime() -> (
    None
):
    spec = require_model(CHAT_MODEL)

    assert spec.kind is ModelKind.CHAT
    assert (spec.canonical_filename, spec.byte_size, spec.sha256) == (
        "qwen3.5-9b-q8_0.gguf",
        9_527_502_048,
        "809626574d0cb43d4becfa56169980da2bb448f2299270f7be443cb89d0a6ae4",
    )
    assert spec.gguf_dataset_slug == "vector-cache-gguf-qwen3-5-9b-q8-0"
    assert spec.serve_runtime is not None
    assert spec.serve_runtime.context_per_slot == 32768
    assert spec.serve_runtime.concurrency == 2 * spec.serve_runtime.server_slots
    assert spec.rerank_search_space is None and spec.vector_dimension is None


def test_every_model_is_a_q8_0_file() -> None:
    assert all("q8_0" in spec.canonical_filename for spec in MODEL_CATALOG.values())


def test_a_kaggle_rerank_request_carries_one_whole_candidate_list() -> None:
    # The profile benchmark samples queries with exactly this many candidates, and the
    # backend sends one search round per request.
    assert KAGGLE_RERANK_REQUEST_BATCH_SIZE == DEFAULT_CANDIDATE_K
