"""Run a job inside the request that queued it: production on Vercel Functions.

A serverless function may be frozen once its response is sent, so a background task could
stop half-way. Here `enqueue` returns only after the job finished or used its runs, within
the function's max duration; a job cut off by that limit is picked up again as stale.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class InlineDispatcher:
    """`run` raises while the job has attempts left, so it is called again after a short
    pause, like a queue retry, until it returns or `max_runs` is reached."""

    def __init__(
        self,
        run: Callable[[uuid.UUID], Awaitable[object]],
        *,
        retry_delay_seconds: float = 2.0,
        max_runs: int = 3,
    ) -> None:
        self._run = run
        self._retry_delay = retry_delay_seconds
        self._max_runs = max_runs

    async def enqueue(self, job_id: uuid.UUID) -> None:
        for attempt in range(1, self._max_runs + 1):
            try:
                await self._run(job_id)
                return
            except Exception:
                # The job records its own failure; the publish request still succeeds.
                logger.exception("publish job %s failed (run %d)", job_id, attempt)
                if attempt < self._max_runs:
                    await asyncio.sleep(self._retry_delay * attempt)
