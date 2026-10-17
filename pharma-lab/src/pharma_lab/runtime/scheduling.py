from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


@dataclass(frozen=True)
class ScheduledBatch[OutputT]:
    results: list[OutputT]
    stopped_early: bool


async def stream_map_ordered[InputT, OutputT, ResourceT](
    items: Sequence[InputT],
    resources: Sequence[ResourceT],
    concurrency_per_resource: int,
    operation: Callable[[ResourceT, int, InputT], Awaitable[OutputT]],
    deadline: float,
    on_completed: Callable[[list[tuple[int, OutputT]]], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> ScheduledBatch[OutputT]:
    """Stream a shared FIFO workload through long-lived resource workers."""
    if not resources:
        raise ValueError("at least one scheduler resource is required")
    if concurrency_per_resource < 1:
        raise ValueError("concurrency_per_resource must be positive")

    queue: asyncio.Queue[tuple[int, InputT]] = asyncio.Queue()
    for index, item in enumerate(items):
        queue.put_nowait((index, item))

    results: dict[int, OutputT] = {}
    stopped_early = False

    async def worker(resource: ResourceT) -> None:
        nonlocal stopped_early
        while True:
            if clock() >= deadline:
                stopped_early = stopped_early or not queue.empty()
                return
            try:
                index, item = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                value = await operation(resource, index, item)
            except asyncio.CancelledError:
                queue.task_done()
                raise
            except Exception:
                queue.task_done()
                raise
            results[index] = value
            if on_completed is not None:
                on_completed([(index, value)])
            queue.task_done()

    tasks = [
        asyncio.create_task(worker(resource))
        for resource in resources
        for _ in range(concurrency_per_resource)
    ]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    if not queue.empty() and clock() >= deadline:
        stopped_early = True
    return ScheduledBatch(
        [results[index] for index in sorted(results)],
        stopped_early,
    )
