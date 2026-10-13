import asyncio
import uuid

from pharma_agent.infrastructure.jobs.inprocess import InProcessDispatcher


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
