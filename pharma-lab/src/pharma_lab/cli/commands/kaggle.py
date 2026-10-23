"""`pharma-lab kaggle status`: what is running on Kaggle across every step and account."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from pharma_lab.cli.runtime import (
    CommandResult,
    CommandStatus,
    run_handler,
    state_from_context,
)
from pharma_lab.config.paths import WORK_DIR
from pharma_lab.integrations.kaggle.api import dataset_list_mine_command
from pharma_lab.integrations.kaggle.job_registry import JobRegistry, ShardRecord
from pharma_lab.integrations.kaggle.parsers import parse_dataset_references
from pharma_lab.integrations.kaggle.quota import read_account_quota
from pharma_lab.integrations.kaggle.service import (
    KaggleExecutionContext,
    resolve_session_contexts,
)

CREDENTIAL_PREFIX = "pipeline-cred-"
LISTING_PAGES = 3

kaggle_app = typer.Typer(
    add_completion=False, no_args_is_help=True, help="Kaggle accounts and kernels."
)


def registry_paths(work_dir: Path) -> list[Path]:
    """The shard registries of every step (e2e, rerank, corpus and query embedding)."""
    return sorted(
        [
            *work_dir.glob("e2e-kaggle/*/jobs.json"),
            *work_dir.glob("kaggle-*/*/jobs.json"),
        ]
    )


def live_shards(work_dir: Path) -> list[ShardRecord]:
    return [
        record
        for path in registry_paths(work_dir)
        for record in JobRegistry(path).live()
    ]


def _age(record: ShardRecord, now: datetime) -> str:
    minutes = int(
        (now - datetime.fromisoformat(record.submitted_at)).total_seconds() / 60
    )
    return f"{minutes // 60}h{minutes % 60:02d}m"


def _quota_line(context: KaggleExecutionContext) -> str:
    try:
        quota = read_account_quota(context)
    except (OSError, RuntimeError, ValueError) as error:
        return f"unavailable: {error}"
    refresh = quota.refresh_at.isoformat() if quota.refresh_at else "unknown"
    return f"{quota.remaining_hours:.2f}h of {quota.total_hours:.2f}h, resets {refresh}"


def credential_datasets(context: KaggleExecutionContext) -> list[str]:
    """This account's datasets named like a run's credential dataset."""
    found: set[str] = set()
    for page in range(1, LISTING_PAGES + 1):
        output = context.runner.run(
            dataset_list_mine_command(CREDENTIAL_PREFIX, page=page),
            capture_output=True,
        )
        references = parse_dataset_references(output)
        if not references:
            break
        found.update(
            ref
            for ref in references
            if ref.partition("/")[2].startswith(CREDENTIAL_PREFIX)
        )
    return sorted(found)


@kaggle_app.command("status")
def status(
    ctx: typer.Context,
    kaggle_account: Annotated[
        str | None,
        typer.Option("--kaggle-account", help="auto (default), accN or acc1,acc3"),
    ] = None,
) -> None:
    """Live kernels by step and account, GPU quota, and credential datasets left behind."""

    def handler() -> CommandResult:
        now = datetime.now(UTC)
        details: dict[str, object] = {}
        groups: dict[tuple[str, str], list[ShardRecord]] = defaultdict(list)
        for record in live_shards(WORK_DIR):
            groups[(record.stage, record.profile)].append(record)
        for (stage, profile), records in sorted(groups.items()):
            units = sum(len(record.unit_keys) for record in records)
            oldest = max(_age(record, now) for record in records)
            details[f"live.{stage}.{profile}"] = (
                f"{len(records)} kernels, {units} units, oldest {oldest}"
            )
        if not groups:
            details["live"] = "none"
        leftovers: list[str] = []
        for context in resolve_session_contexts(kaggle_account or "auto"):
            if context.profile is None:
                continue
            name = context.profile.name
            details[f"quota.{name}"] = _quota_line(context)
            try:
                leftovers += credential_datasets(context)
            except (OSError, RuntimeError, ValueError) as error:
                details[f"credential_check.{name}"] = f"unavailable: {error}"
        details["credential_datasets"] = leftovers
        if leftovers:
            details["delete_hint"] = (
                "; ".join(f"kaggle datasets delete {ref}" for ref in leftovers)
                + " (not while a run that uses them is still going)"
            )
        return CommandResult("kaggle status", CommandStatus.COMPLETE, None, details)

    run_handler(state_from_context(ctx), handler)
