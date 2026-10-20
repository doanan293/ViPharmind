from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from pharma_agent.domain.corpus.bundle import read_bundle

from pharma_lab.cli.runtime import (
    CommandResult,
    CommandStatus,
    run_handler,
    state_from_context,
)
from pharma_lab.config.paths import (
    BACKEND_ENV_FILE,
    BUNDLE_DIR,
    E2E_AUTHORING_DIR,
    GOLD_DIR,
    GOLDEN_E2E_PATH,
    e2e_run_dir,
)
from pharma_lab.e2e.calibration import CONFIGS as CALIBRATION_CONFIGS
from pharma_lab.e2e.calibration import (
    export_calibration,
    refresh_calibration,
    score_calibration,
)
from pharma_lab.e2e.citation_analysis import REPORT_FILE, write_citation_report
from pharma_lab.e2e.configs import E2EConfig
from pharma_lab.e2e.corpus_text import chunk_texts, corpus_text, load_corpus_text
from pharma_lab.e2e.golden import (
    ANSWERABLE_PER_GROUP,
    QUOTAS,
    Category,
    build_golden,
    load_golden,
    manifest_path,
    read_items,
    validate_items,
)
from pharma_lab.e2e.harness import E2ERunRequest, run_e2e
from pharma_lab.e2e.judging.service import (
    JudgeRequest,
    run_citation_rejudge,
    run_judge,
)
from pharma_lab.e2e.judging.structured import JUDGE_MODEL
from pharma_lab.e2e.kaggle_run import KaggleE2ERequest, run_on_kaggle
from pharma_lab.e2e.report import write_report
from pharma_lab.e2e.sampling import (
    replacement_candidates,
    sample_answerable,
    sample_multi_turn,
    write_authoring_batches,
    write_replacement_batch,
)
from pharma_lab.evaluation.artifact_contracts import sha256_file
from pharma_lab.evaluation.backend_retrieval import load_query_rows
from pharma_lab.evaluation.relevance_judgments import judgments_path, load_judgments

GOLD_PATH = GOLD_DIR / "section_retrieval_eval.jsonl"

e2e_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="End-to-end evaluation of the agent on the golden set.",
)
golden_app = typer.Typer(
    add_completion=False, no_args_is_help=True, help="Build the golden set."
)
e2e_app.add_typer(golden_app, name="golden")
calibration_app = typer.Typer(
    add_completion=False, no_args_is_help=True, help="Blind judge calibration."
)
e2e_app.add_typer(calibration_app, name="calibration")


