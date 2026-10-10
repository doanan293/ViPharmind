"""Audit log pages: an organization's log, the user's own activity, and everything."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from pharma_agent.application.errors import ForbiddenRole, OrganizationNotFound
from pharma_agent.application.pagination import decode_cursor, encode_cursor
from pharma_agent.domain.access import policy
from pharma_agent.domain.access.models import Actor
from pharma_agent.domain.account.ports import AccountRepository
from pharma_agent.domain.audit.models import AuditAction, AuditEvent
from pharma_agent.domain.audit.ports import AuditLog, Cursor
from pharma_agent.domain.organizations.ports import OrganizationRepository
from pharma_agent.domain.shared.clock import Clock


class AuditEventView(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    actor_name: str
    actor_was_superadmin: bool
    action: AuditAction
    organization_id: uuid.UUID | None
    subject_user_id: uuid.UUID | None
    collection_id: uuid.UUID | None
    details: dict[str, Any]


class AuditPage(BaseModel):
    items: list[AuditEventView]
    next_cursor: str | None


class AuditService:
    def __init__(
        self,
        *,
        audit: AuditLog,
        accounts: AccountRepository,
        organizations: OrganizationRepository,
        clock: Clock,
    ) -> None:
        self._audit = audit
        self._accounts = accounts
        self._organizations = organizations
        self._clock = clock

    async def _page(self, events: list[AuditEvent], limit: int) -> AuditPage:
        items = events[:limit]
        names: dict[uuid.UUID, str] = {}
        for actor_id in {e.actor_user_id for e in items if e.actor_user_id}:
            user = await self._accounts.get(actor_id)
            names[actor_id] = (
                ""
                if user is None
                else user.display_name or user.email or user.phone_number or ""
            )
        views = [
            AuditEventView(
                id=event.id,
                occurred_at=event.occurred_at,
                actor_user_id=event.actor_user_id,
                actor_name=names.get(event.actor_user_id, "")
                if event.actor_user_id
                else "",
                actor_was_superadmin=event.actor_was_superadmin,
                action=event.action,
                organization_id=event.organization_id,
                subject_user_id=event.subject_user_id,
                collection_id=event.collection_id,
                details=dict(event.details),
            )
            for event in items
        ]
        next_cursor = (
            encode_cursor(items[-1].occurred_at, items[-1].id.hex)
            if len(events) > limit
            else None
        )
        return AuditPage(items=views, next_cursor=next_cursor)

    @staticmethod
    def _after(cursor: str | None) -> Cursor | None:
        return None if cursor is None else decode_cursor(cursor)

    async def for_organization(
        self,
        actor: Actor,
        organization_id: uuid.UUID,
        *,
        limit: int,
        cursor: str | None,
    ) -> AuditPage:
        if await self._organizations.get(
            organization_id
        ) is None or not policy.can_view_organization(actor, organization_id):
            raise OrganizationNotFound(str(organization_id))
        if not policy.can_view_audit(actor, organization_id):
            raise ForbiddenRole("only owners and editors read the organization log")
        events = await self._audit.for_organization(
            organization_id, limit=limit + 1, cursor=self._after(cursor)
        )
        return await self._page(events, limit)

    async def mine(self, actor: Actor, *, limit: int, cursor: str | None) -> AuditPage:
        events = await self._audit.for_user(
            actor.user_id, limit=limit + 1, cursor=self._after(cursor)
        )
        return await self._page(events, limit)

    async def everything(
        self, actor: Actor, *, limit: int, cursor: str | None
    ) -> AuditPage:
        if not actor.is_superadmin:
            raise ForbiddenRole("only superadmins read the whole log")
        events = await self._audit.all(limit=limit + 1, cursor=self._after(cursor))
        return await self._page(events, limit)
