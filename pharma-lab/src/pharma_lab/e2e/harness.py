"""Resumable, concurrent E2E run over the golden set (spec §6.3)."""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from pharma_agent.infrastructure.composition import build_application
from pharma_agent.infrastructure.settings import Settings

from pharma_lab.e2e.configs import (
    E2EConfig,
    config_label,
    graph_for,
    parse_pipeline_options,
    pipeline_for,
    settings_for,
    uses_retrieval,
)
from pharma_lab.e2e.executor import BackendTurnExecutor, ClosedBookExecutor
from pharma_lab.e2e.golden import Category, GoldenItem, load_golden
from pharma_lab.e2e.golden_changes import SUPERSEDED, reconcile_golden
from pharma_lab.e2e.records import (
    ANSWERS_FILE,
    AnswerRecord,
    DecisionRecord,
    JsonlStore,
)
from pharma_lab.e2e.run_identity import (
    RUN_FILE,
    git_commit,
    identity_from_settings,
    open_run,
)
from pharma_lab.evaluation.artifact_contracts import sha256_file, write_json
from pharma_lab.evaluation.backend_retrieval import current_release_id

NO_RELEASE = "none"


class TurnExecutor(Protocol):
    async def execute(self, item: GoldenItem) -> AnswerRecord: ...


@dataclass(frozen=True)
class RunSummary:
    total: int
    ran: int
    errors: int


class DecisionVersionGuard:
    """Keeps the decision model's version in run.json and refuses a different one.

    The hosted model alias moves; answers from two versions must not share a run."""

    def __init__(self, directory: Path) -> None:
        self._path = Path(directory) / RUN_FILE

    def _stored(self) -> dict[str, object]:
        if not self._path.is_file():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def observe(self, decisions: Sequence[DecisionRecord]) -> None:
        for decision in decisions:
            stored = self._stored()
            known = stored.get("decision_model_version")
            if known is None:
                write_json(
                    self._path, {**stored, "decision_model_version": decision.model}
                )
            elif known != decision.model:
                raise ValueError(
                    f"decision model version changed from {known} to {decision.model}; "
                    "start a new --run"
                )


async def run_items(
    items: Sequence[GoldenItem],
    executor: TurnExecutor,
    store: JsonlStore[AnswerRecord],
    *,
    config: str,
    concurrency: int,
    retry_errors: bool,
    decision_guard: DecisionVersionGuard | None = None,
) -> RunSummary:
    """Answer every item without a final record; errors rerun only on request.

    Answers superseded by a revised golden item always run again.
    """
    if concurrency < 1:
        raise ValueError("--concurrency must be >= 1")
    latest = store.latest()
    pending = [
        item
        for item in items
        if item.item_id not in latest
        or latest[item.item_id].status == SUPERSEDED
        or (retry_errors and latest[item.item_id].retryable)
    ]
    semaphore = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    stopped: list[ValueError] = []

    async def answer(item: GoldenItem) -> None:
        async with semaphore:
            if stopped:
                return
            try:
                record = await executor.execute(item)
            except Exception as error:  # a failed item must not stop the run
                record = AnswerRecord.failed(item.item_id, config, error)
        async with lock:
            if decision_guard is not None:
                try:
                    decision_guard.observe(record.decisions)
                except ValueError as error:
                    stopped.append(error)
                    return
            store.append(record)

    await asyncio.gather(*(answer(item) for item in pending))
    if stopped:
        raise stopped[0]
    final = store.latest()
    errors = sum(
        1 for item in items if item.item_id in final and final[item.item_id].retryable
    )
    return RunSummary(total=len(items), ran=len(pending), errors=errors)


def spread(items: Sequence[GoldenItem], limit: int | None) -> list[GoldenItem]:
    """`limit` items taken evenly across the (id-sorted) golden set."""
    if limit is None or limit >= len(items):
        return list(items)
    if limit < 1:
        raise ValueError("--limit must be >= 1")
    step = math.ceil(len(items) / limit)
    return list(items[::step])[:limit]


@dataclass(frozen=True)
class E2ERunRequest:
    run_root: Path
    config: E2EConfig
    golden_path: Path
    backend_env_file: Path
    concurrency: int = 8
    retry_errors: bool = False
    limit: int | None = None
    # Evaluation may wait longer than the production turn deadline; recorded in run.json.
    deadline_seconds: float | None = None
    # key=value overrides of the configuration's PipelineOptions (--pipeline-option).
    pipeline_options: tuple[str, ...] = ()


def with_deadline(settings: Settings, seconds: float | None) -> Settings:
    if seconds is None:
        return settings
    if seconds <= 0:
        raise ValueError("--deadline-seconds must be positive")
    budget = settings.budget.model_copy(update={"deadline_seconds": seconds})
    return settings.model_copy(update={"budget": budget})


def config_dir(run_root: Path, config: E2EConfig | str) -> Path:
    return Path(run_root) / str(config)


def run_e2e(request: E2ERunRequest) -> RunSummary:
    golden = load_golden(request.golden_path)
    items = spread(golden, request.limit)
    settings = settings_for(
        Settings(_env_file=request.backend_env_file), request.config
    )
    settings = with_deadline(settings, request.deadline_seconds)
    pipeline = parse_pipeline_options(
        pipeline_for(request.config), request.pipeline_options
    )
    label = config_label(request.config, request.pipeline_options)
    directory = config_dir(request.run_root, label)
    reconcile_golden(directory, request.golden_path, golden)
    probe = next(
        item.question for item in items if item.category is Category.ANSWERABLE
    )
    app = build_application(settings)
    with asyncio.Runner() as runner:
        try:
            # The closed-book baseline reads no corpus, so it has no release.
            release_id = (
                runner.run(current_release_id(app.retrieval.service, probe))
                if uses_retrieval(request.config)
                else NO_RELEASE
            )
            open_run(
                directory,
                identity_from_settings(
                    settings,
                    golden_sha256=sha256_file(request.golden_path),
                    config=label,
                    pipeline=asdict(pipeline),
                    release_id=release_id,
                ),
                commit=git_commit(Path(__file__).resolve().parent),
                extra={"concurrency": request.concurrency},
            )
            executor: TurnExecutor = (
                BackendTurnExecutor(
                    graph=graph_for(request.config),
                    llm=app.deps.llm,
                    retrieval=app.retrieval.service,
                    limits=settings.budget,
                    pipeline=pipeline,
                    config=label,
                    decisions=app.deps.decisions,
                    guard_thresholds=app.deps.guardrail.thresholds,
                )
                if uses_retrieval(request.config)
                else ClosedBookExecutor(llm=app.deps.llm, config=label)
            )
            return runner.run(
                run_items(
                    items,
                    executor,
                    JsonlStore(directory / ANSWERS_FILE, AnswerRecord),
                    config=label,
                    concurrency=request.concurrency,
                    retry_errors=request.retry_errors,
                    decision_guard=DecisionVersionGuard(directory),
                )
            )
        finally:
            runner.run(app.aclose())
