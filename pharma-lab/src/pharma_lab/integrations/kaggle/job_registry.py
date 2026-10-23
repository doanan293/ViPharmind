"""The Kaggle shards a local command has started and not yet collected.

A command that dies or is stopped leaves its kernels running on Kaggle. The next command
reads this file to relaunch the same shards (which attaches to the running kernels), to
leave their work units to them, and to count the quota they have already promised.
Everything else is recomputed from local state, so a lost or stale file costs quota at
worst, never data.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from pharma_lab.integrations.kaggle.job_lock import kaggle_cache_lock


@dataclass(frozen=True)
class ShardRecord:
    shard_id: str
    stage: str
    profile: str
    unit_keys: tuple[str, ...]
    submitted_at: str
    budget_seconds: int


def sibling_registry_paths(work_root: Path) -> list[Path]:
    """The shard registries of every step under `work_root` (e2e, rerank, embeddings)."""
    return sorted(
        [
            *Path(work_root).glob("e2e-kaggle/*/jobs.json"),
            *Path(work_root).glob("kaggle-*/*/jobs.json"),
        ]
    )


def shared_registry(
    path: Path, work_root: Path, *, lock_root: Path | None = None
) -> JobRegistry:
    """A registry whose committed quota also counts the other steps' running shards,
    because an account's hours are shared by every command that runs on it."""
    return JobRegistry(
        path, lock_root=lock_root, peers=lambda: sibling_registry_paths(work_root)
    )


class JobRegistry:
    def __init__(
        self,
        path: Path,
        *,
        lock_root: Path | None = None,
        peers: Callable[[], Sequence[Path]] | None = None,
    ) -> None:
        self.path = Path(path)
        self._lock_root = lock_root
        self._peers = peers

    def register(self, record: ShardRecord) -> None:
        with self._locked():
            records = [r for r in self._read() if r.shard_id != record.shard_id]
            self._write([*records, record])

    def finish(self, shard_id: str) -> None:
        with self._locked():
            records = self._read()
            kept = [r for r in records if r.shard_id != shard_id]
            if len(kept) != len(records):
                self._write(kept)

    def live(self) -> list[ShardRecord]:
        with self._locked():
            return self._read()

    def committed_seconds(self) -> dict[str, int]:
        """Budget already promised to running sessions, by account profile."""
        totals: dict[str, int] = defaultdict(int)
        records = self.live()
        if self._peers is not None:
            own = self.path.resolve()
            for other in self._peers():
                if Path(other).resolve() != own:
                    records += JobRegistry(
                        Path(other), lock_root=self._lock_root
                    ).live()
        for record in records:
            totals[record.profile] += record.budget_seconds
        return dict(totals)

    def assigned_keys(self, stage: str) -> frozenset[str]:
        """Work-unit keys that a running shard of `stage` already owns."""
        return frozenset(
            key
            for record in self.live()
            if record.stage == stage
            for key in record.unit_keys
        )

    def clear_stale(
        self, *, older_than_seconds: float, now: datetime
    ) -> list[ShardRecord]:
        """Drop shards submitted longer ago than any session can run."""
        with self._locked():
            records = self._read()
            stale = [
                r
                for r in records
                if (now - datetime.fromisoformat(r.submitted_at)).total_seconds()
                > older_than_seconds
            ]
            if stale:
                gone = {r.shard_id for r in stale}
                self._write([r for r in records if r.shard_id not in gone])
            return stale

    def _locked(self):
        return kaggle_cache_lock(self.path, lock_root=self._lock_root)

    def _read(self) -> list[ShardRecord]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return [
                ShardRecord(
                    shard_id=str(item["shard_id"]),
                    stage=str(item["stage"]),
                    profile=str(item["profile"]),
                    unit_keys=tuple(str(key) for key in item["unit_keys"]),
                    submitted_at=str(item["submitted_at"]),
                    budget_seconds=int(item["budget_seconds"]),
                )
                for item in payload["shards"]
            ]
        except (OSError, ValueError, KeyError, TypeError):
            return []

    def _write(self, records: list[ShardRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(
                {"shards": [asdict(record) for record in records]},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
