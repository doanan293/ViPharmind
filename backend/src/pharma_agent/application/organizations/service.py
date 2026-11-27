"""Organization use cases: create, rename, delete, members and leaving."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from pharma_agent.application.errors import InvalidInput
from pharma_agent.application.organizations.errors import (
    ForbiddenRole,
    LastOwner,
    MemberNotFound,
    OrganizationNameInvalid,
    OrganizationNotFound,
)
from pharma_agent.domain.access import policy
from pharma_agent.domain.access.models import Actor, Role
from pharma_agent.domain.audit.models import AuditAction, new_event
from pharma_agent.domain.audit.ports import AuditLog
from pharma_agent.domain.organizations.models import (
    Organization,
    organization_name_problem,
)
from pharma_agent.domain.organizations.ports import OrganizationRepository
from pharma_agent.domain.shared.clock import Clock
from pharma_agent.domain.shared.transaction import TransactionFactory


class OrganizationView(BaseModel):
    """An organization with the actor's role in it (None when not a member)."""

    id: uuid.UUID
    name: str
    role: Role | None
    member_count: int
    created_at: datetime


class MemberItem(BaseModel):
    """One member of an organization."""

    user_id: uuid.UUID
    display_name: str
    email: str | None
    role: Role
    joined_at: datetime


