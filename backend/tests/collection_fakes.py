"""In-memory CollectionRepository sharing its collections with InMemoryCorpusRepository."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from pharma_agent.application.corpus.collections import CollectionService, QuotaPolicy
from pharma_agent.domain.access import policy
from pharma_agent.domain.access.models import Actor
from pharma_agent.domain.corpus.models import (
    Collection,
    CollectionOwner,
    ReleaseStatus,
    Visibility,
)
from pharma_agent.domain.shared.clock import Clock, FixedClock
from pharma_agent.domain.shared.transaction import Transaction
from tests.account_fakes import START, InMemoryAccounts
from tests.corpus_memory import InMemoryCorpusRepository, InMemoryVectorIndex
from tests.organization_fakes import (
    InMemoryAuditLog,
    InMemoryOrganizations,
    InMemoryTransactions,
    InMemoryTx,
)


def _tx(tx: Transaction) -> InMemoryTx:
    if not isinstance(tx, InMemoryTx):
        raise TypeError("expected an InMemoryTx")
    return tx


class InMemoryCollections:
    def __init__(self, corpus: InMemoryCorpusRepository) -> None:
        self.corpus = corpus
        self.deleted: set[uuid.UUID] = set()

    def _by_id(self, collection_id: uuid.UUID) -> Collection | None:
        return next(
            (c for c in self.corpus.collections.values() if c.id == collection_id),
            None,
        )

    def _store(self, collection: Collection) -> None:
        self.corpus.collections[collection.key] = collection

    def _live(self) -> list[Collection]:
        return [c for c in self.corpus.collections.values() if c.id not in self.deleted]

    async def get(self, collection_id: uuid.UUID) -> Collection | None:
        return None if collection_id in self.deleted else self._by_id(collection_id)

    async def visible_for(self, actor: Actor) -> list[Collection]:
        return sorted(
            (c for c in self._live() if policy.can_view_collection(actor, c)),
            key=lambda c: (c.title, c.id),
        )

    async def count_owned(self, owner: CollectionOwner) -> int:
        return sum(
            c.owner_user_id == owner.user_id
            and c.owner_organization_id == owner.organization_id
            for c in self._live()
        )

    async def create(
        self, collection: Collection, now: datetime, tx: Transaction
    ) -> None:
        _tx(tx).later(lambda: self._store(collection))

    def _update(self, collection_id: uuid.UUID, **values: object) -> None:
        current = self._by_id(collection_id)
        assert current is not None
        self._store(current.model_copy(update=values))

    async def rename(
        self, collection_id: uuid.UUID, title: str, now: datetime, tx: Transaction
    ) -> None:
        _tx(tx).later(lambda: self._update(collection_id, title=title))

    async def set_visibility(
        self,
        collection_id: uuid.UUID,
        visibility: Visibility,
        now: datetime,
        tx: Transaction,
    ) -> None:
        _tx(tx).later(lambda: self._update(collection_id, visibility=visibility))

    async def mark_deleted(
        self, collection_id: uuid.UUID, now: datetime, tx: Transaction
    ) -> None:
        def write() -> None:
            self.deleted.add(collection_id)
            self._update(collection_id, current_release_id=None)

        _tx(tx).later(write)

    async def current_releases(
        self, collection_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, uuid.UUID]:
        return {
            c.id: c.current_release_id
            for c in self._live()
            if c.id in collection_ids and c.current_release_id is not None
        }

    async def live_release_ids(self, collection_id: uuid.UUID) -> list[uuid.UUID]:
        return [
            r.id
            for r in self.corpus.releases.values()
            if r.collection_id == collection_id
            and r.status is not ReleaseStatus.RETIRED
        ]

    async def deleted_with_releases(self) -> list[uuid.UUID]:
        return [cid for cid in self.deleted if await self.live_release_ids(cid)]


def build_collection_service(
    corpus: InMemoryCorpusRepository,
    index: InMemoryVectorIndex,
    *,
    clock: Clock | None = None,
    collections: InMemoryCollections | None = None,
) -> CollectionService:
    accounts = InMemoryAccounts()
    return CollectionService(
        collections=collections or InMemoryCollections(corpus),
        organizations=InMemoryOrganizations(accounts),
        accounts=accounts,
        corpus=corpus,
        index=index,
        audit=InMemoryAuditLog(),
        tx=InMemoryTransactions(),
        clock=clock or FixedClock(START),
        quotas=QuotaPolicy(),
    )
