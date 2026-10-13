import pytest

from tests.api.postgres_app import csrf_header, new_email, postgres_app
from tests.api.test_documents_api_postgres import publish_and_wait
from tests.api.test_organizations_api_postgres import create_org, sign_up

pytestmark = pytest.mark.integration

URL = "/api/v1/maintenance/daily"
SECRET = "m" * 40
CRON = {"Authorization": f"Bearer {SECRET}"}


async def test_daily_maintenance_purges_collections_of_a_deleted_organization(
    migrated_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CRON_SECRET", SECRET)
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        assert (await client.get(URL)).status_code == 401
        # Collections left by earlier tests are purged first.
        assert (await client.get(URL, headers=CRON)).status_code == 200

        await sign_up(client, outbox, new_email())
        org = await create_org(client, "Org")
        created = await client.post(
            "/api/v1/collections",
            json={"title": "Thuốc", "owner_organization_id": org["id"]},
            headers=csrf_header(client),
        )
        assert created.status_code == 201, created.text
        base = f"/api/v1/collections/{created.json()['id']}"
        document = await client.post(
            f"{base}/documents",
            json={"title": "Paracetamol", "markdown": "# Liều\n\nNgười lớn 500 mg."},
            headers=csrf_header(client),
        )
        assert document.status_code == 201, document.text
        assert (await publish_and_wait(client, outbox, base))["status"] == "ready"
        deleted = await client.request(
            "DELETE",
            f"/api/v1/organizations/{org['id']}",
            json={"confirm_name": "Org"},
            headers=csrf_header(client),
        )
        assert deleted.status_code == 204

        report = await client.get(URL, headers=CRON)
        assert report.status_code == 200, report.text
        assert report.json()["collections_purged"] == 1
        assert set(report.json()) == {
            "sessions_deleted",
            "codes_deleted",
            "rate_limit_buckets_deleted",
            "collections_purged",
        }
        again = await client.get(URL, headers=CRON)
        assert again.json()["collections_purged"] == 0
