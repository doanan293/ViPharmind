import uuid
from typing import ClassVar

import pytest

from pharma_agent.application.account.errors import (
    AccountNotFound,
    CurrentPasswordInvalid,
    EmailAlreadyUsed,
    InvalidCode,
    LastSignInMethod,
    PhoneAlreadyUsed,
    PhoneSignInDisabled,
    RateLimited,
    SessionNotFound,
)
from pharma_agent.application.account.service import AccountPolicy
from pharma_agent.domain.access.models import Role
from pharma_agent.domain.account.models import session_id_of
from pharma_agent.domain.organizations.models import Organization
from tests.account_fakes import OTP_SECRET, START, build_account_service

PHONE = "+84912345678"


async def test_account_view_and_profile_update() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email="an@example.com", email_verified=True)
    view = await service.update_profile(user.id, "  Nguyễn An ")
    assert view.display_name == "Nguyễn An"
    assert view.email_verified and view.is_verified and not view.phone_verified


async def test_change_email_sends_to_the_new_address_and_notifies_the_old() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email="an@example.com", email_verified=True)
    await service.request_email_change(
        user.id, "An.New@Example.com", locale="vi", client_ip=None
    )
    code = fakes.email.last_code("an.new@example.com")
    view = await service.confirm_email_change(
        user.id, "an.new@example.com", code, locale="vi"
    )
    assert view.email == "an.new@example.com" and view.email_verified
    assert fakes.email.sent[-1].to == "an@example.com"
    assert "an.new@example.com" in fakes.email.sent[-1].text


async def test_change_email_rejects_an_address_of_another_account() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email="an@example.com", email_verified=True)
    fakes.accounts.add(email="bo@example.com")
    with pytest.raises(EmailAlreadyUsed):
        await service.request_email_change(
            user.id, "bo@example.com", locale="vi", client_ip=None
        )


async def test_a_code_for_someone_else_does_not_change_my_email() -> None:
    service, fakes = build_account_service()
    owner = fakes.accounts.add(email="an@example.com", email_verified=True)
    attacker = fakes.accounts.add(email="eve@example.com", email_verified=True)
    await service.request_email_change(
        owner.id, "new@example.com", locale="vi", client_ip=None
    )
    code = fakes.email.last_code("new@example.com")
    with pytest.raises(InvalidCode):
        await service.confirm_email_change(
            attacker.id, "new@example.com", code, locale="vi"
        )


async def test_change_phone_and_conflicts() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email="an@example.com", email_verified=True)
    fakes.accounts.add(email=None, phone="+84987654321", phone_verified=True)
    with pytest.raises(PhoneAlreadyUsed):
        await service.request_phone_change(
            user.id, "0987654321", locale="vi", client_ip=None
        )
    await service.request_phone_change(
        user.id, "0912 345 678", locale="vi", client_ip=None
    )
    view = await service.confirm_phone_change(
        user.id, "0912345678", fakes.sms.last_code(PHONE)
    )
    assert view.phone_number == PHONE and view.phone_verified


async def test_change_password_needs_the_current_one_when_set() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(
        email="an@example.com", email_verified=True, password="old-password"
    )
    with pytest.raises(CurrentPasswordInvalid):
        await service.change_password(
            user.id, current_password="wrong", new_password="new-password"
        )
    with pytest.raises(CurrentPasswordInvalid):
        await service.change_password(
            user.id, current_password=None, new_password="new-password"
        )
    await service.change_password(
        user.id, current_password="old-password", new_password="new-password"
    )
    assert fakes.accounts.passwords[user.id] == "hashed:new-password"


async def test_phone_accounts_set_a_first_password_without_the_current_one() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(
        email=None, phone=PHONE, phone_verified=True, password_set=False
    )
    await service.change_password(
        user.id, current_password=None, new_password="first-password"
    )
    view = await service.get_account(user.id)
    assert view.password_set


async def test_google_cannot_be_unlinked_when_it_is_the_last_method() -> None:
    service, fakes = build_account_service()
    only_google = fakes.accounts.add(
        email="g@example.com", email_verified=True, password_set=False, google=True
    )
    with pytest.raises(LastSignInMethod):
        await service.unlink_google(only_google.id)
    both = fakes.accounts.add(email="b@example.com", email_verified=True, google=True)
    view = await service.unlink_google(both.id)
    assert not view.google_linked


