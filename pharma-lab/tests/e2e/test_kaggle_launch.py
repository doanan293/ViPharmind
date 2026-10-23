from __future__ import annotations

from pathlib import Path

import pytest
from tests.e2e.test_kaggle_shards import ITEMS, adapter, key
from tests.e2e.test_work_state import done, failed, write_answers
from tests.integrations.kaggle.test_scheduler import contexts

from pharma_lab.e2e.kaggle_launch import (
    EXIT_DONE,
    EXIT_PAUSED,
    EXIT_STUCK,
    LaunchOptions,
    exit_code_for,
    launch,
    registry_for,
    run_status,
)
from pharma_lab.integrations.kaggle.job_registry import ShardRecord
from pharma_lab.integrations.kaggle.scheduler import (
    SchedulerReport,
    SchedulerSettings,
    SchedulerStop,
    shard_margin_seconds,
)

OPTIONS = LaunchOptions(None, None, 10_800, None, False)


def no_contexts(_account):
    raise AssertionError("Kaggle must not be touched")


class Scheduler:
    """Stands in for `run_shards`: records the settings, stops for a given reason."""

    def __init__(self, stop: SchedulerStop, remaining: int = 0) -> None:
        self.stop = stop
        self.remaining = remaining
        self.settings: SchedulerSettings | None = None

    def __call__(self, adapter_, contexts, registry, settings, *, log):
        self.settings = settings
        return SchedulerReport(self.stop, 2, 5, self.remaining, ("table",))


def test_nothing_missing_exits_zero_without_touching_kaggle(tmp_path: Path) -> None:
    subject = adapter(tmp_path)
    write_answers(subject.run_root, "full", [done(item.item_id) for item in ITEMS])

    outcome = launch(
        subject,
        OPTIONS,
        resolve_contexts=no_contexts,
        registry=registry_for(tmp_path),
        scheduler=lambda *a, **k: pytest.fail("no scheduler run expected"),
    )

    assert outcome.exit_code == EXIT_DONE
    assert outcome.shards_run == 0


@pytest.mark.parametrize(
    ("stop", "code"),
    [
        (SchedulerStop.COMPLETE, EXIT_DONE),
        (SchedulerStop.QUOTA_EXHAUSTED, EXIT_PAUSED),
        (SchedulerStop.DRAINED, EXIT_PAUSED),
        (SchedulerStop.MAX_SESSIONS, EXIT_PAUSED),
        (SchedulerStop.STUCK, EXIT_STUCK),
    ],
)
def test_exit_codes_for_done_paused_and_stuck(
    tmp_path: Path, stop: SchedulerStop, code: int
) -> None:
    subject = adapter(tmp_path)
    scheduler = Scheduler(stop, remaining=3)

    outcome = launch(
        subject,
        OPTIONS,
        resolve_contexts=lambda _account: contexts("acc1", "acc2"),
        registry=registry_for(tmp_path),
        scheduler=scheduler,
    )

    assert outcome.exit_code == code
    assert scheduler.settings is not None
    assert scheduler.settings.parallel == 4  # two sessions per account


def test_stuck_pairs_make_a_finished_run_exit_eleven(tmp_path: Path) -> None:
    subject = adapter(tmp_path)
    item = ITEMS[0].item_id
    records = [failed(item, "boom")] * 3
    write_answers(
        subject.run_root, "full", [*records, *(done(i.item_id) for i in ITEMS[1:])]
    )

    outcome = launch(
        subject, OPTIONS, resolve_contexts=no_contexts, registry=registry_for(tmp_path)
    )

    assert (outcome.exit_code, outcome.stuck) == (EXIT_STUCK, 1)


def test_paused_wins_over_stuck() -> None:
    assert exit_code_for(SchedulerStop.QUOTA_EXHAUSTED, 2) == EXIT_PAUSED
    assert exit_code_for(SchedulerStop.COMPLETE, 2) == EXIT_STUCK


def test_shard_margin_follows_the_worker_deadline() -> None:
    assert shard_margin_seconds(10_800) == 900
    assert shard_margin_seconds(36_000) == 1800


def test_status_lists_live_shards_and_work_left(tmp_path: Path) -> None:
    subject = adapter(tmp_path)
    write_answers(subject.run_root, "full", [done(ITEMS[0].item_id)])
    registry = registry_for(tmp_path)
    registry.register(
        ShardRecord(
            "s1",
            "e2e-run",
            "acc2",
            (key("full", ITEMS[1]),),
            "2026-10-23T00:00:00+00:00",
            10_800,
        )
    )
    registry.register(
        ShardRecord("x", "rerank", "acc1", (), "2026-10-23T00:00:00+00:00", 10_800)
    )

    status = run_status(subject, registry)

    assert [(r.label, r.done, r.total, r.stuck) for r in status.labels] == [
        ("full", 1, len(ITEMS), 0)
    ]
    assert [r.shard_id for r in status.live] == ["s1"]
    assert (
        status.gpu_hours_needed > 0.5
    )  # the setup of one kernel alone is half an hour


def test_no_account_flag_means_every_account(tmp_path: Path) -> None:
    subject = adapter(tmp_path)
    asked: list[str | None] = []

    def resolve(account):
        asked.append(account)
        return contexts("acc1")

    launch(
        subject,
        OPTIONS,
        resolve_contexts=resolve,
        registry=registry_for(tmp_path),
        scheduler=Scheduler(SchedulerStop.COMPLETE),
    )

    assert asked == ["auto"]