class OrganizationService:
    """Organization use cases; every change is audited in the same transaction."""

    def __init__(
        self,
        *,
        organizations: OrganizationRepository,
        audit: AuditLog,
        tx: TransactionFactory,
        clock: Clock,
    ) -> None:
        """Wire the service to the repository, the audit log, transactions and the clock."""
        self._organizations = organizations
        self._audit = audit
        self._tx = tx
        self._clock = clock

    async def _visible(self, actor: Actor, organization_id: uuid.UUID) -> Organization:
        organization = await self._organizations.get(organization_id)
        if organization is None or not policy.can_view_organization(
            actor, organization_id
        ):
            raise OrganizationNotFound(str(organization_id))
        return organization

    async def _view(
        self, actor: Actor, organization: Organization, role: Role | None = None
    ) -> OrganizationView:
        return OrganizationView(
            id=organization.id,
            name=organization.name,
            role=role if role is not None else actor.role_in(organization.id),
            member_count=await self._organizations.member_count(organization.id),
            created_at=organization.created_at,
        )

    @staticmethod
    def _name(name: str) -> str:
        problem = organization_name_problem(name)
        if problem is not None:
            raise OrganizationNameInvalid(problem)
        return name.strip()

    async def list_mine(self, actor: Actor) -> list[OrganizationView]:
        """List the organizations the actor belongs to, with their role in each."""
        return [
            await self._view(actor, organization, role)
            for organization, role in await self._organizations.list_for_user(
                actor.user_id
            )
        ]

    async def get(self, actor: Actor, organization_id: uuid.UUID) -> OrganizationView:
        """Return one organization the actor can see.

        Raises:
            OrganizationNotFound: If it is missing or not visible to the actor.
        """
        return await self._view(actor, await self._visible(actor, organization_id))

    async def create(self, actor: Actor, name: str) -> OrganizationView:
        """Create an organization owned by the actor.

        Raises:
            OrganizationNameInvalid: If the name is not acceptable.
        """
        now = self._clock.now()
        organization = Organization(
            uuid.uuid4(), self._name(name), None, None, now, now
        )
        owner = Actor(
            actor.user_id,
            actor.is_superadmin,
            {**actor.memberships, organization.id: Role.OWNER},
        )
        async with self._tx.begin() as tx:
            await self._organizations.create(organization, actor.user_id, tx)
            await self._audit.record(
                new_event(
                    owner,
                    AuditAction.ORGANIZATION_CREATED,
                    now,
                    organization_id=organization.id,
                    name=organization.name,
                ),
                tx,
            )
        return await self._view(owner, organization, Role.OWNER)

    async def rename(
        self, actor: Actor, organization_id: uuid.UUID, name: str
    ) -> OrganizationView:
        """Rename an organization.

        Raises:
            OrganizationNotFound: If it is missing or not visible to the actor.
            ForbiddenRole: If the actor is not an owner.
            OrganizationNameInvalid: If the name is not acceptable.
        """
        organization = await self._visible(actor, organization_id)
        if not policy.can_manage_organization(actor, organization_id):
            raise ForbiddenRole("only owners rename the organization")
        new_name = self._name(name)
        now = self._clock.now()
        async with self._tx.begin() as tx:
            await self._organizations.rename(organization_id, new_name, now, tx)
            await self._audit.record(
                new_event(
                    actor,
                    AuditAction.ORGANIZATION_RENAMED,
                    now,
                    organization_id=organization_id,
                    **{"from": organization.name, "to": new_name},
                ),
                tx,
            )
        return await self.get(actor, organization_id)

    async def delete(
        self, actor: Actor, organization_id: uuid.UUID, *, confirm_name: str
    ) -> None:
        """Delete an organization once `confirm_name` matches its name.

        Raises:
            OrganizationNotFound: If it is missing or not visible to the actor.
            ForbiddenRole: If the actor is not an owner.
            InvalidInput: If `confirm_name` does not match.
        """
        organization = await self._visible(actor, organization_id)
        if not policy.can_manage_organization(actor, organization_id):
            raise ForbiddenRole("only owners delete the organization")
        if confirm_name.strip() != organization.name:
            raise InvalidInput("type the organization name to confirm")
        now = self._clock.now()
        async with self._tx.begin() as tx:
            # Recorded first: the event keeps the organization id after the row is gone.
            await self._audit.record(
                new_event(
                    actor,
                    AuditAction.ORGANIZATION_DELETED,
                    now,
                    organization_id=organization_id,
                    name=organization.name,
                ),
                tx,
            )
            await self._organizations.delete(organization_id, tx)

    async def members(
        self, actor: Actor, organization_id: uuid.UUID
    ) -> list[MemberItem]:
        """List the members of an organization the actor can see.

        Raises:
            OrganizationNotFound: If it is missing or not visible to the actor.
        """
        await self._visible(actor, organization_id)
        return [
            MemberItem(
                user_id=member.user_id,
                display_name=member.display_name,
                email=member.email,
                role=member.role,
                joined_at=member.joined_at,
            )
            for member in await self._organizations.members(organization_id)
        ]

    async def _member_role(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> Role:
        role = (await self._organizations.memberships_of(user_id)).get(organization_id)
        if role is None:
            raise MemberNotFound(str(user_id))
        return role

    async def _keep_an_owner(self, organization_id: uuid.UUID, current: Role) -> None:
        if (
            current is Role.OWNER
            and await self._organizations.owner_count(organization_id) <= 1
        ):
            raise LastOwner("an organization keeps at least one owner")

    async def set_role(
        self, actor: Actor, organization_id: uuid.UUID, user_id: uuid.UUID, role: Role
    ) -> None:
        """Change a member's role; nothing happens when it is already `role`.

        Raises:
            OrganizationNotFound: If it is missing or not visible to the actor.
            ForbiddenRole: If the actor cannot manage members.
            MemberNotFound: If the user is not a member.
            LastOwner: If it would demote the last owner.
        """
        await self._visible(actor, organization_id)
        if not policy.can_manage_members(actor, organization_id):
            raise ForbiddenRole("only owners change roles")
        current = await self._member_role(organization_id, user_id)
        if current is role:
            return
        await self._keep_an_owner(organization_id, current)
        now = self._clock.now()
        async with self._tx.begin() as tx:
            await self._organizations.set_role(organization_id, user_id, role, tx)
            await self._audit.record(
                new_event(
                    actor,
                    AuditAction.MEMBER_ROLE_CHANGED,
                    now,
                    organization_id=organization_id,
                    subject_user_id=user_id,
                    **{"from": current.value, "to": role.value},
                ),
                tx,
            )

    async def remove_member(
        self, actor: Actor, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """Remove a member from an organization.

        Raises:
            OrganizationNotFound: If it is missing or not visible to the actor.
            ForbiddenRole: If the actor cannot manage members.
            MemberNotFound: If the user is not a member.
            LastOwner: If the member is the last owner.
        """
        await self._visible(actor, organization_id)
        if not policy.can_manage_members(actor, organization_id):
            raise ForbiddenRole("only owners remove members")
        current = await self._member_role(organization_id, user_id)
        await self._keep_an_owner(organization_id, current)
        await self._remove(actor, organization_id, user_id, AuditAction.MEMBER_REMOVED)

    async def leave(self, actor: Actor, organization_id: uuid.UUID) -> None:
        """Remove the actor from an organization they belong to.

        Raises:
            OrganizationNotFound: If the actor is not a member.
            LastOwner: If the actor is its last owner.
        """
        if actor.role_in(organization_id) is None:
            raise OrganizationNotFound(str(organization_id))
        owners = await self._organizations.owner_count(organization_id)
        if not policy.can_leave(actor, organization_id, owner_count=owners):
            raise LastOwner("an organization keeps at least one owner")
        await self._remove(
            actor, organization_id, actor.user_id, AuditAction.MEMBER_LEFT
        )

    async def _remove(
        self,
        actor: Actor,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        action: AuditAction,
    ) -> None:
        now = self._clock.now()
        async with self._tx.begin() as tx:
            await self._organizations.remove_member(organization_id, user_id, tx)
            await self._audit.record(
                new_event(
                    actor,
                    action,
                    now,
                    organization_id=organization_id,
                    subject_user_id=user_id,
                ),
                tx,
            )
