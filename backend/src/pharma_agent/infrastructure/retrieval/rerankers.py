"""The reranker PHARMA_RETRIEVAL__RERANK__PROTOCOL selects."""

import httpx

from pharma_agent.domain.retrieval.ports import Reranker
from pharma_agent.infrastructure.retrieval.llama_cpp_reranker import (
    NativeReranker,
    NoopReranker,
)
from pharma_agent.infrastructure.settings import RerankSettings


def build_reranker(settings: RerankSettings) -> Reranker:
    if settings.protocol == "none":
        return NoopReranker()
    headers = (
        {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else None
    )
    http = httpx.AsyncClient(
        base_url=settings.base_url, timeout=settings.timeout_seconds, headers=headers
    )
    return NativeReranker(
        http, model=settings.model, max_concurrent=settings.max_concurrent
    )
