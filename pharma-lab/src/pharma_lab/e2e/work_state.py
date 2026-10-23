"""What an e2e run still lacks, and how a shard's answers join the local run.

The local `answers.jsonl` of each configuration directory is the only truth: a pair
(configuration, golden item) is missing when it has no answer yet, a revised golden item
superseded it, or its last answer is a retryable error that has not failed for good.
Kaggle kernels return `<label>/answers.jsonl` and `<label>/run.json` in a tar; merging
appends only the lines the local file lacks and never lets an error hide a completed answer.
"""

from __future__ import annotations

import json
import os
import tarfile
from collections import Counter
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from pharma_lab.e2e.golden import Category, GoldenItem
from pharma_lab.e2e.golden_changes import SUPERSEDED
from pharma_lab.e2e.harness import spread
from pharma_lab.e2e.records import ANSWERS_FILE, AnswerRecord
from pharma_lab.e2e.run_identity import INFORMATIONAL, RUN_FILE
from pharma_lab.integrations.kaggle.job_lock import kaggle_cache_lock

# A pair that failed this many times, or failed twice with the same error (a failure that
# repeats itself will not heal), is stuck: it stops costing quota until `retry_stuck`.
MAX_FAILURES = 3
KEPT_FILES = (ANSWERS_FILE, RUN_FILE)
# Run facts that may differ between the kernels of one run only informationally.
SOFTWARE_MUST_MATCH = ("llama_server", "model_sha256")
SOFTWARE_MAY_DIFFER = ("proxy",)


@dataclass(frozen=True)
class Pair:
    label: str
    item_id: str


@dataclass(frozen=True)
class WorkReport:
    missing: tuple[Pair, ...]
    stuck: tuple[Pair, ...]
    done: int


@dataclass(frozen=True)
class MergeReport:
    appended: int
    skipped: int
    truncated_lines: int
    warnings: tuple[str, ...] = ()


def select_universe(
    golden: Sequence[GoldenItem],
    *,
    categories: Sequence[Category] | None,
    limit: int | None,
) -> list[GoldenItem]:
    """The items of the chosen categories in golden order, then `limit` spread evenly.

    For one category this is exactly `harness.select_items`, so local and Kaggle runs
    agree on what a run is made of."""
    wanted = None if categories is None else set(categories)
    chosen = [item for item in golden if wanted is None or item.category in wanted]
    return spread(chosen, limit)


def missing_pairs(
    run_root: Path,
    labels: Sequence[str],
    universe: Sequence[GoldenItem],
    *,
    retry_stuck: bool = False,
) -> WorkReport:
    missing: list[Pair] = []
    stuck: list[Pair] = []
    done = 0
    for label in labels:
        history = _history(run_root / label / ANSWERS_FILE)
        for item in universe:
            state = _state(history.get(item.item_id, ()), retry_stuck=retry_stuck)
            pair = Pair(label, item.item_id)
            if state == "missing":
                missing.append(pair)
            elif state == "stuck":
                stuck.append(pair)
            else:
                done += 1
    return WorkReport(tuple(missing), tuple(stuck), done)


def merge_shard(
    archive: Path,
    run_root: Path,
    labels: Sequence[str],
    *,
    software_check: bool = True,
    lock_root: Path | None = None,
) -> MergeReport:
    """Merge the tar of one kernel into `run_root`; nothing is written unless every
    configuration in it passes the identity and software checks."""
    payload = _read_archive(archive, labels)
    warnings: list[str] = []
    appended = skipped = truncated = 0
    # Every label is locked before any is checked, so two shards arriving together are
    # judged one after the other against whatever the first one left.
    with ExitStack() as stack:
        for label in sorted(labels):
            stack.enter_context(
                kaggle_cache_lock(run_root / label / ANSWERS_FILE, lock_root=lock_root)
            )
        for label in labels:
            incoming = payload.get(f"{label}/{RUN_FILE}")
            stored_path = run_root / label / RUN_FILE
            if incoming is None:
                if stored_path.is_file() and f"{label}/{ANSWERS_FILE}" in payload:
                    raise ValueError(
                        f"{label}: the shard carries answers but no run.json, so it "
                        "cannot be checked against the run"
                    )
                continue
            if not stored_path.is_file():
                continue
            warnings += _check_identity(
                label,
                json.loads(stored_path.read_text(encoding="utf-8")),
                json.loads(incoming),
                software_check=software_check,
            )
        for label in labels:
            answers = payload.get(f"{label}/{ANSWERS_FILE}")
            run_raw = payload.get(f"{label}/{RUN_FILE}")
            if answers is None and run_raw is None:
                continue
            path = run_root / label / ANSWERS_FILE
            if run_raw is not None and not (run_root / label / RUN_FILE).is_file():
                _write_bytes(run_root / label / RUN_FILE, run_raw)
            if answers is not None:
                added, ignored, cut = _append_new(path, answers)
                appended, skipped, truncated = (
                    appended + added,
                    skipped + ignored,
                    truncated + cut,
                )
    return MergeReport(appended, skipped, truncated, tuple(warnings))


