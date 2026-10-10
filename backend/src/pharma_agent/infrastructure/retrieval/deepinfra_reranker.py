"""Qwen3-Reranker on DeepInfra's inference endpoint (production, spec §2).

DeepInfra pairs `queries[i]` with `documents[i]` and returns one score per pair, so the
query is repeated for every candidate.
"""

import asyncio
from collections.abc import Sequence

import httpx

from pharma_agent.domain.retrieval.models import Hit
from pharma_agent.domain.retrieval.ports import RetrievalError
from pharma_agent.infrastructure.retrieval.llama_cpp_reranker import (
    document_text,
    sorted_top,
)


class DeepInfraReranker:
    def __init__(
        self, http: httpx.AsyncClient, *, model: str, max_concurrent: int = 2
    ) -> None:
        self._http = http
        self._model = model
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def rerank(self, query: str, hits: Sequence[Hit], top_n: int) -> list[Hit]:
        if not hits:
            return []
        body = {
            "queries": [query] * len(hits),
            "documents": [document_text(h) for h in hits],
        }
        try:
            async with self._semaphore:
                response = await self._http.post(
                    f"/v1/inference/{self._model}", json=body
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RetrievalError(f"rerank request failed: {exc}") from exc
        scores = payload.get("scores") if isinstance(payload, dict) else None
        if not isinstance(scores, list) or len(scores) != len(hits):
            raise RetrievalError("rerank response does not score every candidate")
        return sorted_top(hits, [float(s) for s in scores], top_n)
