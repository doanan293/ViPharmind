from dataclasses import replace

import pytest

from pharma_agent.application.account.errors import (
    AccountDisabled,
    DeliveryFailed,
    InvalidCode,
    InvalidCredentials,
    PasswordInvalid,
    PhoneCountryNotAllowed,
    PhoneNumberInvalid,
    RateLimited,
)
from pharma_agent.application.account.service import AccountPolicy
from tests.account_fakes import OTP_SECRET, build_account_service

EMAIL = "an@example.com"
PHONE = "+84912345678"


async def test_verify_email_with_the_sent_code() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email=EMAIL)
    await service.request_email_verification(EMAIL, locale="vi", client_ip="1.1.1.1")
    code = fakes.email.last_code(EMAIL)
    assert (
        await service.verify_email(EMAIL, code, "old-password", client_ip=None)
        == user.id
    )
    verified = await fakes.accounts.get(user.id)
    assert verified is not None and verified.email_verified


async def test_verify_email_normalizes_the_address() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    await service.request_email_verification(
        "  An@Example.COM ", locale="vi", client_ip=None
    )
    code = fakes.email.last_code(EMAIL)
    assert await service.verify_email(
        " AN@example.com", code, "old-password", client_ip=None
    )


async def test_unknown_or_verified_emails_get_no_code_but_the_same_answer() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email="done@example.com", email_verified=True)
    await service.request_email_verification(
        "ghost@example.com", locale="vi", client_ip=None
    )
    await service.request_email_verification(
        "done@example.com", locale="vi", client_ip=None
    )
    assert fakes.email.sent == []


async def test_wrong_codes_count_and_five_failures_burn_the_code() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    code = fakes.email.last_code(EMAIL)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        with pytest.raises(InvalidCode):
            await service.verify_email(EMAIL, wrong, "old-password", client_ip=None)
    with pytest.raises(InvalidCode):
        await service.verify_email(EMAIL, code, "old-password", client_ip=None)


async def test_a_code_cannot_be_used_twice() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    code = fakes.email.last_code(EMAIL)
    await service.verify_email(EMAIL, code, "old-password", client_ip=None)
    with pytest.raises(InvalidCode):
        await service.verify_email(EMAIL, code, "old-password", client_ip=None)


async def test_codes_expire_after_ten_minutes() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    code = fakes.email.last_code(EMAIL)
    fakes.clock.advance(minutes=10, seconds=1)
    with pytest.raises(InvalidCode):
        await service.verify_email(EMAIL, code, "old-password", client_ip=None)


async def test_a_new_code_replaces_the_old_one() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    first = fakes.email.last_code(EMAIL)
    fakes.clock.advance(seconds=61)
    await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    second = fakes.email.last_code(EMAIL)
    if first != second:
        with pytest.raises(InvalidCode):
            await service.verify_email(EMAIL, first, "old-password", client_ip=None)
    assert await service.verify_email(EMAIL, second, "old-password", client_ip=None)


async def test_sending_is_limited_per_destination_and_per_ip() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    await service.request_email_verification(EMAIL, locale="vi", client_ip="1.1.1.1")
    with pytest.raises(RateLimited) as cooldown:
        await service.request_email_verification(
            EMAIL, locale="vi", client_ip="1.1.1.1"
        )
    assert 0 < cooldown.value.retry_after <= 60
    for _ in range(4):
        fakes.clock.advance(seconds=61)
        await service.request_email_verification(
            EMAIL, locale="vi", client_ip="1.1.1.1"
        )
    fakes.clock.advance(seconds=61)
    with pytest.raises(RateLimited):
        await service.request_email_verification(
            EMAIL, locale="vi", client_ip="1.1.1.1"
        )


async def test_limits_apply_even_when_the_account_does_not_exist() -> None:
    service, _ = build_account_service()
    await service.request_password_reset(
        "ghost@example.com", locale="vi", client_ip=None
    )
    with pytest.raises(RateLimited):
        await service.request_password_reset(
            "ghost@example.com", locale="vi", client_ip=None
        )


async def test_delivery_failure_revokes_the_code_and_reports_it() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    fakes.email.fail = True
    with pytest.raises(DeliveryFailed):
        await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    assert all(row.consumed_at is not None for row in fakes.codes.rows)


async def test_reset_password_sets_the_hash_verifies_email_and_ends_sessions() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email=EMAIL)
    fakes.sessions.add(user.id, "t-1")
    await service.request_password_reset(EMAIL, locale="en", client_ip=None)
    assert fakes.email.sent[-1].subject == "Your ViPharMind password reset code"
    await service.reset_password(EMAIL, fakes.email.last_code(EMAIL), "new-password-1")
    assert fakes.accounts.passwords[user.id] == "hashed:new-password-1"
    updated = await fakes.accounts.get(user.id)
    assert updated is not None and updated.email_verified
    assert await fakes.sessions.for_user(user.id) == []


async def test_reset_password_checks_the_password_before_using_the_code() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    await service.request_password_reset(EMAIL, locale="vi", client_ip=None)
    code = fakes.email.last_code(EMAIL)
    with pytest.raises(PasswordInvalid):
        await service.reset_password(EMAIL, code, "short")
    await service.reset_password(EMAIL, code, "long-enough")


