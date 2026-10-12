"""Run jobs in the API process after the request returns: local development and tests.

On Cloud Run the CPU is throttled after a response, so a backend there uses Cloud Tasks instead.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class InProcessDispatcher:
    """`run` raises while the job has attempts left (as it does for Cloud Tasks), so this
    calls it again after a pause, like a queue retry, until it returns or `max_runs`."""

    def __init__(
        self,
        run: Callable[[uuid.UUID], Awaitable[object]],
        *,
        retry_delay_seconds: float = 5.0,
        max_runs: int = 10,
    ) -> None:
        self._run = run
        self._retry_delay = retry_delay_seconds
        self._max_runs = max_runs
        # Strong references: asyncio keeps only weak ones to running tasks.
        self._tasks: set[asyncio.Task[None]] = set()

    async def enqueue(self, job_id: uuid.UUID) -> None:
        task = asyncio.create_task(self._safely(job_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _safely(self, job_id: uuid.UUID) -> None:
        for attempt in range(1, self._max_runs + 1):
            try:
                await self._run(job_id)
                return
            except Exception:
                # The job records its own failure; nothing awaits this task.
                logger.exception("publish job %s failed (run %d)", job_id, attempt)
                if attempt < self._max_runs:
                    await asyncio.sleep(self._retry_delay * attempt)

    async def drain(self) -> None:
        """Wait for every queued job; tests and the E2E server use it."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks))
