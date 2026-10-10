import httpx
import pytest
from sqlalchemy import text

from pharma_agent.infrastructure.persistence.postgres.database import Database
from tests.api.postgres_app import (
    cookie_login,
    csrf_header,
    new_email,
    postgres_app,
    verified_register,
)

pytestmark = pytest.mark.integration


async def make_superadmin(database: Database, email: str) -> None:
    async with database.engine.begin() as connection:
        await connection.execute(
            text('UPDATE "user" SET is_superuser = true WHERE email = :email'),
            {"email": email},
        )


async def sign_in(client: httpx.AsyncClient, email: str) -> None:
    client.cookies.clear()
    await cookie_login(client, email)
    await client.get("/api/v1/users/me")


async def test_the_console_is_hidden_from_everyone_but_superadmins(
    migrated_dsn: str,
) -> None:
    async with postgres_app(migrated_dsn) as (client, database, outbox):
        admin, user = new_email(), new_email()
        await verified_register(client, outbox, user)
        conversation = (
            await client.post("/api/v1/conversations", headers=csrf_header(client))
        ).json()
        for path in ("/api/v1/admin/users", "/api/v1/admin/audit"):
            assert (await client.get(path)).status_code == 404

        client.cookies.clear()
        await verified_register(client, outbox, admin)
        await make_superadmin(database, admin)
        await sign_in(client, admin)
        users = (await client.get("/api/v1/admin/users", params={"q": user})).json()
        [row] = users["items"]
        assert row["email"] == user and row["is_active"]

        before = len((await client.get("/api/v1/admin/audit")).json()["items"])
        listed = await client.get(f"/api/v1/admin/users/{row['id']}/conversations")
        # Like the user's own list, an empty conversation stays hidden until it has a turn.
        assert listed.status_code == 200 and listed.json()["items"] == []
        messages = await client.get(
            f"/api/v1/admin/users/{row['id']}/conversations/{conversation['id']}/messages"
        )
        assert messages.status_code == 200
        after = len((await client.get("/api/v1/admin/audit")).json()["items"])
        # Reading conversations leaves no audit event (spec §2).
        assert after == before

        disabled = await client.patch(
            f"/api/v1/admin/users/{row['id']}",
            json={"is_active": False},
            headers=csrf_header(client),
        )
        assert disabled.status_code == 200 and disabled.json()["is_active"] is False
        actions = [
            e["action"]
            for e in (await client.get("/api/v1/admin/audit")).json()["items"]
        ]
        assert actions[0] == "user.disabled"
        quotas = await client.patch(
            f"/api/v1/admin/users/{row['id']}",
            json={"collection_quota": 9},
            headers=csrf_header(client),
        )
        assert quotas.json()["collection_quota"] == 9
        assert (await client.get("/api/v1/admin/collections")).status_code == 200
        assert (await client.get("/api/v1/admin/ingest-jobs")).status_code == 200
        assert (await client.get("/api/v1/admin/organizations")).status_code == 200

        client.cookies.clear()
        refused = await client.post(
            "/api/v1/auth/cookie/login",
            data={"username": user, "password": "S3cure-password!"},
        )
        assert refused.status_code == 400
