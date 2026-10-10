import httpx
import pytest

from tests.api.postgres_app import (
    AppOutbox,
    csrf_header,
    new_email,
    postgres_app,
    verified_register,
)

pytestmark = pytest.mark.integration

MARKDOWN = "# Liều dùng\n\nNgười lớn 500 mg mỗi 6 giờ.\n\n## Trẻ em\n\n10 mg/kg."


async def collection(client: httpx.AsyncClient) -> str:
    response = await client.post(
        "/api/v1/collections",
        json={"title": "Ghi chú", "owner_organization_id": None},
        headers=csrf_header(client),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_write_upload_and_publish_a_collection(migrated_dsn: str) -> None:
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await verified_register(client, outbox, new_email())
        headers = csrf_header(client)
        cid = await collection(client)
        base = f"/api/v1/collections/{cid}"

        nothing = await client.post(f"{base}/publish", headers=headers)
        assert nothing.status_code == 422

        created = await client.post(
            f"{base}/documents",
            json={"title": "Paracetamol", "markdown": MARKDOWN},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        document = created.json()
        assert document["key"] == "paracetamol"
        assert document["char_count"] == len(MARKDOWN)
        listed = (await client.get(f"{base}/documents")).json()
        assert [d["title"] for d in listed] == ["Paracetamol"]
        assert "markdown" not in listed[0]

        uploaded = await client.post(
            f"{base}/documents/upload",
            files={
                "file": ("ibuprofen.md", b"# Ibuprofen\n\nGiam dau.", "text/markdown")
            },
            headers=headers,
        )
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["title"] == "Ibuprofen"
        assert len((await client.get(f"{base}/documents")).json()) == 1

        sections = (await client.get(f"{base}/sections")).json()
        assert [s["label"] for s in sections] == [
            "Paracetamol › Liều dùng",
            "Paracetamol › Liều dùng › Trẻ em",
        ]
        duplicate = await client.put(
            f"{base}/glossary",
            json=[{"term": "ADR"}, {"term": "adr"}],
            headers=headers,
        )
        assert duplicate.status_code == 422
        saved = await client.put(
            f"{base}/colloquial",
            json=[{"key": "hạ sốt", "section_keys": [sections[0]["key"]]}],
            headers=headers,
        )
        assert saved.status_code == 200, saved.text

        job = await publish_and_wait(client, outbox, base)
        assert job["status"] == "ready" and job["release_number"] == 1
        view = (await client.get(base)).json()
        assert view["current_release_number"] == 1
        releases = (await client.get(f"{base}/releases")).json()
        assert [(r["number"], r["current"]) for r in releases] == [(1, True)]

        again = await publish_and_wait(client, outbox, base)
        assert again["release_number"] == 1


async def publish_and_wait(
    client: httpx.AsyncClient, outbox: AppOutbox, base: str
) -> dict[str, object]:
    queued = await client.post(f"{base}/publish", headers=csrf_header(client))
    assert queued.status_code == 202, queued.text
    assert queued.json()["status"] == "queued"
    await outbox.drain_jobs()
    response = await client.get(f"/api/v1/ingest-jobs/{queued.json()['id']}")
    assert response.status_code == 200, response.text
    return response.json()


async def test_uploads_must_be_utf8_text_files(migrated_dsn: str) -> None:
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await verified_register(client, outbox, new_email())
        cid = await collection(client)
        url = f"/api/v1/collections/{cid}/documents/upload"
        binary = await client.post(
            url,
            files={"file": ("a.pdf", b"%PDF-1.7", "application/pdf")},
            headers=csrf_header(client),
        )
        assert binary.status_code == 422
        latin = await client.post(
            url,
            files={"file": ("a.txt", "Liều".encode("utf-16"), "text/plain")},
            headers=csrf_header(client),
        )
        assert latin.status_code == 422
        plain = await client.post(
            url,
            files={
                "file": ("ghi chu.txt", "Dòng một\nDòng hai".encode(), "text/plain")
            },
            headers=csrf_header(client),
        )
        assert plain.json() == {
            "title": "ghi chu",
            "markdown": "Dòng một\nDòng hai",
            "char_count": 17,
        }
