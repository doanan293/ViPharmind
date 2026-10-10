"""Embed and index the chunks of a release, batch by batch (spec C §8.2 steps 7-8).

Vectors never pile up in memory and never touch Postgres: each batch takes its vectors from
the bundle or the embedder and goes to Qdrant at once. A rerun after a failure skips the
points Qdrant already holds, so it resumes where the last run stopped.
"""

import asyncio
import itertools
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from pharma_agent.domain.corpus.models import CorpusImportError, IndexItem
from pharma_agent.domain.corpus.ports import Embedder, VectorIndex


class IndexCounts(BaseModel):
    model_config = ConfigDict(frozen=True)

    upserted: int
    updated: int
    embeddings_from_bundle: int
    embeddings_computed: int


class IndexWriter:
    def __init__(
        self,
        index: VectorIndex,
        embedder: Embedder,
        *,
        batch_size: int,
        max_concurrent: int,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        self._index = index
        self._embedder = embedder
        self._batch_size = batch_size
        self._max_concurrent = max_concurrent

    async def write(
        self,
        items: Sequence[IndexItem],
        *,
        bundled: Mapping[str, Sequence[float]],
        overwrite: bool = False,
    ) -> IndexCounts:
        """Upsert the points Qdrant lacks (all of them with `overwrite`) and refresh the
        release ids of the rest. Counts are per point."""
        if overwrite:
            new, existing = list(items), []
        else:
            present = await self._index.existing_ids(
                [item.chunk_version_id for item in items]
            )
            new = [item for item in items if item.chunk_version_id not in present]
            existing = [item for item in items if item.chunk_version_id in present]
        batches = itertools.batched(new, self._batch_size)
        counts = {"bundle": 0, "computed": 0}

        async def worker() -> None:
            # The workers share one iterator, so each takes the next unclaimed batch.
            for batch in batches:
                await self._write_batch(batch, bundled, counts)

        try:
            async with asyncio.TaskGroup() as group:
                for _ in range(self._max_concurrent):
                    group.create_task(worker())
        except ExceptionGroup as errors:
            raise errors.exceptions[0] from errors
        if existing:
            await self._index.set_release_ids(existing)
        return IndexCounts(
            upserted=len(new),
            updated=len(existing),
            embeddings_from_bundle=counts["bundle"],
            embeddings_computed=counts["computed"],
        )

    async def _write_batch(
        self,
        batch: Sequence[IndexItem],
        bundled: Mapping[str, Sequence[float]],
        counts: dict[str, int],
    ) -> None:
        vectors: dict[str, Sequence[float]] = {}
        texts: dict[str, str] = {}
        for item in batch:
            sha = item.embedding_text_sha256
            if sha in bundled:
                vectors[sha] = bundled[sha]
                counts["bundle"] += 1
            else:
                texts.setdefault(sha, item.embedding_text)
                counts["computed"] += 1
        if texts:
            hashes = list(texts)
            embedded = await self._embedder.embed([texts[sha] for sha in hashes])
            dimension = self._embedder.dimension
            if len(embedded) != len(hashes) or any(
                len(vector) != dimension for vector in embedded
            ):
                raise CorpusImportError(
                    f"{self._embedder.model} returned {len(embedded)} vectors for "
                    f"{len(hashes)} texts, or vectors without {dimension} dims"
                )
            vectors.update(zip(hashes, embedded, strict=True))
        await self._index.upsert(batch, vectors)
