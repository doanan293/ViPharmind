from __future__ import annotations

import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tests.integrations.kaggle.factories import owners, stage_job

from pharma_lab.artifacts.manifest import Completion
from pharma_lab.integrations.kaggle.api import KaggleCommandRunner
from pharma_lab.integrations.kaggle.config import KaggleAccountProfile
from pharma_lab.integrations.kaggle.job_lock import kaggle_account_lock
from pharma_lab.integrations.kaggle.job_registry import JobRegistry, ShardRecord
from pharma_lab.integrations.kaggle.models import PipelineResult
from pharma_lab.integrations.kaggle.quota import AccountQuota
from pharma_lab.integrations.kaggle.scheduler import (
    SchedulerSettings,
    SchedulerStop,
    run_shards,
)
from pharma_lab.integrations.kaggle.service import KaggleExecutionContext
from pharma_lab.integrations.kaggle.sessions import (
    KaggleSessionCapacityReached,
    ReservedAccount,
)
from pharma_lab.integrations.kaggle.shards import Shard, WorkUnit

REFRESH = datetime(2026, 10, 24, tzinfo=UTC)
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def contexts(*names: str) -> tuple[KaggleExecutionContext, ...]:
    return tuple(
        KaggleExecutionContext(
            KaggleAccountProfile(name, f"user-{name}", f"token-{name}"),
            owners(f"user-{name}"),
            KaggleCommandRunner(environment={}),
        )
        for name in names
    )


class Book:
    """Fake `kaggle quota`: remaining GPU hours per account."""

    def __init__(self, **remaining: float) -> None:
        self.remaining = dict(remaining)

    def __call__(self, context: KaggleExecutionContext) -> AccountQuota:
        assert context.profile is not None
        name = context.profile.name
        return AccountQuota(
            name, context.profile.username, self.remaining[name], 30.0, REFRESH
        )


@dataclass
class Call:
    shard_id: str
    keys: tuple[str, ...]
    profile: str


class FakeAdapter:
    """Work units that a shard completes unless it is told to fail."""

    stage = "fake"

    def __init__(self, tmp_path: Path, keys: Sequence[str], *, seconds: float = 600.0):
        self.pending = set(keys)
        self.seconds = seconds
        self.setup = 0.0
        self.calls: list[Call] = []
        self.lock = threading.Lock()
        self.job = stage_job(tmp_path)
        self.running = 0
        self.max_running = 0
        self.completes_nothing = False
        self.before_return = None
        self._done: dict[int, tuple[str, ...]] = {}

    def missing(self) -> list[WorkUnit]:
        with self.lock:
            return [WorkUnit(key, self.seconds, "") for key in sorted(self.pending)]

    def setup_seconds(self) -> float:
        return self.setup

    def preferred_profile(self, shard: Shard, record: ShardRecord | None) -> str | None:
        return None if record is None else record.profile

    def run_shard(self, shard: Shard, reserved: ReservedAccount) -> PipelineResult:
        keys = tuple(unit.key for unit in shard.units)
        with self.lock:
            self.calls.append(Call(shard.shard_id, keys, reserved.profile))
            self.running += 1
            self.max_running = max(self.max_running, self.running)
        try:
            if self.before_return is not None:
                self.before_return(shard, reserved)
        finally:
            with self.lock:
                self.running -= 1
        done = () if self.completes_nothing else keys
        completion = Completion(len(keys), len(done), len(keys) - len(done))
        result = PipelineResult(self.job, completion, (), None, 1)
        with self.lock:
            self._done[id(result)] = done
        return result

    def merge(self, shard: Shard, result: PipelineResult) -> int:
        with self.lock:
            done = self._done.pop(id(result))
            fresh = [key for key in done if key in self.pending]
            self.pending.difference_update(fresh)
            return len(fresh)


def locker(lock_root: Path):
    def make(profile: str, slot: int = 0):
        return kaggle_account_lock(profile, lock_root=lock_root, slot=slot)

    return make


def settings(**overrides) -> SchedulerSettings:
    values = {
        "parallel": 3,
        "budget_seconds": 7_200,
        "margin_seconds": 900,
        "max_sessions": None,
        "backoff_seconds": 30.0,
        "backoff_max": 6,
    }
    values.update(overrides)
    return SchedulerSettings(**values)


