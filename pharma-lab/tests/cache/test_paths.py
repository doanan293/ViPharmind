from pharma_lab.cache import paths as cache_paths
from pharma_lab.config import paths


def test_cache_files_are_named_after_the_model_slug() -> None:
    model = "qwen3-embedding:0.6b-q8_0"
    slug = "qwen3_embedding_0_6b_q8_0"

    assert cache_paths.text_embedding_cache_path(model) == (
        paths.TEXT_EMBEDDING_CACHE_DIR / f"{slug}.jsonl"
    )
    assert cache_paths.query_embedding_cache_path(model) == (
        paths.QUERY_EMBEDDING_CACHE_DIR / f"{slug}.jsonl"
    )
    assert cache_paths.rerank_score_cache_path("qwen3-reranker:0.6b-q8_0") == (
        paths.RERANK_SCORE_CACHE_DIR / "qwen3_reranker_0_6b_q8_0.jsonl"
    )


def test_rerank_logs_live_under_work(isolated_logs_dir) -> None:
    # tests/conftest.py redirects LOGS_DIR for every test; the original is the real value.
    assert isolated_logs_dir.original == paths.WORK_DIR / "logs"
    assert cache_paths.rerank_log_path("qwen3-reranker:0.6b-q8_0") == (
        isolated_logs_dir.root / "rerank" / "qwen3_reranker_0_6b_q8_0.log"
    )
