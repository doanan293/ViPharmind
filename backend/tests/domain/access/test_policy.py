import uuid
from collections.abc import Callable

import pytest

from pharma_agent.domain.access import policy
from pharma_agent.domain.access.models import Actor, Role
from pharma_agent.domain.corpus.models import Collection, Visibility

ORG = uuid.uuid4()
OTHER_ORG = uuid.uuid4()
ME = uuid.uuid4()
SOMEONE = uuid.uuid4()


def actor(role: Role | None, *, superadmin: bool = False) -> Actor:
    return Actor(ME, superadmin, {} if role is None else {ORG: role})


OWNER = actor(Role.OWNER)
EDITOR = actor(Role.EDITOR)
MEMBER = actor(Role.MEMBER)
OUTSIDER = actor(None)
ADMIN = actor(None, superadmin=True)
ACTORS = [OWNER, EDITOR, MEMBER, OUTSIDER, ADMIN]


def col(
    *,
    owner_user_id: uuid.UUID | None = None,
    owner_organization_id: uuid.UUID | None = None,
    visibility: Visibility = Visibility.PRIVATE,
) -> Collection:
    return Collection(
        id=uuid.uuid4(),
        key="k",
        title="t",
        owner_user_id=owner_user_id,
        owner_organization_id=owner_organization_id,
        visibility=visibility,
    )


SYSTEM = col(visibility=Visibility.PUBLIC)
MINE = col(owner_user_id=ME)
THEIRS = col(owner_user_id=SOMEONE)
ORG_PRIVATE = col(owner_organization_id=ORG)
ORG_SHARED = col(owner_organization_id=ORG, visibility=Visibility.ORGANIZATION)
OTHER_ORG_SHARED = col(
    owner_organization_id=OTHER_ORG, visibility=Visibility.ORGANIZATION
)

Check = Callable[[Actor], bool]


@pytest.mark.parametrize(
    ("check", "expected"),
    [
        (lambda a: policy.can_view_organization(a, ORG), [1, 1, 1, 0, 1]),
        (lambda a: policy.can_manage_organization(a, ORG), [1, 0, 0, 0, 1]),
        (lambda a: policy.can_manage_members(a, ORG), [1, 0, 0, 0, 1]),
        (lambda a: policy.can_view_audit(a, ORG), [1, 1, 0, 0, 1]),
        (lambda a: policy.invite_needs_approval(a, ORG), [0, 0, 1, 0, 0]),
        (lambda a: policy.can_decide_invitation(a, ORG), [1, 1, 0, 0, 1]),
        (
            lambda a: policy.can_cancel_invitation(a, ORG, invited_by=SOMEONE),
            [1, 1, 0, 0, 1],
        ),
        (
            lambda a: policy.can_cancel_invitation(a, ORG, invited_by=ME),
            [1, 1, 1, 0, 1],
        ),
        (lambda a: policy.can_leave(a, ORG, owner_count=1), [0, 1, 1, 0, 0]),
        (lambda a: policy.can_leave(a, ORG, owner_count=2), [1, 1, 1, 0, 0]),
    ],
)
def test_organization_rules(check: Check, expected: list[int]) -> None:
    assert [check(a) for a in ACTORS] == [bool(x) for x in expected]


def test_invitable_roles() -> None:
    assert policy.invitable_roles(OWNER, ORG) == frozenset(Role)
    assert policy.invitable_roles(EDITOR, ORG) == frozenset({Role.EDITOR, Role.MEMBER})
    assert policy.invitable_roles(MEMBER, ORG) == frozenset({Role.MEMBER})
    assert policy.invitable_roles(OUTSIDER, ORG) == frozenset()
    assert policy.invitable_roles(ADMIN, ORG) == frozenset(Role)


@pytest.mark.parametrize(
    ("collection", "view", "edit"),
    [
        (SYSTEM, [1, 1, 1, 1, 1], [0, 0, 0, 0, 1]),
        (MINE, [1, 1, 1, 1, 1], [1, 1, 1, 1, 1]),
        (THEIRS, [0, 0, 0, 0, 1], [0, 0, 0, 0, 1]),
        (ORG_PRIVATE, [1, 1, 0, 0, 1], [1, 1, 0, 0, 1]),
        (ORG_SHARED, [1, 1, 1, 0, 1], [1, 1, 0, 0, 1]),
        (OTHER_ORG_SHARED, [0, 0, 0, 0, 1], [0, 0, 0, 0, 1]),
    ],
)
def test_collection_rules(
    collection: Collection, view: list[int], edit: list[int]
) -> None:
    assert [policy.can_view_collection(a, collection) for a in ACTORS] == [
        bool(x) for x in view
    ]
    assert [policy.can_edit_collection(a, collection) for a in ACTORS] == [
        bool(x) for x in edit
    ]


def test_only_superadmin_sets_public_and_organization_needs_an_org() -> None:
    assert not policy.can_set_visibility(OWNER, ORG_SHARED, Visibility.PUBLIC)
    assert policy.can_set_visibility(ADMIN, ORG_SHARED, Visibility.PUBLIC)
    assert policy.can_set_visibility(EDITOR, ORG_PRIVATE, Visibility.ORGANIZATION)
    assert not policy.can_set_visibility(MEMBER, ORG_PRIVATE, Visibility.ORGANIZATION)
    assert not policy.can_set_visibility(OUTSIDER, MINE, Visibility.ORGANIZATION)
    assert not policy.can_set_visibility(ADMIN, MINE, Visibility.ORGANIZATION)
    assert policy.can_set_visibility(OUTSIDER, MINE, Visibility.PRIVATE)
    assert not policy.can_set_visibility(ADMIN, SYSTEM, Visibility.PRIVATE)


def test_create_collection_for_owner() -> None:
    def create(a: Actor, user: uuid.UUID | None, org: uuid.UUID | None) -> bool:
        return policy.can_create_collection_for(
            a, owner_user_id=user, owner_organization_id=org
        )

    assert create(OUTSIDER, ME, None)
    assert not create(OUTSIDER, SOMEONE, None)
    assert create(EDITOR, None, ORG)
    assert not create(MEMBER, None, ORG)
    assert create(ADMIN, None, None)
    assert not create(OWNER, None, None)
    assert not create(ADMIN, ME, ORG)
