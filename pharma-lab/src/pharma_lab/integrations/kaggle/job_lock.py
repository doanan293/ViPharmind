from __future__ import annotations

import os
from collections.abc import Generator
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
    slot: int = 0,
) -> AbstractContextManager[str]:
    """Hold one session slot of one Kaggle account, failing at once if it is taken.

    Parallel `pharma-lab rerank` commands for different models share the account pool;
    by default (slot 0) this lock keeps each account to one GPU session started from
    this machine. Kaggle runs two batch GPU sessions per account, so a scheduler that
    wants both takes slots 0 and 1; slot 0 keeps the lock file every command already uses.
    """
    if ACCOUNT_NAME.fullmatch(profile) is None:
        raise ValueError(f"invalid Kaggle account profile: {profile!r}")
    if slot < 0:
        raise ValueError(f"invalid Kaggle account slot: {slot!r}")
    root = paths.LOCK_DIR if lock_root is None else lock_root
    name = f"{profile}.lock" if slot == 0 else f"{profile}.{slot}.lock"
    return _account_lock(profile, Path(root) / ACCOUNT_LOCK_DIRNAME / name)


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
