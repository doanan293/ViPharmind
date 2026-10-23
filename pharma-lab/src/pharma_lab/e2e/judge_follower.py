"""Judge answers while the shards that produce them are still coming back.

Judging goes through the local judge endpoint, so it costs no GPU quota. `notify_merged`
only marks configurations as having new answers; one background thread judges them, and
`run_judge` itself continues per item, so it only does what is still unjudged. A judge
error is logged and never reaches the thread that merges answers.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable

from pharma_lab.e2e.judging.service import JudgeRequest, JudgeSummary

RequestFactory = Callable[[str], JudgeRequest]


class JudgeFollower:
    def __init__(
        self,
        run_judge: Callable[[JudgeRequest], JudgeSummary],
        *,
        log: Callable[[str], None] = print,
    ) -> None:
        self._run_judge = run_judge
        self._log = log
        self._factory: RequestFactory | None = None
        self._dirty: list[str] = []
        self._wake = threading.Condition()
        self._stopping = False
        self._drain = True
        self._thread: threading.Thread | None = None

    def start(self, request_factory: RequestFactory) -> None:
        self._factory = request_factory
        self._thread = threading.Thread(
            target=self._work, name="judge-follower", daemon=True
        )
        self._thread.start()

    def notify_merged(self, labels: Iterable[str]) -> None:
        if self._thread is None:
            raise RuntimeError("start the judge follower before notifying it")
        with self._wake:
            for label in labels:
                if label not in self._dirty:
                    self._dirty.append(label)
            self._wake.notify()

    def stop(self, *, drain: bool = True) -> None:
        """Wait for the judge that is running; with `drain` also judge what is queued."""
        with self._wake:
            self._stopping = True
            self._drain = drain
            self._wake.notify()
        if self._thread is not None:
            self._thread.join()

    def _next(self) -> str | None:
        with self._wake:
            while not self._dirty:
                if self._stopping:
                    return None
                self._wake.wait()
            if self._stopping and not self._drain:
                return None
            return self._dirty.pop(0)

    def _work(self) -> None:
        factory = self._factory
        assert factory is not None
        while (label := self._next()) is not None:
            try:
                summary = self._run_judge(factory(label))
                self._log(
                    f"judged {label}: {summary.judged} new of {summary.total} answers"
                    f", {summary.errors} errors"
                )
            except Exception as error:
                self._log(f"judging {label} failed: {type(error).__name__}: {error}")
