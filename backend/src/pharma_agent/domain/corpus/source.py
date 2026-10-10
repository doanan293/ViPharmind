"""Content people write in the app, and the jobs that publish it (spec §4.7, §5).

Authored documents, glossary entries and colloquial names are editable; publishing turns
them into a KnowledgeBundle and runs the same import as the CLI.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pharma_agent.domain.corpus.bundle import (
    ColloquialMappingRecord,
    DocumentKind,
    GlossaryEntry,
)
from pharma_agent.domain.corpus.models import CollectionOwner
from pharma_agent.domain.shared.errors import DomainError
from pharma_agent.domain.shared.transaction import Transaction

MAX_DOCUMENT_CHARS = 200_000
MAX_TITLE_CHARS = 200


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"


class JobStep(StrEnum):
    BUNDLE = "bundle"
    CHUNK = "chunk"
    EMBED = "embed"
    INDEX = "index"
    PUBLISH = "publish"


OPEN_JOB_STATUSES = frozenset({JobStatus.QUEUED, JobStatus.RUNNING})


@dataclass(frozen=True)
class SourceDocument:
    id: uuid.UUID
    collection_id: uuid.UUID
    key: str
    title: str
    kind: DocumentKind
    source_title: str
    source_url: str | None
    markdown: str
    char_count: int
    created_by: uuid.UUID | None
    created_at: datetime
    updated_by: uuid.UUID | None
    updated_at: datetime


@dataclass(frozen=True)
class IngestJob:
    id: uuid.UUID
    collection_id: uuid.UUID
    release_id: uuid.UUID | None
    status: JobStatus
    step: JobStep
    progress: int
    error: str | None
    requested_by: uuid.UUID | None
    attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_JOB_STATUSES


def document_problem(title: str, markdown: str) -> str | None:
    if not title.strip():
        return "the title is required"
    if len(title.strip()) > MAX_TITLE_CHARS:
        return "the title is too long"
    if not markdown.strip():
        return "the document is empty"
    if len(markdown) > MAX_DOCUMENT_CHARS:
        return f"the document has more than {MAX_DOCUMENT_CHARS} characters"
    return None


class DocumentKeyConflict(DomainError):
    code = "DOCUMENT_KEY_CONFLICT"


class JobConflict(DomainError):
    """The collection already has a queued or running job."""

    code = "JOB_CONFLICT"


class SourceRepository(Protocol):
    async def list_documents(self, collection_id: uuid.UUID) -> list[SourceDocument]:
        """Ordered by title."""
        ...

    async def get_document(self, document_id: uuid.UUID) -> SourceDocument | None: ...

    async def document_keys(self, collection_id: uuid.UUID) -> set[str]: ...

    async def create_document(self, document: SourceDocument, tx: Transaction) -> None:
        """Raises DocumentKeyConflict when the key is taken in the collection."""
        ...

    async def update_document(
        self, document: SourceDocument, tx: Transaction
    ) -> None: ...

    async def delete_document(
        self, document_id: uuid.UUID, tx: Transaction
    ) -> None: ...

    async def count_documents(self, collection_id: uuid.UUID) -> int: ...

    async def purge_content(self, collection_id: uuid.UUID, tx: Transaction) -> None:
        """Delete the documents, glossary and colloquial names of a deleted collection."""
        ...

    async def text_usage(self, owner: CollectionOwner) -> int:
        """Characters of authored text across the owner's live collections."""
        ...

    async def glossary(self, collection_id: uuid.UUID) -> list[GlossaryEntry]: ...

    async def replace_glossary(
        self,
        collection_id: uuid.UUID,
        entries: list[GlossaryEntry],
        tx: Transaction,
    ) -> None: ...

    async def colloquial(
        self, collection_id: uuid.UUID
    ) -> list[ColloquialMappingRecord]: ...

    async def replace_colloquial(
        self,
        collection_id: uuid.UUID,
        mappings: list[ColloquialMappingRecord],
        tx: Transaction,
    ) -> None: ...


class IngestJobRepository(Protocol):
    async def get(self, job_id: uuid.UUID) -> IngestJob | None: ...

    async def open_for(self, collection_id: uuid.UUID) -> IngestJob | None: ...

    async def create(self, job: IngestJob, tx: Transaction) -> None:
        """Raises JobConflict when the collection already has an open job."""
        ...

    async def update(self, job: IngestJob) -> None:
        """Progress updates commit on their own so readers see them at once."""
        ...

    async def list_recent(self, *, limit: int) -> list[IngestJob]: ...


class JobDispatcher(Protocol):
    async def enqueue(self, job_id: uuid.UUID) -> None:
        """Arrange for the job to run soon, outside the current request."""
        ...
