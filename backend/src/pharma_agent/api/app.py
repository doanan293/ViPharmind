"""FastAPI application factory: `uvicorn pharma_agent.api.app:create_app --factory`."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pharma_agent.api.csrf import install_csrf
from pharma_agent.api.deps import (
    actor_dependency,
    session_factory,
    superadmin_dependency,
    user_id_dependency,
)
from pharma_agent.api.errors import install_error_handlers
from pharma_agent.api.openapi import PharmaAgentAPI
from pharma_agent.api.routers.account import build_account_router
from pharma_agent.api.routers.admin import build_admin_router
from pharma_agent.api.routers.audit import build_audit_router
from pharma_agent.api.routers.chat import build_chat_router
from pharma_agent.api.routers.citations import build_citations_router
from pharma_agent.api.routers.collections import build_collections_router
from pharma_agent.api.routers.conversations import build_conversations_router
from pharma_agent.api.routers.documents import build_documents_router
from pharma_agent.api.routers.feedback import build_feedback_router
from pharma_agent.api.routers.health import build_health_router
from pharma_agent.api.routers.internal import build_internal_router
from pharma_agent.api.routers.invitations import build_invitations_router
from pharma_agent.api.routers.jobs import build_jobs_router
from pharma_agent.api.routers.organizations import build_organizations_router
from pharma_agent.infrastructure.auth.users import build_auth, include_auth_routes
from pharma_agent.infrastructure.container import ContainerFactory, open_container
from pharma_agent.infrastructure.settings import Settings


def create_app(
    settings: Settings | None = None,
    *,
    container_factory: ContainerFactory = open_container,
) -> FastAPI:
    resolved = settings if settings is not None else Settings()
    auth = build_auth(resolved.auth, session_factory)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        async with container_factory(resolved) as container:
            app.state.container = container
            yield

    app = PharmaAgentAPI(
        title="Pharma Agent API",
        version="0.1.0",
        lifespan=lifespan,
        generate_unique_id_function=lambda route: route.name,
    )
    app.state.auth = auth
    app.state.trusted_proxy_hops = resolved.api.trusted_proxy_hops
    app.state.jobs_settings = resolved.jobs
    app.state.phone_sign_in_enabled = resolved.sms.provider != "none"
    install_csrf(app, resolved.auth)
    if resolved.api.cors_origins:
        # Added after CSRF, so CORS is the outer layer and 403 problems carry CORS headers.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=resolved.api.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    install_error_handlers(app)

    api = APIRouter(prefix="/api/v1")
    include_auth_routes(api, auth)
    current_user_id = user_id_dependency(auth)
    api.include_router(build_account_router(current_user_id, auth.login_session))
    api.include_router(build_health_router())
    api.include_router(build_chat_router(current_user_id))
    api.include_router(build_conversations_router(current_user_id))
    api.include_router(build_feedback_router(current_user_id))
    api.include_router(build_citations_router(current_user_id))
    current_actor = actor_dependency(current_user_id)
    api.include_router(build_organizations_router(current_actor))
    api.include_router(build_invitations_router(current_actor))
    api.include_router(build_audit_router(current_actor))
    api.include_router(build_collections_router(current_actor))
    api.include_router(build_documents_router(current_actor))
    api.include_router(build_jobs_router(current_actor))
    api.include_router(build_admin_router(superadmin_dependency(current_actor)))
    api.include_router(build_internal_router())
    app.include_router(api)
    return app
