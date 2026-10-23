"""Run the shards of one Kaggle step in parallel across accounts.

The local store is the source of truth: `ShardAdapter.missing()` says what is left, the
scheduler cuts it into shards, runs each shard in a Kaggle session of an account that has
quota, and the adapter merges every result back. Stopping the command (Ctrl-C) leaves the
kernels running; the next command finds them in the `JobRegistry`, relaunches the same
shards, which attaches to the running kernels, and plans the rest.
"""

from __future__ import annotations

import queue
import threading
import time
from collections import Counter, deque
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from pharma_lab.integrations.kaggle.job_registry import JobRegistry, ShardRecord
from pharma_lab.integrations.kaggle.models import PipelineResult
from pharma_lab.integrations.kaggle.service import KaggleExecutionContext
from pharma_lab.integrations.kaggle.sessions import (
    ACCOUNT_WAIT_SECONDS,
    SESSION_CAPACITY_MARKER,
    AccountLock,
    KaggleSessionCapacityReached,
    QuotaExhausted,
    QuotaReader,
    ReservedAccount,
    SessionLog,
    reserve_session_account,
)
from pharma_lab.integrations.kaggle.shards import Shard, WorkUnit, plan_shards
from pharma_lab.integrations.kaggle.workers.runtime import (
    WORKER_MARGIN_FLOOR_SECONDS,
    WORKER_MARGIN_FRACTION,
)

# Kaggle batch sessions end well before this; older registry entries are dead.
STALE_AFTER_SECONDS = 13 * 3600
# Two completed-nothing sessions of one shard, or two failures, mean it will not progress.
ATTEMPTS_BEFORE_STUCK = 2


def shard_margin_seconds(budget_seconds: int) -> int:
    """Time a shard leaves unused at the end of a session: the kernel's own deadline
    margin (it stops starting work that long before the session ends)."""
    return int(
        max(WORKER_MARGIN_FLOOR_SECONDS, budget_seconds * WORKER_MARGIN_FRACTION)
    )


class ShardAdapter(Protocol):
    """What one Kaggle step provides to the scheduler."""

    stage: str

    def missing(self) -> Sequence[WorkUnit]:
        """Work units that the local store still lacks."""
        ...

    def setup_seconds(self) -> float:
        """Time a fresh kernel spends before its first unit."""
        ...

    def run_shard(self, shard: Shard, reserved: ReservedAccount) -> PipelineResult:
        """Run the shard in a session of `reserved`. The same units must give the same
        job, so that a relaunch attaches to the kernel already running."""
        ...

    def merge(self, shard: Shard, result: PipelineResult) -> int:
        """Merge a result into the local store (idempotent); the units it newly completed."""
        ...

    def preferred_profile(self, shard: Shard, record: ShardRecord | None) -> str | None:
        """The account to try first: the one a recorded kernel runs on."""
        ...


@dataclass(frozen=True)
class SchedulerSettings:
    parallel: int
    budget_seconds: int
    margin_seconds: int
    max_sessions: int | None
    drain: bool = False
    backoff_seconds: float = 30.0
    backoff_max: int = 6


class SchedulerStop(StrEnum):
    NOTHING_MISSING = "nothing-missing"
    COMPLETE = "complete"
    QUOTA_EXHAUSTED = "quota-exhausted"
    DRAINED = "drained"
    MAX_SESSIONS = "max-sessions"
    STUCK = "stuck"


@dataclass(frozen=True)
class SchedulerReport:
    stop: SchedulerStop
    shards_run: int
    merged_units: int
    remaining: int
    quota_table: tuple[str, ...] = ()


@dataclass
class _Outcome:
    shard: Shard
    result: PipelineResult | None = None
    error: BaseException | None = None
    exhausted: bool = False
    quota_table: tuple[str, ...] = ()


