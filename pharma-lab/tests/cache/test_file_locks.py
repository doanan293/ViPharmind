from pathlib import Path

import pytest

from pharma_lab.cache.file_locks import LockHeldError, flock, lock_file_name


def test_lock_file_is_named_after_the_target_inside_data(tmp_path: Path) -> None:
    data = tmp_path / "data"
    target = data / "cache" / "text_embeddings" / "qwen3_embedding_4b_q8_0.jsonl"

    assert (
        lock_file_name(target, "job", data_dir=data)
        == "cache__text_embeddings__qwen3_embedding_4b_q8_0.jsonl.job.lock"
    )


def test_lock_file_for_a_target_outside_data_is_marked_external(tmp_path: Path) -> None:
    data = tmp_path / "data"
    target = tmp_path / "elsewhere" / "run.json"
    expected = "_external/" + target.resolve().as_posix().lstrip("/")

    assert lock_file_name(target, "cache", data_dir=data) == (
        expected.replace("/", "__") + ".cache.lock"
    )


def test_flock_reports_a_held_lock_without_blocking(tmp_path: Path) -> None:
    lock_path = tmp_path / "locks" / "x.lock"

    with flock(lock_path, "first", non_blocking=True):
        with (
            pytest.raises(LockHeldError),
            flock(lock_path, "second", non_blocking=True),
        ):
            raise AssertionError("a held lock must not be entered")
        assert lock_path.read_text(encoding="utf-8") == "first"
    with flock(lock_path, "third", non_blocking=True):
        assert lock_path.read_text(encoding="utf-8") == "third"
