"""Run a job inside the request that queued it: production on Vercel Functions.

A serverless function may be frozen once its response is sent, so a background task could
stop half-way. Here `enqueue` returns only after the job finished or used its runs. Every
run and retry happens inside that one request, so Vercel's maxDuration bounds them all; the
job's stale window (`PHARMA_JOBS__STALE_AFTER_SECONDS`, longer than maxDuration) counts from
its first run, so a job only looks stale once its request is gone, and a later publish then
takes it over.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class InlineDispatcher:
    """`run` raises while the job has attempts left, so it is called again after a short
    pause until it returns or `max_runs` (the job's max attempts) is reached."""

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
