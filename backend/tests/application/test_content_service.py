import uuid

import pytest

from pharma_agent.application.corpus.collections import CollectionService, QuotaPolicy
from pharma_agent.application.corpus.content import ContentService, DocumentInput
from pharma_agent.application.corpus.errors import (
    CollectionNotFoundForActor,
    QuotaExceeded,
    SystemCollectionReadOnly,
)
from pharma_agent.application.errors import ForbiddenRole, InvalidInput
from pharma_agent.domain.access.models import Actor, Role
from pharma_agent.domain.audit.models import AuditAction
from pharma_agent.domain.corpus.bundle import ColloquialMappingRecord, GlossaryEntry
from pharma_agent.domain.corpus.models import Collection, Visibility, collection_id_for
from pharma_agent.domain.organizations.models import Organization
from tests.account_fakes import START, InMemoryAccounts, MutableClock
from tests.collection_fakes import InMemoryCollections, InMemorySources
from tests.corpus_memory import CorpusAdapters
from tests.organization_fakes import (
    InMemoryAuditLog,
    InMemoryOrganizations,
    InMemoryTransactions,
    actor,
)


class World:
    def __init__(self, quotas: QuotaPolicy | None = None) -> None:
        self.clock = MutableClock()
        self.accounts = InMemoryAccounts()
        self.organizations = InMemoryOrganizations(self.accounts)
        self.adapters = CorpusAdapters()
        self.collections = InMemoryCollections(self.adapters.repository)
        self.sources = InMemorySources(self.collections)
        self.audit = InMemoryAuditLog()
        self.me = self.accounts.add(email="me@example.com").id
        self.org = Organization(uuid.uuid4(), "Org", None, None, START, START)
        self.organizations.organizations[self.org.id] = self.org
        self.organizations.seed_member(self.org.id, self.me, Role.EDITOR)
        policy = quotas or QuotaPolicy()
        tx = InMemoryTransactions()
        self.collection_service = CollectionService(
            collections=self.collections,
            organizations=self.organizations,
            accounts=self.accounts,
            corpus=self.adapters.repository,
            index=self.adapters.index,
            audit=self.audit,
            tx=tx,
            clock=self.clock,
            quotas=policy,
            sources=self.sources,
        )
        self.service = ContentService(
            collections=self.collections,
            sources=self.sources,
            organizations=self.organizations,
            accounts=self.accounts,
            audit=self.audit,
            tx=tx,
            clock=self.clock,
            quotas=policy,
        )

    def editor(self) -> Actor:
        return actor(self.me, {self.org.id: Role.EDITOR})

    async def org_collection(self) -> uuid.UUID:
        view = await self.collection_service.create(
            self.editor(), title="Chung", owner_organization_id=self.org.id
        )
        await self.collection_service.set_visibility(
            self.editor(), view.id, Visibility.ORGANIZATION
        )
        return view.id


def doc(
    title: str = "Paracetamol", markdown: str = "# Liều\n\n500 mg"
) -> DocumentInput:
    return DocumentInput(title=title, markdown=markdown)


async def test_editors_write_documents_and_keys_stay_unique() -> None:
    w = World()
    collection = await w.org_collection()
    first = await w.service.create_document(w.editor(), collection, doc())
    second = await w.service.create_document(w.editor(), collection, doc())
    assert (first.key, second.key) == ("paracetamol", "paracetamol-2")
    assert first.char_count == len("# Liều\n\n500 mg")
    updated = await w.service.update_document(
        w.editor(), collection, first.id, doc(title="Paracetamol 500", markdown="Mới")
    )
    assert updated.key == "paracetamol" and updated.markdown == "Mới"
    listed = await w.service.list_documents(w.editor(), collection)
    assert [d.title for d in listed] == ["Paracetamol", "Paracetamol 500"]
    await w.service.delete_document(w.editor(), collection, second.id)
    assert len(await w.service.list_documents(w.editor(), collection)) == 1
    assert w.audit.actions()[-4:] == [
        AuditAction.DOCUMENT_CREATED,
        AuditAction.DOCUMENT_CREATED,
        AuditAction.DOCUMENT_UPDATED,
        AuditAction.DOCUMENT_DELETED,
    ]
    assert w.audit.events[-1].details["document"] == "Paracetamol"


