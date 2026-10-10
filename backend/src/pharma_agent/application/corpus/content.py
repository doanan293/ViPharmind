"""Authored content of a collection: documents, glossary and colloquial names (spec §5)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from pharma_agent.application.corpus.collections import QuotaPolicy, owner_limits
from pharma_agent.application.corpus.errors import (
    CollectionNotFoundForActor,
    QuotaExceeded,
    SystemCollectionReadOnly,
)
from pharma_agent.application.errors import ForbiddenRole, InvalidInput
from pharma_agent.domain.access import policy
from pharma_agent.domain.access.models import Actor
from pharma_agent.domain.account.ports import AccountRepository
from pharma_agent.domain.audit.models import AuditAction, new_event
from pharma_agent.domain.audit.ports import AuditLog
from pharma_agent.domain.corpus.authoring import section_choices, slugify
from pharma_agent.domain.corpus.bundle import (
    ColloquialMappingRecord,
    DocumentKind,
    GlossaryEntry,
)
from pharma_agent.domain.corpus.models import Collection, CollectionOwner
from pharma_agent.domain.corpus.ports import CollectionRepository
from pharma_agent.domain.corpus.source import (
    SourceDocument,
    SourceRepository,
    document_problem,
)
from pharma_agent.domain.organizations.ports import OrganizationRepository
from pharma_agent.domain.shared.clock import Clock
from pharma_agent.domain.shared.transaction import Transaction, TransactionFactory


class DocumentInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: DocumentKind = DocumentKind.DRUG_MONOGRAPH
    source_title: str = Field(default="", max_length=500)
    source_url: str | None = Field(default=None, max_length=2000)
    markdown: str = Field(min_length=1)


class DocumentView(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID
    key: str
    title: str
    kind: DocumentKind
    source_title: str
    source_url: str | None
    char_count: int
    updated_at: datetime


class DocumentDetail(DocumentView):
    markdown: str


class SectionChoice(BaseModel):
    key: str
    label: str


def _detail(document: SourceDocument) -> DocumentDetail:
    return DocumentDetail(
        id=document.id,
        collection_id=document.collection_id,
        key=document.key,
        title=document.title,
        kind=document.kind,
        source_title=document.source_title,
        source_url=document.source_url,
        char_count=document.char_count,
        updated_at=document.updated_at,
        markdown=document.markdown,
    )


class ContentService:
    def __init__(
        self,
        *,
        collections: CollectionRepository,
        sources: SourceRepository,
        organizations: OrganizationRepository,
        accounts: AccountRepository,
        audit: AuditLog,
        tx: TransactionFactory,
        clock: Clock,
        quotas: QuotaPolicy,
    ) -> None:
        self._collections = collections
        self._sources = sources
        self._organizations = organizations
        self._accounts = accounts
        self._audit = audit
        self._tx = tx
        self._clock = clock
        self._quotas = quotas

    # Access ------------------------------------------------------------------------

    async def _visible(self, actor: Actor, collection_id: uuid.UUID) -> Collection:
        collection = await self._collections.get(collection_id)
        if collection is None or not policy.can_view_collection(actor, collection):
            raise CollectionNotFoundForActor(str(collection_id))
        return collection

    async def _writable(self, actor: Actor, collection_id: uuid.UUID) -> Collection:
        collection = await self._visible(actor, collection_id)
        if collection.is_system:
            # The system corpus comes from bundle imports; authoring would replace it.
            raise SystemCollectionReadOnly("the system corpus is imported, not written")
        if not policy.can_edit_collection(actor, collection):
            raise ForbiddenRole("your role cannot change this collection")
        return collection

    async def _document(
        self, collection: Collection, document_id: uuid.UUID
    ) -> SourceDocument:
        document = await self._sources.get_document(document_id)
        if document is None or document.collection_id != collection.id:
            raise CollectionNotFoundForActor(str(document_id))
        return document

    async def _record(
        self,
        tx: Transaction,
        actor: Actor,
        action: AuditAction,
        collection: Collection,
        **details: object,
    ) -> None:
        await self._audit.record(
            new_event(
                actor,
                action,
                self._clock.now(),
                organization_id=collection.owner_organization_id,
                subject_user_id=collection.owner_user_id,
                collection_id=collection.id,
                title=collection.title,
                **details,
            ),
            tx,
        )

    # Quotas -------------------------------------------------------------------------

    async def _check_text(self, collection: Collection, growth: int) -> None:
        if growth <= 0:
            return
        owner = CollectionOwner(
            user_id=collection.owner_user_id,
            organization_id=collection.owner_organization_id,
        )
        limit, _ = await owner_limits(
            owner,
            organizations=self._organizations,
            accounts=self._accounts,
            quotas=self._quotas,
        )
        used = await self._sources.text_usage(owner)
        if used + growth > limit:
            raise QuotaExceeded(unit="characters", used=used, limit=limit)

    @staticmethod
    def _validate(data: DocumentInput) -> None:
        problem = document_problem(data.title, data.markdown)
        if problem is not None:
            raise InvalidInput(problem)

    # Documents ----------------------------------------------------------------------

    async def list_documents(
        self, actor: Actor, collection_id: uuid.UUID
    ) -> list[DocumentView]:
        await self._visible(actor, collection_id)
        return [
            DocumentView(**_detail(document).model_dump(exclude={"markdown"}))
            for document in await self._sources.list_documents(collection_id)
        ]

    async def get_document(
        self, actor: Actor, collection_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentDetail:
        collection = await self._visible(actor, collection_id)
        return _detail(await self._document(collection, document_id))

    async def create_document(
        self, actor: Actor, collection_id: uuid.UUID, data: DocumentInput
    ) -> DocumentDetail:
        collection = await self._writable(actor, collection_id)
        self._validate(data)
        count = await self._sources.count_documents(collection_id)
        if count >= self._quotas.documents_per_collection:
            raise QuotaExceeded(
                unit="documents",
                used=count,
                limit=self._quotas.documents_per_collection,
            )
        await self._check_text(collection, len(data.markdown))
        taken = await self._sources.document_keys(collection_id)
        base = slugify(data.title) or "tai-lieu"
        key, n = base, 1
        while key in taken:
            n += 1
            key = f"{base}-{n}"
        now = self._clock.now()
        document = SourceDocument(
            id=uuid.uuid4(),
            collection_id=collection_id,
            key=key,
            title=data.title.strip(),
            kind=data.kind,
            source_title=data.source_title.strip(),
            source_url=data.source_url,
            markdown=data.markdown,
            char_count=len(data.markdown),
            created_by=actor.user_id,
            created_at=now,
            updated_by=actor.user_id,
            updated_at=now,
        )
        async with self._tx.begin() as tx:
            await self._sources.create_document(document, tx)
            await self._record(
                tx,
                actor,
                AuditAction.DOCUMENT_CREATED,
                collection,
                document=document.title,
            )
        return _detail(document)

    async def update_document(
        self,
        actor: Actor,
        collection_id: uuid.UUID,
        document_id: uuid.UUID,
        data: DocumentInput,
    ) -> DocumentDetail:
        collection = await self._writable(actor, collection_id)
        current = await self._document(collection, document_id)
        self._validate(data)
        await self._check_text(collection, len(data.markdown) - current.char_count)
        updated = SourceDocument(
            id=current.id,
            collection_id=current.collection_id,
            key=current.key,
            title=data.title.strip(),
            kind=data.kind,
            source_title=data.source_title.strip(),
            source_url=data.source_url,
            markdown=data.markdown,
            char_count=len(data.markdown),
            created_by=current.created_by,
            created_at=current.created_at,
            updated_by=actor.user_id,
            updated_at=self._clock.now(),
        )
        async with self._tx.begin() as tx:
            await self._sources.update_document(updated, tx)
            await self._record(
                tx,
                actor,
                AuditAction.DOCUMENT_UPDATED,
                collection,
                document=updated.title,
            )
        return _detail(updated)

    async def delete_document(
        self, actor: Actor, collection_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        collection = await self._writable(actor, collection_id)
        document = await self._document(collection, document_id)
        async with self._tx.begin() as tx:
            await self._sources.delete_document(document_id, tx)
            await self._record(
                tx,
                actor,
                AuditAction.DOCUMENT_DELETED,
                collection,
                document=document.title,
            )

    # Metadata -----------------------------------------------------------------------

    async def glossary(
        self, actor: Actor, collection_id: uuid.UUID
    ) -> list[GlossaryEntry]:
        await self._visible(actor, collection_id)
        return await self._sources.glossary(collection_id)

    async def replace_glossary(
        self, actor: Actor, collection_id: uuid.UUID, entries: list[GlossaryEntry]
    ) -> list[GlossaryEntry]:
        collection = await self._writable(actor, collection_id)
        seen: set[str] = set()
        for entry in entries:
            term = entry.term.strip().casefold()
            if not term:
                raise InvalidInput("every glossary entry needs a term")
            if term in seen:
                raise InvalidInput(f"the term {entry.term} appears twice")
            seen.add(term)
        async with self._tx.begin() as tx:
            await self._sources.replace_glossary(collection_id, entries, tx)
            await self._record(
                tx,
                actor,
                AuditAction.GLOSSARY_UPDATED,
                collection,
                entries=len(entries),
            )
        return entries

    async def colloquial(
        self, actor: Actor, collection_id: uuid.UUID
    ) -> list[ColloquialMappingRecord]:
        await self._visible(actor, collection_id)
        return await self._sources.colloquial(collection_id)

    async def sections(
        self, actor: Actor, collection_id: uuid.UUID
    ) -> list[SectionChoice]:
        collection = await self._visible(actor, collection_id)
        documents = await self._sources.list_documents(collection_id)
        return [
            SectionChoice(key=key, label=label)
            for key, label in section_choices(collection, documents)
        ]

    async def replace_colloquial(
        self,
        actor: Actor,
        collection_id: uuid.UUID,
        mappings: list[ColloquialMappingRecord],
    ) -> list[ColloquialMappingRecord]:
        collection = await self._writable(actor, collection_id)
        known = {choice.key for choice in await self.sections(actor, collection_id)}
        keys: set[str] = set()
        for mapping in mappings:
            key = mapping.key.strip().casefold()
            if not key:
                raise InvalidInput("every colloquial name needs a key")
            if key in keys:
                raise InvalidInput(f"the name {mapping.key} appears twice")
            keys.add(key)
            unknown = [k for k in mapping.section_keys if k not in known]
            if unknown:
                raise InvalidInput(f"unknown sections: {', '.join(unknown)}")
        async with self._tx.begin() as tx:
            await self._sources.replace_colloquial(collection_id, mappings, tx)
            await self._record(
                tx,
                actor,
                AuditAction.COLLOQUIAL_UPDATED,
                collection,
                entries=len(mappings),
            )
        return mappings
