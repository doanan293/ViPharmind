import asyncio
import uuid

import pytest
from pydantic import SecretStr

from pharma_agent.infrastructure.jobs.inprocess import InProcessDispatcher
from pharma_agent.infrastructure.jobs.internal_auth import (
    InternalAuthError,
    verify_internal_request,
)
from pharma_agent.infrastructure.settings import JobsSettings


async def test_in_process_dispatcher_runs_jobs_and_retries_a_failed_run() -> None:
    ran: list[uuid.UUID] = []

    async def run(job_id: uuid.UUID) -> None:
        await asyncio.sleep(0)
        ran.append(job_id)
        if len(ran) == 2:
            raise RuntimeError("boom")

    dispatcher = InProcessDispatcher(run, retry_delay_seconds=0)
    first, second = uuid.uuid4(), uuid.uuid4()
    await dispatcher.enqueue(first)
    await dispatcher.enqueue(second)
    await dispatcher.drain()
    assert ran == [first, second, second]


def test_in_process_requests_need_the_shared_token() -> None:
    settings = JobsSettings(internal_token=SecretStr("t" * 40))
    verify_internal_request({"x-internal-token": "t" * 40}, settings)
    with pytest.raises(InternalAuthError):
        verify_internal_request({"x-internal-token": "wrong"}, settings)
    with pytest.raises(InternalAuthError):
        verify_internal_request({}, settings)
    with pytest.raises(InternalAuthError):
        verify_internal_request({"x-internal-token": ""}, JobsSettings())
