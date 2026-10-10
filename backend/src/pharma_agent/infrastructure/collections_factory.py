"""CollectionService over Postgres and a Qdrant index."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.application.corpus.collections import CollectionService, QuotaPolicy
from pharma_agent.domain.corpus.ports import VectorIndex
from pharma_agent.domain.shared.clock import Clock
from pharma_agent.infrastructure.persistence.postgres.account_repository import (
    PostgresAccountRepository,
)
from pharma_agent.infrastructure.persistence.postgres.audit_log import PostgresAuditLog
from pharma_agent.infrastructure.persistence.postgres.collection_repository import (
    PostgresCollectionRepository,
)
from pharma_agent.infrastructure.persistence.postgres.corpus_repository import (
    PostgresCorpusRepository,
)
from pharma_agent.infrastructure.persistence.postgres.organization_repository import (
    PostgresOrganizationRepository,
)
from pharma_agent.infrastructure.persistence.postgres.transaction import (
    PostgresTransactionFactory,
)
from pharma_agent.infrastructure.settings import Settings


def quota_policy(settings: Settings) -> QuotaPolicy:
    quotas = settings.quotas
    return QuotaPolicy(
        document_chars=quotas.document_chars,
        documents_per_collection=quotas.documents_per_collection,
        user_text_bytes=quotas.user_text_bytes,
        user_collections=quotas.user_collections,
        org_text_bytes=quotas.org_text_bytes,
        org_collections=quotas.org_collections,
    )


def build_collection_service(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
    *,
    index: VectorIndex,
    clock: Clock,
) -> CollectionService:
    return CollectionService(
        collections=PostgresCollectionRepository(sessions),
        organizations=PostgresOrganizationRepository(sessions),
        accounts=PostgresAccountRepository(sessions),
        corpus=PostgresCorpusRepository(sessions),
        index=index,
        audit=PostgresAuditLog(sessions),
        tx=PostgresTransactionFactory(sessions),
        clock=clock,
        quotas=quota_policy(settings),
    )
