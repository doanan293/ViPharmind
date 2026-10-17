import threading
from pathlib import Path

import pytest

from pharma_lab.integrations.kaggle.job_lock import (
    ACCOUNT_POLL_SECONDS,
    KaggleAccountBusy,
    kaggle_account_lock,
    kaggle_cache_lock,
    kaggle_job_lock,
    wait_for_kaggle_account,
)


def test_same_target_lock_fails_immediately(tmp_path):
    target = tmp_path / "results" / "scores.jsonl"
    lock_root = tmp_path / "locks"
    with (
        kaggle_job_lock(target, lock_root=lock_root),
        pytest.raises(RuntimeError, match="already has an active Kaggle job"),
        kaggle_job_lock(target, lock_root=lock_root),
    ):
        raise AssertionError("contended lock must not be entered")


def test_distinct_targets_can_lock_concurrently(tmp_path):
    lock_root = tmp_path / "locks"
    with (
        kaggle_job_lock(tmp_path / "a", lock_root=lock_root),
        kaggle_job_lock(tmp_path / "b", lock_root=lock_root),
    ):
        assert True


def test_lock_releases_after_exception(tmp_path):
    target = tmp_path / "result"
    lock_root = tmp_path / "locks"
    with (
        pytest.raises(ValueError, match="boom"),
        kaggle_job_lock(target, lock_root=lock_root),
    ):
        raise ValueError("boom")
    with kaggle_job_lock(target, lock_root=lock_root):
        assert True


def test_cache_lock_serializes_writers(tmp_path):
    entered = threading.Event()
    finished = threading.Event()
    target = tmp_path / "cache.jsonl"
    lock_root = tmp_path / "cache-locks"

    def second_writer():
        with kaggle_cache_lock(target, lock_root=lock_root):
            entered.set()
        finished.set()

    with kaggle_cache_lock(target, lock_root=lock_root):
        thread = threading.Thread(target=second_writer)
        thread.start()
        assert not entered.wait(0.1)
    assert entered.wait(1.0)
    assert finished.wait(1.0)
    thread.join()


def test_job_and_cache_locks_on_one_target_can_nest(tmp_path: Path) -> None:
    target = tmp_path / "cache.jsonl"
    lock_root = tmp_path / "locks"

    with (
        kaggle_job_lock(target, lock_root=lock_root),
        kaggle_cache_lock(target, lock_root=lock_root),
    ):
        kinds = sorted(path.name.rsplit(".", 2)[-2] for path in lock_root.iterdir())

    assert kinds == ["cache", "job"]


def test_account_lock_uses_one_file_per_account(tmp_path: Path) -> None:
    lock_root = tmp_path / "locks"

    with kaggle_account_lock("acc2", lock_root=lock_root) as profile:
        assert profile == "acc2"
        assert (lock_root / "kaggle-accounts" / "acc2.lock").is_file()


def test_two_jobs_cannot_hold_the_same_account(tmp_path: Path) -> None:
    lock_root = tmp_path / "locks"
    entered = threading.Event()
    release = threading.Event()

    def first_job() -> None:
        with kaggle_account_lock("acc3", lock_root=lock_root):
            entered.set()
            release.wait(2)

    thread = threading.Thread(target=first_job)
    thread.start()
    assert entered.wait(2)
    try:
        with (
            pytest.raises(KaggleAccountBusy, match="acc3"),
            kaggle_account_lock("acc3", lock_root=lock_root),
        ):
            raise AssertionError("a held account must not be entered")
        with kaggle_account_lock("acc1", lock_root=lock_root):
            pass
    finally:
        release.set()
        thread.join()

    with kaggle_account_lock("acc3", lock_root=lock_root):
        pass


@pytest.mark.parametrize("profile", ["auto", "../acc1", "acc0", ""])
def test_account_lock_rejects_names_that_are_not_profiles(
    profile: str, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="invalid Kaggle account profile"):
        kaggle_account_lock(profile, lock_root=tmp_path)


def test_waiting_for_an_account_takes_it_once_the_other_job_lets_go(tmp_path):
    lock_root = tmp_path / "locks"
    other = kaggle_account_lock("acc1", lock_root=lock_root)
    other.__enter__()
    waits: list[float] = []

    def let_go(seconds: float) -> None:
        waits.append(seconds)
        other.__exit__(None, None, None)

    with wait_for_kaggle_account(
        "acc1", lock_root=lock_root, wait=let_go, log=lambda _line: None
    ) as profile:
        assert profile == "acc1"
        with pytest.raises(KaggleAccountBusy):
            kaggle_account_lock("acc1", lock_root=lock_root).__enter__()

    assert waits == [ACCOUNT_POLL_SECONDS]
    with kaggle_account_lock("acc1", lock_root=lock_root):
        pass


def test_an_error_inside_the_held_account_is_not_mistaken_for_a_busy_lock(tmp_path):
    waits: list[float] = []

    with (
        pytest.raises(KaggleAccountBusy),
        wait_for_kaggle_account(
            "acc2", lock_root=tmp_path / "locks", wait=waits.append, log=print
        ),
    ):
        raise KaggleAccountBusy("acc9")

    assert waits == []
