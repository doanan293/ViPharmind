import pytest

from tests.api.postgres_app import (
    cookie_login,
    csrf_header,
    new_email,
    postgres_app,
    verified_register,
)

pytestmark = pytest.mark.integration


async def test_personal_collections_stay_private_and_public_is_superadmin_only(
    migrated_dsn: str,
) -> None:
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        owner, other = new_email(), new_email()
        await verified_register(client, outbox, owner)
        created = await client.post(
            "/api/v1/collections",
            json={"title": "Ghi chú thuốc", "owner_organization_id": None},
            headers=csrf_header(client),
        )
        assert created.status_code == 201, created.text
        collection = created.json()
        assert collection["visibility"] == "private" and collection["can_edit"]
        groups = (await client.get("/api/v1/collections")).json()
        assert [c["id"] for c in groups["mine"]] == [collection["id"]]
        public = await client.patch(
            f"/api/v1/collections/{collection['id']}",
            json={"visibility": "public"},
            headers=csrf_header(client),
        )
        assert public.status_code == 403
        assert public.json()["code"] == "FORBIDDEN_ROLE"
        quota = (await client.get("/api/v1/collections/quota")).json()
        assert quota["collections_used"] == 1 and quota["collections_limit"] == 5

        client.cookies.clear()
        await verified_register(client, outbox, other)
        assert (await client.get("/api/v1/collections")).json()["mine"] == []
        hidden = await client.get(f"/api/v1/collections/{collection['id']}")
        assert hidden.status_code == 404
        assert hidden.json()["code"] == "COLLECTION_NOT_FOUND"

        client.cookies.clear()
        await cookie_login(client, owner)
        await client.get("/api/v1/users/me")
        deleted = await client.delete(
            f"/api/v1/collections/{collection['id']}", headers=csrf_header(client)
        )
        assert deleted.status_code == 204
        assert (await client.get("/api/v1/collections")).json()["mine"] == []


async def test_a_conversation_keeps_its_chosen_sources(migrated_dsn: str) -> None:
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await verified_register(client, outbox, new_email())
        headers = csrf_header(client)
        conversation = (
            await client.post("/api/v1/conversations", headers=headers)
        ).json()
        url = f"/api/v1/conversations/{conversation['id']}"
        empty = await client.patch(url, json={"collection_ids": []}, headers=headers)
        assert empty.status_code == 422
        chosen = "0b8f7a52-5d4e-4c7b-9a51-3f7d1c2b9e10"
        narrowed = await client.patch(
            url, json={"collection_ids": [chosen]}, headers=headers
        )
        assert narrowed.status_code == 200, narrowed.text
        assert narrowed.json()["collection_ids"] == [chosen]
        renamed = await client.patch(url, json={"title": "Tim mạch"}, headers=headers)
        assert renamed.json()["collection_ids"] == [chosen]
        reset = await client.patch(url, json={"collection_ids": None}, headers=headers)
        assert reset.json()["collection_ids"] is None
