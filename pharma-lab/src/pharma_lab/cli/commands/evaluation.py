from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from pharma_agent.domain.corpus.bundle import BundleValidationError, read_bundle

from pharma_lab.bundle.evaluation_chunks import write_evaluation_chunks
from pharma_lab.cli.commands.bundle import invalid_bundle
from pharma_lab.cli.runtime import (
    CommandResult,
    CommandStatus,
    run_handler,
    state_from_context,
)
from pharma_lab.config.paths import (
    BUNDLE_DIR,
    EVALUATION_CHUNKS_PATH,
    GOLD_DIR,
    RAG_FINAL_SECTIONS_PATH,
    run_dir,
)
from pharma_lab.e2e.benchmark_extension import extend_rows
from pharma_lab.e2e.conversational import PHENOMENA
from pharma_lab.e2e.corpus_text import corpus_text
from pharma_lab.e2e.one_round import load_one_round
from pharma_lab.evaluation.build_dataset import (
    EvaluationBuildRequest,
    build_evaluation_dataset,
)
from pharma_lab.evaluation.relevance_judgments import build_evaluation_judgments

evaluation_app = typer.Typer(no_args_is_help=True, add_completion=False)
GOLD_EVALUATION_PATH = GOLD_DIR / "section_retrieval_eval.jsonl"


def evaluation_build_command(
    *,
    sections: Path = RAG_FINAL_SECTIONS_PATH,
    bundle: Path = BUNDLE_DIR,
    chunks_output: Path = EVALUATION_CHUNKS_PATH,
    output_dir: Path = GOLD_DIR,
    patient_query_count: int = 500,
    evaluation_row_count: int = 10_000,
) -> CommandResult:
    try:
        knowledge = read_bundle(bundle)
    except BundleValidationError as exc:
        raise invalid_bundle(exc) from exc
    chunk_count = write_evaluation_chunks(knowledge, chunks_output)
    result = build_evaluation_dataset(
        EvaluationBuildRequest(
            sections_path=sections,
            chunks_path=chunks_output,
            output_dir=output_dir,
            patient_query_count=patient_query_count,
            evaluation_row_count=evaluation_row_count,
        )
    )
    judgments = build_evaluation_judgments(result.evaluation_path, bundle)
    return CommandResult(
        command="evaluation build",
        status=CommandStatus.COMPLETE,
        artifact=result.evaluation_path,
        details={
            "chunks": chunk_count,
            "patient_queries": str(result.patient_queries_path),
            "patient_query_count": result.patient_query_count,
            "evaluation_row_count": result.evaluation_row_count,
            "judgments": str(judgments),
        },
    )


@evaluation_app.command("build")
def evaluation_build(
    ctx: typer.Context,
    sections: Annotated[Path, typer.Option("--sections")] = RAG_FINAL_SECTIONS_PATH,
    bundle: Annotated[Path, typer.Option("--bundle", file_okay=False)] = BUNDLE_DIR,
    chunks_output: Annotated[
        Path, typer.Option("--chunks-output", dir_okay=False)
    ] = EVALUATION_CHUNKS_PATH,
    output_dir: Annotated[Path, typer.Option("--output-dir")] = GOLD_DIR,
    patient_query_count: Annotated[int, typer.Option("--patient-query-count")] = 500,
    evaluation_row_count: Annotated[
        int, typer.Option("--evaluation-row-count")
    ] = 10_000,
) -> None:
    run_handler(
        state_from_context(ctx),
        lambda: evaluation_build_command(
            sections=sections,
            bundle=bundle,
            chunks_output=chunks_output,
            output_dir=output_dir,
            patient_query_count=patient_query_count,
            evaluation_row_count=evaluation_row_count,
        ),
    )


def evaluation_judgments_command(
    *, evaluation: Path = GOLD_EVALUATION_PATH, bundle: Path = BUNDLE_DIR
) -> CommandResult:
    try:
        path = build_evaluation_judgments(evaluation, bundle)
    except BundleValidationError as exc:
        raise invalid_bundle(exc) from exc
    return CommandResult(
        command="evaluation judgments",
        status=CommandStatus.COMPLETE,
        artifact=path,
        details={},
    )


@evaluation_app.command("judgments")
def evaluation_judgments(
    ctx: typer.Context,
    evaluation: Annotated[
        Path, typer.Option("--evaluation", dir_okay=False)
    ] = GOLD_EVALUATION_PATH,
    bundle: Annotated[Path, typer.Option("--bundle", file_okay=False)] = BUNDLE_DIR,
) -> None:
    """Rebuild the relevance judgments of a gold file; runs keep their candidates."""
    run_handler(
        state_from_context(ctx),
        lambda: evaluation_judgments_command(evaluation=evaluation, bundle=bundle),
    )


@evaluation_app.command("extend")
def evaluation_extend(
    ctx: typer.Context,
    evaluation: Annotated[
        Path, typer.Option("--evaluation", dir_okay=False)
    ] = GOLD_EVALUATION_PATH,
    bundle: Annotated[Path, typer.Option("--bundle", file_okay=False)] = BUNDLE_DIR,
    run_name: Annotated[
        str | None,
        typer.Option("--run", help="Run whose one-round coverage stratifies parents"),
    ] = "hybrid-qwen4b-v2-p50-k20-rrf2",
    model: Annotated[str, typer.Option("--model")] = "qwen3-reranker:4b-q8_0",
    conversational_total: Annotated[
        int, typer.Option("--conversational-total", min=len(PHENOMENA))
    ] = 1_500,
    seed: Annotated[int, typer.Option("--seed")] = 0,
) -> None:
    """Append the generated groups to the benchmark in place and rebuild its judgments:
    colloquial names absent from their leaflet, plain-language phrases for abbreviated
    terms, and conversational follow-ups that inherit a question's gold sections. Rows
    of these groups already in the file are replaced, so extending twice is the same."""

    def handler() -> CommandResult:
        try:
            knowledge = read_bundle(bundle)
        except BundleValidationError as exc:
            raise invalid_bundle(exc) from exc
        base = [
            json.loads(line)
            for line in evaluation.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        covered = None
        if run_name:
            found = load_one_round(run_dir(run_name), model=model, top_k=5).coverage
            covered = {query_id: not c.missing for query_id, c in found.items()}
        aliases = [
            (alias, mapping.section_keys)
            for mapping in knowledge.colloquial_mappings
            for alias in mapping.aliases
        ]
        rows = extend_rows(
            base,
            corpus_text(knowledge),
            aliases,
            covered=covered,
            conversational_total=conversational_total,
            seed=seed,
        )
        evaluation.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
        judgments = build_evaluation_judgments(evaluation, bundle)
        groups: dict[str, int] = {}
        for row in rows:
            group = str(row.get("eval_group"))
            groups[group] = groups.get(group, 0) + 1
        return CommandResult(
            "evaluation extend",
            CommandStatus.COMPLETE,
            evaluation,
            {"rows": len(rows), "judgments": str(judgments), **groups},
        )

    run_handler(state_from_context(ctx), handler)
