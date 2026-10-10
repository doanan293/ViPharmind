import uuid

import pytest

from pharma_agent.application.corpus.collections import (
    CollectionService,
    QuotaPolicy,
)
from pharma_agent.application.corpus.errors import (
    CollectionNotFoundForActor,
    QuotaExceeded,
    SystemCollectionReadOnly,
)
from pharma_agent.application.errors import ForbiddenRole
from pharma_agent.domain.access.models import Actor, Role
from pharma_agent.domain.audit.models import AuditAction
from pharma_agent.domain.corpus.bundle import GlossaryEntry
from pharma_agent.domain.corpus.models import (
    Collection,
    CollectionOwner,
    Visibility,
    collection_id_for,
)
from pharma_agent.domain.corpus.source import DocumentKind, SourceDocument
from pharma_agent.domain.organizations.models import Organization
from tests.account_fakes import START, InMemoryAccounts, MutableClock
from tests.collection_fakes import InMemoryCollections, InMemorySources
from tests.corpus_fixtures import small_bundle, small_bundle_embeddings
from tests.corpus_memory import CorpusAdapters, build_importer
from tests.fakes import FakeEmbedder
from tests.organization_fakes import (
    InMemoryAuditLog,
    InMemoryOrganizations,
    InMemoryTransactions,
    actor,
)


class World:
    def __init__(self) -> None:
        self.clock = MutableClock()
        self.accounts = InMemoryAccounts()
        self.organizations = InMemoryOrganizations(self.accounts)
        self.adapters = CorpusAdapters()
        self.collections = InMemoryCollections(self.adapters.repository)
        self.audit = InMemoryAuditLog()
        self.sources = InMemorySources(self.collections)
        self.me = self.accounts.add(email="me@example.com").id
        self.org = Organization(uuid.uuid4(), "Khoa Dược", None, None, START, START)
        self.organizations.organizations[self.org.id] = self.org
        self.organizations.seed_member(self.org.id, self.me, Role.OWNER)
        self.service = CollectionService(
            collections=self.collections,
            organizations=self.organizations,
            accounts=self.accounts,
            corpus=self.adapters.repository,
            index=self.adapters.index,
            audit=self.audit,
            tx=InMemoryTransactions(),
            clock=self.clock,
            quotas=QuotaPolicy(user_collections=2, org_collections=3),
            sources=self.sources,
        )

    def owner(self) -> Actor:
        return actor(self.me, {self.org.id: Role.OWNER})


async def test_create_groups_and_ids_follow_the_key() -> None:
    w = World()
    personal = await w.service.create(
        w.owner(), title="Ghi chú", owner_organization_id=None
    )
    shared = await w.service.create(
        w.owner(), title="Thuốc tim mạch", owner_organization_id=w.org.id
    )
    assert personal.key.startswith("u-") and shared.key.startswith("o-")
    assert personal.id == collection_id_for(personal.key)
    assert personal.visibility is Visibility.PRIVATE and personal.can_edit
    groups = await w.service.visible(w.owner())
    assert [c.id for c in groups.mine] == [personal.id]
    assert [(g.name, [c.id for c in g.items]) for g in groups.organizations] == [
        ("Khoa Dược", [shared.id])
    ]
    assert w.audit.actions() == [AuditAction.COLLECTION_CREATED] * 2
    assert w.audit.events[0].subject_user_id == w.me


async def test_quotas_limit_the_number_of_collections() -> None:
    w = World()
    for title in ("a", "b"):
        await w.service.create(w.owner(), title=title, owner_organization_id=None)
    with pytest.raises(QuotaExceeded) as exceeded:
        await w.service.create(w.owner(), title="c", owner_organization_id=None)
    assert (exceeded.value.used, exceeded.value.limit) == (2, 2)
    usage = await w.service.quota(w.owner(), owner_organization_id=None)
    assert (usage.collections_used, usage.collections_limit) == (2, 2)


async def test_members_cannot_create_in_the_organization_and_outsiders_see_nothing() -> (
    None
):
    w = World()
    member = actor(uuid.uuid4(), {w.org.id: Role.MEMBER})
    with pytest.raises(ForbiddenRole):
        await w.service.create(member, title="x", owner_organization_id=w.org.id)
    draft = await w.service.create(
        w.owner(), title="Nháp", owner_organization_id=w.org.id
    )
    with pytest.raises(CollectionNotFoundForActor):
        await w.service.get(member, draft.id)
    await w.service.set_visibility(w.owner(), draft.id, Visibility.ORGANIZATION)
    assert (await w.service.get(member, draft.id)).can_edit is False
    with pytest.raises(CollectionNotFoundForActor):
        await w.service.get(actor(uuid.uuid4()), draft.id)


