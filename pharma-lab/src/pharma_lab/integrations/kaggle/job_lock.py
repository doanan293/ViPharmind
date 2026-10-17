from __future__ import annotations

import os
import time
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager, ExitStack, contextmanager
from pathlib import Path

from pharma_lab.cache.file_locks import LockHeldError, LockKind, flock, lock_file_name
from pharma_lab.config import paths
from pharma_lab.integrations.kaggle.config import ACCOUNT_NAME

ACCOUNT_LOCK_DIRNAME = "kaggle-accounts"


class KaggleAccountBusy(RuntimeError):
    """Another local command holds the session lock of this Kaggle account."""

    def __init__(self, profile: str):
        super().__init__(
            f"Kaggle account {profile} already runs a session for another local job"
        )
        self.profile = profile


@contextmanager
def _acquire(
    target: Path,
    *,
    kind: LockKind,
    lock_root: Path,
    non_blocking: bool,
) -> Generator[Path, None, None]:
    canonical = str(Path(target).resolve(strict=False))
    lock_path = Path(lock_root) / lock_file_name(target, kind)
    with ExitStack() as stack:
        # Only the acquisition is translated; errors from the body pass through.
        try:
            stack.enter_context(flock(lock_path, canonical, non_blocking=non_blocking))
        except LockHeldError as exc:
            raise RuntimeError(
                f"Local target {canonical} already has an active Kaggle job; "
                "wait for it to finish or choose a different run/job"
            ) from exc
        yield Path(target)


def kaggle_job_lock(
    target: Path,
    *,
    lock_root: Path | None = None,
) -> AbstractContextManager[Path]:
    root = paths.LOCK_DIR if lock_root is None else lock_root
    return _acquire(target, kind="job", lock_root=root, non_blocking=True)


def kaggle_cache_lock(
    target: Path,
    *,
    lock_root: Path | None = None,
) -> AbstractContextManager[Path]:
    root = paths.LOCK_DIR if lock_root is None else lock_root
    return _acquire(target, kind="cache", lock_root=root, non_blocking=False)


def kaggle_account_lock(
    profile: str,
    *,
    lock_root: Path | None = None,
) -> AbstractContextManager[str]:
    """Hold the session lock of one Kaggle account, failing at once if it is taken.

    Parallel `pharma-lab rerank` commands for different models share the account pool;
    this lock keeps each account to one GPU session started from this machine.
    """
    if ACCOUNT_NAME.fullmatch(profile) is None:
        raise ValueError(f"invalid Kaggle account profile: {profile!r}")
    root = paths.LOCK_DIR if lock_root is None else lock_root
    return _account_lock(profile, Path(root) / ACCOUNT_LOCK_DIRNAME / f"{profile}.lock")


@contextmanager
def _account_lock(profile: str, lock_path: Path) -> Generator[str, None, None]:
    with ExitStack() as stack:
        try:
            stack.enter_context(
                flock(lock_path, f"{profile} pid={os.getpid()}\n", non_blocking=True)
            )
        except LockHeldError as exc:
            raise KaggleAccountBusy(profile) from exc
        yield profile


# How long a command sleeps before trying again for an account another local job holds.
ACCOUNT_POLL_SECONDS = 60


@contextmanager
def wait_for_kaggle_account(
    profile: str,
    *,
    lock_root: Path | None = None,
    wait: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> Generator[str, None, None]:
    """Hold the session lock of one Kaggle account, waiting while another local job has it.

    Commands pinned to one account (`--kaggle-account accN`) use it, so a GPU job never
    shares an account with another job started from this machine and never fails just
    because the account is busy for a while.
    """
    with ExitStack() as stack:
        while True:
            try:
                stack.enter_context(kaggle_account_lock(profile, lock_root=lock_root))
                break
            except KaggleAccountBusy:
                log(f"account={profile} is held by another local job; waiting")
                wait(ACCOUNT_POLL_SECONDS)
        yield profile


@contextmanager
def hold_pinned_account(kaggle_account: str | None) -> Generator[None, None, None]:
    """Hold the account a command is pinned to (`--kaggle-account accN`) for its whole run.

    Commands that pick an account per session (`auto`) or run on the default
    credentials lock nothing here.
    """
    profile = (kaggle_account or "").strip()
    if not profile or profile.casefold() == "auto":
        yield
        return
    with wait_for_kaggle_account(profile):
        yield