async def test_sessions_list_marks_the_current_one_and_revokes() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email="an@example.com", email_verified=True)
    fakes.sessions.add(user.id, "t-current")
    fakes.sessions.add(user.id, "t-other")
    views = await service.list_sessions(user.id, "t-current")
    assert {view.current for view in views} == {True, False}
    assert all("t-" not in view.id for view in views)
    await service.revoke_session(user.id, session_id_of("t-other"))
    with pytest.raises(SessionNotFound):
        await service.revoke_session(user.id, session_id_of("t-other"))
    fakes.sessions.add(user.id, "t-third")
    assert await service.revoke_other_sessions(user.id, "t-current") == 1
    assert [
        view.current for view in await service.list_sessions(user.id, "t-current")
    ] == [True]


async def test_unknown_account_is_reported() -> None:
    service, _ = build_account_service()
    with pytest.raises(AccountNotFound):
        await service.get_account(uuid.uuid4())


async def test_probing_taken_addresses_is_rate_limited_per_ip() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email="an@example.com", email_verified=True)
    for index in range(20):
        fakes.accounts.add(email=f"taken{index}@example.com")
    for index in range(20):
        with pytest.raises(EmailAlreadyUsed):
            await service.request_email_change(
                user.id, f"taken{index}@example.com", locale="vi", client_ip="9.9.9.9"
            )
    with pytest.raises(RateLimited):
        await service.request_email_change(
            user.id, "taken0@example.com", locale="vi", client_ip="9.9.9.9"
        )


async def test_an_email_taken_meanwhile_keeps_the_change_code_unused() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email="an@example.com", email_verified=True)
    await service.request_email_change(
        user.id, "new@example.com", locale="vi", client_ip=None
    )
    code = fakes.email.last_code("new@example.com")
    fakes.accounts.add(email="new@example.com", email_verified=True)
    with pytest.raises(EmailAlreadyUsed):
        await service.confirm_email_change(
            user.id, "new@example.com", code, locale="vi"
        )
    assert all(row.consumed_at is None for row in fakes.codes.rows)


async def test_a_phone_taken_meanwhile_keeps_the_change_code_unused() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email="an@example.com", email_verified=True)
    await service.request_phone_change(
        user.id, "0987654321", locale="vi", client_ip=None
    )
    code = fakes.sms.last_code("+84987654321")
    fakes.accounts.add(email=None, phone="+84987654321", phone_verified=True)
    with pytest.raises(PhoneAlreadyUsed):
        await service.confirm_phone_change(user.id, "0987654321", code)
    assert all(row.consumed_at is None for row in fakes.codes.rows)


async def test_the_account_lists_its_organizations() -> None:
    service, fakes = build_account_service(memberships=FakeMemberships())
    user = fakes.accounts.add(email="an@example.com", email_verified=True)
    org = Organization(uuid.uuid4(), "Khoa Dược", None, None, START, START)
    FakeMemberships.rows[user.id] = [(org, Role.EDITOR)]
    view = await service.get_account(user.id)
    assert [(m.organization_id, m.name, m.role) for m in view.memberships] == [
        (org.id, "Khoa Dược", Role.EDITOR)
    ]
    assert view.is_superadmin is False and view.phone_sign_in_enabled is True


async def test_phone_codes_are_refused_when_sms_is_off() -> None:
    policy = AccountPolicy(otp_secret=OTP_SECRET, sms_enabled=False)
    service, fakes = build_account_service(policy=policy)
    user = fakes.accounts.add(email="an@example.com", email_verified=True)
    with pytest.raises(PhoneSignInDisabled):
        await service.request_phone_login("0912345678", locale="vi", client_ip=None)
    with pytest.raises(PhoneSignInDisabled):
        await service.request_phone_change(
            user.id, "0912345678", locale="vi", client_ip=None
        )
    assert fakes.sms.sent == []
    assert (await service.get_account(user.id)).phone_sign_in_enabled is False


class FakeMemberships:
    rows: ClassVar[dict[uuid.UUID, list[tuple[Organization, Role]]]] = {}

    async def list_for_user(
        self, user_id: uuid.UUID
    ) -> list[tuple[Organization, Role]]:
        return self.rows.get(user_id, [])
