from __future__ import annotations

import threading
from pathlib import Path

import pytest

from pharma_lab.e2e.judge_follower import JudgeFollower
from pharma_lab.e2e.judging.service import JudgeRequest, JudgeSummary


def request_for(root: Path):
    def factory(label: str) -> JudgeRequest:
        return JudgeRequest(
            run_root=root,
            config=label,
            golden_path=root / "golden.jsonl",
            backend_env_file=root / ".env",
        )

    return factory


class Judge:
    """Stands in for `run_judge`: records the labels it is asked about."""

    def __init__(self) -> None:
        self.labels: list[str] = []
        self.lock = threading.Lock()

    def __call__(self, request: JudgeRequest) -> JudgeSummary:
        with self.lock:
            self.labels.append(request.config)
        return JudgeSummary(total=3, judged=3, errors=0)


def test_judges_only_labels_that_returned_answers(tmp_path: Path) -> None:
    judge = Judge()
    follower = JudgeFollower(judge, log=lambda _line: None)
    follower.start(request_for(tmp_path))

    follower.notify_merged(["full"])
    follower.notify_merged(["full", "one-step"])
    follower.stop()

    assert sorted(set(judge.labels)) == ["full", "one-step"]
    assert judge.labels.count("one-step") == 1


def test_a_label_with_no_new_answers_is_not_judged(tmp_path: Path) -> None:
    judge = Judge()
    follower = JudgeFollower(judge, log=lambda _line: None)
    follower.start(request_for(tmp_path))

    follower.stop()

    assert judge.labels == []


def test_judge_error_does_not_stop_merging(tmp_path: Path) -> None:
    said: list[str] = []
    calls: list[str] = []

    def failing(request: JudgeRequest) -> JudgeSummary:
        calls.append(request.config)
        if request.config == "full":
            raise RuntimeError("judge endpoint is down")
        return JudgeSummary(1, 1, 0)

    follower = JudgeFollower(failing, log=said.append)
    follower.start(request_for(tmp_path))

    follower.notify_merged(["full"])  # must not raise into the merging thread
    follower.notify_merged(["other"])
    follower.stop()

    assert sorted(calls) == ["full", "other"]
    assert any("judge endpoint is down" in line and "full" in line for line in said)


def test_stop_waits_for_the_running_judge(tmp_path: Path) -> None:
    started, release = threading.Event(), threading.Event()
    finished: list[str] = []

    def slow(request: JudgeRequest) -> JudgeSummary:
        started.set()
        release.wait(timeout=5)
        finished.append(request.config)
        return JudgeSummary(1, 1, 0)

    follower = JudgeFollower(slow, log=lambda _line: None)
    follower.start(request_for(tmp_path))
    follower.notify_merged(["full"])
    assert started.wait(timeout=5)

    stopper = threading.Thread(target=follower.stop)
    stopper.start()
    stopper.join(timeout=0.2)
    assert stopper.is_alive()  # still waiting for the judge
    release.set()
    stopper.join(timeout=5)

    assert finished == ["full"]
    assert not stopper.is_alive()


def test_stop_without_drain_skips_what_is_still_queued(tmp_path: Path) -> None:
    started, release = threading.Event(), threading.Event()
    seen: list[str] = []

    def slow(request: JudgeRequest) -> JudgeSummary:
        seen.append(request.config)
        started.set()
        release.wait(timeout=5)
        return JudgeSummary(1, 1, 0)

    follower = JudgeFollower(slow, log=lambda _line: None)
    follower.start(request_for(tmp_path))
    follower.notify_merged(["first"])
    assert started.wait(timeout=5)
    follower.notify_merged(["second"])  # queued behind the running one

    stopper = threading.Thread(target=lambda: follower.stop(drain=False))
    stopper.start()
    release.set()
    stopper.join(timeout=5)

    assert seen == ["first"]


def test_notify_before_start_is_refused(tmp_path: Path) -> None:
    follower = JudgeFollower(Judge(), log=lambda _line: None)

    with pytest.raises(RuntimeError, match="start"):
        follower.notify_merged(["full"])
