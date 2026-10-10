"""Collections as owned, visible things: create, rename, share, delete (spec §3, §4.6)."""

import secrets
import uuid
from dataclasses import dataclass

from pydantic import BaseModel

from pharma_agent.application.corpus.errors import (
    CollectionNotFoundForActor,
    QuotaExceeded,
    SystemCollectionReadOnly,
)
from pharma_agent.application.errors import (
    ForbiddenRole,
    InvalidInput,
    OrganizationNotFound,
)
from pharma_agent.domain.access import policy
from pharma_agent.domain.access.models import Actor, Role
from pharma_agent.domain.account.ports import AccountRepository
from pharma_agent.domain.audit.models import AuditAction, AuditEvent, new_event
from pharma_agent.domain.audit.ports import AuditLog
from pharma_agent.domain.corpus.models import (
    Collection,
    CollectionOwner,
    Visibility,
    collection_id_for,
)
from pharma_agent.domain.corpus.ports import (
    CollectionRepository,
    CorpusRepository,
    VectorIndex,
)
from pharma_agent.domain.corpus.source import SourceRepository
from pharma_agent.domain.organizations.ports import OrganizationRepository
from pharma_agent.domain.shared.clock import Clock
from pharma_agent.domain.shared.transaction import TransactionFactory

TITLE_MAX_LENGTH = 200


__all__ = ["Visibility"]


@dataclass(frozen=True)
class QuotaPolicy:
    """Defaults of spec §2; users and organizations may carry their own overrides."""

    document_chars: int = 200_000
    documents_per_collection: int = 100
    user_text_bytes: int = 1_000_000
    user_collections: int = 5
    org_text_bytes: int = 5_000_000
    org_collections: int = 20


async def owner_limits(
    owner: CollectionOwner,
    *,
    organizations: OrganizationRepository,
    accounts: AccountRepository,
    quotas: QuotaPolicy,
) -> tuple[int, int]:
    """(text characters, collections) for the owner, its overrides first."""
    if owner.organization_id is not None:
        organization = await organizations.get(owner.organization_id)
        text = organization.text_quota_bytes if organization else None
        count = organization.collection_quota if organization else None
        return (
            text if text is not None else quotas.org_text_bytes,
            count if count is not None else quotas.org_collections,
        )
    user = None if owner.user_id is None else await accounts.get(owner.user_id)
    text = None if user is None else user.text_quota_bytes
    count = None if user is None else user.collection_quota
    return (
        text if text is not None else quotas.user_text_bytes,
        count if count is not None else quotas.user_collections,
    )


class CollectionView(BaseModel):
    id: uuid.UUID
    key: str
    title: str
    visibility: Visibility
    owner_user_id: uuid.UUID | None
    owner_organization_id: uuid.UUID | None
    owner_name: str
    is_system: bool
    can_edit: bool
    can_set_public: bool
    current_release_id: uuid.UUID | None
    current_release_number: int | None


class CollectionStats(BaseModel):
    """What the superadmin console shows per collection: size in Postgres and Qdrant."""

    collection: CollectionView
    documents: int
    qdrant_points: int


class OrganizationCollections(BaseModel):
    organization_id: uuid.UUID
    name: str
    role: Role | None
    items: list[CollectionView]


class CollectionGroups(BaseModel):
    public: list[CollectionView]
    organizations: list[OrganizationCollections]
    mine: list[CollectionView]
    # Only superadmins see collections that are neither public, theirs nor their orgs'.
    others: list[CollectionView]


class QuotaUsage(BaseModel):
    text_used: int
    text_limit: int
    collections_used: int
    collections_limit: int


