import uuid

import pytest

from pharma_agent.application.access.service import ActorResolver
from pharma_agent.application.errors import AccountNotFound
from pharma_agent.domain.access.models import Role
from tests.account_fakes import InMemoryAccounts
from tests.organization_fakes import InMemoryOrganizations


async def test_resolves_memberships_and_the_superadmin_flag() -> None:
    accounts = InMemoryAccounts()
    organizations = InMemoryOrganizations(accounts)
    user = accounts.add(email="an@example.com")
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    organizations.seed_member(org_a, user.id, Role.OWNER)
    organizations.seed_member(org_b, user.id, Role.MEMBER)

    actor = await ActorResolver(accounts, organizations).resolve(user.id)

    assert actor.user_id == user.id and not actor.is_superadmin
    assert actor.memberships == {org_a: Role.OWNER, org_b: Role.MEMBER}


async def test_unknown_users_are_not_found() -> None:
    accounts = InMemoryAccounts()
    resolver = ActorResolver(accounts, InMemoryOrganizations(accounts))
    with pytest.raises(AccountNotFound):
        await resolver.resolve(uuid.uuid4())
