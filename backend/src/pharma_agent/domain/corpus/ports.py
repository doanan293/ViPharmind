"""Ports the corpus application services depend on (adapters live in infrastructure)."""

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol

from pharma_agent.domain.access.models import Actor
from pharma_agent.domain.corpus.models import (
    Collection,
    CollectionOwner,
    CorpusSnapshot,
    IndexItem,
    PurgeResult,
    Release,
    ReleaseStats,
    ReleaseSummary,
    Visibility,
)
from pharma_agent.domain.shared.transaction import Transaction


class CorpusRepository(Protocol):
    async def get_collection(self, key: str) -> Collection | None: ...

    async def get_release(self, release_id: uuid.UUID) -> Release | None: ...

    async def find_release(
        self,
        collection_id: uuid.UUID,
        *,
        bundle_digest: str,
        chunker_version: str,
        embedding_model: str,
    ) -> Release | None:
        """Newest non-retired release of the collection built from the same inputs."""
        ...

    async def list_releases(self, collection_key: str | None) -> list[ReleaseSummary]:
        """Ordered by collection key, then release number descending."""
        ...

    async def stage_release(
        self,
        snapshot: CorpusSnapshot,
        *,
        release_id: uuid.UUID,
        embedding_model: str,
        at: datetime,
    ) -> Release:
        """Spec C §8.2 steps 3-6 in one transaction, idempotent.

        Upserts collection, documents and sections, inserts missing section revisions and
        chunk versions, and creates the release (status `building`, next number) with its
        `release_chunks` unless `release_id` already exists. Returns the stored release.
        """
        ...

    async def index_items(self, release_ids: Sequence[uuid.UUID]) -> list[IndexItem]:
        """Items for every chunk version in the releases; `release_ids` of each item lists
        the non-retired releases containing it (possibly empty)."""
        ...

    async def mark_ready(
        self, release_id: uuid.UUID, stats: ReleaseStats, at: datetime
    ) -> None: ...

    async def publish(self, release_id: uuid.UUID, at: datetime) -> None:
        """One transaction: collection.current_release_id and first published_at."""
        ...

    async def retire(self, release_ids: Sequence[uuid.UUID], at: datetime) -> None: ...

    async def purge_retired(self, collection_id: uuid.UUID) -> PurgeResult:
        """Spec C §8.5 steps 3-4 for every retired release of the collection.

        Then deletes the collection's sections that no section revision or release chunk
        references, and the documents left without sections.
        """
        ...


class Embedder(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class VectorIndex(Protocol):
    """Derived index of chunk versions for one embedding model."""

    async def ensure_collection(self) -> str:
        """Create the physical collection, payload indexes and alias when missing; verify
        metadata otherwise (raises IndexMismatch). Returns the physical name."""
        ...

    async def existing_ids(self, ids: Sequence[uuid.UUID]) -> set[uuid.UUID]: ...

    async def upsert(
        self, items: Sequence[IndexItem], vectors: Mapping[str, Sequence[float]]
    ) -> None:
        """Write points; `vectors` is keyed by embedding_text_sha256."""
        ...

    async def set_release_ids(self, items: Sequence[IndexItem]) -> None:
        """Overwrite the `release_ids` payload of existing points."""
        ...

    async def delete(self, ids: Sequence[uuid.UUID]) -> None: ...

    async def delete_unreleased(
        self, collection_id: uuid.UUID, live_release_ids: Sequence[uuid.UUID]
    ) -> int:
        """Delete the collection's points that name none of `live_release_ids`, such as
        points left after their rows were removed from Postgres. Returns the count."""
        ...

    async def count_release(self, release_id: uuid.UUID) -> int: ...


class CollectionRepository(Protocol):
    """Collections as things people own and see. Deleted collections are invisible here."""

    async def get(self, collection_id: uuid.UUID) -> Collection | None: ...

    async def visible_for(self, actor: Actor) -> list[Collection]:
        """Every collection the actor may see, by the rules of domain/access/policy."""
        ...

    async def count_owned(self, owner: CollectionOwner) -> int: ...

    async def create(
        self, collection: Collection, now: datetime, tx: Transaction
    ) -> None: ...

    async def rename(
        self, collection_id: uuid.UUID, title: str, now: datetime, tx: Transaction
    ) -> None: ...

    async def set_visibility(
        self,
        collection_id: uuid.UUID,
        visibility: Visibility,
        now: datetime,
        tx: Transaction,
    ) -> None: ...

    async def mark_deleted(
        self, collection_id: uuid.UUID, now: datetime, tx: Transaction
    ) -> None:
        """Hide the collection and clear its current release."""
        ...

    async def current_releases(
        self, collection_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, uuid.UUID]:
        """collection_id -> current release for live collections that have one."""
        ...

    async def live_release_ids(self, collection_id: uuid.UUID) -> list[uuid.UUID]:
        """Releases that are not retired, deleted collections included."""
        ...

    async def deleted_with_releases(self) -> list[uuid.UUID]:
        """Deleted collections that still have live releases or authored content to clean."""
        ...