class CollectionService:
    def __init__(
        self,
        *,
        collections: CollectionRepository,
        organizations: OrganizationRepository,
        accounts: AccountRepository,
        corpus: CorpusRepository,
        index: VectorIndex,
        audit: AuditLog,
        tx: TransactionFactory,
        clock: Clock,
        quotas: QuotaPolicy,
        sources: SourceRepository | None = None,
    ) -> None:
        self._sources = sources
        self._collections = collections
        self._organizations = organizations
        self._accounts = accounts
        self._corpus = corpus
        self._index = index
        self._audit = audit
        self._tx = tx
        self._clock = clock
        self._quotas = quotas

    # Views -------------------------------------------------------------------------

    async def _owner_name(self, collection: Collection) -> str:
        if collection.owner_organization_id is None:
            return ""
        organization = await self._organizations.get(collection.owner_organization_id)
        return "" if organization is None else organization.name

    async def _view(self, actor: Actor, collection: Collection) -> CollectionView:
        number = None
        if collection.current_release_id is not None:
            release = await self._corpus.get_release(collection.current_release_id)
            number = None if release is None else release.number
        return CollectionView(
            id=collection.id,
            key=collection.key,
            title=collection.title,
            visibility=collection.visibility,
            owner_user_id=collection.owner_user_id,
            owner_organization_id=collection.owner_organization_id,
            owner_name=await self._owner_name(collection),
            is_system=collection.is_system,
            can_edit=policy.can_edit_collection(actor, collection),
            can_set_public=policy.can_set_visibility(
                actor, collection, Visibility.PUBLIC
            ),
            current_release_id=collection.current_release_id,
            current_release_number=number,
        )

    async def _visible(self, actor: Actor, collection_id: uuid.UUID) -> Collection:
        collection = await self._collections.get(collection_id)
        if collection is None or not policy.can_view_collection(actor, collection):
            raise CollectionNotFoundForActor(str(collection_id))
        return collection

    async def _editable(self, actor: Actor, collection_id: uuid.UUID) -> Collection:
        collection = await self._visible(actor, collection_id)
        if collection.is_system and not actor.is_superadmin:
            raise SystemCollectionReadOnly("only superadmins change the system corpus")
        if not policy.can_edit_collection(actor, collection):
            raise ForbiddenRole("your role cannot change this collection")
        return collection

    async def visible(self, actor: Actor) -> CollectionGroups:
        public: list[CollectionView] = []
        mine: list[CollectionView] = []
        others: list[CollectionView] = []
        by_org: dict[uuid.UUID, list[CollectionView]] = {}
        for collection in await self._collections.visible_for(actor):
            view = await self._view(actor, collection)
            if collection.visibility is Visibility.PUBLIC:
                public.append(view)
            elif collection.owner_user_id == actor.user_id:
                mine.append(view)
            elif (
                collection.owner_organization_id is not None
                and actor.role_in(collection.owner_organization_id) is not None
            ):
                by_org.setdefault(collection.owner_organization_id, []).append(view)
            else:
                others.append(view)
        organizations = []
        for organization_id, items in by_org.items():
            organization = await self._organizations.get(organization_id)
            organizations.append(
                OrganizationCollections(
                    organization_id=organization_id,
                    name="" if organization is None else organization.name,
                    role=actor.role_in(organization_id),
                    items=items,
                )
            )
        organizations.sort(key=lambda group: (group.name, group.organization_id))
        return CollectionGroups(
            public=public, organizations=organizations, mine=mine, others=others
        )

    async def overview(self, actor: Actor) -> list[CollectionStats]:
        """Every live collection with its size; Qdrant is the first free tier to fill."""
        if not actor.is_superadmin:
            raise ForbiddenRole("only superadmins see the overview")
        stats = []
        for collection in await self._collections.visible_for(actor):
            points = (
                0
                if collection.current_release_id is None
                else await self._index.count_release(collection.current_release_id)
            )
            documents = (
                0
                if self._sources is None
                else await self._sources.count_documents(collection.id)
            )
            stats.append(
                CollectionStats(
                    collection=await self._view(actor, collection),
                    documents=documents,
                    qdrant_points=points,
                )
            )
        return stats

    async def get(self, actor: Actor, collection_id: uuid.UUID) -> CollectionView:
        return await self._view(actor, await self._visible(actor, collection_id))

    # Quotas --------------------------------------------------------------------------

    async def _limits(self, owner: CollectionOwner) -> tuple[int, int]:
        return await owner_limits(
            owner,
            organizations=self._organizations,
            accounts=self._accounts,
            quotas=self._quotas,
        )

    def _owner_for(
        self, actor: Actor, owner_organization_id: uuid.UUID | None
    ) -> CollectionOwner:
        if owner_organization_id is None:
            return CollectionOwner(user_id=actor.user_id)
        if not policy.can_view_organization(actor, owner_organization_id):
            raise OrganizationNotFound(str(owner_organization_id))
        return CollectionOwner(organization_id=owner_organization_id)

    async def quota(
        self, actor: Actor, *, owner_organization_id: uuid.UUID | None
    ) -> QuotaUsage:
        owner = self._owner_for(actor, owner_organization_id)
        text_limit, count_limit = await self._limits(owner)
        return QuotaUsage(
            text_used=0
            if self._sources is None
            else await self._sources.text_usage(owner),
            text_limit=text_limit,
            collections_used=await self._collections.count_owned(owner),
            collections_limit=count_limit,
        )

    # Changes ------------------------------------------------------------------------

    def _event(
        self,
        actor: Actor,
        action: AuditAction,
        collection: Collection,
        **details: object,
    ) -> AuditEvent:
        return new_event(
            actor,
            action,
            self._clock.now(),
            organization_id=collection.owner_organization_id,
            subject_user_id=collection.owner_user_id,
            collection_id=collection.id,
            title=collection.title,
            **details,
        )

    @staticmethod
    def _title(title: str) -> str:
        stripped = title.strip()
        if not stripped:
            raise InvalidInput("the title is required")
        if len(stripped) > TITLE_MAX_LENGTH:
            raise InvalidInput("the title is too long")
        return stripped

    async def create(
        self,
        actor: Actor,
        *,
        title: str,
        owner_organization_id: uuid.UUID | None,
    ) -> CollectionView:
        owner = self._owner_for(actor, owner_organization_id)
        if not policy.can_create_collection_for(
            actor,
            owner_user_id=owner.user_id,
            owner_organization_id=owner.organization_id,
        ):
            raise ForbiddenRole("your role cannot create collections here")
        clean_title = self._title(title)
        _, count_limit = await self._limits(owner)
        used = await self._collections.count_owned(owner)
        if used >= count_limit:
            raise QuotaExceeded(unit="collections", used=used, limit=count_limit)
        prefix = "o" if owner.organization_id is not None else "u"
        key = f"{prefix}-{secrets.token_hex(4)}"
        # The id follows the key, as for imported bundles, so publishing upserts onto it.
        collection = Collection(
            id=collection_id_for(key),
            key=key,
            title=clean_title,
            owner_user_id=owner.user_id,
            owner_organization_id=owner.organization_id,
            visibility=Visibility.PRIVATE,
        )
        now = self._clock.now()
        async with self._tx.begin() as tx:
            await self._collections.create(collection, now, tx)
            await self._audit.record(
                self._event(actor, AuditAction.COLLECTION_CREATED, collection), tx
            )
        return await self._view(actor, collection)

    async def rename(
        self, actor: Actor, collection_id: uuid.UUID, title: str
    ) -> CollectionView:
        collection = await self._editable(actor, collection_id)
        clean_title = self._title(title)
        async with self._tx.begin() as tx:
            await self._collections.rename(
                collection_id, clean_title, self._clock.now(), tx
            )
            await self._audit.record(
                self._event(
                    actor,
                    AuditAction.COLLECTION_RENAMED,
                    collection,
                    **{"from": collection.title, "to": clean_title},
                ),
                tx,
            )
        return await self.get(actor, collection_id)

    async def set_visibility(
        self, actor: Actor, collection_id: uuid.UUID, visibility: Visibility
    ) -> CollectionView:
        collection = await self._visible(actor, collection_id)
        if collection.is_system:
            raise SystemCollectionReadOnly("the system corpus is always public")
        if not policy.can_set_visibility(actor, collection, visibility):
            raise ForbiddenRole(f"your role cannot make this {visibility.value}")
        if collection.visibility is not visibility:
            async with self._tx.begin() as tx:
                await self._collections.set_visibility(
                    collection_id, visibility, self._clock.now(), tx
                )
                await self._audit.record(
                    self._event(
                        actor,
                        AuditAction.COLLECTION_VISIBILITY_CHANGED,
                        collection,
                        **{"from": collection.visibility.value, "to": visibility.value},
                    ),
                    tx,
                )
        return await self.get(actor, collection_id)

    async def delete(self, actor: Actor, collection_id: uuid.UUID) -> None:
        """Hide the collection at once, then retire its releases and drop its points.

        Rows that a conversation cites stay, so old answers keep their sources. The
        authored content goes: quotas no longer count it, so keeping it would let
        storage grow without bound.
        """
        collection = await self._editable(actor, collection_id)
        async with self._tx.begin() as tx:
            await self._collections.mark_deleted(collection_id, self._clock.now(), tx)
            if self._sources is not None:
                await self._sources.purge_content(collection_id, tx)
            await self._audit.record(
                self._event(actor, AuditAction.COLLECTION_DELETED, collection), tx
            )
        await self._discard(collection_id)

    async def purge_deleted(self) -> int:
        """Retire and unindex collections deleted along with their organization."""
        doomed = await self._collections.deleted_with_releases()
        for collection_id in doomed:
            await self._discard(collection_id)
        return len(doomed)

    async def _discard(self, collection_id: uuid.UUID) -> None:
        if self._sources is not None:
            async with self._tx.begin() as tx:
                await self._sources.purge_content(collection_id, tx)
        release_ids = await self._collections.live_release_ids(collection_id)
        if release_ids:
            items = await self._corpus.index_items(release_ids)
            await self._index.delete([item.chunk_version_id for item in items])
            await self._corpus.retire(release_ids, self._clock.now())
        await self._corpus.purge_retired(collection_id)