@golden_app.command("sample")
def golden_sample(
    ctx: typer.Context,
    evaluation: Annotated[
        Path, typer.Option("--evaluation", dir_okay=False)
    ] = GOLD_PATH,
    bundle: Annotated[Path, typer.Option("--bundle", file_okay=False)] = BUNDLE_DIR,
    output: Annotated[
        Path, typer.Option("--output", file_okay=False)
    ] = E2E_AUTHORING_DIR,
    seed: Annotated[int, typer.Option("--seed")] = 0,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Pick the gold queries to author from and write *.todo.jsonl batches."""

    def handler() -> CommandResult:
        knowledge = read_bundle(bundle)
        corpus = corpus_text(knowledge)
        rows = load_query_rows(evaluation)
        answerable = sample_answerable(
            rows, per_group=ANSWERABLE_PER_GROUP, seed=seed, corpus=corpus
        )
        pairs = sample_multi_turn(
            rows,
            count=QUOTAS[Category.MULTI_TURN],
            seed=seed,
            corpus=corpus,
            exclude={row["query_id"] for row in answerable},
        )
        sources = [*answerable, *(row for pair in pairs for row in pair)]
        sections = {
            section for row in sources for section in row["expected_section_ids"]
        }
        paths = write_authoring_batches(
            output,
            answerable,
            pairs,
            corpus,
            force=force,
            chunks=chunk_texts(knowledge, sections),
        )
        return CommandResult(
            "e2e golden sample",
            CommandStatus.COMPLETE,
            output,
            {
                "batches": len(paths),
                "answerable": len(answerable),
                "multi_turn": len(pairs),
            },
        )

    run_handler(state_from_context(ctx), handler)


@golden_app.command("resample")
def golden_resample(
    ctx: typer.Context,
    slots: Annotated[
        str, typer.Option("--slots", help="Comma-separated answerable slot ids")
    ],
    evaluation: Annotated[
        Path, typer.Option("--evaluation", dir_okay=False)
    ] = GOLD_PATH,
    bundle: Annotated[Path, typer.Option("--bundle", file_okay=False)] = BUNDLE_DIR,
    authoring: Annotated[
        Path, typer.Option("--authoring", file_okay=False)
    ] = E2E_AUTHORING_DIR,
    per_slot: Annotated[int, typer.Option("--per-slot", min=1)] = 4,
    seed: Annotated[int, typer.Option("--seed")] = 0,
) -> None:
    """Offer unused same-stratum questions for slots whose gold section is off."""

    def handler() -> CommandResult:
        wanted = {slot.strip() for slot in slots.split(",") if slot.strip()}
        todo = [
            json.loads(line)
            for path in sorted(authoring.glob("*.todo.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        used = {
            row["query_id"]
            for slot in todo
            for option in [slot, *slot.get("candidates", [])]
            for row in option.get("source_rows", [])
        }
        sources = {
            slot["slot_id"]: slot["source_rows"][0]
            for slot in todo
            if slot["slot_id"] in wanted and slot.get("source_rows")
        }
        missing = sorted(wanted - set(sources))
        if missing:
            raise ValueError(f"unknown answerable slots: {', '.join(missing)}")
        knowledge = read_bundle(bundle)
        corpus = corpus_text(knowledge)
        candidates = replacement_candidates(
            load_query_rows(evaluation),
            sources,
            used=used,
            per_slot=per_slot,
            seed=seed,
            corpus=corpus,
        )
        sections = {
            section
            for rows in candidates.values()
            for row in rows
            for section in row["expected_section_ids"]
        }
        path = write_replacement_batch(
            authoring, candidates, corpus, chunks=chunk_texts(knowledge, sections)
        )
        return CommandResult(
            "e2e golden resample",
            CommandStatus.COMPLETE,
            path,
            {"slots": len(candidates)},
        )

    run_handler(state_from_context(ctx), handler)


@golden_app.command("check")
def golden_check(
    ctx: typer.Context,
    batch: Annotated[Path, typer.Argument(dir_okay=False, exists=True)],
    bundle: Annotated[Path, typer.Option("--bundle", file_okay=False)] = BUNDLE_DIR,
) -> None:
    """Validate one authored batch without the set-wide quotas."""

    def handler() -> CommandResult:
        items, problems = read_items(batch)
        problems += validate_items(items, load_corpus_text(bundle), complete=False)
        if problems:
            raise ValueError(
                f"{batch} has {len(problems)} problem(s):\n" + "\n".join(problems)
            )
        return CommandResult(
            "e2e golden check", CommandStatus.COMPLETE, batch, {"items": len(items)}
        )

    run_handler(state_from_context(ctx), handler)


@golden_app.command("build")
def golden_build(
    ctx: typer.Context,
    sources: Annotated[
        Path, typer.Option("--sources", file_okay=False)
    ] = E2E_AUTHORING_DIR,
    output: Annotated[Path, typer.Option("--output", dir_okay=False)] = GOLDEN_E2E_PATH,
    bundle: Annotated[Path, typer.Option("--bundle", file_okay=False)] = BUNDLE_DIR,
    evaluation: Annotated[
        Path, typer.Option("--evaluation", dir_okay=False)
    ] = GOLD_PATH,
) -> None:
    """Validate authored batches (*.authored.jsonl) and freeze the golden set."""

    def handler() -> CommandResult:
        manifest = build_golden(
            sorted(sources.glob("*.authored.jsonl")),
            output,
            load_corpus_text(bundle),
            bundle_manifest_sha256=sha256_file(bundle / "manifest.json"),
            gold_sha256=sha256_file(evaluation),
        )
        return CommandResult(
            "e2e golden build",
            CommandStatus.COMPLETE,
            output,
            {"manifest": str(manifest_path(output)), **manifest.counts},
        )

    run_handler(state_from_context(ctx), handler)


class RunBackend(StrEnum):
    LOCAL = "local"
    KAGGLE = "kaggle"


@e2e_app.command("run")
def run(
    ctx: typer.Context,
    run_name: Annotated[str, typer.Option("--run")],
    config: Annotated[
        list[E2EConfig],
        typer.Option("--config", help="Repeatable with --backend kaggle"),
    ],
    golden: Annotated[Path, typer.Option("--golden", dir_okay=False)] = GOLDEN_E2E_PATH,
    limit: Annotated[
        int | None,
        typer.Option("--limit", min=1, help="Only N items spread across the set"),
    ] = None,
    category: Annotated[
        list[Category] | None,
        typer.Option(
            "--category",
            help="Only the items of this golden category; repeatable with kaggle",
        ),
    ] = None,
    concurrency: Annotated[int, typer.Option("--concurrency", min=1)] = 4,
    retry_errors: Annotated[bool, typer.Option("--retry-errors")] = False,
    deadline_seconds: Annotated[
        float | None,
        typer.Option(
            "--deadline-seconds",
            help="Turn deadline for this run instead of the backend budget",
        ),
    ] = None,
    backend_env_file: Annotated[
        Path, typer.Option("--backend-env-file", dir_okay=False)
    ] = BACKEND_ENV_FILE,
    backend: Annotated[
        RunBackend,
        typer.Option(
            "--backend",
            help="kaggle runs the Qwen setting inside one Kaggle kernel",
        ),
    ] = RunBackend.LOCAL,
    kaggle_account: Annotated[
        str | None, typer.Option("--kaggle-account", help="Default: .env account")
    ] = None,
) -> None:
    """Answer the golden set with one configuration; re-run to resume."""
    categories = list(category or [])
    if backend is RunBackend.KAGGLE:
        kaggle_request = KaggleE2ERequest(
            run_name=run_name,
            configs=tuple(config),
            categories=tuple(categories or list(Category)),
            golden_path=golden,
            kaggle_account=kaggle_account,
            deadline_seconds=deadline_seconds or 900.0,
        )

        def kaggle_handler() -> CommandResult:
            written = run_on_kaggle(kaggle_request)
            return CommandResult(
                "e2e run",
                CommandStatus.COMPLETE,
                e2e_run_dir(run_name),
                {"files": ",".join(str(path) for path in written)},
            )

        run_handler(state_from_context(ctx), kaggle_handler)
        return
    if len(config) != 1 or len(categories) > 1:
        raise typer.BadParameter(
            "a local run takes one --config and at most one --category"
        )
    request = E2ERunRequest(
        run_root=e2e_run_dir(run_name),
        config=config[0],
        golden_path=golden,
        backend_env_file=backend_env_file,
        concurrency=concurrency,
        retry_errors=retry_errors,
        limit=limit,
        category=categories[0] if categories else None,
        deadline_seconds=deadline_seconds,
    )

    def handler() -> CommandResult:
        summary = run_e2e(request)
        return CommandResult(
            "e2e run",
            CommandStatus.INCOMPLETE if summary.errors else CommandStatus.COMPLETE,
            request.run_root / str(config[0]),
            {"items": summary.total, "ran": summary.ran, "errors": summary.errors},
        )

    run_handler(state_from_context(ctx), handler)


@e2e_app.command("judge")
def judge(
    ctx: typer.Context,
    run_name: Annotated[str, typer.Option("--run")],
    config: Annotated[E2EConfig, typer.Option("--config")],
    golden: Annotated[Path, typer.Option("--golden", dir_okay=False)] = GOLDEN_E2E_PATH,
    concurrency: Annotated[int, typer.Option("--concurrency", min=1)] = 4,
    force: Annotated[
        bool, typer.Option("--force", help="Judge every answer again")
    ] = False,
    judge_model: Annotated[
        str,
        typer.Option("--judge-model", help="Model name on the backend LLM endpoint"),
    ] = JUDGE_MODEL,
    items: Annotated[
        str,
        typer.Option("--items", help="Comma-separated item ids to judge again"),
    ] = "",
    category: Annotated[
        Category | None,
        typer.Option("--category", help="Only the items of one golden category"),
    ] = None,
    backend_env_file: Annotated[
        Path, typer.Option("--backend-env-file", dir_okay=False)
    ] = BACKEND_ENV_FILE,
) -> None:
    """Score one configuration's answers with RAGAS and the structured judges."""
    request = JudgeRequest(
        run_root=e2e_run_dir(run_name),
        config=config,
        golden_path=golden,
        backend_env_file=backend_env_file,
        concurrency=concurrency,
        force=force,
        judge_model=judge_model,
        only=frozenset(key.strip() for key in items.split(",") if key.strip()),
        category=category,
    )

    def handler() -> CommandResult:
        summary = run_judge(request)
        return CommandResult(
            "e2e judge",
            CommandStatus.INCOMPLETE if summary.errors else CommandStatus.COMPLETE,
            request.run_root / str(config),
            {
                "answers": summary.total,
                "judged": summary.judged,
                "errors": summary.errors,
            },
        )

    run_handler(state_from_context(ctx), handler)


@calibration_app.command("export")
def calibration_export(
    ctx: typer.Context,
    run_name: Annotated[str, typer.Option("--run")],
    golden: Annotated[Path, typer.Option("--golden", dir_okay=False)] = GOLDEN_E2E_PATH,
    seed: Annotated[int, typer.Option("--seed")] = 0,
    configs: Annotated[
        list[E2EConfig] | None,
        typer.Option("--config", help="Repeat to choose configurations"),
    ] = None,
) -> None:
    """Write 50 blind items per configuration (default: full, one-step) for grading."""

    def handler() -> CommandResult:
        items = {item.item_id: item for item in load_golden(golden)}
        path = export_calibration(
            e2e_run_dir(run_name),
            items,
            seed=seed,
            configs=tuple(configs) if configs else CALIBRATION_CONFIGS,
        )
        return CommandResult("e2e calibration export", CommandStatus.COMPLETE, path)

    run_handler(state_from_context(ctx), handler)


@calibration_app.command("refresh")
def calibration_refresh(
    ctx: typer.Context,
    run_name: Annotated[str, typer.Option("--run")],
    golden: Annotated[Path, typer.Option("--golden", dir_okay=False)] = GOLDEN_E2E_PATH,
) -> None:
    """Re-export blind items whose answer or golden item changed, for regrading."""

    def handler() -> CommandResult:
        items = {item.item_id: item for item in load_golden(golden)}
        changed = refresh_calibration(e2e_run_dir(run_name), items)
        return CommandResult(
            "e2e calibration refresh",
            CommandStatus.COMPLETE,
            e2e_run_dir(run_name) / "calibration",
            {"regrade": ",".join(changed) or "none"},
        )

    run_handler(state_from_context(ctx), handler)


@calibration_app.command("score")
def calibration_score(
    ctx: typer.Context,
    run_name: Annotated[str, typer.Option("--run")],
    golden: Annotated[Path, typer.Option("--golden", dir_okay=False)] = GOLDEN_E2E_PATH,
) -> None:
    """Measure agreement between the judge and calibration/grades.jsonl."""

    def handler() -> CommandResult:
        items = {item.item_id: item for item in load_golden(golden)}
        rows = score_calibration(e2e_run_dir(run_name), items)
        return CommandResult(
            "e2e calibration score",
            CommandStatus.COMPLETE,
            e2e_run_dir(run_name) / "calibration",
            {
                f"{row.metric}.{row.statistic}": (
                    f"{row.value:.3f} [{row.ci_low:.3f}, {row.ci_high:.3f}] "
                    f"n={row.n} reliable={row.reliable}"
                )
                for row in rows
            },
        )

    run_handler(state_from_context(ctx), handler)


@e2e_app.command("report")
def report(
    ctx: typer.Context,
    run_name: Annotated[str, typer.Option("--run")],
    golden: Annotated[Path, typer.Option("--golden", dir_okay=False)] = GOLDEN_E2E_PATH,
    evaluation: Annotated[
        Path, typer.Option("--evaluation", dir_okay=False)
    ] = GOLD_PATH,
) -> None:
    """Write CSV and LaTeX tables for every judged configuration of a run."""
    # `evaluation` is the gold file whose relevance judgments extend citation scoring.

    def handler() -> CommandResult:
        items = {item.item_id: item for item in load_golden(golden)}
        relevance = load_judgments(
            judgments_path(evaluation), evaluation_sha256=sha256_file(evaluation)
        )
        written = write_report(e2e_run_dir(run_name), items, relevance)
        return CommandResult(
            "e2e report",
            CommandStatus.COMPLETE,
            e2e_run_dir(run_name) / "reports",
            {"files": ",".join(path.name for path in written)},
        )

    run_handler(state_from_context(ctx), handler)


@e2e_app.command("citations")
def citations(
    ctx: typer.Context,
    run_name: Annotated[str, typer.Option("--run")],
    config: Annotated[E2EConfig, typer.Option("--config")] = E2EConfig.FULL,
) -> None:
    """Where citation recall is lost: uncited, dangling, unsupported, supported."""
    run_dir = e2e_run_dir(run_name)

    def handler() -> CommandResult:
        report = write_citation_report(run_dir / str(config), run_dir / "reports")
        return CommandResult(
            "e2e citations",
            CommandStatus.COMPLETE,
            run_dir / "reports" / REPORT_FILE,
            {"items": report["items"], "sentences": report["sentences"]},
        )

    run_handler(state_from_context(ctx), handler)


@e2e_app.command("rejudge-citations")
def rejudge_citations(
    ctx: typer.Context,
    run_name: Annotated[str, typer.Option("--run")],
    config: Annotated[E2EConfig, typer.Option("--config")],
    concurrency: Annotated[int, typer.Option("--concurrency", min=1)] = 4,
    judge_model: Annotated[
        str,
        typer.Option(
            "--judge-model", help="Must be the model the configuration was judged with"
        ),
    ] = JUDGE_MODEL,
    backend_env_file: Annotated[
        Path, typer.Option("--backend-env-file", dir_okay=False)
    ] = BACKEND_ENV_FILE,
) -> None:
    """Judge citation support again (after a citation-parser fix); other fields stay."""
    request = JudgeRequest(
        run_root=e2e_run_dir(run_name),
        config=config,
        golden_path=GOLDEN_E2E_PATH,
        backend_env_file=backend_env_file,
        concurrency=concurrency,
        judge_model=judge_model,
    )

    def handler() -> CommandResult:
        summary = run_citation_rejudge(request)
        return CommandResult(
            "e2e rejudge-citations",
            CommandStatus.INCOMPLETE if summary.errors else CommandStatus.COMPLETE,
            request.run_root / str(config),
            {"judged": summary.judged, "errors": summary.errors},
        )

    run_handler(state_from_context(ctx), handler)
