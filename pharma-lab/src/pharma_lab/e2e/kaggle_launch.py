"""`e2e run --backend kaggle` and `e2e status`: wire the adapter to the scheduler.

Exit codes: 0 done, 10 paused (no quota left, `--drain` or `--max-sessions` reached; run
the same command again to continue), 11 some pairs are stuck (they failed for good; look
at them with `e2e status`, retry with `--retry-stuck`).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pharma_lab.e2e.kaggle_shards import SETUP_SECONDS, E2EShardAdapter
from pharma_lab.integrations.kaggle.job_registry import JobRegistry, ShardRecord
from pharma_lab.integrations.kaggle.scheduler import (
    SchedulerReport,
    SchedulerSettings,
    SchedulerStop,
    run_shards,
)
from pharma_lab.integrations.kaggle.service import KaggleExecutionContext
from pharma_lab.integrations.kaggle.workers.runtime import (
    WORKER_MARGIN_FLOOR_SECONDS,
    WORKER_MARGIN_FRACTION,
)

EXIT_DONE = 0
EXIT_PAUSED = 10
EXIT_STUCK = 11
JOBS_FILE = "jobs.json"
# A shard that fills a 3 h session leaves this long for its turns (spec 4.2: ~2 h).
SHARD_WORK_SECONDS = 5400.0
PAUSED = frozenset(
    {
        SchedulerStop.QUOTA_EXHAUSTED,
        SchedulerStop.DRAINED,
        SchedulerStop.MAX_SESSIONS,
    }
)


@dataclass(frozen=True)
class LaunchOptions:
    kaggle_account: str | None
    parallel: int | None
    budget_seconds: int
    max_sessions: int | None
    drain: bool


@dataclass(frozen=True)
class LaunchOutcome:
    exit_code: int
    stop: SchedulerStop | None
    shards_run: int
    merged_units: int
    remaining: int
    stuck: int
    quota_table: tuple[str, ...] = ()


@dataclass(frozen=True)
class LabelStatus:
    label: str
    done: int
    total: int
    stuck: int


@dataclass(frozen=True)
class RunStatus:
    labels: tuple[LabelStatus, ...]
    live: tuple[ShardRecord, ...]
    gpu_hours_needed: float


def margin_seconds(budget_seconds: int) -> int:
    return int(
        max(WORKER_MARGIN_FLOOR_SECONDS, budget_seconds * WORKER_MARGIN_FRACTION)
    )


def registry_for(work_dir: Path) -> JobRegistry:
    return JobRegistry(work_dir / JOBS_FILE)


def exit_code_for(stop: SchedulerStop | None, stuck: int) -> int:
    if stop in PAUSED:
        return EXIT_PAUSED
    if stop is SchedulerStop.STUCK or stuck:
        return EXIT_STUCK
    return EXIT_DONE


def launch(
    adapter: E2EShardAdapter,
    options: LaunchOptions,
    *,
    resolve_contexts: Callable[[str | None], Sequence[KaggleExecutionContext]],
    registry: JobRegistry,
    log: Callable[[str], None] = print,
    scheduler: Callable[..., SchedulerReport] = run_shards,
) -> LaunchOutcome:
    """Run what is missing. With nothing missing no Kaggle account is even resolved."""
    if not adapter.missing():
        stuck = len(adapter.report().stuck)
        return LaunchOutcome(exit_code_for(None, stuck), None, 0, 0, 0, stuck)
    contexts = resolve_contexts(options.kaggle_account)
    settings = SchedulerSettings(
        parallel=options.parallel or 2 * len(contexts),
        budget_seconds=options.budget_seconds,
        margin_seconds=margin_seconds(options.budget_seconds),
        max_sessions=options.max_sessions,
        drain=options.drain,
    )
    report = scheduler(adapter, contexts, registry, settings, log=log)
    stuck = len(adapter.report().stuck)
    return LaunchOutcome(
        exit_code_for(report.stop, stuck),
        report.stop,
        report.shards_run,
        report.merged_units,
        report.remaining,
        stuck,
        report.quota_table,
    )


def run_status(adapter: E2EShardAdapter, registry: JobRegistry) -> RunStatus:
    work = adapter.report()
    total = len(adapter.universe)
    missing = Counter(pair.label for pair in work.missing)
    stuck = Counter(pair.label for pair in work.stuck)
    labels = tuple(
        LabelStatus(
            label,
            total - missing[label] - stuck[label],
            total,
            stuck[label],
        )
        for label in adapter.plan.labels
    )
    seconds = sum(unit.seconds for unit in adapter.missing())
    shards = math.ceil(seconds / SHARD_WORK_SECONDS) if seconds else 0
    live = tuple(r for r in registry.live() if r.stage == adapter.stage)
    return RunStatus(
        labels, live, (seconds + shards * SETUP_SECONDS) / 3600 if shards else 0.0
    )
