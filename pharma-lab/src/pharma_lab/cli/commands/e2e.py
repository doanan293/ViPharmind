from __future__ import annotations

import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer
from pharma_agent.domain.corpus.bundle import read_bundle
from pharma_agent.infrastructure.settings import Settings

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
    run_dir,
)
from pharma_lab.e2e.calibration import CONFIGS as CALIBRATION_CONFIGS
from pharma_lab.e2e.calibration import (
    export_calibration,
    refresh_calibration,
    score_calibration,
)
from pharma_lab.e2e.configs import E2EConfig
from pharma_lab.e2e.corpus_text import chunk_texts, corpus_text, load_corpus_text
from pharma_lab.e2e.golden import (
    ANSWERABLE_PER_GROUP,
    MULTI_HOP_QUOTAS,
    QUOTAS,
    Category,
    build_golden,
    load_golden,
    manifest_path,
    read_items,
    validate_items,
)
from pharma_lab.e2e.golden_draft import (
    DRAFT_MODEL,
    authored_state,
    draft_multi_hop,
    load_candidates,
    needed_counts,
    select_candidates,
    used_query_ids,
    write_drafts,
)
from pharma_lab.e2e.golden_generate import generate
from pharma_lab.e2e.harness import E2ERunRequest, run_e2e
from pharma_lab.e2e.judging.service import JudgeRequest, run_judge
from pharma_lab.e2e.judging.structured import JUDGE_MODEL, judge_llm
from pharma_lab.e2e.model_server import attach_model, env_path, serve_model
from pharma_lab.e2e.one_round import load_one_round, trim_covered
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


@golden_app.command("hard-candidates")
def golden_hard_candidates(
    ctx: typer.Context,
    run_name: Annotated[str, typer.Option("--run")],
    model: Annotated[str, typer.Option("--model")] = "qwen3-reranker:4b-q8_0",
    top_k: Annotated[int, typer.Option("--top-k", min=1)] = 5,
    authoring_dir: Annotated[
        Path, typer.Option("--authoring-dir", file_okay=False)
    ] = E2E_AUTHORING_DIR,
) -> None:
    """List benchmark questions one retrieval round misses, by multi-hop kind."""

    def handler() -> CommandResult:
        candidates = load_one_round(
            run_dir(run_name), model=model, top_k=top_k
        ).hard_candidates()
        output = authoring_dir / "multi-hop.todo.jsonl"
        output.write_text(
            "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in candidates),
            encoding="utf-8",
        )
        kinds = Counter(str(c["kind"]) for c in candidates)
        return CommandResult(
            "e2e golden hard-candidates", CommandStatus.COMPLETE, output, dict(kinds)
        )

    run_handler(state_from_context(ctx), handler)


@golden_app.command("generate")
def golden_generate(
    ctx: typer.Context,
    bundle: Annotated[Path, typer.Option("--bundle", file_okay=False)] = BUNDLE_DIR,
    authoring_dir: Annotated[
        Path, typer.Option("--authoring-dir", file_okay=False)
    ] = E2E_AUTHORING_DIR,
    two_drug: Annotated[int, typer.Option("--two-drug", min=0)] = 2
    * MULTI_HOP_QUOTAS["two_drug"],
    brand: Annotated[int, typer.Option("--brand", min=0)] = 2
    * MULTI_HOP_QUOTAS["brand_to_ingredient"],
    seed: Annotated[int, typer.Option("--seed")] = 0,
) -> None:
    """Build two-drug and brand-to-ingredient candidates from the corpus
    (multi-hop.generated.jsonl); twice the quota by default, to cover rejected drafts."""

    def handler() -> CommandResult:
        rows = generate(
            load_corpus_text(bundle),
            {"two_drug": two_drug, "brand_to_ingredient": brand},
            seed=seed,
        )
        output = authoring_dir / "multi-hop.generated.jsonl"
        output.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
        kinds = Counter(str(row["kind"]) for row in rows)
        return CommandResult(
            "e2e golden generate", CommandStatus.COMPLETE, output, dict(kinds)
        )

    run_handler(state_from_context(ctx), handler)