async def test_phone_login_creates_the_account_once() -> None:
    service, fakes = build_account_service()
    await service.request_phone_login("0912 345 678", locale="vi", client_ip=None)
    assert fakes.sms.sent[-1].to == PHONE and fakes.sms.sent[-1].text.isascii()
    first = await service.login_with_phone("0912345678", fakes.sms.last_code(PHONE))
    fakes.clock.advance(seconds=61)
    await service.request_phone_login("+84 91 234 5678", locale="vi", client_ip=None)
    second = await service.login_with_phone(PHONE, fakes.sms.last_code(PHONE))
    assert first == second
    created = await fakes.accounts.get(first)
    assert created is not None and created.email is None and not created.password_set


async def test_phone_login_rejects_invalid_and_foreign_numbers() -> None:
    service, fakes = build_account_service()
    with pytest.raises(PhoneNumberInvalid):
        await service.request_phone_login("12345", locale="vi", client_ip=None)
    with pytest.raises(PhoneCountryNotAllowed):
        await service.request_phone_login(
            "+1 650 253 0000", locale="vi", client_ip=None
        )
    assert fakes.sms.sent == []


async def test_login_failures_lock_the_email_for_the_window() -> None:
    service, fakes = build_account_service()
    for _ in range(10):
        await service.check_login_allowed(EMAIL, "1.1.1.1")
        await service.record_login_failure(EMAIL, "1.1.1.1")
    with pytest.raises(RateLimited):
        await service.check_login_allowed(EMAIL, "2.2.2.2")
    with pytest.raises(RateLimited):
        await service.check_login_allowed("other@example.com", "1.1.1.1")
    fakes.clock.advance(minutes=15)
    await service.check_login_allowed(EMAIL, "2.2.2.2")


async def test_a_failed_delivery_does_not_use_up_the_resend_cooldown() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    fakes.email.fail = True
    with pytest.raises(DeliveryFailed):
        await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    fakes.email.fail = False
    await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    assert fakes.email.last_code(EMAIL)


async def test_verify_email_needs_the_account_password() -> None:
    """Whoever registered the address set the password; the inbox owner who did not
    must go through password reset, which replaces it."""
    service, fakes = build_account_service()
    user = fakes.accounts.add(email=EMAIL)
    await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    code = fakes.email.last_code(EMAIL)
    with pytest.raises(InvalidCredentials):
        await service.verify_email(EMAIL, code, "guess", client_ip=None)
    with pytest.raises(InvalidCredentials):
        await service.verify_email(EMAIL, code, None, client_ip=None)
    unverified = await fakes.accounts.get(user.id)
    assert unverified is not None and not unverified.email_verified
    # A wrong password does not burn the code.
    assert await service.verify_email(EMAIL, code, "old-password", client_ip=None)


async def test_verify_email_password_guesses_share_the_login_throttle() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    code = fakes.email.last_code(EMAIL)
    for _ in range(10):
        with pytest.raises(InvalidCredentials):
            await service.verify_email(EMAIL, code, "guess", client_ip="1.1.1.1")
    with pytest.raises(RateLimited):
        await service.verify_email(EMAIL, code, "old-password", client_ip="1.1.1.1")


async def test_verify_email_without_a_password_set_needs_only_the_code() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email=EMAIL, password_set=False)
    await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    code = fakes.email.last_code(EMAIL)
    assert await service.verify_email(EMAIL, code, None, client_ip=None) == user.id


async def test_reset_password_refuses_a_disabled_account() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email=EMAIL)
    await service.request_password_reset(EMAIL, locale="vi", client_ip=None)
    code = fakes.email.last_code(EMAIL)
    fakes.accounts.users[user.id] = replace(
        fakes.accounts.users[user.id], is_active=False
    )
    with pytest.raises(AccountDisabled):
        await service.reset_password(EMAIL, code, "new-password-1")
    assert fakes.accounts.passwords[user.id] == "hashed:old-password"


async def test_the_send_cooldown_lasts_a_full_minute_from_the_send() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    fakes.clock.advance(seconds=50)
    await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    fakes.clock.advance(seconds=20)
    with pytest.raises(RateLimited) as cooldown:
        await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    assert cooldown.value.retry_after == pytest.approx(40)
    fakes.clock.advance(seconds=40)
    await service.request_email_verification(EMAIL, locale="vi", client_ip=None)


async def test_a_refused_send_does_not_count_against_the_other_limits() -> None:
    policy = AccountPolicy(otp_secret=OTP_SECRET, sends_per_ip_per_hour=2)
    service, fakes = build_account_service(policy=policy)
    fakes.accounts.add(email=EMAIL)
    await service.request_email_verification(EMAIL, locale="vi", client_ip="1.1.1.1")
    for _ in range(3):
        with pytest.raises(RateLimited):
            await service.request_email_verification(
                EMAIL, locale="vi", client_ip="1.1.1.1"
            )
    # The cooldown refusals above did not use up the IP's second send.
    await service.request_password_reset(EMAIL, locale="vi", client_ip="1.1.1.1")
