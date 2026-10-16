"""flock-based lock files named after the file they protect."""

from __future__ import annotations

import fcntl
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pharma_lab.config import paths

LockKind = Literal["job", "cache", "publish"]
MAX_LOCK_FILE_NAME_BYTES = 255


class LockHeldError(Exception):
    """A non-blocking flock found the lock taken."""


def lock_file_name(
    target: Path, kind: LockKind, *, data_dir: Path | None = None
) -> str:
    """Name a lock after its target: the path under data/ with "/" replaced by "__".

    The kind is part of the name because one command holds a job lock and a cache lock on
    the same target, and flock locks belong to the open handle, not to the process.
    """
    resolved = Path(target).resolve(strict=False)
    base = Path(paths.DATA_DIR if data_dir is None else data_dir).resolve(strict=False)
    try:
        relative = resolved.relative_to(base).as_posix()
    except ValueError:
        relative = "_external/" + resolved.as_posix().lstrip("/")
    name = f"{relative.replace('/', '__')}.{kind}.lock"
    if len(name.encode("utf-8")) > MAX_LOCK_FILE_NAME_BYTES:
        raise ValueError(f"Lock target path is too long for a lock file name: {target}")
    return name


@contextmanager
def flock(
    lock_path: Path, content: str, *, non_blocking: bool
) -> Generator[None, None, None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if non_blocking else 0)
        try:
            fcntl.flock(handle.fileno(), flags)
        except BlockingIOError as exc:
            raise LockHeldError(str(lock_path)) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(content)
        handle.flush()
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
