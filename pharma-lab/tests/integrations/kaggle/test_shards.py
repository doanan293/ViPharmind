import random

from pharma_lab.integrations.kaggle.shards import Shard, WorkUnit, plan_shards

SETTINGS = {
    "setup_seconds": 1800.0,
    "budget_seconds": 7200.0,
    "margin_seconds": 900.0,
    "slots": 6,
}
WORK_PER_SHARD = 7200.0 - 900.0 - 1800.0


def units(count: int, seconds: float = 600.0, group: str = "") -> list[WorkUnit]:
    return [WorkUnit(f"k{index:04d}", seconds, group) for index in range(count)]


def keys(shards: list[Shard]) -> list[str]:
    return sorted(unit.key for shard in shards for unit in shard.units)


def test_plan_is_deterministic() -> None:
    work = units(120)
    shuffled = list(work)
    random.Random(1).shuffle(shuffled)

    first = plan_shards(work, **SETTINGS)
    second = plan_shards(shuffled, **SETTINGS)

    assert [(s.shard_id, [u.key for u in s.units]) for s in first] == [
        (s.shard_id, [u.key for u in s.units]) for s in second
    ]


def test_no_unit_lost_or_duplicated() -> None:
    work = units(97, seconds=431.0)

    shards = plan_shards(work, **SETTINGS)

    assert keys(shards) == sorted(unit.key for unit in work)


def test_shard_respects_budget() -> None:
    work = [WorkUnit(f"k{i:03d}", 100.0 + (i * 37) % 900, "") for i in range(150)]

    shards = plan_shards(work, **SETTINGS)

    for shard in shards:
        assert shard.seconds <= WORK_PER_SHARD


def test_oversized_unit_gets_its_own_shard() -> None:
    work = [WorkUnit("huge", WORK_PER_SHARD * 2, ""), *units(5)]

    shards = plan_shards(work, **SETTINGS)

    alone = [shard for shard in shards if shard.units[0].key == "huge"]
    assert len(alone) == 1
    assert len(alone[0].units) == 1


def test_work_below_setup_is_not_split() -> None:
    shards = plan_shards(units(3, seconds=300.0), **SETTINGS)

    assert len(shards) == 1


def test_uses_available_slots_when_work_is_large() -> None:
    shards = plan_shards(units(120, seconds=600.0), **SETTINGS)

    assert len(shards) >= 6
    weights = [shard.seconds for shard in shards]
    assert (max(weights) - min(weights)) / max(weights) <= 0.25


def test_parallelism_inside_a_kernel_allows_bigger_shards() -> None:
    work = units(120, seconds=600.0)

    serial = plan_shards(work, **SETTINGS)
    parallel = plan_shards(work, effective_parallelism=4.0, **SETTINGS)

    assert len(parallel) < len(serial)


def test_groups_are_never_mixed() -> None:
    work = [*units(40, group="a"), *units(30, group="b")]
    work = [WorkUnit(f"{u.group}-{u.key}", u.seconds, u.group) for u in work]

    shards = plan_shards(work, **SETTINGS)

    assert all(
        {unit.group for unit in shard.units} == {shard.group} for shard in shards
    )
    assert {shard.group for shard in shards} == {"a", "b"}


def test_shard_id_depends_only_on_unit_keys() -> None:
    first = plan_shards(units(3, seconds=100.0), **SETTINGS)
    same_keys = plan_shards(units(3, seconds=250.0), **SETTINGS)
    other_keys = plan_shards(
        [WorkUnit(f"z{i}", 100.0, "") for i in range(3)], **SETTINGS
    )

    assert first[0].shard_id == same_keys[0].shard_id
    assert first[0].shard_id != other_keys[0].shard_id


def test_nothing_to_do_gives_no_shards() -> None:
    assert plan_shards([], **SETTINGS) == []
