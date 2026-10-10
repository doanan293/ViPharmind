"""Run jobs in the API process: for local development and tests.

On Cloud Run the CPU is throttled after a response, so production uses Cloud Tasks.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class InProcessDispatcher:
    def __init__(self, run: Callable[[uuid.UUID], Awaitable[object]]) -> None:
        self._run = run
        # Strong references: asyncio keeps only weak ones to running tasks.
        self._tasks: set[asyncio.Task[None]] = set()

    async def enqueue(self, job_id: uuid.UUID) -> None:
        task = asyncio.create_task(self._safely(job_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _safely(self, job_id: uuid.UUID) -> None:
        try:
            await self._run(job_id)
        except Exception:
            # The job records its own failure; nothing awaits this task.
            logger.exception("publish job %s failed", job_id)

    async def drain(self) -> None:
        """Wait for every queued job; tests and the E2E server use it."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks))
