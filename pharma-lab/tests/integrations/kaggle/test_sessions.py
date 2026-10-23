from contextlib import ExitStack, nullcontext
from datetime import datetime
from pathlib import Path

import pytest
from tests.integrations.kaggle.factories import owners, stage_job

from pharma_lab.artifacts.manifest import Completion
from pharma_lab.integrations.kaggle.api import KaggleCommandRunner
from pharma_lab.integrations.kaggle.config import KaggleAccountProfile
from pharma_lab.integrations.kaggle.job_lock import (
    KaggleAccountBusy,
    kaggle_account_lock,
)
from pharma_lab.integrations.kaggle.models import PipelineResult
from pharma_lab.integrations.kaggle.quota import AccountQuota
from pharma_lab.integrations.kaggle.service import KaggleExecutionContext
from pharma_lab.integrations.kaggle.sessions import (
    ACCOUNT_WAIT_SECONDS,
    QuotaExhausted,
    ReservedAccount,
    reserve_session_account,
    reserve_session_account_waiting,
)

REFRESH = datetime(2026, 9, 19)


def _contexts(*names: str) -> tuple[KaggleExecutionContext, ...]:
    return tuple(
        KaggleExecutionContext(
            KaggleAccountProfile(name, f"user-{name}", f"token-{name}"),
            owners(f"user-{name}"),
            KaggleCommandRunner(environment={}),
        )
        for name in names
    )


class QuotaBook:
    """Fake `kaggle quota -v` per account; sessions spend hours from it."""

    def __init__(self, **remaining: float):
        self.remaining = dict(remaining)
        self.reads: list[str] = []

    def __call__(self, context: KaggleExecutionContext) -> AccountQuota:
        assert context.profile is not None
        name = context.profile.name
        self.reads.append(name)
        return AccountQuota(
            name, context.profile.username, self.remaining[name], 30.0, REFRESH
        )


class ScriptedSessions:
    def __init__(
        self,
        tmp_path: Path,
        book: QuotaBook,
        completes: list[int],
        *,
        total: int = 300_000,
        spent_hours: float = 6.0,
    ):
        self.job = stage_job(tmp_path)
        self.book = book
        self.completes = completes
        self.total = total
        self.spent_hours = spent_hours
        self.accounts: list[tuple[str, int]] = []

    def __call__(self, reserved: ReservedAccount, index: int) -> PipelineResult:
        self.accounts.append((reserved.profile, reserved.budget_seconds))
        self.book.remaining[reserved.profile] -= self.spent_hours
        complete = self.completes[index - 1]
        completion = Completion(self.total, complete, self.total - complete)
        return PipelineResult(self.job, completion, (), None, 1)


def _quiet(_line: str) -> None:
    return None


class BusyThenFree:
    """An account lock another local job holds for the first `busy` attempts."""

    def __init__(self, busy: int):
        self.busy = busy
        self.attempts = 0

    def __call__(self, profile: str):
        self.attempts += 1
        if self.attempts <= self.busy:
            raise KaggleAccountBusy(profile)
        return nullcontext(profile)


def test_a_one_off_reservation_waits_for_an_account_another_job_holds():
    """The profile benchmark reserves an account once, outside the session loop; a
    busy account with quota is waited for there too, not reported as exhausted."""
    book = QuotaBook(acc3=15.28)
    waits: list[float] = []
    log: list[str] = []

    with reserve_session_account_waiting(
        _contexts("acc3"),
        requested_budget_seconds=21_600,
        log=log.append,
        read_quota=book,
        account_lock=BusyThenFree(busy=1),
        wait=waits.append,
    ) as reserved:
        assert reserved.profile == "acc3"

    assert waits == [ACCOUNT_WAIT_SECONDS]
    assert any("waiting for an account another local job holds" in line for line in log)


def test_a_one_off_reservation_still_stops_without_quota():
    book = QuotaBook(acc3=0.4)
    waits: list[float] = []

    with (
        pytest.raises(QuotaExhausted),
        reserve_session_account_waiting(
            _contexts("acc3"),
            requested_budget_seconds=21_600,
            log=_quiet,
            read_quota=book,
            wait=waits.append,
        ),
    ):
        pass

    assert waits == []


def _slot_locker(lock_root: Path):
    def locker(profile: str, slot: int = 0):
        return kaggle_account_lock(profile, lock_root=lock_root, slot=slot)

    return locker


def test_two_sessions_can_hold_one_account(tmp_path: Path) -> None:
    book = QuotaBook(acc1=30.0)
    contexts = _contexts("acc1")
    with ExitStack() as stack:
        reserve = {
            "requested_budget_seconds": 7_200,
            "log": lambda _message: None,
            "read_quota": book,
            "account_lock": _slot_locker(tmp_path),
            "slots_per_account": 2,
        }
        first = stack.enter_context(reserve_session_account(contexts, **reserve))
        second = stack.enter_context(reserve_session_account(contexts, **reserve))
        assert (first.profile, second.profile) == ("acc1", "acc1")
        with pytest.raises(QuotaExhausted):
            stack.enter_context(reserve_session_account(contexts, **reserve))


def test_a_third_session_goes_to_the_next_account(tmp_path: Path) -> None:
    book = QuotaBook(acc1=30.0, acc2=29.0)
    contexts = _contexts("acc1", "acc2")
    with ExitStack() as stack:
        reserve = {
            "requested_budget_seconds": 7_200,
            "log": lambda _message: None,
            "read_quota": book,
            "account_lock": _slot_locker(tmp_path),
            "slots_per_account": 2,
        }
        profiles = [
            stack.enter_context(reserve_session_account(contexts, **reserve)).profile
            for _ in range(3)
        ]

    assert profiles == ["acc1", "acc1", "acc2"]


def test_committed_seconds_are_subtracted_when_choosing(tmp_path: Path) -> None:
    book = QuotaBook(acc1=4.0, acc2=3.5)

    with reserve_session_account(
        _contexts("acc1", "acc2"),
        requested_budget_seconds=7_200,
        log=lambda _message: None,
        read_quota=book,
        account_lock=_slot_locker(tmp_path),
        committed_seconds=lambda: {"acc1": 7_200},
    ) as reserved:
        assert reserved.profile == "acc2"


def test_a_busy_slot_is_skipped_not_fatal(tmp_path: Path) -> None:
    book = QuotaBook(acc1=30.0)
    with (
        kaggle_account_lock("acc1", lock_root=tmp_path, slot=0),
        reserve_session_account(
            _contexts("acc1"),
            requested_budget_seconds=7_200,
            log=lambda _message: None,
            read_quota=book,
            account_lock=_slot_locker(tmp_path),
            slots_per_account=2,
        ) as reserved,
    ):
        assert reserved.profile == "acc1"
