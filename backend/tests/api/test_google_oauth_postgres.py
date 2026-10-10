"""Google OAuth on the cookie backend: the callback logs the user in with pharma_session.

Google's token and People API endpoints are mocked with respx, so the real GoogleOAuth2
client and the fastapi-users OAuth router run unchanged.
"""

from uuid import uuid4

import httpx
import pytest
import respx

from tests.api.postgres_app import (
    new_email,
    postgres_app,
    register,
    set_cookie,
    verified_register,
)

pytestmark = pytest.mark.integration

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_PROFILE_URL = "https://people.googleapis.com/v1/people/me"
GOOGLE_AUTH: dict[str, object] = {
    "google_client_id": "client-id",
    "google_client_secret": "client-secret",
}
TOKEN_RESPONSE = httpx.Response(
    200,
    json={
        "access_token": "google-access-token",
        "token_type": "Bearer",
        "expires_in": 3600,
    },
)


async def test_google_callback_sets_the_session_cookie(migrated_dsn: str) -> None:
    email = new_email()
    async with respx.mock(assert_all_called=True) as google:
        token_route = google.post(GOOGLE_TOKEN_URL).mock(return_value=TOKEN_RESPONSE)
        google.get(GOOGLE_PROFILE_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "resourceName": "people/1234567890",
                    "emailAddresses": [{"value": email, "metadata": {"primary": True}}],
                },
            )
        )
        async with postgres_app(migrated_dsn, auth=GOOGLE_AUTH) as (client, _, _outbox):
            authorize = await client.get("/api/v1/auth/google/authorize")
            assert authorize.status_code == 200, authorize.text
            authorization_url = httpx.URL(authorize.json()["authorization_url"])
            assert (
                authorization_url.params["redirect_uri"]
                == "http://localhost:3000/auth/google/callback"
            )
            callback = await client.get(
                "/api/v1/auth/google/callback",
                params={
                    "code": "auth-code",
                    "state": authorization_url.params["state"],
                },
            )
            assert callback.status_code == 204, callback.text
            assert "httponly" in set_cookie(callback, "pharma_session")
            me = await client.get("/api/v1/users/me")
            assert me.status_code == 200, me.text
            assert me.json()["email"] == email
            assert me.json()["is_verified"] is True
    assert b"code=auth-code" in token_route.calls.last.request.content


async def test_google_callback_without_the_state_cookie_is_rejected(
    migrated_dsn: str,
) -> None:
    async with respx.mock(assert_all_called=True) as google:
        google.post(GOOGLE_TOKEN_URL).mock(return_value=TOKEN_RESPONSE)
        async with postgres_app(migrated_dsn, auth=GOOGLE_AUTH) as (client, _, _outbox):
            authorize = await client.get("/api/v1/auth/google/authorize")
            state = httpx.URL(authorize.json()["authorization_url"]).params["state"]
            client.cookies.clear()
            callback = await client.get(
                "/api/v1/auth/google/callback",
                params={"code": "auth-code", "state": state},
            )
            assert callback.status_code == 400
            assert callback.json()["code"] == "OAUTH_INVALID_STATE"
            assert "pharma_session" not in client.cookies


async def google_login(
    client: httpx.AsyncClient, google: respx.MockRouter, email: str
) -> httpx.Response:
    google.post(GOOGLE_TOKEN_URL).mock(return_value=TOKEN_RESPONSE)
    google.get(GOOGLE_PROFILE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                # A new Google account per login: the database is shared by the session.
                "resourceName": f"people/{uuid4().int}",
                "emailAddresses": [{"value": email, "metadata": {"primary": True}}],
            },
        )
    )
    authorize = await client.get("/api/v1/auth/google/authorize")
    state = httpx.URL(authorize.json()["authorization_url"]).params["state"]
    return await client.get(
        "/api/v1/auth/google/callback", params={"code": "auth-code", "state": state}
    )


async def test_google_does_not_take_over_an_unverified_registration(
    migrated_dsn: str,
) -> None:
    email = new_email()
    async with (
        respx.mock() as google,
        postgres_app(migrated_dsn, auth=GOOGLE_AUTH) as (client, _, _outbox),
    ):
        await register(client, email)
        callback = await google_login(client, google, email)
    assert callback.status_code == 400
    assert callback.json()["code"] == "OAUTH_USER_ALREADY_EXISTS"


async def test_google_links_to_a_verified_registration(migrated_dsn: str) -> None:
    email = new_email()
    async with (
        respx.mock() as google,
        postgres_app(migrated_dsn, auth=GOOGLE_AUTH) as (client, _, outbox),
    ):
        await verified_register(client, outbox, email)
        client.cookies.clear()
        callback = await google_login(client, google, email)
        assert callback.status_code == 204, callback.text
        me = await client.get("/api/v1/users/me")
    assert me.json()["google_linked"] is True and me.json()["password_set"] is True


async def test_google_sign_up_has_no_password_and_a_verified_email(
    migrated_dsn: str,
) -> None:
    email = new_email()
    async with (
        respx.mock() as google,
        postgres_app(migrated_dsn, auth=GOOGLE_AUTH) as (client, _, _outbox),
    ):
        assert (await google_login(client, google, email)).status_code == 204
        me = (await client.get("/api/v1/users/me")).json()
    assert me["email_verified"] is True and me["password_set"] is False