def run_shards(
    adapter: ShardAdapter,
    contexts: Sequence[KaggleExecutionContext],
    registry: JobRegistry,
    settings: SchedulerSettings,
    *,
    log: SessionLog,
    read_quota: QuotaReader | None = None,
    account_lock: AccountLock | None = None,
    slots_per_account: int = 2,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> SchedulerReport:
    """Run the adapter's missing work until it is done, out of quota, drained or stuck."""
    return _Scheduler(
        adapter,
        contexts,
        registry,
        settings,
        log=log,
        read_quota=read_quota,
        account_lock=account_lock,
        slots=slots_per_account,
        sleep=sleep,
        now=now,
    ).run()


class _Scheduler:
    def __init__(
        self,
        adapter: ShardAdapter,
        contexts: Sequence[KaggleExecutionContext],
        registry: JobRegistry,
        settings: SchedulerSettings,
        *,
        log: SessionLog,
        read_quota: QuotaReader | None,
        account_lock: AccountLock | None,
        slots: int,
        sleep: Callable[[float], None],
        now: Callable[[], datetime],
    ) -> None:
        if settings.parallel < 1:
            raise ValueError("--parallel must be at least 1")
        self.adapter = adapter
        self.contexts = tuple(contexts)
        self.registry = registry
        self.settings = settings
        self.log = log
        self.read_quota = read_quota
        self.account_lock = account_lock
        self.slots = slots
        self.sleep = sleep
        self.now = now
        self.parallel = min(settings.parallel, len(self.contexts) * slots)
        self.results: queue.Queue[_Outcome] = queue.Queue()
        self.live: dict[str, Shard] = {}
        self.orphans: deque[tuple[Shard, str | None]] = deque()
        self.launched = 0
        self.merged = 0
        self.stalled: set[str] = set()
        self.zero_merges: Counter[str] = Counter()
        self.failures: Counter[str] = Counter()
        self.exhausted = False
        self.quota_table: tuple[str, ...] = ()
        self.reservation_lock = threading.Lock()

    def run(self) -> SchedulerReport:
        # Orphans first: a kernel that ended long ago still holds output to download.
        self._queue_orphans()
        self._clear_stale()
        while True:
            self._launch()
            if not self.live:
                return self._report()
            self._collect(self.results.get())

    # Planning

    def _clear_stale(self) -> None:
        for record in self.registry.clear_stale(
            older_than_seconds=STALE_AFTER_SECONDS, now=self.now()
        ):
            self.log(f"dropped stale shard {record.shard_id} on {record.profile}")

    def _queue_orphans(self) -> None:
        """Shards a previous command left running: relaunch them to harvest or attach."""
        missing = {unit.key: unit for unit in self.adapter.missing()}
        for record in self.registry.live():
            if record.stage != self.adapter.stage:
                continue
            if not any(key in missing for key in record.unit_keys):
                self.registry.finish(record.shard_id)
                continue
            units = tuple(
                sorted(
                    (
                        missing.get(key) or WorkUnit(key, 0.0, "")
                        for key in record.unit_keys
                    ),
                    key=lambda unit: unit.key,
                )
            )
            shard = Shard(record.shard_id, units, units[0].group)
            self.orphans.append((shard, self.adapter.preferred_profile(shard, record)))

    def _unassigned(self) -> list[WorkUnit]:
        owned = self.registry.assigned_keys(self.adapter.stage) | {
            unit.key for shard in self.live.values() for unit in shard.units
        }
        return [
            unit
            for unit in self.adapter.missing()
            if unit.key not in owned and unit.key not in self.stalled
        ]

    def _free_slots(self) -> int:
        free = self.parallel - len(self.live)
        if self.settings.max_sessions is not None:
            free = min(free, self.settings.max_sessions - self.launched)
        return free

    def _launch(self) -> None:
        if self.exhausted:
            return
        while self.orphans and self._free_slots() > 0:
            shard, preferred = self.orphans.popleft()
            self._start(shard, preferred)
        if self.settings.drain or self._free_slots() <= 0:
            return
        free = self._free_slots()
        missing = self._unassigned()
        if not missing:
            return
        shards = plan_shards(
            missing,
            setup_seconds=self.adapter.setup_seconds(),
            budget_seconds=self.settings.budget_seconds,
            margin_seconds=self.settings.margin_seconds,
            slots=free,
        )
        for shard in shards[:free]:
            self._start(shard, None)

    def _start(self, shard: Shard, preferred: str | None) -> None:
        self.live[shard.shard_id] = shard
        self.launched += 1
        self.log(f"shard {shard.shard_id}: {len(shard.units)} units, starting")
        threading.Thread(
            target=self._work, args=(shard, preferred), daemon=True
        ).start()

    # Workers

    def _work(self, shard: Shard, preferred: str | None) -> None:
        outcome = _Outcome(shard)
        try:
            outcome.result = self._execute(shard, preferred)
        except QuotaExhausted as exhausted:
            outcome.exhausted = True
            outcome.quota_table = exhausted.table
        except BaseException as error:
            outcome.error = error
        self.results.put(outcome)

    def _execute(self, shard: Shard, preferred: str | None) -> PipelineResult:
        unavailable: frozenset[str] = frozenset()
        while True:
            stack = ExitStack()
            try:
                with self.reservation_lock:
                    reserved = stack.enter_context(
                        reserve_session_account(
                            self.contexts,
                            requested_budget_seconds=self.settings.budget_seconds,
                            log=self.log,
                            read_quota=self.read_quota,
                            account_lock=self.account_lock,
                            preferred_profile=preferred,
                            unavailable=unavailable,
                            slots_per_account=self.slots,
                            committed_seconds=self.registry.committed_seconds,
                        )
                    )
                    self.registry.register(
                        ShardRecord(
                            shard.shard_id,
                            self.adapter.stage,
                            reserved.profile,
                            tuple(unit.key for unit in shard.units),
                            self.now().isoformat(),
                            reserved.budget_seconds,
                        )
                    )
            except QuotaExhausted as exhausted:
                stack.close()
                if exhausted.held_with_quota(self.settings.budget_seconds):
                    self.log("waiting for an account another session holds")
                    self.sleep(ACCOUNT_WAIT_SECONDS)
                    continue
                raise
            with stack:
                try:
                    return self._run_with_backoff(shard, reserved)
                except KaggleSessionCapacityReached as capped:
                    self.log(f"account={capped.profile} has no free GPU session")
                    unavailable = unavailable | {capped.profile}
                    preferred = None

    def _run_with_backoff(
        self, shard: Shard, reserved: ReservedAccount
    ) -> PipelineResult:
        attempt = 0
        while True:
            try:
                return self.adapter.run_shard(shard, reserved)
            except KaggleSessionCapacityReached:
                raise
            except Exception as error:
                if SESSION_CAPACITY_MARKER in str(error).casefold():
                    raise KaggleSessionCapacityReached(reserved.profile) from error
                if not _rate_limited(error) or attempt >= self.settings.backoff_max:
                    raise
                wait = self.settings.backoff_seconds * 2**attempt
                attempt += 1
                self.log(f"Kaggle rate limit; retrying in {wait:.0f}s")
                self.sleep(wait)

    # Results

    def _collect(self, outcome: _Outcome) -> None:
        shard = outcome.shard
        self.live.pop(shard.shard_id, None)
        keys = {unit.key for unit in shard.units}
        if outcome.exhausted:
            self.exhausted = True
            self.quota_table = outcome.quota_table
            self.registry.finish(shard.shard_id)
            self.log("no account has quota for another session")
            return
        if outcome.error is not None:
            self.registry.finish(shard.shard_id)
            self.failures[shard.shard_id] += 1
            self.log(
                f"shard {shard.shard_id} failed: "
                f"{type(outcome.error).__name__}: {outcome.error}"
            )
            if self.failures[shard.shard_id] >= ATTEMPTS_BEFORE_STUCK:
                self.stalled |= keys
            return
        assert outcome.result is not None
        merged = self.adapter.merge(shard, outcome.result)
        self.registry.finish(shard.shard_id)
        self.merged += merged
        self.log(f"shard {shard.shard_id}: merged {merged}/{len(shard.units)} units")
        if merged == 0:
            self.zero_merges[shard.shard_id] += 1
            if self.zero_merges[shard.shard_id] >= ATTEMPTS_BEFORE_STUCK:
                self.stalled |= keys

    def _report(self) -> SchedulerReport:
        remaining = len(self.adapter.missing())
        if remaining == 0:
            stop = (
                SchedulerStop.NOTHING_MISSING
                if self.launched == 0
                else SchedulerStop.COMPLETE
            )
        elif self.settings.drain:
            stop = SchedulerStop.DRAINED
        elif self.exhausted:
            stop = SchedulerStop.QUOTA_EXHAUSTED
        elif (
            self.settings.max_sessions is not None
            and self.launched >= self.settings.max_sessions
        ):
            stop = SchedulerStop.MAX_SESSIONS
        else:
            stop = SchedulerStop.STUCK
        return SchedulerReport(
            stop, self.launched, self.merged, remaining, self.quota_table
        )


def _rate_limited(error: Exception) -> bool:
    text = str(error).casefold()
    return "429" in text or "too many requests" in text