@golden_app.command("draft")
def golden_draft(
    ctx: typer.Context,
    bundle: Annotated[Path, typer.Option("--bundle", file_okay=False)] = BUNDLE_DIR,
    authoring_dir: Annotated[
        Path, typer.Option("--authoring-dir", file_okay=False)
    ] = E2E_AUTHORING_DIR,
    seed: Annotated[int, typer.Option("--seed")] = 0,
    model: Annotated[
        str, typer.Option("--model", help="Model name on the backend LLM endpoint")
    ] = DRAFT_MODEL,
    concurrency: Annotated[int, typer.Option("--concurrency", min=1)] = 8,
    backend_env_file: Annotated[
        Path, typer.Option("--backend-env-file", dir_okay=False)
    ] = BACKEND_ENV_FILE,
) -> None:
    """Draft the multi-hop items still missing from the per-kind quotas, from
    multi-hop.todo.jsonl and multi-hop.generated.jsonl, into new *.draft.jsonl batches."""

    def handler() -> CommandResult:
        authored, highest = authored_state(authoring_dir)
        counts = needed_counts(authored)
        candidates = select_candidates(
            load_candidates(authoring_dir),
            exclude=used_query_ids(authoring_dir),
            seed=seed,
        )
        llm = judge_llm(Settings(_env_file=backend_env_file), model)
        items, failures = asyncio.run(
            draft_multi_hop(
                llm,
                candidates,
                counts,
                load_corpus_text(bundle),
                concurrency=concurrency,
                first_number=highest + 1,
            )
        )
        paths = write_drafts(authoring_dir, items, failures)
        kinds = Counter(item.tags[0] for item in items)
        total = sum(counts.values())
        return CommandResult(
            "e2e golden draft",
            CommandStatus.COMPLETE if len(items) == total else CommandStatus.INCOMPLETE,
            authoring_dir,
            {
                "needed": total,
                "drafted": len(items),
                "failed": len(failures),
                "files": len(paths),
                **kinds,
            },
        )

    run_handler(state_from_context(ctx), handler)


