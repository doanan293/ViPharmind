import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pharma_lab.integrations.kaggle.job_registry import JobRegistry, ShardRecord

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def record(
    shard_id: str = "s1",
    *,
    stage: str = "e2e-run",
    profile: str = "acc1",
    keys: tuple[str, ...] = ("a", "b"),
    budget: int = 7200,
    submitted: datetime = NOW,
) -> ShardRecord:
    return ShardRecord(
        shard_id=shard_id,
        stage=stage,
        profile=profile,
        unit_keys=keys,
        submitted_at=submitted.isoformat(),
        budget_seconds=budget,
    )


def registry(tmp_path: Path) -> JobRegistry:
    return JobRegistry(tmp_path / "jobs.json", lock_root=tmp_path / "locks")


def test_register_and_finish_roundtrip(tmp_path: Path) -> None:
    jobs = registry(tmp_path)

    jobs.register(record("s1"))
    jobs.register(record("s2", profile="acc2"))
    assert [r.shard_id for r in jobs.live()] == ["s1", "s2"]

    jobs.finish("s1")
    assert [r.shard_id for r in jobs.live()] == ["s2"]


def test_finishing_an_unknown_shard_is_not_an_error(tmp_path: Path) -> None:
    jobs = registry(tmp_path)

    jobs.finish("never-registered")

    assert jobs.live() == []


def test_registering_a_shard_twice_replaces_it(tmp_path: Path) -> None:
    jobs = registry(tmp_path)

    jobs.register(record("s1", profile="acc1"))
    jobs.register(record("s1", profile="acc3"))

    assert [(r.shard_id, r.profile) for r in jobs.live()] == [("s1", "acc3")]


def test_two_registries_see_each_others_records(tmp_path: Path) -> None:
    first = registry(tmp_path)
    second = registry(tmp_path)

    first.register(record("s1"))

    assert [r.shard_id for r in second.live()] == ["s1"]
    second.finish("s1")
    assert first.live() == []


def test_records_keep_their_fields_through_the_file(tmp_path: Path) -> None:
    jobs = registry(tmp_path)
    original = ShardRecord(
        "s9", "rerank", "acc2", ("q1", "q2"), NOW.isoformat(), 5400, "user/kernel-x"
    )

    jobs.register(original)

    assert registry(tmp_path).live() == [original]


def test_corrupt_file_is_treated_as_empty_and_does_not_block_new_records(
    tmp_path: Path,
) -> None:
    path = tmp_path / "jobs.json"
    path.write_text("{ this is not json", encoding="utf-8")
    jobs = JobRegistry(path, lock_root=tmp_path / "locks")

    assert jobs.live() == []
    jobs.register(record("s1"))
    assert [r.shard_id for r in jobs.live()] == ["s1"]


def test_missing_file_is_empty(tmp_path: Path) -> None:
    assert registry(tmp_path).live() == []
    assert registry(tmp_path).committed_seconds() == {}


def test_committed_seconds_sum_by_profile(tmp_path: Path) -> None:
    jobs = registry(tmp_path)
    jobs.register(record("s1", profile="acc1", budget=7200))
    jobs.register(record("s2", profile="acc1", budget=3600))
    jobs.register(record("s3", profile="acc2", budget=5400))

    assert jobs.committed_seconds() == {"acc1": 10800, "acc2": 5400}


def test_assigned_keys_are_per_stage(tmp_path: Path) -> None:
    jobs = registry(tmp_path)
    jobs.register(record("s1", stage="e2e-run", keys=("a", "b")))
    jobs.register(record("s2", stage="rerank", keys=("q1",)))

    assert jobs.assigned_keys("e2e-run") == frozenset({"a", "b"})
    assert jobs.assigned_keys("rerank") == frozenset({"q1"})
    assert jobs.assigned_keys("query-embed") == frozenset()


def test_clear_stale_returns_the_removed_records(tmp_path: Path) -> None:
    jobs = registry(tmp_path)
    old = record("old", submitted=NOW - timedelta(hours=10))
    fresh = record("fresh", submitted=NOW - timedelta(minutes=5))
    jobs.register(old)
    jobs.register(fresh)

    removed = jobs.clear_stale(older_than_seconds=4 * 3600, now=NOW)

    assert removed == [old]
    assert [r.shard_id for r in jobs.live()] == ["fresh"]


def test_concurrent_registrations_do_not_lose_records(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"

    def add(index: int) -> None:
        JobRegistry(path, lock_root=tmp_path / "locks").register(
            record(f"s{index:02d}", keys=(f"k{index}",))
        )

    threads = [threading.Thread(target=add, args=(i,)) for i in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    ids = sorted(
        r.shard_id for r in JobRegistry(path, lock_root=tmp_path / "locks").live()
    )
    assert ids == [f"s{i:02d}" for i in range(12)]
