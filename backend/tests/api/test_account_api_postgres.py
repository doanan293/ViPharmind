import pytest
from sqlalchemy import text

from pharma_agent.domain.account.models import session_id_of
from tests.api.postgres_app import (
    PASSWORD,
    csrf_header,
    new_email,
    postgres_app,
    register,
    verified_register,
)

pytestmark = pytest.mark.integration
PHONE = "+84912345678"


async def test_login_before_verification_is_refused_then_allowed(
    migrated_dsn: str,
) -> None:
    email = new_email()
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await register(client, email)
        refused = await client.post(
            "/api/v1/auth/cookie/login", data={"username": email, "password": PASSWORD}
        )
        assert (
            refused.status_code == 403
            and refused.json()["code"] == "EMAIL_NOT_VERIFIED"
        )
        verify = await client.post(
            "/api/v1/auth/email/verify",
            json={
                "email": email.upper(),
                "code": outbox.email.last_code(email),
                "password": PASSWORD,
            },
        )
        assert verify.status_code == 204 and "pharma_session" in client.cookies
        me = (await client.get("/api/v1/users/me")).json()
        assert me["email"] == email and me["email_verified"] and me["password_set"]


async def test_registration_uses_the_ui_language(migrated_dsn: str) -> None:
    email = new_email()
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": PASSWORD},
            headers={"Accept-Language": "en"},
        )
    assert outbox.email.sent[-1].subject == "Your ViPharmind verification code"


async def test_resend_inside_the_cooldown_is_429_with_retry_after(
    migrated_dsn: str,
) -> None:
    email = new_email()
    async with postgres_app(migrated_dsn) as (client, _, _outbox):
        await register(client, email)
        again = await client.post(
            "/api/v1/auth/email/verify/request", json={"email": email}
        )
    assert again.status_code == 429
    assert again.json()["code"] == "RATE_LIMITED"
    assert 1 <= int(again.headers["retry-after"]) <= 60


async def test_verify_with_a_wrong_password_is_400_and_keeps_the_code(
    migrated_dsn: str,
) -> None:
    email = new_email()
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await register(client, email)
        code = outbox.email.last_code(email)
        guessed = await client.post(
            "/api/v1/auth/email/verify",
            json={"email": email, "code": code, "password": "not-the-password"},
        )
        assert guessed.status_code == 400
        assert guessed.json()["code"] == "LOGIN_BAD_CREDENTIALS"
        assert "pharma_session" not in client.cookies
        missing = await client.post(
            "/api/v1/auth/email/verify", json={"email": email, "code": code}
        )
        assert missing.status_code == 400
        verified = await client.post(
            "/api/v1/auth/email/verify",
            json={"email": email, "code": code, "password": PASSWORD},
        )
        assert verified.status_code == 204, verified.text


async def test_wrong_code_is_400_otp_invalid(migrated_dsn: str) -> None:
    email = new_email()
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await register(client, email)
        real = outbox.email.last_code(email)
        wrong = "000000" if real != "000000" else "111111"
        response = await client.post(
            "/api/v1/auth/email/verify",
            json={"email": email, "code": wrong, "password": PASSWORD},
        )
    assert response.status_code == 400 and response.json()["code"] == "OTP_INVALID"


async def test_forgot_password_answers_the_same_and_reset_works(
    migrated_dsn: str,
) -> None:
    email = new_email()
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await verified_register(client, outbox, email)
        old_session = client.cookies["pharma_session"]
        client.cookies.clear()
        ghost = await client.post(
            "/api/v1/auth/password/forgot", json={"email": new_email()}
        )
        real = await client.post("/api/v1/auth/password/forgot", json={"email": email})
        assert ghost.status_code == real.status_code == 202
        reset = await client.post(
            "/api/v1/auth/password/reset",
            json={
                "email": email,
                "code": outbox.email.last_code(email),
                "password": "brand-new-pass",
            },
        )
        assert reset.status_code == 204
        replay = await client.get(
            "/api/v1/users/me", headers={"Cookie": f"pharma_session={old_session}"}
        )
        assert replay.status_code == 401
        login = await client.post(
            "/api/v1/auth/cookie/login",
            data={"username": email, "password": "brand-new-pass"},
        )
        assert login.status_code == 204


