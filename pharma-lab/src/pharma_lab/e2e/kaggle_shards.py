"""The e2e step as shards for the Kaggle scheduler.

The unit of work is a pair (configuration label, golden item). What is missing is read
from the local `answers.jsonl` files; a shard becomes one `e2e_job.json` for one Kaggle
kernel; whatever a kernel returns, even half of it, is merged into the local run. Nothing
here keeps state of its own, so every command recomputes the plan from the run directory.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from pharma_lab.e2e.configs import E2EConfig, config_label
from pharma_lab.e2e.golden import Category, GoldenItem
from pharma_lab.e2e.golden_changes import reconcile_golden
from pharma_lab.e2e.llm_presets import LlmPreset
from pharma_lab.e2e.records import ANSWERS_FILE, AnswerRecord
from pharma_lab.e2e.run_identity import RUN_FILE
from pharma_lab.e2e.work_state import (
    WorkReport,
    merge_shard,
    missing_pairs,
    select_universe,
)
from pharma_lab.integrations.kaggle.artifacts import sha256_file
from pharma_lab.integrations.kaggle.e2e_stage import (
    CREDENTIALS_FILE,
    E2E_MODELS,
    JOB_FILE,
    META_FILE,
)
from pharma_lab.integrations.kaggle.job_registry import ShardRecord
from pharma_lab.integrations.kaggle.models import (
    CloudArtifact,
    PipelineResult,
    StageJob,
    StageName,
)
from pharma_lab.integrations.kaggle.sessions import ReservedAccount
from pharma_lab.integrations.kaggle.shards import Shard, WorkUnit
from pharma_lab.runtime.runtime_profiles import RuntimeCandidate

SEPARATOR = "\x1f"
LAYOUT_A = "A"
# Qwen3.5-9B answers a turn in about this long at concurrency 1 (measured, v1 runs).
DEFAULT_TURN_SECONDS = 60.0
# Postgres, Qdrant, the venv, three models and the corpus import (spec 4.3).
SETUP_SECONDS = 1800.0
DEFAULT_CONCURRENCY = 8
LATENCY_SUFFIX = "-c1"

StageRunner = Callable[..., PipelineResult]
RerankerProfile = Callable[[str], RuntimeCandidate]
StaticBuilder = Callable[[Path], None]


@dataclass(frozen=True)
class Entry:
    """A configuration with its pipeline options, answered into one label directory."""

    config: E2EConfig
    pipeline_options: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return config_label(self.config, self.pipeline_options)


@dataclass(frozen=True)
class E2EPlan:
    run_name: str
    entries: tuple[Entry, ...]
    golden_path: Path
    categories: tuple[Category, ...] | None
    limit: int | None
    llm: LlmPreset
    concurrency: int = DEFAULT_CONCURRENCY
    deadline_seconds: float = 900.0
    retry_stuck: bool = False
    latency: bool = False

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(entry.label for entry in self.entries)


def make_plan(
    *,
    run_name: str,
    entries: Sequence[Entry],
    golden_path: Path,
    categories: Sequence[Category] | None,
    limit: int | None,
    llm: LlmPreset,
    concurrency: int = DEFAULT_CONCURRENCY,
    deadline_seconds: float = 900.0,
    retry_stuck: bool = False,
    latency: bool = False,
    parallel: int = 1,
) -> E2EPlan:
    """Validate a request. A latency run is one shard, concurrency 1, layout A, written
    to `<run>-c1`: several shards or several configurations would make it meaningless."""
    if not entries:
        raise ValueError("an e2e run needs at least one configuration")
    if latency:
        if parallel > 1:
            raise ValueError("--latency measures in one kernel: use --parallel 1")
        if len(entries) > 1:
            raise ValueError(
                "--latency measures one configuration per run; "
                f"got {len(entries)}: run them one after another"
            )
        run_name, concurrency = f"{run_name}{LATENCY_SUFFIX}", 1
    if llm.max_in_flight is not None:
        concurrency = min(concurrency, llm.max_in_flight)
    return E2EPlan(
        run_name,
        tuple(entries),
        golden_path,
        None if categories is None else tuple(categories),
        limit,
        llm,
        concurrency,
        deadline_seconds,
        retry_stuck,
        latency,
    )


def turn_estimates(
    run_root: Path, labels: Sequence[str], universe: Sequence[GoldenItem]
) -> dict[tuple[str, Category], float]:
    """Mean seconds of a finished turn per (label, category), from the answers on disk."""
    category = {item.item_id: item.category for item in universe}
    totals: dict[tuple[str, Category], list[float]] = defaultdict(list)
    for label in labels:
        path = run_root / label / ANSWERS_FILE
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = AnswerRecord.model_validate_json(line)
            except (ValidationError, ValueError):
                continue
            if (
                record.status != "error"
                and record.latency_seconds > 0
                and record.item_id in category
            ):
                totals[(label, category[record.item_id])].append(record.latency_seconds)
    return {key: sum(values) / len(values) for key, values in totals.items()}


class CredentialSource(Protocol):
    """The staged proxy credentials of a run (see `proxy_credentials.CredentialDataset`)."""

    fingerprint: str

    @property
    def stage_dir(self) -> Path: ...

    def slug(self, profile: str) -> str: ...

    def used(self, profile: str, reference: str) -> None: ...


class E2EShardAdapter:
    stage = "e2e-run"

    def __init__(
        self,
        plan: E2EPlan,
        *,
        golden: Sequence[GoldenItem],
        run_root: Path,
        work_dir: Path,
        stage_runner: StageRunner,
        reranker_profile: RerankerProfile,
        build_static: StaticBuilder,
        commit: str | None = None,
        log: Callable[[str], None] = print,
        credentials: CredentialSource | None = None,
        on_merged: Callable[[Sequence[str]], None] | None = None,
    ) -> None:
        self.plan = plan
        self.run_root = run_root
        self.work_dir = work_dir
        self._golden = list(golden)
        self._static_lock = threading.Lock()
        self._reconciled = False
        self._universe = select_universe(
            golden, categories=plan.categories, limit=plan.limit
        )
        self._order = {item.item_id: index for index, item in enumerate(self._universe)}
        self._entries = {entry.label: entry for entry in plan.entries}
        self._stage_runner = stage_runner
        self._reranker_profile = reranker_profile
        self._build_static = build_static
        self._commit = commit
        self._credentials = credentials
        self._on_merged = on_merged
        self._log = log
        self._attach: set[str] = set()

    @property
    def universe(self) -> Sequence[GoldenItem]:
        return self._universe

    def report(self) -> WorkReport:
        return missing_pairs(
            self.run_root,
            self.plan.labels,
            self._universe,
            retry_stuck=self.plan.retry_stuck,
        )

    def _reconcile_golden(self) -> None:
        """Mark answers of revised golden items superseded, as the local harness does,
        so they are answered again instead of staying done under the old question."""
        if self._reconciled:
            return
        self._reconciled = True
        if not self.plan.golden_path.is_file():
            return
        for label in self.plan.labels:
            directory = self.run_root / label
            if (directory / RUN_FILE).is_file():
                reconcile_golden(directory, self.plan.golden_path, self._golden)

    def missing(self) -> Sequence[WorkUnit]:
        self._reconcile_golden()
        estimates = turn_estimates(self.run_root, self.plan.labels, self._universe)
        category = {item.item_id: item.category for item in self._universe}
        return [
            WorkUnit(
                f"{pair.label}{SEPARATOR}{pair.item_id}",
                # The kernel answers `concurrency` turns at once.
                estimates.get(
                    (pair.label, category[pair.item_id]), DEFAULT_TURN_SECONDS
                )
                / self.plan.concurrency,
                LAYOUT_A,
            )
            for pair in self.report().missing
        ]

    def setup_seconds(self) -> float:
        return SETUP_SECONDS

    def preferred_profile(self, shard: Shard, record: ShardRecord | None) -> str | None:
        if record is None:
            return None
        self._attach.add(shard.shard_id)
        return record.profile

    def run_shard(self, shard: Shard, reserved: ReservedAccount) -> PipelineResult:
        directory = self.work_dir / shard.shard_id
        job_path = self._write_job(shard, directory)
        self._write_credentials(directory, reserved)

        def sink(_job: StageJob, artifact: CloudArtifact) -> None:
            self._merge(shard, artifact.data_path)

        return self._stage_runner(
            stage=StageName.E2E_RUN,
            model=E2E_MODELS.llm,
            input_path=job_path,
            output_dir=directory / "kernels",
            max_runs=1,
            budget_seconds=reserved.budget_seconds,
            runtime_profile=self._reranker_profile(reserved.profile),
            kaggle_account=reserved.profile,
            # A relaunched shard attaches to its running kernel; a new one starts clean.
            resume_remote=shard.shard_id in self._attach,
            artifact_sink=sink,
        )

    def merge(self, shard: Shard, result: PipelineResult) -> int:
        if result.artifact_path is not None:
            self._merge(shard, result.artifact_path)
        # Units that now have a final answer, not lines appended: an error line is
        # not progress, and a shard that only errors must count as having done nothing.
        still = {unit.key for unit in self.missing()}
        return sum(1 for unit in shard.units if unit.key not in still)

    def _merge(self, shard: Shard, archive: Path) -> None:
        labels = sorted(
            {
                *self.plan.labels,
                *(unit.key.partition(SEPARATOR)[0] for unit in shard.units),
            }
        )
        report = merge_shard(archive, self.run_root, labels)
        for warning in report.warnings:
            self._log(f"warning: {warning}")
        if report.appended and self._on_merged is not None:
            labels = sorted({unit.key.partition(SEPARATOR)[0] for unit in shard.units})
            self._on_merged(labels)

    def _write_credentials(self, directory: Path, reserved: ReservedAccount) -> None:
        """Tell the stage where the credentials are staged and which dataset carries them.

        Recorded as used before anything is uploaded, so the command deletes the
        dataset even if it dies between the upload and the end of the shard."""
        if self._credentials is None:
            (directory / CREDENTIALS_FILE).unlink(missing_ok=True)
            return
        slug = self._credentials.slug(reserved.profile)
        owner = reserved.context.owners.execution
        self._credentials.used(reserved.profile, f"{owner}/{slug}")
        (directory / CREDENTIALS_FILE).write_text(
            json.dumps(
                {
                    "local_dir": str(self._credentials.stage_dir),
                    "slug": slug,
                    "sha256": self._credentials.fingerprint,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _static_inputs(self) -> Path:
        """The inputs every shard shares, built whole once per golden set.

        Built beside the final name and moved into place, so a shard that starts while
        another is building waits for the lock and a crash leaves no half-built tree."""
        golden = self.plan.golden_path
        key = sha256_file(golden)[:16] if golden.is_file() else "none"
        static = self.work_dir / f"static-{key}"
        with self._static_lock:
            if not (static / COMPLETE_MARK).is_file():
                partial = self.work_dir / f".static-{key}.partial"
                shutil.rmtree(partial, ignore_errors=True)
                shutil.rmtree(static, ignore_errors=True)
                self._build_static(partial)
                (partial / COMPLETE_MARK).write_text("ok\n", encoding="utf-8")
                os.replace(partial, static)
        return static

    def _entry_for(self, label: str) -> Entry:
        """The plan's entry, or one read back from a label a relaunched shard carries
        (the command was narrowed since the shard was cut)."""
        if label in self._entries:
            return self._entries[label]
        config, *options = label.split("+")
        return Entry(E2EConfig(config), tuple(options))

    def _write_job(self, shard: Shard, directory: Path) -> Path:
        static = self._static_inputs()
        directory.mkdir(parents=True, exist_ok=True)
        link_tree(static, directory)
        by_label: dict[str, list[str]] = defaultdict(list)
        for unit in shard.units:
            label, _, item_id = unit.key.partition(SEPARATOR)
            by_label[label].append(item_id)
        entries = [
            {
                "config": self._entry_for(label).config.value,
                "pipeline_options": list(self._entry_for(label).pipeline_options),
                "item_ids": sorted(
                    ids,
                    key=lambda item_id: (
                        self._order.get(item_id, len(self._order)),
                        item_id,
                    ),
                ),
            }
            for label, ids in sorted(by_label.items())
        ]
        job = {
            "run": self.plan.run_name,
            "llm": self.plan.llm.name,
            "layout": LAYOUT_A,
            "concurrency": self.plan.concurrency,
            "shards": entries,
            "deadline_seconds": self.plan.deadline_seconds,
        }
        path = directory / JOB_FILE
        path.write_text(
            json.dumps(job, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        # Beside the job, not in it: a commit must not rename the kernel of a shard.
        (directory / META_FILE).write_text(
            json.dumps({"commit": self._commit}) + "\n", encoding="utf-8"
        )
        return path


COMPLETE_MARK = ".complete"


def link_tree(source: Path, target: Path) -> None:
    """Mirror `source` under `target` with hard links (copies across filesystems)."""
    for path in sorted(source.rglob("*")):
        if path.name == COMPLETE_MARK:
            continue
        destination = target / path.relative_to(source)
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(path, destination)
            except OSError:
                shutil.copy2(path, destination)


def check_no_decision_roles(env_file: Path) -> None:
    """A kernel cannot reach the local decision model; refuse instead of answering with
    a different one."""
    from pharma_agent.domain.llm.models import LlmRole
    from pharma_agent.infrastructure.settings import LlmEndpoint, Settings

    # Read the declared providers, not `resolve()`: an env file may configure no LLM.
    llm = Settings(_env_file=env_file).llm
    roles = [
        role
        for role in LlmRole
        if ((llm.roles.get(role) or LlmEndpoint()).provider or llm.default.provider)
        == "systemone"
    ]
    if roles:
        names = ", ".join(sorted(role.value for role in roles))
        raise ValueError(
            f"{env_file} sends {names} to the decision model (provider systemone), "
            "which a Kaggle kernel cannot reach yet; run with --backend local"
        )
