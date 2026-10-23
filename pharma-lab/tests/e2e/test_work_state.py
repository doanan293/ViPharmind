from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from pharma_lab.e2e.golden import Category, GoldenItem
from pharma_lab.e2e.harness import select_items
from pharma_lab.e2e.records import ANSWERS_FILE, AnswerRecord
from pharma_lab.e2e.run_identity import RUN_FILE
from pharma_lab.e2e.work_state import (
    MAX_FAILURES,
    Pair,
    merge_shard,
    missing_pairs,
    select_universe,
)


def golden(index: int, category: Category = Category.ANSWERABLE) -> GoldenItem:
    return GoldenItem.model_validate(
        {
            "item_id": f"e2e-{category.value[:3]}-{index:04d}",
            "category": category.value,
            "turns": [{"role": "user", "text": f"question {index}"}],
            "expected_behavior": "grounded",
        }
    )


def done(item_id: str, label: str = "full", answer_text: str = "") -> AnswerRecord:
    return AnswerRecord(
        item_id=item_id, config=label, status="completed", answer_text=answer_text
    )


def failed(item_id: str, message: str, label: str = "full") -> AnswerRecord:
    return AnswerRecord(
        item_id=item_id,
        config=label,
        status="error",
        error=message,
        retryable=True,
    )


def write_answers(run_root: Path, label: str, records: list[AnswerRecord]) -> Path:
    path = run_root / label / ANSWERS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(record.model_dump_json() + "\n" for record in records),
        encoding="utf-8",
    )
    return path


def run_json(**overrides: object) -> dict[str, object]:
    stored: dict[str, object] = {
        "golden_sha256": "g" * 64,
        "config": "full",
        "pipeline": {"rephrase": True},
        "release_id": "release-1",
        "retrieval": {"mode": "hybrid"},
        "rerank": {"protocol": "native_rerank"},
        "role_models": {"answer": {"model": "qwen"}},
        "budget": {"deadline_seconds": 900},
        "git_commit": "abc",
        "created_at": "2026-10-23T00:00:00+00:00",
    }
    stored.update(overrides)
    return stored


def tar_of(path: Path, members: dict[str, bytes]) -> Path:
    with tarfile.open(path, "w") as archive:
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return path


def lines(*records: AnswerRecord) -> bytes:
    return "".join(record.model_dump_json() + "\n" for record in records).encode()


def shard_archive(
    tmp_path: Path,
    records: list[AnswerRecord],
    *,
    label: str = "full",
    identity: dict[str, object] | None = None,
    name: str = "shard.tar",
    raw: bytes | None = None,
) -> Path:
    return tar_of(
        tmp_path / name,
        {
            f"{label}/{ANSWERS_FILE}": raw if raw is not None else lines(*records),
            f"{label}/{RUN_FILE}": json.dumps(identity or run_json()).encode(),
        },
    )


