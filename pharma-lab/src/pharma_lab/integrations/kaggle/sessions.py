"""Reserve one GPU session of the Kaggle account with the most free quota."""

from __future__ import annotations

import time
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import AbstractContextManager, ExitStack, contextmanager
from dataclasses import dataclass

from pharma_lab.integrations.kaggle.job_lock import (
    KaggleAccountBusy,
    kaggle_account_lock,
)
from pharma_lab.integrations.kaggle.quota import (
    AccountQuota,
    SessionAccount,
    quota_table,
    read_account_quota,
    select_session_account,
)
from pharma_lab.integrations.kaggle.service import KaggleExecutionContext

QuotaReader = Callable[[KaggleExecutionContext], AccountQuota]
AccountLock = Callable[..., AbstractContextManager[str]]
SessionLog = Callable[[str], None]


class QuotaExhausted(RuntimeError):
    """No free account has at least one hour of GPU quota for a session."""

    def __init__(self, quotas: tuple[AccountQuota, ...], locked: frozenset[str]):
        super().__init__(
            "no free Kaggle account has at least one hour of GPU quota for a session"
        )
        self.quotas = quotas
        self.locked = locked

    def held_with_quota(self, requested_budget_seconds: int) -> bool:
        """Whether an account other jobs hold would have quota for a session, so
        waiting for it beats stopping."""
        held = tuple(quota for quota in self.quotas if quota.profile in self.locked)
        return (
            select_session_account(
                held,
                locked=frozenset(),
                requested_budget_seconds=requested_budget_seconds,
            )
            is not None
        )

    @property
    def table(self) -> tuple[str, ...]:
        return quota_table(self.quotas, locked=self.locked)


@dataclass(frozen=True)
class ReservedAccount:
    context: KaggleExecutionContext
    quota: AccountQuota
    budget_seconds: int

    @property
    def profile(self) -> str:
        return self.quota.profile


# How long a command sleeps before trying again for an account another local job holds.
ACCOUNT_WAIT_SECONDS = 60

# Kaggle runs two batch GPU sessions per account and rejects the next kernel push.
SESSION_CAPACITY_MARKER = "maximum batch gpu session count"


class KaggleSessionCapacityReached(Exception):
    """An account already runs its two Kaggle GPU sessions."""

    def __init__(self, profile: str) -> None:
        super().__init__(f"account {profile} has no free Kaggle GPU session")
        self.profile = profile


def _profile_name(context: KaggleExecutionContext) -> str:
    if context.profile is None:
        raise ValueError("Kaggle sessions need account profiles (acc1, acc2, ...)")
    return context.profile.name


def _format_quota(quota: AccountQuota) -> str:
    refresh = quota.refresh_at.isoformat() if quota.refresh_at else "unknown"
    return (
        f"quota account={quota.profile} remaining={quota.remaining_hours:.2f}h "
        f"total={quota.total_hours:.2f}h refresh_at={refresh}"
    )


def _lock_slot(stack: ExitStack, locker: AccountLock, profile: str, slots: int) -> bool:
    """Take the first free session slot of the account; False when every slot is held.

    With one slot the locker is called with the profile alone, so lockers that only
    know accounts keep working."""
    for slot in range(slots):
        try:
            held = locker(profile) if slots == 1 else locker(profile, slot=slot)
            stack.enter_context(held)
        except KaggleAccountBusy:
            continue
        return True
    return False


def _lock_preferred(
    profile: str | None,
    *,
    requested_budget_seconds: int,
    stack: ExitStack,
    locker: AccountLock,
    log: SessionLog,
    slots: int = 1,
) -> SessionAccount | None:
    if profile is None:
        return None
    if not _lock_slot(stack, locker, profile, slots):
        log(
            f"account={profile} runs this job's kernel but is locked by another "
            "local job; choosing by quota"
        )
        return None
    log(f"account={profile} already runs this job's kernel; attaching")
    return SessionAccount(profile, requested_budget_seconds)