def run(
    tmp_path: Path,
    adapter: FakeAdapter,
    *,
    book: Book | None = None,
    accounts: Sequence[str] = ("acc1", "acc2"),
    registry: JobRegistry | None = None,
    sleeps: list[float] | None = None,
    **overrides,
):
    messages: list[str] = []
    sleep_log = sleeps if sleeps is not None else []

    def pause(seconds: float) -> None:
        sleep_log.append(seconds)
        time.sleep(0.001)

    report = run_shards(
        adapter,
        contexts(*accounts),
        registry or JobRegistry(tmp_path / "jobs.json", lock_root=tmp_path / "l"),
        settings(**overrides),
        log=messages.append,
        read_quota=book or Book(**dict.fromkeys(accounts, 30.0)),
        account_lock=locker(tmp_path / "locks"),
        sleep=pause,
        now=lambda: NOW,
    )
    return report, messages


def keys(count: int) -> list[str]:
    return [f"k{index:04d}" for index in range(count)]


def test_nothing_missing_returns_immediately(tmp_path: Path) -> None:
    adapter = FakeAdapter(tmp_path, [])

    report, _ = run(tmp_path, adapter)

    assert report.stop is SchedulerStop.NOTHING_MISSING
    assert adapter.calls == []
    assert report.remaining == 0


def test_all_work_is_done_and_reported_complete(tmp_path: Path) -> None:
    adapter = FakeAdapter(tmp_path, keys(40))

    report, _ = run(tmp_path, adapter)

    assert report.stop is SchedulerStop.COMPLETE
    assert adapter.pending == set()
    assert report.merged_units == 40
    covered = [key for call in adapter.calls for key in call.keys]
    assert sorted(covered) == keys(40)


def test_runs_shards_in_parallel_up_to_parallel(tmp_path: Path) -> None:
    adapter = FakeAdapter(tmp_path, keys(120))
    barrier = threading.Barrier(3, timeout=5)
    adapter.before_return = lambda shard, reserved: (
        barrier.wait() if len(adapter.calls) <= 3 else None
    )

    report, _ = run(tmp_path, adapter, parallel=3)

    assert report.stop is SchedulerStop.COMPLETE
    assert adapter.max_running == 3


def test_units_of_live_shards_are_not_planned_again(tmp_path: Path) -> None:
    # Review focus 2: a shard another command still owns keeps its units.
    registry = JobRegistry(tmp_path / "jobs.json", lock_root=tmp_path / "l")
    owned = tuple(keys(5))
    registry.register(
        ShardRecord("orphan", "fake", "acc2", owned, NOW.isoformat(), 7_200)
    )
    adapter = FakeAdapter(tmp_path, keys(20))

    report, _ = run(tmp_path, adapter, registry=registry)

    covered = [key for call in adapter.calls for key in call.keys]
    assert sorted(covered) == keys(20)
    assert len(covered) == len(set(covered))
    assert [c.keys for c in adapter.calls if c.shard_id == "orphan"] == [owned]
    assert report.stop is SchedulerStop.COMPLETE


def test_orphan_shard_is_relaunched_with_its_account(tmp_path: Path) -> None:
    registry = JobRegistry(tmp_path / "jobs.json", lock_root=tmp_path / "l")
    registry.register(
        ShardRecord("orphan", "fake", "acc2", tuple(keys(3)), NOW.isoformat(), 7_200)
    )
    adapter = FakeAdapter(tmp_path, keys(3))

    run(tmp_path, adapter, registry=registry)

    [call] = [c for c in adapter.calls if c.shard_id == "orphan"]
    assert call.profile == "acc2"


def test_quota_exhausted_with_nothing_live_stops(tmp_path: Path) -> None:
    adapter = FakeAdapter(tmp_path, keys(10))

    report, _ = run(tmp_path, adapter, book=Book(acc1=0.5, acc2=0.5))

    assert report.stop is SchedulerStop.QUOTA_EXHAUSTED
    assert adapter.calls == []
    assert report.remaining == 10
    assert report.quota_table


def test_quota_exhausted_waits_for_live_shards_then_stops(tmp_path: Path) -> None:
    # One account with 4 h: two sessions fit at once (7200 s, then 5400 s), the third
    # has to wait for them, and by then the quota they spent is gone.
    book = Book(acc1=4.0)
    adapter = FakeAdapter(tmp_path, keys(14), seconds=1_500.0)
    release = threading.Event()

    def spend(shard: Shard, reserved: ReservedAccount) -> None:
        release.wait(5)
        book.remaining[reserved.profile] = max(
            0.0, book.remaining[reserved.profile] - 3.5
        )

    adapter.before_return = spend
    threading.Timer(0.5, release.set).start()

    report, messages = run(tmp_path, adapter, book=book, accounts=("acc1",))

    assert report.stop is SchedulerStop.QUOTA_EXHAUSTED
    assert len(adapter.calls) == 2
    assert report.merged_units > 0
    assert report.remaining > 0
    assert report.quota_table
    assert any("quota" in message.lower() for message in messages)