async def test_only_superadmin_makes_a_collection_public() -> None:
    w = World()
    created = await w.service.create(
        w.owner(), title="x", owner_organization_id=w.org.id
    )
    with pytest.raises(ForbiddenRole):
        await w.service.set_visibility(w.owner(), created.id, Visibility.PUBLIC)
    admin = actor(uuid.uuid4(), superadmin=True)
    public = await w.service.set_visibility(admin, created.id, Visibility.PUBLIC)
    assert public.visibility is Visibility.PUBLIC
    changed = w.audit.events[-1]
    assert changed.action is AuditAction.COLLECTION_VISIBILITY_CHANGED
    assert changed.details == {"title": "x", "from": "private", "to": "public"}
    assert changed.actor_was_superadmin


async def test_system_collections_are_read_only_for_everyone_else() -> None:
    w = World()
    await build_importer(w.adapters, FakeEmbedder())(
        small_bundle(), embeddings=small_bundle_embeddings, publish=True
    )
    system = collection_id_for("formulary")
    view = await w.service.get(w.owner(), system)
    assert view.is_system and not view.can_edit and view.current_release_number == 1
    with pytest.raises(SystemCollectionReadOnly):
        await w.service.rename(w.owner(), system, "x")
    assert [c.id for c in (await w.service.visible(w.owner())).public] == [system]


async def test_delete_hides_at_once_and_removes_the_points() -> None:
    w = World()
    created = await w.service.create(w.owner(), title="x", owner_organization_id=None)
    bundle = small_bundle().model_copy(deep=True)
    bundle.manifest.collection.key = created.key
    await build_importer(w.adapters, FakeEmbedder())(
        bundle, embeddings=small_bundle_embeddings, publish=True
    )
    assert w.adapters.index.points
    await w.service.delete(w.owner(), created.id)
    with pytest.raises(CollectionNotFoundForActor):
        await w.service.get(w.owner(), created.id)
    assert (await w.service.visible(w.owner())).mine == []
    assert w.adapters.index.points == {}
    assert await w.collections.current_releases([created.id]) == {}
    assert w.audit.actions()[-1] is AuditAction.COLLECTION_DELETED


def test_collection_owner_is_one_of_user_organization_or_system() -> None:
    assert CollectionOwner(user_id=uuid.uuid4()).organization_id is None
    with pytest.raises(ValueError):
        CollectionOwner(user_id=uuid.uuid4(), organization_id=uuid.uuid4())
    assert CollectionOwner().is_system
    assert Collection(id=uuid.uuid4(), key="k", title="t").is_system


async def test_purge_deleted_cleans_collections_of_a_deleted_organization() -> None:
    w = World()
    created = await w.service.create(
        w.owner(), title="x", owner_organization_id=w.org.id
    )
    bundle = small_bundle().model_copy(deep=True)
    bundle.manifest.collection.key = created.key
    await build_importer(w.adapters, FakeEmbedder())(
        bundle, embeddings=small_bundle_embeddings, publish=True
    )
    # What deleting the organization does to its collections in the repository.
    w.collections.deleted.add(created.id)
    assert await w.service.purge_deleted() == 1
    assert w.adapters.index.points == {}
    assert await w.service.purge_deleted() == 0


async def test_delete_drops_the_authored_content_so_quotas_stay_honest() -> None:
    w = World()
    created = await w.service.create(w.owner(), title="x", owner_organization_id=None)
    tx = InMemoryTransactions()
    async with tx.begin() as t:
        await w.sources.create_document(
            SourceDocument(
                id=uuid.uuid4(),
                collection_id=created.id,
                key=f"{created.key}:a",
                title="A",
                kind=DocumentKind.LEAFLET,
                source_title="",
                source_url=None,
                markdown="x" * 10,
                char_count=10,
                created_by=None,
                created_at=START,
                updated_by=None,
                updated_at=START,
            ),
            t,
        )
        await w.sources.replace_glossary(created.id, [GlossaryEntry(term="IV")], t)
    await w.service.delete(w.owner(), created.id)
    assert await w.sources.count_documents(created.id) == 0
    assert await w.sources.glossary(created.id) == []
