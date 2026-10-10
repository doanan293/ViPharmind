import uuid

from pharma_agent.infrastructure.jobs.inprocess import InProcessDispatcher


async def test_a_run_that_raises_is_retried_until_it_returns() -> None:
    calls: list[uuid.UUID] = []

    async def run(job_id: uuid.UUID) -> None:
        calls.append(job_id)
        if len(calls) < 3:
            raise RuntimeError("embedding endpoint unavailable")

    dispatcher = InProcessDispatcher(run, retry_delay_seconds=0)
    job = uuid.uuid4()
    await dispatcher.enqueue(job)
    await dispatcher.drain()
    assert calls == [job, job, job]


async def test_retries_stop_after_the_limit() -> None:
    calls = 0

    async def run(_job_id: uuid.UUID) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("always down")

    dispatcher = InProcessDispatcher(run, retry_delay_seconds=0, max_runs=4)
    await dispatcher.enqueue(uuid.uuid4())
    await dispatcher.drain()
    assert calls == 4
