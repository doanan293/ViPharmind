from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pharma_lab.cli.runtime import (
    CommandResult,
    CommandStatus,
    run_handler,
    state_from_context,
)
from pharma_lab.config.defaults import DEFAULT_TOP_K
from pharma_lab.config.paths import DATA_DIR, run_dir
from pharma_lab.evaluation.config_selection import (
    ConfigReport,
    select_config,
    selection_details,
)
from pharma_lab.evaluation.metrics_service import MetricsRequest, run_metrics
from pharma_lab.evaluation.run_workspace import (
    load_run_record,
    resolve_evaluation_reference,
)

metrics_app = typer.Typer(add_completion=False, invoke_without_command=True)


@metrics_app.callback()
def metrics(
    ctx: typer.Context,
    run: Annotated[str | None, typer.Option("--run")] = None,
    top_k: Annotated[int, typer.Option("--top-k")] = DEFAULT_TOP_K,
    model: Annotated[str | None, typer.Option("--model")] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
    gold_only: Annotated[
        bool,
        typer.Option(
            "--gold-only",
            help="Score by gold sections only, without relevance judgments "
            "(reports top<k>-gold); required for a rechunked run",
        ),
    ] = False,
) -> None:
    """Write metrics reports for a run; `select` applies the selection rule."""
    if ctx.invoked_subcommand is not None:
        return
    if run is None:
        raise typer.BadParameter(
            "required unless a subcommand is given", param_hint="'--run'"
        )
    request = MetricsRequest(run_dir(run), top_k, model, force, gold_only)
    run_handler(state_from_context(ctx), lambda: _run(request))


def _run(request: MetricsRequest) -> CommandResult:
    result = run_metrics(request)
    return CommandResult(
        "metrics",
        CommandStatus.COMPLETE,
        result.baseline.artifact_dir,
        {
            "baseline": {
                "artifact": str(result.baseline.artifact_dir),
                "metrics_sha256": result.baseline.metrics_sha256,
            },
            "reranked": [
                {
                    "model": item.model,
                    "variant_sha256": item.variant_sha256,
                    "metrics_sha256": item.metrics_sha256,
                    "artifact": str(item.artifact_dir),
                }
                for item in sorted(result.reranked, key=lambda item: item.model or "")
            ],
        },
    )


def _config(value: str) -> ConfigReport:
    label, sep, target = value.partition("=")
    if not sep or not label or not target:
        raise typer.BadParameter(
            f"{value!r} is not LABEL=RUN[@MODEL]", param_hint="'--config'"
        )
    run, _, model = target.partition("@")
    return ConfigReport(label, run_dir(run), model or None)


def run_evaluation_path(run_root: Path) -> Path:
    """The gold evaluation file a retrieval run was built on."""
    record = load_run_record(run_root / "run.json")
    return resolve_evaluation_reference(record.identity.evaluation_path, DATA_DIR)


@metrics_app.command("select")
def select(
    ctx: typer.Context,
    configs: Annotated[
        list[str],
        typer.Option(
            "--config",
            help="LABEL=RUN[@MODEL], repeated, cheapest first; no MODEL = no reranker",
        ),
    ],
    metric: Annotated[str, typer.Option("--metric", help="Primary metric")],
    secondary: Annotated[str, typer.Option("--secondary", help="Secondary metric")],
    top_k: Annotated[int, typer.Option("--top-k")] = DEFAULT_TOP_K,
    exclude_groups: Annotated[
        list[str] | None,
        typer.Option("--exclude-group", help="eval_group left out of the decision"),
    ] = None,
) -> None:
    """Apply the agent's retrieval selection rule (spec v2 §3.4) to the configurations."""
    reports = [_config(value) for value in configs]

    def handler() -> CommandResult:
        selection = select_config(
            reports,
            primary=metric,
            secondary=secondary,
            top_k=top_k,
            evaluation_path=run_evaluation_path(reports[0].run_root),
            exclude_groups=tuple(exclude_groups or ()),
        )
        return CommandResult(
            "metrics select",
            CommandStatus.COMPLETE,
            reports[-1].run_root,
            selection_details(selection),
        )

    run_handler(state_from_context(ctx), handler)
