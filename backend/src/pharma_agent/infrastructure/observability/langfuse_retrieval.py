"""Langfuse observations for retrieval steps the OpenAI integration cannot see."""

from collections.abc import Sequence

from langfuse import Langfuse

from pharma_agent.domain.retrieval.models import Hit
from pharma_agent.domain.retrieval.ports import Reranker, RetrievalError

RERANK_OBSERVATION_NAME = "rerank"


class LangfuseTracedReranker:
    """Records each rerank call as a `retriever` observation inside the current trace."""

    def __init__(
        self, inner: Reranker, client: Langfuse, *, protocol: str, model: str
    ) -> None:
        """Wrap `inner`; `protocol` and `model` go into each observation's metadata."""
        self._inner = inner
        self._client = client
        self._metadata = {"protocol": protocol, "model": model}

    async def rerank(self, query: str, hits: Sequence[Hit], top_n: int) -> list[Hit]:
        """Rerank with the inner reranker and record the candidates and scores.

        Raises:
            RetrievalError: From the inner reranker, after marking the observation as an
                error.
        """
        with self._client.start_as_current_observation(
            name=RERANK_OBSERVATION_NAME,
            as_type="retriever",
            input={"query": query, "candidates": len(hits), "top_n": top_n},
            metadata=self._metadata,
        ) as observation:
            try:
                ranked = await self._inner.rerank(query, hits, top_n)
            except RetrievalError as exc:
                observation.update(level="ERROR", status_message=str(exc))
                raise
            observation.update(
                output=[
                    {
                        "chunk_version_id": str(hit.chunk_version_id),
                        "rerank_score": hit.rerank_score,
                    }
                    for hit in ranked
                ]
            )
            return ranked

    async def aclose(self) -> None:
        """Close the inner reranker when it can be closed."""
        close = getattr(self._inner, "aclose", None)
        if close is not None:
            await close()