async def test_members_read_but_cannot_write_and_outsiders_see_nothing() -> None:
    w = World()
    collection = await w.org_collection()
    member = actor(uuid.uuid4(), {w.org.id: Role.MEMBER})
    assert await w.service.list_documents(member, collection) == []
    with pytest.raises(ForbiddenRole):
        await w.service.create_document(member, collection, doc())
    with pytest.raises(CollectionNotFoundForActor):
        await w.service.list_documents(actor(uuid.uuid4()), collection)


async def test_documents_are_validated_and_quotas_enforced() -> None:
    w = World(QuotaPolicy(documents_per_collection=2, org_text_bytes=30))
    collection = await w.org_collection()
    with pytest.raises(InvalidInput):
        await w.service.create_document(w.editor(), collection, doc(markdown="  "))
    await w.service.create_document(w.editor(), collection, doc(markdown="x" * 20))
    with pytest.raises(QuotaExceeded) as exceeded:
        await w.service.create_document(w.editor(), collection, doc(markdown="x" * 11))
    assert (exceeded.value.unit, exceeded.value.used, exceeded.value.limit) == (
        "characters",
        20,
        30,
    )
    await w.service.create_document(w.editor(), collection, doc(markdown="x" * 10))
    with pytest.raises(QuotaExceeded) as full:
        await w.service.create_document(w.editor(), collection, doc(markdown="y"))
    assert full.value.unit == "documents"
    usage = await w.collection_service.quota(w.editor(), owner_organization_id=w.org.id)
    assert (usage.text_used, usage.text_limit) == (30, 30)


async def test_an_update_counts_only_the_growth_against_the_quota() -> None:
    w = World(QuotaPolicy(org_text_bytes=10))
    collection = await w.org_collection()
    created = await w.service.create_document(
        w.editor(), collection, doc(markdown="x" * 8)
    )
    await w.service.update_document(
        w.editor(), collection, created.id, doc(markdown="y" * 10)
    )
    with pytest.raises(QuotaExceeded):
        await w.service.update_document(
            w.editor(), collection, created.id, doc(markdown="z" * 11)
        )


async def test_glossary_and_colloquial_names_are_replaced_as_a_whole() -> None:
    w = World()
    collection = await w.org_collection()
    await w.service.create_document(w.editor(), collection, doc())
    entries = [
        GlossaryEntry(term="ADR", vietnamese_expansions=["phản ứng có hại"]),
        GlossaryEntry(term="IV"),
    ]
    assert [
        e.term
        for e in await w.service.replace_glossary(w.editor(), collection, entries)
    ] == ["ADR", "IV"]
    with pytest.raises(InvalidInput):
        await w.service.replace_glossary(
            w.editor(),
            collection,
            [GlossaryEntry(term="adr"), GlossaryEntry(term="ADR")],
        )
    sections = await w.service.sections(w.editor(), collection)
    assert [s.label for s in sections] == ["Paracetamol › Liều"]
    mapping = ColloquialMappingRecord(key="hạ sốt", section_keys=[sections[0].key])
    saved = await w.service.replace_colloquial(w.editor(), collection, [mapping])
    assert saved == [mapping]
    with pytest.raises(InvalidInput):
        await w.service.replace_colloquial(
            w.editor(),
            collection,
            [ColloquialMappingRecord(key="x", section_keys=["nope#body"])],
        )
    assert AuditAction.GLOSSARY_UPDATED in w.audit.actions()


async def test_the_system_corpus_is_never_authored() -> None:
    w = World()
    system = Collection(
        id=collection_id_for("formulary"),
        key="formulary",
        title="Dược thư",
        visibility=Visibility.PUBLIC,
    )
    w.adapters.repository.collections[system.key] = system
    admin = actor(uuid.uuid4(), superadmin=True)
    with pytest.raises(SystemCollectionReadOnly):
        await w.service.create_document(admin, system.id, doc())
