import uuid

from pharma_agent.infrastructure.jobs.inline import InlineDispatcher


async def test_enqueue_returns_only_after_the_job_has_run() -> None:
    calls: list[uuid.UUID] = []

    async def run(job_id: uuid.UUID) -> None:
        calls.append(job_id)
        if len(calls) < 2:
            raise RuntimeError("embedding endpoint unavailable")

    job = uuid.uuid4()
    await InlineDispatcher(run, retry_delay_seconds=0).enqueue(job)
    assert calls == [job, job]


async def test_a_failing_job_does_not_fail_the_request() -> None:
    calls = 0

    async def run(_job_id: uuid.UUID) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("always down")

    await InlineDispatcher(run, retry_delay_seconds=0, max_runs=3).enqueue(uuid.uuid4())
    assert calls == 3
