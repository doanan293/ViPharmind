import pytest

from tests.api.harness import build_harness

URL = "/api/v1/maintenance/daily"
SECRET = "m" * 40


async def test_maintenance_is_refused_without_a_cron_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CRON_SECRET", raising=False)
    async with build_harness().client() as client:
        for headers in ({}, {"Authorization": "Bearer "}, {"Authorization": "Bearer"}):
            response = await client.get(URL, headers=headers)
            assert response.status_code == 401
            assert response.json()["code"] == "UNAUTHORIZED"


async def test_maintenance_needs_the_exact_vercel_cron_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRON_SECRET", SECRET)
    async with build_harness().client() as client:
        for headers in (
            {},
            {"Authorization": SECRET},
            {"Authorization": f"Bearer {SECRET}x"},
            {"Authorization": "Bearer " + "n" * 40},
        ):
            assert (await client.get(URL, headers=headers)).status_code == 401
        # Past the check; this harness has no database, so nothing can be cleaned.
        allowed = await client.get(URL, headers={"Authorization": f"Bearer {SECRET}"})
        assert allowed.status_code == 503
        assert (await client.post(URL)).status_code == 405


def test_maintenance_is_not_in_the_openapi_document() -> None:
    paths = build_harness().app.openapi()["paths"]
    assert not [path for path in paths if "maintenance" in path]