async def test_phone_sign_in_creates_a_phone_only_account(migrated_dsn: str) -> None:
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        sent = await client.post(
            "/api/v1/auth/phone/request", json={"phone": "0912 345 678"}
        )
        assert sent.status_code == 202
        login = await client.post(
            "/api/v1/auth/phone/login",
            json={"phone": "0912345678", "code": outbox.sms.last_code(PHONE)},
        )
        assert login.status_code == 204
        me = (await client.get("/api/v1/users/me")).json()
    assert me["email"] is None and me["phone_number"] == PHONE and me["phone_verified"]


async def test_foreign_numbers_are_422(migrated_dsn: str) -> None:
    async with postgres_app(migrated_dsn) as (client, _, _outbox):
        response = await client.post(
            "/api/v1/auth/phone/request", json={"phone": "+16502530000"}
        )
    assert (
        response.status_code == 422
        and response.json()["code"] == "PHONE_COUNTRY_NOT_ALLOWED"
    )


async def test_settings_change_email_password_and_profile(migrated_dsn: str) -> None:
    email, new = new_email(), new_email()
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await verified_register(client, outbox, email)
        # The first GET makes the CSRF middleware set `csrftoken`.
        await client.get("/api/v1/users/me")
        headers = csrf_header(client)
        assert (
            await client.post(
                "/api/v1/account/email", json={"email": new}, headers=headers
            )
        ).status_code == 202
        confirmed = await client.post(
            "/api/v1/account/email/confirm",
            json={"email": new, "code": outbox.email.last_code(new)},
            headers=headers,
        )
        assert confirmed.status_code == 200 and confirmed.json()["email"] == new
        wrong = await client.put(
            "/api/v1/account/password",
            json={"current_password": "nope", "new_password": "another-pass"},
            headers=headers,
        )
        assert (
            wrong.status_code == 400
            and wrong.json()["code"] == "CURRENT_PASSWORD_INVALID"
        )
        changed = await client.put(
            "/api/v1/account/password",
            json={"current_password": PASSWORD, "new_password": "another-pass"},
            headers=headers,
        )
        assert changed.status_code == 204
        profile = await client.patch(
            "/api/v1/users/me", json={"display_name": "An"}, headers=headers
        )
        assert profile.json()["display_name"] == "An"


async def test_revoking_the_current_session_logs_out(migrated_dsn: str) -> None:
    email = new_email()
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await verified_register(client, outbox, email)
        await client.get("/api/v1/users/me")
        sessions = (await client.get("/api/v1/account/sessions")).json()
        assert len(sessions) == 1 and sessions[0]["current"] is True
        assert sessions[0]["id"] == session_id_of(client.cookies["pharma_session"])
        revoke = await client.delete(
            f"/api/v1/account/sessions/{sessions[0]['id']}", headers=csrf_header(client)
        )
        assert revoke.status_code == 204
        assert (await client.get("/api/v1/users/me")).status_code == 401


async def test_login_is_throttled_after_ten_failures(migrated_dsn: str) -> None:
    email = new_email()
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await verified_register(client, outbox, email)
        client.cookies.clear()
        for _ in range(10):
            failed = await client.post(
                "/api/v1/auth/cookie/login",
                data={"username": email, "password": "wrong-pass"},
            )
            assert failed.status_code == 400
        locked = await client.post(
            "/api/v1/auth/cookie/login", data={"username": email, "password": PASSWORD}
        )
    assert locked.status_code == 429 and "retry-after" in locked.headers


async def test_sessions_and_limits_use_the_forwarded_client_ip(
    migrated_dsn: str,
) -> None:
    email = new_email()
    async with postgres_app(migrated_dsn, api={"trusted_proxy_hops": 1}) as (
        client,
        database,
        outbox,
    ):
        client.headers["x-forwarded-for"] = "203.0.113.9"
        await verified_register(client, outbox, email)
        sessions = (await client.get("/api/v1/account/sessions")).json()
        async with database.sessions() as session:
            keys = (
                (
                    await session.execute(
                        text(
                            "SELECT key FROM rate_limit_buckets WHERE key LIKE 'otp-send-ip:%'"
                        )
                    )
                )
                .scalars()
                .all()
            )
    assert sessions[0]["ip_address"] == "203.0.113.9"
    assert keys == ["otp-send-ip:203.0.113.9"]