def test_drain_relaunches_orphans_but_starts_no_new_shard(tmp_path: Path) -> None:
    registry = JobRegistry(tmp_path / "jobs.json", lock_root=tmp_path / "l")
    registry.register(
        ShardRecord("orphan", "fake", "acc1", tuple(keys(5)), NOW.isoformat(), 7_200)
    )
    adapter = FakeAdapter(tmp_path, keys(20))

    report, _ = run(tmp_path, adapter, registry=registry, drain=True)

    assert [c.shard_id for c in adapter.calls] == ["orphan"]
    assert report.stop is SchedulerStop.DRAINED
    assert report.remaining == 15


def test_a_freed_slot_takes_new_work_while_another_shard_still_runs(
    tmp_path: Path,
) -> None:
    adapter = FakeAdapter(tmp_path, keys(120))
    third_started = threading.Event()

    def hold_first(shard: Shard, reserved: ReservedAccount) -> None:
        if len(adapter.calls) >= 3:
            third_started.set()
        if len(adapter.calls) == 2:
            assert third_started.wait(5), "no new shard started while one still ran"

    adapter.before_return = hold_first

    report, _ = run(tmp_path, adapter, parallel=2)

    assert report.stop is SchedulerStop.COMPLETE
    assert third_started.is_set()


def test_a_shard_that_completes_nothing_twice_ends_the_run_as_stuck(
    tmp_path: Path,
) -> None:
    adapter = FakeAdapter(tmp_path, keys(10))
    adapter.completes_nothing = True

    report, _ = run(tmp_path, adapter)

    assert report.stop is SchedulerStop.STUCK
    assert report.remaining == 10
    assert len(adapter.calls) <= 8


def test_rate_limits_are_backed_off_and_retried(tmp_path: Path) -> None:
    adapter = FakeAdapter(tmp_path, keys(3))
    attempts = {"count": 0}

    def flaky(shard: Shard, reserved: ReservedAccount) -> None:
        attempts["count"] += 1
        if attempts["count"] <= 2:
            raise RuntimeError("429 Client Error: Too Many Requests")

    adapter.before_return = flaky
    sleeps: list[float] = []

    report, _ = run(tmp_path, adapter, sleeps=sleeps, parallel=1)

    assert report.stop is SchedulerStop.COMPLETE
    assert sleeps[:2] == [30.0, 60.0]


def test_other_errors_do_not_loop_forever(tmp_path: Path) -> None:
    adapter = FakeAdapter(tmp_path, keys(3))

    def broken(shard: Shard, reserved: ReservedAccount) -> None:
        raise RuntimeError("kernel push refused")

    adapter.before_return = broken

    report, messages = run(tmp_path, adapter, parallel=1)

    assert report.stop is SchedulerStop.STUCK
    assert any("kernel push refused" in message for message in messages)


def test_registry_is_cleaned_after_each_shard_even_when_it_fails(
    tmp_path: Path,
) -> None:
    registry = JobRegistry(tmp_path / "jobs.json", lock_root=tmp_path / "l")
    adapter = FakeAdapter(tmp_path, keys(6))
    adapter.before_return = lambda shard, reserved: (_ for _ in ()).throw(
        RuntimeError("boom")
    )

    run(tmp_path, adapter, registry=registry, parallel=1)

    assert registry.live() == []


def test_max_sessions_limits_the_launches(tmp_path: Path) -> None:
    adapter = FakeAdapter(tmp_path, keys(120))

    report, _ = run(tmp_path, adapter, max_sessions=2)

    assert report.stop is SchedulerStop.MAX_SESSIONS
    assert len(adapter.calls) == 2
    assert report.remaining > 0


def test_a_full_account_is_skipped_for_the_next_account(tmp_path: Path) -> None:
    adapter = FakeAdapter(tmp_path, keys(3))
    raised = {"done": False}

    def refuse_once(shard: Shard, reserved: ReservedAccount) -> None:
        if not raised["done"]:
            raised["done"] = True
            raise KaggleSessionCapacityReached(reserved.profile)

    adapter.before_return = refuse_once

    report, _ = run(tmp_path, adapter, parallel=1)

    assert report.stop is SchedulerStop.COMPLETE
    first, second = adapter.calls[0], adapter.calls[1]
    assert first.profile != second.profile
