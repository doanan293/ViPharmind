import uuid

import pytest

from tests.api.postgres_app import postgres_app

pytestmark = pytest.mark.integration

TOKEN = "i" * 40


async def test_the_job_runner_endpoint_needs_the_internal_token(
    migrated_dsn: str,
) -> None:
    jobs: dict[str, object] = {"internal_token": TOKEN}
    async with postgres_app(migrated_dsn, jobs=jobs) as (client, _, _outbox):
        url = f"/api/v1/internal/ingest-jobs/{uuid.uuid4()}/run"
        refused = await client.post(url)
        assert refused.status_code == 401
        wrong = await client.post(url, headers={"x-internal-token": "nope"})
        assert wrong.status_code == 401
        unknown = await client.post(url, headers={"x-internal-token": TOKEN})
        assert unknown.status_code == 422
        assert unknown.json()["code"] == "INVALID_INPUT"
