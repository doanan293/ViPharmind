import re

import httpx
import pytest

from tests.api.postgres_app import (
    AppOutbox,
    cookie_login,
    csrf_header,
    new_email,
    postgres_app,
    verified_register,
)

pytestmark = pytest.mark.integration

TOKEN = re.compile(r"/invitations/([A-Za-z0-9_-]+)")


def invitation_token(outbox: AppOutbox, to: str) -> str:
    sent = [mail for mail in outbox.email.sent if mail.to == to]
    match = TOKEN.search(sent[-1].text)
    assert match is not None
    return match.group(1)


async def sign_up(client: httpx.AsyncClient, outbox: AppOutbox, email: str) -> None:
    client.cookies.clear()
    await verified_register(client, outbox, email)


async def sign_in(client: httpx.AsyncClient, email: str) -> None:
    client.cookies.clear()
    await cookie_login(client, email)
    # The first authenticated GET sets the csrftoken cookie.
    await client.get("/api/v1/users/me")


async def create_org(client: httpx.AsyncClient, name: str = "Org") -> dict[str, str]:
    response = await client.post(
        "/api/v1/organizations", json={"name": name}, headers=csrf_header(client)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_invite_accept_and_roles(migrated_dsn: str) -> None:
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        owner, invitee = new_email(), new_email()
        await sign_up(client, outbox, owner)
        org = await create_org(client, "Khoa Dược")
        assert org["role"] == "owner" and org["member_count"] == 1
        base = f"/api/v1/organizations/{org['id']}"
        invited = await client.post(
            f"{base}/invitations",
            json={"email": invitee, "role": "member"},
            headers=csrf_header(client),
        )
        assert invited.status_code == 201, invited.text
        assert invited.json()["status"] == "sent"
        token = invitation_token(outbox, invitee)

        await sign_up(client, outbox, invitee)
        client.cookies.clear()
        preview = await client.get(f"/api/v1/invitations/{token}")
        assert preview.status_code == 200, preview.text
        assert preview.json()["organization_name"] == "Khoa Dược"

        await sign_in(client, invitee)
        accepted = await client.post(
            f"/api/v1/invitations/{token}/accept", headers=csrf_header(client)
        )
        assert accepted.status_code == 200, accepted.text
        mine = (await client.get("/api/v1/organizations")).json()
        assert [(o["name"], o["role"]) for o in mine] == [("Khoa Dược", "member")]

        renamed = await client.patch(
            base, json={"name": "X"}, headers=csrf_header(client)
        )
        assert renamed.status_code == 403
        assert renamed.json()["code"] == "FORBIDDEN_ROLE"
        assert (await client.get(f"{base}/audit")).status_code == 403
        members = (await client.get(f"{base}/members")).json()
        assert {m["role"] for m in members} == {"owner", "member"}

        await sign_in(client, owner)
        log = (await client.get(f"{base}/audit")).json()
        assert "member.joined" in [item["action"] for item in log["items"]]


async def test_outsiders_see_404_on_every_organization_route(migrated_dsn: str) -> None:
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await sign_up(client, outbox, new_email())
        org = await create_org(client)
        await sign_up(client, outbox, new_email())
        headers = csrf_header(client)
        base = f"/api/v1/organizations/{org['id']}"
        responses = [
            await client.get(base),
            await client.patch(base, json={"name": "x"}, headers=headers),
            await client.request(
                "DELETE", base, json={"confirm_name": "Org"}, headers=headers
            ),
            await client.get(f"{base}/members"),
            await client.get(f"{base}/invitations"),
            await client.post(
                f"{base}/invitations",
                json={"email": "c@example.com", "role": "member"},
                headers=headers,
            ),
            await client.get(f"{base}/audit"),
            await client.post(f"{base}/leave", headers=headers),
        ]
        for response in responses:
            assert response.status_code == 404, (response.request.url, response.text)


async def test_owner_deletes_with_the_name_and_the_last_owner_stays(
    migrated_dsn: str,
) -> None:
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await sign_up(client, outbox, new_email())
        org = await create_org(client, "Org")
        base = f"/api/v1/organizations/{org['id']}"
        left = await client.post(f"{base}/leave", headers=csrf_header(client))
        assert left.status_code == 409 and left.json()["code"] == "LAST_OWNER"
        wrong = await client.request(
            "DELETE", base, json={"confirm_name": "org"}, headers=csrf_header(client)
        )
        assert wrong.status_code == 422
        deleted = await client.request(
            "DELETE", base, json={"confirm_name": "Org"}, headers=csrf_header(client)
        )
        assert deleted.status_code == 204
        assert (await client.get("/api/v1/organizations")).json() == []
        mine = (await client.get("/api/v1/account/audit")).json()
        assert mine["items"] == []