def local_records(run_root: Path, label: str = "full") -> list[AnswerRecord]:
    path = run_root / label / ANSWERS_FILE
    return [
        AnswerRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# Universe and missing pairs


def test_universe_equals_select_items_for_one_category() -> None:
    items = [golden(i, Category.ANSWERABLE) for i in range(20)] + [
        golden(i, Category.INJECTION) for i in range(5)
    ]

    universe = select_universe(items, categories=[Category.ANSWERABLE], limit=7)

    assert universe == select_items(items, limit=7, category=Category.ANSWERABLE)


def test_universe_unions_categories_in_golden_order_then_applies_the_limit() -> None:
    items = [
        golden(1, Category.ANSWERABLE),
        golden(1, Category.INJECTION),
        golden(2, Category.ANSWERABLE),
        golden(1, Category.OUT_OF_SCOPE),
    ]

    everything = select_universe(
        items, categories=[Category.ANSWERABLE, Category.INJECTION], limit=None
    )
    assert [i.item_id for i in everything] == [
        items[0].item_id,
        items[1].item_id,
        items[2].item_id,
    ]
    assert select_universe(items, categories=None, limit=None) == items


def test_missing_follows_run_items_semantics(tmp_path: Path) -> None:
    universe = [golden(i) for i in range(5)]
    ids = [item.item_id for item in universe]
    write_answers(
        tmp_path,
        "full",
        [
            done(ids[0]),
            failed(ids[1], "timeout"),
            AnswerRecord(
                item_id=ids[2],
                config="full",
                status="superseded",
                error="golden item changed",
                retryable=True,
            ),
            AnswerRecord(
                item_id=ids[3],
                config="full",
                status="error",
                error="blocked for good",
                retryable=False,
            ),
        ],
    )

    report = missing_pairs(tmp_path, ["full"], universe)

    assert {pair.item_id for pair in report.missing} == {ids[1], ids[2], ids[4]}
    assert report.done == 2
    assert report.stuck == ()


def test_two_different_errors_are_still_missing(tmp_path: Path) -> None:
    item = golden(1)
    write_answers(
        tmp_path, "full", [failed(item.item_id, "a"), failed(item.item_id, "b")]
    )

    report = missing_pairs(tmp_path, ["full"], [item])

    assert report.missing == (Pair("full", item.item_id),)
    assert report.stuck == ()


def test_the_maximum_number_of_failures_makes_a_pair_stuck(tmp_path: Path) -> None:
    item = golden(1)
    errors = [failed(item.item_id, f"error {n}") for n in range(MAX_FAILURES)]
    write_answers(tmp_path, "full", errors)

    report = missing_pairs(tmp_path, ["full"], [item])

    assert report.missing == ()
    assert report.stuck == (Pair("full", item.item_id),)


def test_the_same_error_twice_makes_a_pair_stuck(tmp_path: Path) -> None:
    item = golden(1)
    write_answers(
        tmp_path,
        "full",
        [failed(item.item_id, "KeyError: x"), failed(item.item_id, "KeyError: x")],
    )

    report = missing_pairs(tmp_path, ["full"], [item])

    assert report.stuck == (Pair("full", item.item_id),)


def test_retry_stuck_brings_stuck_pairs_back(tmp_path: Path) -> None:
    item = golden(1)
    write_answers(
        tmp_path,
        "full",
        [failed(item.item_id, "KeyError: x"), failed(item.item_id, "KeyError: x")],
    )

    report = missing_pairs(tmp_path, ["full"], [item], retry_stuck=True)

    assert report.missing == (Pair("full", item.item_id),)
    assert report.stuck == ()


def test_limit_change_does_not_touch_existing_records(tmp_path: Path) -> None:
    # Review focus 5: a different --limit changes what is wanted, never what exists.
    items = [golden(i) for i in range(20)]
    path = write_answers(tmp_path, "full", [done(items[0].item_id)])
    before = path.read_bytes()

    small = missing_pairs(
        tmp_path, ["full"], select_universe(items, categories=None, limit=5)
    )
    large = missing_pairs(
        tmp_path, ["full"], select_universe(items, categories=None, limit=10)
    )

    assert path.read_bytes() == before
    assert len(large.missing) > len(small.missing)


def test_a_missing_answers_file_means_everything_is_missing(tmp_path: Path) -> None:
    universe = [golden(i) for i in range(3)]

    report = missing_pairs(tmp_path, ["full", "one-step"], universe)

    assert len(report.missing) == 6
    assert report.done == 0


# Merging a shard


def test_merge_copies_run_json_the_first_time_and_appends_the_answers(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    archive = shard_archive(tmp_path, [done("a"), done("b")])

    report = merge_shard(archive, run_root, ["full"])

    assert (report.appended, report.skipped, report.truncated_lines) == (2, 0, 0)
    assert [r.item_id for r in local_records(run_root)] == ["a", "b"]
    assert json.loads((run_root / "full" / RUN_FILE).read_text()) == run_json()


def test_merge_never_lets_an_error_replace_a_completed_answer(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    write_answers(run_root, "full", [done("a", answer_text="good")])
    (run_root / "full" / RUN_FILE).write_text(json.dumps(run_json()))
    archive = shard_archive(tmp_path, [failed("a", "timeout"), done("b")])

    report = merge_shard(archive, run_root, ["full"])

    assert report.appended == 1
    assert report.skipped == 1
    records = {r.item_id: r for r in local_records(run_root)}
    assert records["a"].status == "completed"
    assert records["a"].answer_text == "good"
    assert records["b"].status == "completed"


def test_merge_is_idempotent(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    archive = shard_archive(tmp_path, [failed("a", "x"), done("a"), done("b")])

    merge_shard(archive, run_root, ["full"])
    once = (run_root / "full" / ANSWERS_FILE).read_bytes()
    second = merge_shard(archive, run_root, ["full"])

    assert (run_root / "full" / ANSWERS_FILE).read_bytes() == once
    assert second.appended == 0


def test_a_later_snapshot_adds_only_its_new_lines(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    first = shard_archive(tmp_path, [done("a"), failed("b", "x")], name="one.tar")
    cumulative = shard_archive(
        tmp_path, [done("a"), failed("b", "x"), done("b"), done("c")], name="two.tar"
    )

    merge_shard(first, run_root, ["full"])
    report = merge_shard(cumulative, run_root, ["full"])

    assert report.appended == 2
    assert [r.item_id for r in local_records(run_root)] == ["a", "b", "b", "c"]


def test_merge_ignores_a_truncated_last_line(tmp_path: Path) -> None:
    # Review focus 1: a killed kernel leaves half a JSON line at the end.
    run_root = tmp_path / "run"
    raw = lines(done("a"), done("b")) + b'{"item_id": "c", "config": "fu'
    archive = shard_archive(tmp_path, [], raw=raw)

    report = merge_shard(archive, run_root, ["full"])

    assert report.truncated_lines == 1
    assert [r.item_id for r in local_records(run_root)] == ["a", "b"]


def test_merge_rejects_unexpected_members(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    archive = tar_of(
        tmp_path / "bad.tar",
        {
            f"full/{ANSWERS_FILE}": lines(done("a")),
            f"full/{RUN_FILE}": json.dumps(run_json()).encode(),
            "full/secrets.txt": b"nope",
        },
    )

    with pytest.raises(ValueError, match="unexpected"):
        merge_shard(archive, run_root, ["full"])

    assert not (run_root / "full" / ANSWERS_FILE).exists()


def test_merge_refuses_a_different_identity_and_writes_nothing(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    write_answers(run_root, "full", [done("a")])
    (run_root / "full" / RUN_FILE).write_text(json.dumps(run_json()))
    before = (run_root / "full" / ANSWERS_FILE).read_bytes()
    archive = shard_archive(
        tmp_path,
        [done("b")],
        identity=run_json(golden_sha256="other" + "0" * 59),
    )

    with pytest.raises(ValueError, match="golden_sha256"):
        merge_shard(archive, run_root, ["full"])

    assert (run_root / "full" / ANSWERS_FILE).read_bytes() == before


def test_commit_and_created_at_may_differ_between_shards(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    merge_shard(shard_archive(tmp_path, [done("a")], name="a.tar"), run_root, ["full"])
    other = shard_archive(
        tmp_path,
        [done("b")],
        identity=run_json(git_commit="def", created_at="2026-10-24T00:00:00+00:00"),
        name="b.tar",
    )

    report = merge_shard(other, run_root, ["full"])

    assert report.appended == 1


SOFTWARE = {
    "llama_server": "b9637",
    "model_sha256": {"qwen3.5:9b-q8_0": "a" * 64},
    "proxy": "8.0.28",
}


def test_merge_refuses_a_different_model_file_or_llama_build(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    merge_shard(
        shard_archive(
            tmp_path, [done("a")], identity=run_json(software=SOFTWARE), name="a.tar"
        ),
        run_root,
        ["full"],
    )
    for key, value in (
        ("llama_server", "b9999"),
        ("model_sha256", {"qwen3.5:9b-q8_0": "b" * 64}),
    ):
        other = shard_archive(
            tmp_path,
            [done("b")],
            identity=run_json(software={**SOFTWARE, key: value}),
            name=f"{key}.tar",
        )
        with pytest.raises(ValueError, match=key):
            merge_shard(other, run_root, ["full"])


def test_merge_only_warns_about_a_different_proxy_version(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    merge_shard(
        shard_archive(
            tmp_path, [done("a")], identity=run_json(software=SOFTWARE), name="a.tar"
        ),
        run_root,
        ["full"],
    )
    other = shard_archive(
        tmp_path,
        [done("b")],
        identity=run_json(software={**SOFTWARE, "proxy": "8.1.0"}),
        name="b.tar",
    )

    report = merge_shard(other, run_root, ["full"])

    assert report.appended == 1
    assert any("proxy" in warning for warning in report.warnings)


def test_software_check_can_be_switched_off(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    merge_shard(
        shard_archive(
            tmp_path, [done("a")], identity=run_json(software=SOFTWARE), name="a.tar"
        ),
        run_root,
        ["full"],
    )
    other = shard_archive(
        tmp_path,
        [done("b")],
        identity=run_json(software={**SOFTWARE, "llama_server": "b9999"}),
        name="b.tar",
    )

    report = merge_shard(other, run_root, ["full"], software_check=False)

    assert report.appended == 1


def test_each_kernel_imports_its_own_release_so_release_id_may_differ(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    merge_shard(shard_archive(tmp_path, [done("a")], name="a.tar"), run_root, ["full"])
    other = shard_archive(
        tmp_path,
        [done("b")],
        identity=run_json(release_id="another-kernel-release"),
        name="b.tar",
    )

    report = merge_shard(other, run_root, ["full"])

    assert report.appended == 1


def test_the_same_failure_from_two_kernels_counts_twice_but_one_kernel_once(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    first = failed("a", "boom").model_copy(update={"session": "kernel-1"})
    second = first.model_copy(update={"session": "kernel-2"})

    merge_shard(shard_archive(tmp_path, [first], name="1.tar"), run_root, ["full"])
    merge_shard(shard_archive(tmp_path, [first], name="1b.tar"), run_root, ["full"])
    assert len((run_root / "full" / ANSWERS_FILE).read_text().splitlines()) == 1

    merge_shard(shard_archive(tmp_path, [second], name="2.tar"), run_root, ["full"])
    item = GoldenItem.model_validate(
        {
            "item_id": "a",
            "category": "answerable",
            "turns": [{"role": "user", "text": "q"}],
            "expected_behavior": "grounded",
        }
    )
    report = missing_pairs(run_root, ["full"], [item])

    assert len((run_root / "full" / ANSWERS_FILE).read_text().splitlines()) == 2
    assert [p.item_id for p in report.stuck] == ["a"]  # the same error twice
