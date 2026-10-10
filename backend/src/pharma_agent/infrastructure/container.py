"""Owns every long-lived resource of the HTTP service and wires application services."""

import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import (
    AbstractAsyncContextManager,
    AsyncExitStack,
    asynccontextmanager,
)
from dataclasses import dataclass, field

from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.application.account.service import AccountService
from pharma_agent.application.chat.service import ChatService, MemoryPolicy
from pharma_agent.application.conversation.service import ConversationService
from pharma_agent.application.corpus.collections import CollectionService
from pharma_agent.application.feedback.service import FeedbackService
from pharma_agent.application.memory.summarize import SummarizeConversation
from pharma_agent.application.tracing import NullTracing, Tracing
from pharma_agent.domain.account.ports import EmailSender, SmsSender
from pharma_agent.domain.corpus.ports import Embedder
from pharma_agent.domain.llm.port import LlmPort
from pharma_agent.domain.retrieval.ports import RetrievalError
from pharma_agent.domain.shared.clock import SystemClock
from pharma_agent.infrastructure.account_factory import build_account_service
from pharma_agent.infrastructure.collections_factory import build_collection_service
from pharma_agent.infrastructure.composition import Application, build_application
from pharma_agent.infrastructure.observability.langfuse_tracing import LangfuseTracing
from pharma_agent.infrastructure.organizations_factory import (
    OrganizationServices,
    build_organization_services,
)
from pharma_agent.infrastructure.persistence.postgres.citation_reader import (
    PostgresCitationReader,
)
from pharma_agent.infrastructure.persistence.postgres.collection_repository import (
    PostgresCollectionRepository,
)
from pharma_agent.infrastructure.persistence.postgres.conversation_repository import (
    PostgresConversationRepository,
)
from pharma_agent.infrastructure.persistence.postgres.database import Database
from pharma_agent.infrastructure.persistence.postgres.feedback_repository import (
    PostgresFeedbackRepository,
)
from pharma_agent.infrastructure.retrieval.qdrant_index import QdrantVectorIndex
from pharma_agent.infrastructure.retrieval.scope_resolver import PostgresScopeResolver
from pharma_agent.infrastructure.settings import Settings

logger = logging.getLogger(__name__)

HealthCheck = Callable[[], Awaitable[bool]]

CORPUS_NOT_READY = "CORPUS_NOT_READY"


@dataclass
class Container:
    sessions: async_sessionmaker[AsyncSession] | None
    conversations: ConversationService
    account: AccountService | None = None
    organizations: OrganizationServices | None = None
    collections: CollectionService | None = None
    chat: ChatService | None = None
    summarizer: SummarizeConversation | None = None
    feedback: FeedbackService | None = None
    health_checks: dict[str, HealthCheck] = field(default_factory=dict)
    # Reason code /health reports when the named check fails.
    health_reasons: dict[str, str] = field(default_factory=dict)


ContainerFactory = Callable[[Settings], AbstractAsyncContextManager[Container]]


def _corpus_check(agent: Application, settings: Settings) -> HealthCheck:
    async def check() -> bool:
        try:
            await agent.retrieval.retriever.verify_corpus(
                embedding_model=settings.retrieval.embedding.model,
                dimension=settings.retrieval.embedding.dimension,
            )
        except RetrievalError as exc:
            logger.warning("corpus not ready: %s", exc)
            return False
        return True

    return check


@asynccontextmanager
async def open_container(
    settings: Settings,
    *,
    llm: LlmPort | None = None,
    embedder: Embedder | None = None,
    email_sender: EmailSender | None = None,
    sms_sender: SmsSender | None = None,
) -> AsyncGenerator[Container]:
    """Open every long-lived resource; `llm` and `embedder` replace the settings-built adapters."""
    database = Database(
        settings.postgres.dsn,
        pool_size=settings.postgres.pool_size,
        echo=settings.postgres.echo,
    )
    clock = SystemClock()
    repository = PostgresConversationRepository(database.sessions)
    tracing: Tracing = (
        LangfuseTracing.from_settings(settings.langfuse)
        if settings.langfuse.enabled
        else NullTracing()
    )
    feedback_repository = PostgresFeedbackRepository(database.sessions)
    organization_services = build_organization_services(
        settings, database.sessions, clock=clock, email=email_sender
    )
    container = Container(
        sessions=database.sessions,
        conversations=ConversationService(
            repository,
            clock,
            feedback=feedback_repository,
            citations=PostgresCitationReader(database.sessions),
        ),
        feedback=FeedbackService(repository, feedback_repository, tracing, clock),
        health_checks={"postgres": database.ping},
        organizations=organization_services,
    )
    if settings.auth.otp_secret is None:
        logger.warning("PHARMA_AUTH__OTP_SECRET is not set: account flows are disabled")
    else:
        container.account = build_account_service(
            settings, database.sessions, clock=clock, email=email_sender, sms=sms_sender
        )
    try:
        async with AsyncExitStack() as stack:
            if isinstance(tracing, LangfuseTracing):
                stack.callback(tracing.shutdown)
            # Deleting a collection removes its Qdrant points; creating the client
            # does not connect, so a missing Qdrant only fails those calls.
            qdrant = AsyncQdrantClient(
                url=settings.qdrant.url,
                api_key=settings.qdrant.api_key,
                timeout=int(settings.qdrant.timeout_seconds),
                check_compatibility=False,
            )
            stack.push_async_callback(qdrant.close)
            container.collections = build_collection_service(
                settings,
                database.sessions,
                index=QdrantVectorIndex(
                    qdrant,
                    model=settings.retrieval.embedding.model,
                    dimension=settings.retrieval.embedding.dimension,
                    alias=settings.retrieval.qdrant_collection,
                ),
                clock=clock,
            )
            if settings.llm.configured or llm is not None:
                agent = build_application(
                    settings,
                    tracer=tracing,
                    database=database,
                    llm=llm,
                    embedder=embedder,
                )
                stack.push_async_callback(agent.aclose)
                container.chat = ChatService(
                    agent.runner,
                    repository,
                    clock,
                    MemoryPolicy(
                        context_turns=settings.memory.context_turns,
                        context_chars=settings.memory.context_chars,
                    ),
                    scopes=PostgresScopeResolver(
                        organization_services.actors,
                        PostgresCollectionRepository(database.sessions),
                    ),
                )
                container.summarizer = SummarizeConversation(
                    agent.deps.llm,
                    repository,
                    clock,
                    every=settings.memory.summary_every_turns,
                    max_chars=settings.memory.summary_max_chars,
                )
                container.health_checks["corpus"] = _corpus_check(agent, settings)
                container.health_reasons["corpus"] = CORPUS_NOT_READY
            yield container
    finally:
        await database.dispose()
