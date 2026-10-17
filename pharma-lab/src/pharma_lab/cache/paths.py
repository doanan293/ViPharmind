"""Cache and log files of one model, named after the catalog slug."""

from __future__ import annotations

from pathlib import Path

from pharma_lab.config import paths as layout
from pharma_lab.runtime.catalog import require_model


def query_embedding_cache_path(model: str) -> Path:
    return layout.QUERY_EMBEDDING_CACHE_DIR / f"{require_model(model).slug}.jsonl"


def text_embedding_cache_path(model: str) -> Path:
    return layout.TEXT_EMBEDDING_CACHE_DIR / f"{require_model(model).slug}.jsonl"


def rerank_score_cache_path(model: str) -> Path:
    return layout.RERANK_SCORE_CACHE_DIR / f"{require_model(model).slug}.jsonl"


def rerank_log_path(model: str) -> Path:
    return layout.LOGS_DIR / "rerank" / f"{require_model(model).slug}.log"
