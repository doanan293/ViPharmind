import asyncio
import uuid
from typing import Any

import pytest
from pydantic import SecretStr

from pharma_agent.infrastructure.jobs.cloud_tasks import CloudTasksDispatcher
from pharma_agent.infrastructure.jobs.inprocess import InProcessDispatcher
from pharma_agent.infrastructure.jobs.internal_auth import (
    InternalAuthError,
    verify_internal_request,
)
from pharma_agent.infrastructure.settings import JobsSettings


async def test_in_process_dispatcher_runs_jobs_and_swallows_their_errors() -> None:
    ran: list[uuid.UUID] = []

    async def run(job_id: uuid.UUID) -> None:
        await asyncio.sleep(0)
        ran.append(job_id)
        if len(ran) == 2:
            raise RuntimeError("boom")

    dispatcher = InProcessDispatcher(run)
    first, second = uuid.uuid4(), uuid.uuid4()
    await dispatcher.enqueue(first)
    await dispatcher.enqueue(second)
    await dispatcher.drain()
    assert ran == [first, second]


def test_in_process_requests_need_the_shared_token() -> None:
    settings = JobsSettings(internal_token=SecretStr("t" * 40))
    verify_internal_request({"x-internal-token": "t" * 40}, settings)
    with pytest.raises(InternalAuthError):
        verify_internal_request({"x-internal-token": "wrong"}, settings)
    with pytest.raises(InternalAuthError):
        verify_internal_request({}, settings)
    with pytest.raises(InternalAuthError):
        verify_internal_request({"x-internal-token": ""}, JobsSettings())


def test_cloud_tasks_requests_need_a_google_token_for_the_invoker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = JobsSettings(
        dispatcher="cloud_tasks",
        backend_url="https://api.example.run.app",
        service_account_email="tasks@p.iam.gserviceaccount.com",
    )
    seen: list[tuple[str, str]] = []

    def verify(token: str, request: object, audience: str) -> dict[str, Any]:
        seen.append((token, audience))
        if token != "good":
            raise ValueError("bad signature")
        return {"email": "tasks@p.iam.gserviceaccount.com", "email_verified": True}

    monkeypatch.setattr(
        "pharma_agent.infrastructure.jobs.internal_auth.id_token.verify_oauth2_token",
        verify,
    )
    verify_internal_request({"authorization": "Bearer good"}, settings)
    assert seen == [("good", "https://api.example.run.app")]
    with pytest.raises(InternalAuthError):
        verify_internal_request({"authorization": "Bearer bad"}, settings)
    with pytest.raises(InternalAuthError):
        verify_internal_request({}, settings)

    def other(token: str, request: object, audience: str) -> dict[str, Any]:
        return {"email": "someone@example.com", "email_verified": True}

    monkeypatch.setattr(
        "pharma_agent.infrastructure.jobs.internal_auth.id_token.verify_oauth2_token",
        other,
    )
    with pytest.raises(InternalAuthError):
        verify_internal_request({"authorization": "Bearer good"}, settings)


class FakeTasksClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def queue_path(self, project: str, location: str, queue: str) -> str:
        return f"projects/{project}/locations/{location}/queues/{queue}"

    async def create_task(self, *, parent: str, task: dict[str, Any]) -> None:
        self.requests.append({"parent": parent, "task": task})


async def test_cloud_tasks_dispatcher_posts_back_with_an_oidc_token() -> None:
    client = FakeTasksClient()
    settings = JobsSettings(
        dispatcher="cloud_tasks",
        backend_url="https://api.example.run.app/",
        cloud_tasks_project="vipharmind",
        service_account_email="tasks@vipharmind.iam.gserviceaccount.com",
    )
    job_id = uuid.uuid4()
    await CloudTasksDispatcher(settings, client=client).enqueue(job_id)
    [request] = client.requests
    assert request["parent"] == (
        "projects/vipharmind/locations/asia-southeast1/queues/ingest"
    )
    http = request["task"]["http_request"]
    assert http["url"] == (
        f"https://api.example.run.app/api/v1/internal/ingest-jobs/{job_id}/run"
    )
    assert http["oidc_token"] == {
        "service_account_email": "tasks@vipharmind.iam.gserviceaccount.com",
        "audience": "https://api.example.run.app",
    }
    assert request["task"]["dispatch_deadline"] == {"seconds": 600}
