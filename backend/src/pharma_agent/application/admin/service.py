"""Account and quota administration for superadmins.

Reading conversations, collections and jobs goes through the services that own them; the
API checks the superadmin flag before calling those.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from pharma_agent.application.errors import (
    AccountNotFound,
    ForbiddenRole,
    InvalidInput,
    OrganizationNotFound,
)
from pharma_agent.application.pagination import decode_cursor, encode_cursor
from pharma_agent.domain.access.models import Actor
from pharma_agent.domain.account.models import AccountUser
from pharma_agent.domain.account.ports import AccountAdmin, SessionStore
from pharma_agent.domain.audit.models import AuditAction, new_event
from pharma_agent.domain.audit.ports import AuditLog
from pharma_agent.domain.organizations.models import Organization
from pharma_agent.domain.organizations.ports import OrganizationRepository
from pharma_agent.domain.shared.clock import Clock
from pharma_agent.domain.shared.transaction import TransactionFactory


class AdminUserView(BaseModel):
    id: uuid.UUID
    email: str | None
    phone_number: str | None
    display_name: str
    is_active: bool
    is_superadmin: bool
    created_at: datetime | None
    text_quota_bytes: int | None
    collection_quota: int | None

    @classmethod
    def of(cls, user: AccountUser) -> "AdminUserView":
        return cls(
            id=user.id,
            email=user.email,
            phone_number=user.phone_number,
            display_name=user.display_name,
            is_active=user.is_active,
            is_superadmin=user.is_superuser,
            created_at=user.created_at,
            text_quota_bytes=user.text_quota_bytes,
            collection_quota=user.collection_quota,
        )


class AdminUserPage(BaseModel):
    items: list[AdminUserView]
    next_cursor: str | None


class AdminOrganizationView(BaseModel):
    id: uuid.UUID
    name: str
    member_count: int
    text_quota_bytes: int | None
    collection_quota: int | None
    created_at: datetime


class AdminOrganizationPage(BaseModel):
    items: list[AdminOrganizationView]
    next_cursor: str | None


class AdminService:
    def __init__(
        self,
        *,
        accounts: AccountAdmin,
        organizations: OrganizationRepository,
        sessions: SessionStore,
        audit: AuditLog,
        tx: TransactionFactory,
        clock: Clock,
    ) -> None:
        self._accounts = accounts
        self._organizations = organizations
        self._sessions = sessions
        self._audit = audit
        self._tx = tx
        self._clock = clock

    @staticmethod
    def _require(actor: Actor) -> None:
        if not actor.is_superadmin:
            raise ForbiddenRole("only superadmins use the console")

    async def _user(self, user_id: uuid.UUID) -> AccountUser:
        user = await self._accounts.get(user_id)
        if user is None:
            raise AccountNotFound(str(user_id))
        return user

    async def get_user(self, actor: Actor, user_id: uuid.UUID) -> AdminUserView:
        self._require(actor)
        return AdminUserView.of(await self._user(user_id))

    async def users(
        self, actor: Actor, *, query: str | None, limit: int, cursor: str | None
    ) -> AdminUserPage:
        self._require(actor)
        rows = await self._accounts.search(
            query.strip() if query else None,
            limit=limit + 1,
            cursor=None if cursor is None else decode_cursor(cursor),
        )
        items = rows[:limit]
        last = items[-1] if items else None
        next_cursor = (
            encode_cursor(last.created_at, last.id.hex)
            if len(rows) > limit and last is not None and last.created_at is not None
            else None
        )
        return AdminUserPage(
            items=[AdminUserView.of(user) for user in items], next_cursor=next_cursor
        )

    async def set_user_active(
        self, actor: Actor, user_id: uuid.UUID, *, active: bool
    ) -> AdminUserView:
        self._require(actor)
        if user_id == actor.user_id and not active:
            raise InvalidInput("you cannot disable your own account")
        await self._user(user_id)
        async with self._tx.begin() as tx:
            await self._accounts.set_active(user_id, active, tx)
            await self._audit.record(
                new_event(
                    actor,
                    AuditAction.USER_ENABLED if active else AuditAction.USER_DISABLED,
                    self._clock.now(),
                    subject_user_id=user_id,
                ),
                tx,
            )
        if not active:
            # A disabled account must not keep a working session anywhere.
            await self._sessions.delete_all(user_id)
        return AdminUserView.of(await self._user(user_id))

    async def set_user_quotas(
        self,
        actor: Actor,
        user_id: uuid.UUID,
        *,
        text_quota_bytes: int | None,
        collection_quota: int | None,
    ) -> AdminUserView:
        self._require(actor)
        await self._user(user_id)
        async with self._tx.begin() as tx:
            await self._accounts.set_quotas(
                user_id,
                text_quota_bytes=text_quota_bytes,
                collection_quota=collection_quota,
                tx=tx,
            )
            await self._audit.record(
                new_event(
                    actor,
                    AuditAction.QUOTA_CHANGED,
                    self._clock.now(),
                    subject_user_id=user_id,
                    text_quota_bytes=text_quota_bytes,
                    collection_quota=collection_quota,
                ),
                tx,
            )
        return AdminUserView.of(await self._user(user_id))

    async def _organization_view(
        self, organization: Organization
    ) -> AdminOrganizationView:
        return AdminOrganizationView(
            id=organization.id,
            name=organization.name,
            member_count=await self._organizations.member_count(organization.id),
            text_quota_bytes=organization.text_quota_bytes,
            collection_quota=organization.collection_quota,
            created_at=organization.created_at,
        )

    async def organizations(
        self, actor: Actor, *, limit: int, cursor: str | None
    ) -> AdminOrganizationPage:
        self._require(actor)
        rows = await self._organizations.list_all(
            limit=limit + 1, cursor=None if cursor is None else decode_cursor(cursor)
        )
        items = rows[:limit]
        next_cursor = (
            encode_cursor(items[-1].created_at, items[-1].id.hex)
            if len(rows) > limit
            else None
        )
        return AdminOrganizationPage(
            items=[await self._organization_view(o) for o in items],
            next_cursor=next_cursor,
        )

    async def set_organization_quotas(
        self,
        actor: Actor,
        organization_id: uuid.UUID,
        *,
        text_quota_bytes: int | None,
        collection_quota: int | None,
    ) -> AdminOrganizationView:
        self._require(actor)
        if await self._organizations.get(organization_id) is None:
            raise OrganizationNotFound(str(organization_id))
        async with self._tx.begin() as tx:
            await self._organizations.set_quotas(
                organization_id,
                text_quota_bytes=text_quota_bytes,
                collection_quota=collection_quota,
                now=self._clock.now(),
                tx=tx,
            )
            await self._audit.record(
                new_event(
                    actor,
                    AuditAction.QUOTA_CHANGED,
                    self._clock.now(),
                    organization_id=organization_id,
                    text_quota_bytes=text_quota_bytes,
                    collection_quota=collection_quota,
                ),
                tx,
            )
        organization = await self._organizations.get(organization_id)
        assert organization is not None
        return await self._organization_view(organization)
