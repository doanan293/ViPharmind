"""The permission table of spec §3 as pure functions.

Superadmin passes every check about data. Leaving and the approval rule describe
membership itself, so they apply to superadmin only through a real membership.
"""

import uuid

from pharma_agent.domain.access.models import ROLE_RANK, Actor, Role
from pharma_agent.domain.corpus.models import Collection, Visibility


def _at_least(actor: Actor, organization_id: uuid.UUID, role: Role) -> bool:
    if actor.is_superadmin:
        return True
    current = actor.role_in(organization_id)
    return current is not None and ROLE_RANK[current] >= ROLE_RANK[role]


def can_view_organization(actor: Actor, organization_id: uuid.UUID) -> bool:
    return _at_least(actor, organization_id, Role.MEMBER)


def can_manage_organization(actor: Actor, organization_id: uuid.UUID) -> bool:
    """Rename or delete the organization."""
    return _at_least(actor, organization_id, Role.OWNER)


def can_manage_members(actor: Actor, organization_id: uuid.UUID) -> bool:
    """Change roles and remove members."""
    return _at_least(actor, organization_id, Role.OWNER)


def can_view_audit(actor: Actor, organization_id: uuid.UUID) -> bool:
    return _at_least(actor, organization_id, Role.EDITOR)


def invitable_roles(actor: Actor, organization_id: uuid.UUID) -> frozenset[Role]:
    if actor.is_superadmin:
        return frozenset(Role)
    match actor.role_in(organization_id):
        case Role.OWNER:
            return frozenset(Role)
        case Role.EDITOR:
            return frozenset({Role.EDITOR, Role.MEMBER})
        case Role.MEMBER:
            return frozenset({Role.MEMBER})
        case _:
            return frozenset()


def invite_needs_approval(actor: Actor, organization_id: uuid.UUID) -> bool:
    """A member's invitation waits for an owner or editor before any email goes out."""
    return not actor.is_superadmin and actor.role_in(organization_id) is Role.MEMBER


def can_decide_invitation(actor: Actor, organization_id: uuid.UUID) -> bool:
    """Approve or reject an invitation that waits for approval."""
    return _at_least(actor, organization_id, Role.EDITOR)


def can_cancel_invitation(
    actor: Actor, organization_id: uuid.UUID, *, invited_by: uuid.UUID | None
) -> bool:
    """Revoke or resend: owners, editors, and the member who sent it."""
    if can_decide_invitation(actor, organization_id):
        return True
    return actor.role_in(organization_id) is not None and actor.user_id == invited_by


def can_leave(actor: Actor, organization_id: uuid.UUID, *, owner_count: int) -> bool:
    role = actor.role_in(organization_id)
    if role is None:
        return False
    return role is not Role.OWNER or owner_count > 1


def can_view_collection(actor: Actor, collection: Collection) -> bool:
    if actor.is_superadmin or collection.visibility is Visibility.PUBLIC:
        return True
    if collection.owner_user_id is not None:
        return collection.owner_user_id == actor.user_id
    if collection.owner_organization_id is not None:
        # A private organization collection is a draft for its owners and editors.
        needed = (
            Role.MEMBER
            if collection.visibility is Visibility.ORGANIZATION
            else Role.EDITOR
        )
        return _at_least(actor, collection.owner_organization_id, needed)
    return False


def can_edit_collection(actor: Actor, collection: Collection) -> bool:
    """Write content, rename, delete and publish."""
    if actor.is_superadmin:
        return True
    if collection.owner_user_id is not None:
        return collection.owner_user_id == actor.user_id
    if collection.owner_organization_id is not None:
        return _at_least(actor, collection.owner_organization_id, Role.EDITOR)
    return False


def can_set_visibility(
    actor: Actor, collection: Collection, visibility: Visibility
) -> bool:
    if collection.is_system:
        # System collections are public by construction.
        return False
    if visibility is Visibility.PUBLIC:
        return actor.is_superadmin
    if (
        visibility is Visibility.ORGANIZATION
        and collection.owner_organization_id is None
    ):
        return False
    return can_edit_collection(actor, collection)


def can_create_collection_for(
    actor: Actor,
    *,
    owner_user_id: uuid.UUID | None,
    owner_organization_id: uuid.UUID | None,
) -> bool:
    if owner_user_id is not None and owner_organization_id is not None:
        return False
    if owner_user_id is not None:
        return actor.is_superadmin or owner_user_id == actor.user_id
    if owner_organization_id is not None:
        return _at_least(actor, owner_organization_id, Role.EDITOR)
    return actor.is_superadmin