@golden_app.command("trim")
def golden_trim(
    ctx: typer.Context,
    run_name: Annotated[str, typer.Option("--run")],
    model: Annotated[str, typer.Option("--model")] = "qwen3-reranker:4b-q8_0",
    top_k: Annotated[int, typer.Option("--top-k", min=1)] = 5,
    per_group: Annotated[
        int, typer.Option("--per-group", min=1)
    ] = ANSWERABLE_PER_GROUP,
    authoring_dir: Annotated[
        Path, typer.Option("--authoring-dir", file_okay=False)
    ] = E2E_AUTHORING_DIR,
) -> None:
    """Drop answerable items one retrieval round covers, evenly per group."""

    def handler() -> CommandResult:
        paths = sorted(authoring_dir.glob("answerable-*.authored.jsonl"))
        items = [item for path in paths for item in read_items(path)[0]]
        found = load_one_round(run_dir(run_name), model=model, top_k=top_k).coverage
        dropped = set(trim_covered(items, found, keep_per_group=per_group))
        for path in paths:
            kept = [
                line
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and json.loads(line)["item_id"] not in dropped
            ]
            path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        return CommandResult(
            "e2e golden trim",
            CommandStatus.COMPLETE,
            authoring_dir,
            {"dropped": len(dropped), "kept": len(items) - len(dropped)},
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


@e2e_app.command("run")
def run(
    ctx: typer.Context,
    run_name: Annotated[str, typer.Option("--run")],
    config: Annotated[E2EConfig, typer.Option("--config")],
    golden: Annotated[Path, typer.Option("--golden", dir_okay=False)] = GOLDEN_E2E_PATH,
    limit: Annotated[
        int | None,
        typer.Option("--limit", min=1, help="Only N items spread across the set"),
    ] = None,
    concurrency: Annotated[int, typer.Option("--concurrency", min=1)] = 8,
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
) -> None:
    """Answer the golden set with one configuration; re-run to resume."""
    request = E2ERunRequest(
        run_root=e2e_run_dir(run_name),
        config=config,
        golden_path=golden,
        backend_env_file=backend_env_file,
        concurrency=concurrency,
        retry_errors=retry_errors,
        limit=limit,
        deadline_seconds=deadline_seconds,
    )

    def handler() -> CommandResult:
        summary = run_e2e(request)
        return CommandResult(
            "e2e run",
            CommandStatus.INCOMPLETE if summary.errors else CommandStatus.COMPLETE,
            request.run_root / str(config),
            {"items": summary.total, "ran": summary.ran, "errors": summary.errors},
        )

    run_handler(state_from_context(ctx), handler)


@e2e_app.command("judge")
def judge(
    ctx: typer.Context,
    run_name: Annotated[str, typer.Option("--run")],
    config: Annotated[E2EConfig, typer.Option("--config")],
    golden: Annotated[Path, typer.Option("--golden", dir_okay=False)] = GOLDEN_E2E_PATH,
    concurrency: Annotated[int, typer.Option("--concurrency", min=1)] = 8,
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


def _serve(
    ctx: typer.Context,
    command: str,
    *,
    model: str,
    hours: float,
    kaggle_account: str | None,
    attach: str | None,
) -> None:
    def handler() -> CommandResult:
        target = env_path(model)
        typer.echo(f"env file (while serving): {target}")

        def log(line: str) -> None:
            typer.echo(f"[{command}] {line}")

        if attach is not None:
            if kaggle_account is None or kaggle_account == "auto":
                raise ValueError("--attach needs the owning --kaggle-account accN")
            attach_model(
                model=model, reference=attach, kaggle_account=kaggle_account, log=log
            )
        else:
            serve_model(
                model=model, hours=hours, kaggle_account=kaggle_account, log=log
            )
        return CommandResult(f"e2e {command}", CommandStatus.COMPLETE, target)

    run_handler(state_from_context(ctx), handler)


HoursOption = Annotated[float, typer.Option("--hours", min=0.1, max=11.0)]
AccountOption = Annotated[
    str | None, typer.Option("--kaggle-account", help="accN or auto")
]


def _attach_option(stage: str) -> object:
    return typer.Option(
        "--attach",
        help=f"OWNER/SLUG of a running {stage} kernel to reuse "
        "(with --kaggle-account accN)",
    )


@e2e_app.command("rerank-server")
def rerank_server(
    ctx: typer.Context,
    model: Annotated[str, typer.Option("--model")] = "qwen3-reranker:4b-q8_0",
    hours: HoursOption = 8.0,
    kaggle_account: AccountOption = "auto",
    attach: Annotated[str | None, _attach_option("rerank-serve")] = None,
) -> None:
    """Serve the reranker from a Kaggle GPU; E2E runs source the printed env file."""
    _serve(
        ctx,
        "rerank-server",
        model=model,
        hours=hours,
        kaggle_account=kaggle_account,
        attach=attach,
    )


@e2e_app.command("llm-server")
def llm_server(
    ctx: typer.Context,
    model: Annotated[str, typer.Option("--model")] = "qwen3.5:9b-q8_0",
    hours: HoursOption = 8.0,
    kaggle_account: AccountOption = "auto",
    attach: Annotated[str | None, _attach_option("llm-serve")] = None,
) -> None:
    """Serve an open-weight chat model from two Kaggle T4s for every pipeline role."""
    _serve(
        ctx,
        "llm-server",
        model=model,
        hours=hours,
        kaggle_account=kaggle_account,
        attach=attach,
    )
