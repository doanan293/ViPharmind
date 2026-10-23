"""Split work into shards, one Kaggle kernel each (pure planning, no I/O)."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkUnit:
    """One thing to compute. `group` units share one kernel layout and never mix."""

    key: str
    seconds: float
    group: str = ""


@dataclass(frozen=True)
class Shard:
    shard_id: str
    units: tuple[WorkUnit, ...]
    group: str

    @property
    def seconds(self) -> float:
        return sum(unit.seconds for unit in self.units)


def shard_id_of(keys: Sequence[str]) -> str:
    digest = hashlib.sha256("\n".join(sorted(keys)).encode("utf-8")).hexdigest()
    return digest[:16]


def plan_shards(
    units: Sequence[WorkUnit],
    *,
    setup_seconds: float,
    budget_seconds: float,
    margin_seconds: float,
    slots: int,
    effective_parallelism: float = 1.0,
) -> list[Shard]:
    """Shards that fit one session each and use the free slots when that pays off.

    A shard's work is bounded by `(budget - margin - setup) * effective_parallelism`
    seconds, except for a unit that alone exceeds it. Splitting further only pays
    when every shard keeps at least `setup_seconds` of work, because each new shard
    repeats the environment setup. The result depends only on the units, so the
    same missing work always gives the same shards (and the same job identities).
    """
    if slots < 1:
        raise ValueError("slots must be at least 1")
    capacity = (budget_seconds - margin_seconds - setup_seconds) * max(
        effective_parallelism, 1e-9
    )
    if capacity <= 0:
        raise ValueError("the session budget does not cover the setup and margin")
    by_group: dict[str, list[WorkUnit]] = defaultdict(list)
    for unit in units:
        by_group[unit.group].append(unit)
    shards: list[Shard] = []
    for group in sorted(by_group):
        shards.extend(
            _plan_group(group, by_group[group], capacity, setup_seconds, slots)
        )
    return shards


def _plan_group(
    group: str,
    units: list[WorkUnit],
    capacity: float,
    setup_seconds: float,
    slots: int,
) -> list[Shard]:
    ordered = sorted(units, key=lambda unit: (-unit.seconds, unit.key))
    total = sum(unit.seconds for unit in ordered)
    by_budget = max(1, math.ceil(total / capacity))
    by_speed = (
        slots
        if setup_seconds <= 0
        else min(slots, max(1, math.floor(total / setup_seconds)))
    )
    count = min(len(ordered), max(by_budget, by_speed))
    while True:
        bins = _pack(ordered, count)
        too_big = any(
            len(items) > 1 and sum(unit.seconds for unit in items) > capacity
            for items in bins
        )
        if not too_big or count >= len(ordered):
            break
        count += 1
    return [
        Shard(
            shard_id_of([unit.key for unit in items]),
            tuple(sorted(items, key=lambda unit: unit.key)),
            group,
        )
        for items in bins
        if items
    ]


def _pack(ordered: list[WorkUnit], count: int) -> list[list[WorkUnit]]:
    """Longest unit first into the lightest shard (ties go to the lowest index)."""
    bins: list[list[WorkUnit]] = [[] for _ in range(count)]
    loads = [0.0] * count
    for unit in ordered:
        index = min(range(count), key=lambda i: (loads[i], i))
        bins[index].append(unit)
        loads[index] += unit.seconds
    return bins