# Reading


def _read_lines(raw: str) -> tuple[list[tuple[str, AnswerRecord]], int]:
    """(line, record) pairs; lines that do not parse (a cut-off last line) are counted."""
    records: list[tuple[str, AnswerRecord]] = []
    unreadable = 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            records.append((line, AnswerRecord.model_validate_json(line)))
        except (ValidationError, ValueError):
            unreadable += 1
    return records, unreadable


def _history(path: Path) -> dict[str, list[tuple[str, AnswerRecord]]]:
    if not path.is_file():
        return {}
    records, _ = _read_lines(path.read_text(encoding="utf-8"))
    history: dict[str, list[tuple[str, AnswerRecord]]] = {}
    for line, record in records:
        history.setdefault(record.item_id, []).append((line, record))
    return history


def _state(history: Sequence[tuple[str, AnswerRecord]], *, retry_stuck: bool) -> str:
    if not history:
        return "missing"
    last = history[-1][1]
    if last.status == SUPERSEDED:
        return "missing"
    if last.status != "error" or not last.retryable:
        return "done"
    # By message, not by line: a failure repeated by another kernel differs in `session`.
    errors = Counter(record.error for _, record in history if record.status == "error")
    failed_for_good = sum(errors.values()) >= MAX_FAILURES or max(errors.values()) >= 2
    if failed_for_good and not retry_stuck:
        return "stuck"
    return "missing"


def _read_archive(archive: Path, labels: Sequence[str]) -> dict[str, bytes]:
    allowed = {f"{label}/{name}" for label in labels for name in KEPT_FILES}
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        unexpected = [
            m.name for m in members if m.name not in allowed or not m.isfile()
        ]
        if unexpected:
            raise ValueError(f"unexpected files in the kernel output: {unexpected}")
        payload: dict[str, bytes] = {}
        for member in members:
            source = tar.extractfile(member)
            assert source is not None
            payload[member.name] = source.read()
    return payload


# Checking and writing


def _check_identity(
    label: str,
    stored: Mapping[str, object],
    incoming: Mapping[str, object],
    *,
    software_check: bool,
) -> list[str]:
    # Every kernel imports the corpus into its own Postgres and so into its own release.
    ignored = {*INFORMATIONAL, "software", "release_id"}
    left = {k: v for k, v in stored.items() if k not in ignored}
    right = {k: v for k, v in incoming.items() if k not in ignored}
    changed = sorted(k for k in set(left) | set(right) if left.get(k) != right.get(k))
    if changed:
        raise ValueError(
            f"{label}: the shard was run for a different setup ({', '.join(changed)})"
        )
    old, new = stored.get("software"), incoming.get("software")
    if not software_check or not isinstance(old, dict) or not isinstance(new, dict):
        return []
    for key in SOFTWARE_MUST_MATCH:
        if key in old and key in new and old[key] != new[key]:
            raise ValueError(
                f"{label}: software.{key} differs ({old[key]!r} vs {new[key]!r}); "
                "the answers are not comparable"
            )
    return [
        f"{label}: {key} changed ({old[key]!r} -> {new[key]!r})"
        for key in SOFTWARE_MAY_DIFFER
        if key in old and key in new and old[key] != new[key]
    ]


def _append_new(path: Path, raw: bytes) -> tuple[int, int, int]:
    """Append the incoming lines the local file does not already hold.

    Lines are compared as a multiset, so merging the same tar again, or a later and
    longer snapshot of the same kernel, adds only what is new."""
    local, _ = _read_lines(path.read_text(encoding="utf-8") if path.is_file() else "")
    held = Counter((record.item_id, line) for line, record in local)
    last_status = {record.item_id: record.status for _, record in local}
    incoming, unreadable = _read_lines(raw.decode("utf-8", errors="replace"))
    seen: Counter[tuple[str, str]] = Counter()
    fresh: list[str] = []
    skipped = 0
    for line, record in incoming:
        key = (record.item_id, line)
        seen[key] += 1
        if seen[key] <= held[key]:
            skipped += 1
            continue
        previous = last_status.get(record.item_id)
        if record.status == "error" and previous not in (None, "error", SUPERSEDED):
            skipped += 1
            continue
        fresh.append(line)
        last_status[record.item_id] = record.status
    if fresh:
        path.parent.mkdir(parents=True, exist_ok=True)
        needs_newline = path.is_file() and not path.read_bytes().endswith(b"\n")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(("\n" if needs_newline else "") + "\n".join(fresh) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return len(fresh), skipped, unreadable


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)