def _lock_best(
    quotas: tuple[AccountQuota, ...],
    *,
    requested_budget_seconds: int,
    stack: ExitStack,
    locker: AccountLock,
    log: SessionLog,
    unavailable: frozenset[str] = frozenset(),
    slots: int = 1,
    committed_seconds: Callable[[], Mapping[str, int]] | None = None,
) -> SessionAccount:
    busy: set[str] = set(unavailable)
    while True:
        choice = select_session_account(
            quotas,
            locked=frozenset(busy),
            requested_budget_seconds=requested_budget_seconds,
            committed_seconds=(
                None if committed_seconds is None else committed_seconds()
            ),
        )
        if choice is None:
            raise QuotaExhausted(quotas, frozenset(busy))
        if not _lock_slot(stack, locker, choice.profile, slots):
            busy.add(choice.profile)
            log(f"account={choice.profile} is locked by another local job; skipped")
            continue
        return choice


@contextmanager
def reserve_session_account(
    contexts: Sequence[KaggleExecutionContext],
    *,
    requested_budget_seconds: int,
    log: SessionLog,
    read_quota: QuotaReader | None = None,
    account_lock: AccountLock | None = None,
    preferred_profile: str | None = None,
    unavailable: frozenset[str] = frozenset(),
    slots_per_account: int = 1,
    committed_seconds: Callable[[], Mapping[str, int]] | None = None,
) -> Generator[ReservedAccount, None, None]:
    """Read every account's GPU quota, then lock one account for one session.

    `unavailable` holds accounts a caller already found unusable, for example one whose
    Kaggle GPU sessions are all taken. `slots_per_account` is how many sessions of one
    account may run at once (Kaggle allows two); `committed_seconds` returns the budget
    of the sessions already running per account, which the choice subtracts from the
    reported quota.
    """
    reader = read_quota or read_account_quota
    locker = account_lock or kaggle_account_lock
    by_profile = {_profile_name(context): context for context in contexts}
    quotas = tuple(reader(context) for context in contexts)
    for quota in quotas:
        log(_format_quota(quota))
    with ExitStack() as stack:
        choice = _lock_preferred(
            preferred_profile,
            requested_budget_seconds=requested_budget_seconds,
            stack=stack,
            locker=locker,
            log=log,
            slots=slots_per_account,
        ) or _lock_best(
            quotas,
            requested_budget_seconds=requested_budget_seconds,
            stack=stack,
            locker=locker,
            log=log,
            unavailable=unavailable,
            slots=slots_per_account,
            committed_seconds=committed_seconds,
        )
        quota = next(item for item in quotas if item.profile == choice.profile)
        log(
            f"account={choice.profile} username={quota.username} "
            f"budget_seconds={choice.budget_seconds}"
        )
        yield ReservedAccount(by_profile[choice.profile], quota, choice.budget_seconds)


@contextmanager
def reserve_session_account_waiting(
    contexts: Sequence[KaggleExecutionContext],
    *,
    requested_budget_seconds: int,
    log: SessionLog,
    read_quota: QuotaReader | None = None,
    account_lock: AccountLock | None = None,
    wait: Callable[[float], None] = time.sleep,
) -> Generator[ReservedAccount, None, None]:
    """`reserve_session_account` for a one-off reservation (a profile benchmark, a model
    server): an account that has quota but is held by another local job is waited for,
    the way a shard waits for one; only a lack of quota raises QuotaExhausted."""
    while True:
        stack = ExitStack()
        try:
            reserved = stack.enter_context(
                reserve_session_account(
                    contexts,
                    requested_budget_seconds=requested_budget_seconds,
                    log=log,
                    read_quota=read_quota,
                    account_lock=account_lock,
                )
            )
        except QuotaExhausted as exhausted:
            if not exhausted.held_with_quota(requested_budget_seconds):
                raise
            log(
                "waiting for an account another local job holds: "
                f"{', '.join(sorted(exhausted.locked))}"
            )
            wait(ACCOUNT_WAIT_SECONDS)
            continue
        with stack:
            yield reserved
        return
