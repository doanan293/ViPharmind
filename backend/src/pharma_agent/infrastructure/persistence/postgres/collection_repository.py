"""CollectionRepository over `corpus.collections`; deleted rows are invisible here."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import (
    ColumnElement,
    and_,
    false,
    func,
    insert,
    or_,
    select,
    true,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.domain.access.models import ROLE_RANK, Actor, Role
from pharma_agent.domain.corpus.models import (
    Collection,
    CollectionOwner,
    ReleaseStatus,
    Visibility,
)
from pharma_agent.domain.shared.transaction import Transaction
from pharma_agent.infrastructure.persistence.postgres.corpus_tables import (
    CollectionTable,
    ReleaseTable,
)
from pharma_agent.infrastructure.persistence.postgres.transaction import session_of

_c = CollectionTable.__table__.c
_r = ReleaseTable.__table__.c


def _collection(row: CollectionTable) -> Collection:
    return Collection(
        id=row.id,
        key=row.key,
        title=row.title,
        owner_user_id=row.owner_user_id,
        owner_organization_id=row.owner_organization_id,
        visibility=Visibility(row.visibility),
        current_release_id=row.current_release_id,
    )


def visible_condition(actor: Actor) -> ColumnElement[bool]:
    """SQL form of domain/access/policy.can_view_collection for live collections."""
    if actor.is_superadmin:
        return true()
    members = list(actor.memberships)
    editors = [
        organization_id
        for organization_id, role in actor.memberships.items()
        if ROLE_RANK[role] >= ROLE_RANK[Role.EDITOR]
    ]
    return or_(
        _c.visibility == Visibility.PUBLIC.value,
        _c.owner_user_id == actor.user_id,
        and_(
            _c.owner_organization_id.in_(members),
            _c.visibility == Visibility.ORGANIZATION.value,
        )
        if members
        else false(),
        _c.owner_organization_id.in_(editors) if editors else false(),
    )


def _owned_by(owner: CollectionOwner) -> ColumnElement[bool]:
    return and_(
        _c.owner_user_id.is_(None)
        if owner.user_id is None
        else _c.owner_user_id == owner.user_id,
        _c.owner_organization_id.is_(None)
        if owner.organization_id is None
        else _c.owner_organization_id == owner.organization_id,
    )


class PostgresCollectionRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get(self, collection_id: uuid.UUID) -> Collection | None:
        query = select(CollectionTable).where(
            _c.id == collection_id, _c.deleted_at.is_(None)
        )
        async with self._sessions() as session:
            row = (await session.scalars(query)).first()
        return None if row is None else _collection(row)

    async def visible_for(self, actor: Actor) -> list[Collection]:
        query = (
            select(CollectionTable)
            .where(_c.deleted_at.is_(None), visible_condition(actor))
            .order_by(_c.title, _c.id)
        )
        async with self._sessions() as session:
            rows = (await session.scalars(query)).all()
        return [_collection(row) for row in rows]

    async def count_owned(self, owner: CollectionOwner) -> int:
        query = select(func.count()).where(_c.deleted_at.is_(None), _owned_by(owner))
        async with self._sessions() as session:
            return (await session.execute(query)).scalar_one()

    async def create(
        self, collection: Collection, now: datetime, tx: Transaction
    ) -> None:
        await session_of(tx).execute(
            insert(CollectionTable).values(
                id=collection.id,
                key=collection.key,
                title=collection.title,
                owner_user_id=collection.owner_user_id,
                owner_organization_id=collection.owner_organization_id,
                visibility=collection.visibility.value,
                created_at=now,
                updated_at=now,
            )
        )

    async def _update(
        self, collection_id: uuid.UUID, tx: Transaction, **values: object
    ) -> None:
        await session_of(tx).execute(
            update(CollectionTable).where(_c.id == collection_id).values(**values)
        )

    async def rename(
        self, collection_id: uuid.UUID, title: str, now: datetime, tx: Transaction
    ) -> None:
        await self._update(collection_id, tx, title=title, updated_at=now)

    async def set_visibility(
        self,
        collection_id: uuid.UUID,
        visibility: Visibility,
        now: datetime,
        tx: Transaction,
    ) -> None:
        await self._update(
            collection_id, tx, visibility=visibility.value, updated_at=now
        )

    async def mark_deleted(
        self, collection_id: uuid.UUID, now: datetime, tx: Transaction
    ) -> None:
        await self._update(
            collection_id, tx, deleted_at=now, current_release_id=None, updated_at=now
        )

    async def current_releases(
        self, collection_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, uuid.UUID]:
        if not collection_ids:
            return {}
        query = select(_c.id, _c.current_release_id).where(
            _c.id.in_(list(collection_ids)),
            _c.deleted_at.is_(None),
            _c.current_release_id.is_not(None),
        )
        async with self._sessions() as session:
            rows = (await session.execute(query)).tuples().all()
        return dict(rows)

    async def live_release_ids(self, collection_id: uuid.UUID) -> list[uuid.UUID]:
        query = select(_r.id).where(
            _r.collection_id == collection_id,
            _r.status != ReleaseStatus.RETIRED.value,
        )
        async with self._sessions() as session:
            return list((await session.scalars(query)).all())

    async def deleted_with_releases(self) -> list[uuid.UUID]:
        query = (
            select(_c.id)
            .join(ReleaseTable, _r.collection_id == _c.id)
            .where(
                _c.deleted_at.is_not(None),
                _r.status != ReleaseStatus.RETIRED.value,
            )
            .distinct()
        )
        async with self._sessions() as session:
            return list((await session.scalars(query)).all())
