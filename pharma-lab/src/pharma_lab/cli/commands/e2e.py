from __future__ import annotations

import asyncio
import json
import tempfile
from collections import Counter
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from openai.types import ReasoningEffort
from pharma_agent.domain.corpus.bundle import read_bundle
from pharma_agent.infrastructure.llm.systemone_adapter import SystemOneAdapter
from pharma_agent.infrastructure.settings import Settings
from pydantic import TypeAdapter

from pharma_lab.artifacts.manifest import sha256_file
from pharma_lab.bundle.corpus_text import (
    chunk_texts,
    corpus_text,
    load_corpus_text,
)
from pharma_lab.cli.commands.kaggle import credential_datasets
from pharma_lab.cli.runtime import (
    CommandResult,
    CommandStatus,
    run_handler,
    state_from_context,
)
from pharma_lab.config.paths import (
    BACKEND_ENV_FILE,
    BUNDLE_DIR,
    DECISION_CALIBRATION_DIR,
    E2E_AUTHORING_DIR,
    GOLD_DIR,
    GOLDEN_E2E_PATH,
    PROJECT_ROOT,
    e2e_run_dir,
    run_dir,
)
from pharma_lab.e2e.calibration import CONFIGS as CALIBRATION_CONFIGS
from pharma_lab.e2e.calibration import (
    export_calibration,
    refresh_calibration,
    score_calibration,
)
from pharma_lab.e2e.citation_analysis import REPORT_FILE, write_citation_report
from pharma_lab.e2e.compare import SIGNIFICANCE, compare_runs
from pharma_lab.e2e.configs import E2EConfig, config_label
from pharma_lab.e2e.decision_calibration import (
    build_judge_set,
    draft_guard_set,
    load_rows,
)
from pharma_lab.e2e.decision_probe import (
    longest_chunk_texts,
    probe_state,
    recommended_evidence_chars,
    run_probe,
)
from pharma_lab.e2e.decision_scoring import (
    score_decision_set,
    score_inputs,
    write_scores,
)
from pharma_lab.e2e.golden import (
    ANSWERABLE_GROUP_QUOTAS,
    CONVERSATIONAL_GROUP,
    EVAL_GROUPS,
    QUOTAS,
    Category,
    build_golden,
    load_golden,
    manifest_path,
    read_items,
    validate_items,
)
from pharma_lab.e2e.golden_audit import (
    PACK_SIZE,
    render_pack,
    review_rows,
    review_score,
)
from pharma_lab.e2e.golden_draft import (
    DRAFT_MODEL,
    FAMILIES,
    MULTI_HOP,
    NATURAL,
    SLICE,
    answerable_candidates,
    authored_sections,
    authored_state,
    draft_multi_hop,
    load_candidates,
    needed_counts,
    select_candidates,
    used_query_ids,
    write_drafts,
)
from pharma_lab.e2e.harness import E2ERunRequest, run_e2e
from pharma_lab.e2e.judge_follower import JudgeFollower
from pharma_lab.e2e.judging.service import (
    JudgeRequest,
    run_citation_rejudge,
    run_judge,
)
from pharma_lab.e2e.judging.structured import (
    DEFAULT_JUDGE_REASONING,
    JUDGE_MODEL,
    judge_llm,
)
from pharma_lab.e2e.kaggle_launch import (
    LaunchOptions,
    launch,
    registry_for,
    run_status,
)
from pharma_lab.e2e.kaggle_run import (
    DEFAULT_BUDGET_SECONDS,
    E2E_KAGGLE_WORK_DIR,
    build_static_inputs,
    reranker_profile,
)
from pharma_lab.e2e.kaggle_shards import (
    CredentialSource,
    E2EPlan,
    E2EShardAdapter,
    Entry,
    check_no_decision_roles,
    make_plan,
)
from pharma_lab.e2e.llm_presets import preset_named
from pharma_lab.e2e.proxy_credentials import (
    DOCKER_VOLUME,
    CredentialDataset,
    export_credentials_from_volume,
    list_credentials,
    select_credentials,
)
from pharma_lab.e2e.report import write_report
from pharma_lab.e2e.run_identity import git_commit
from pharma_lab.e2e.sampling import (
    multi_hop_candidates,
    replacement_candidates,
    sample_answerable,
    sample_multi_turn,
    write_authoring_batches,
    write_replacement_batch,
)
from pharma_lab.evaluation.backend_retrieval import load_query_rows
from pharma_lab.evaluation.relevance_judgments import judgments_path, load_judgments
from pharma_lab.integrations.kaggle.e2e_stage import E2E_MODELS
from pharma_lab.integrations.kaggle.job_lock import kaggle_job_lock
from pharma_lab.integrations.kaggle.quota import AccountQuota
from pharma_lab.integrations.kaggle.workspace import unwind_on_sigterm

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
decision_set_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Held-out calibration set of the decision model.",
)
e2e_app.add_typer(decision_set_app, name="decision-set")

GUARD_DRAFT_MODEL = "gemini-3.1-flash-lite"


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
            rows,
            quotas={group: ANSWERABLE_GROUP_QUOTAS[group] for group in EVAL_GROUPS},
            seed=seed,
            corpus=corpus,
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


@golden_app.command("multi-hop-candidates")
def golden_multi_hop_candidates(
    ctx: typer.Context,
    evaluation: Annotated[
        Path, typer.Option("--evaluation", dir_okay=False)
    ] = GOLD_PATH,
    bundle: Annotated[Path, typer.Option("--bundle", file_okay=False)] = BUNDLE_DIR,
    authoring_dir: Annotated[
        Path, typer.Option("--authoring-dir", file_okay=False)
    ] = E2E_AUTHORING_DIR,
) -> None:
    """List the benchmark's multi_hop rows as candidates (multi-hop.todo.jsonl), with the
    subjects the generator named in multi-hop.generated.jsonl when it is there."""

    def handler() -> CommandResult:
        generated_path = authoring_dir / "multi-hop.generated.jsonl"
        generated = (
            [
                json.loads(line)
                for line in generated_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if generated_path.is_file()
            else []
        )
        candidates = multi_hop_candidates(
            load_query_rows(evaluation), load_corpus_text(bundle), generated
        )
        output = authoring_dir / MULTI_HOP.candidate_files[0]
        output.write_text(
            "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in candidates),
            encoding="utf-8",
        )
        kinds = Counter(str(c["kind"]) for c in candidates)
        return CommandResult(
            "e2e golden multi-hop-candidates",
            CommandStatus.COMPLETE,
            output,
            dict(kinds),
        )

    run_handler(state_from_context(ctx), handler)


@golden_app.command("answerable-candidates")
def golden_answerable_candidates(
    ctx: typer.Context,
    evaluation: Annotated[
        Path, typer.Option("--evaluation", dir_okay=False)
    ] = GOLD_PATH,
    authoring_dir: Annotated[
        Path, typer.Option("--authoring-dir", file_okay=False)
    ] = E2E_AUTHORING_DIR,
) -> None:
    """List the benchmark's answerable rows as candidates: by group
    (natural.todo.jsonl) and by construction-defined slice (slice.todo.jsonl)."""

    def handler() -> CommandResult:
        rows = [
            json.loads(line)
            for line in evaluation.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        natural, slices = answerable_candidates(rows)
        for family, candidates in ((NATURAL, natural), (SLICE, slices)):
            path = authoring_dir / family.candidate_files[0]
            path.write_text(
                "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in candidates),
                encoding="utf-8",
            )
        kinds = Counter(str(c["kind"]) for c in [*natural, *slices])
        return CommandResult(
            "e2e golden answerable-candidates",
            CommandStatus.COMPLETE,
            authoring_dir,
            dict(kinds),
        )

    run_handler(state_from_context(ctx), handler)


@golden_app.command("multi-turn-candidates")
def golden_multi_turn_candidates(
    ctx: typer.Context,
    evaluation: Annotated[
        Path, typer.Option("--evaluation", dir_okay=False)
    ] = GOLD_PATH,
    authoring_dir: Annotated[
        Path, typer.Option("--authoring-dir", file_okay=False)
    ] = E2E_AUTHORING_DIR,
) -> None:
    """List the benchmark's conversational rows as multi-turn candidates
    (multi-turn.todo.jsonl), the phenomenon as their kind."""

    def handler() -> CommandResult:
        rows = [
            json.loads(line)
            for line in evaluation.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        candidates = [
            {**row, "kind": row["query_form"]}
            for row in rows
            if row.get("eval_group") == CONVERSATIONAL_GROUP
        ]
        output = authoring_dir / "multi-turn.todo.jsonl"
        output.write_text(
            "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in candidates),
            encoding="utf-8",
        )
        kinds = Counter(str(c["kind"]) for c in candidates)
        return CommandResult(
            "e2e golden multi-turn-candidates",
            CommandStatus.COMPLETE,
            output,
            dict(kinds),
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
    family_name: Annotated[
        str, typer.Option("--family", help="multi-hop, natural, slice or multi-turn")
    ] = MULTI_HOP.batch,
    backend_env_file: Annotated[
        Path, typer.Option("--backend-env-file", dir_okay=False)
    ] = BACKEND_ENV_FILE,
) -> None:
    """Draft the items of a family (multi-hop items or answerable probes) still missing
    from its per-kind quotas, from <family>.todo.jsonl and <family>.generated.jsonl,
    into new <family>-NN.draft.jsonl batches."""

    def handler() -> CommandResult:
        family = FAMILIES[family_name]
        authored, highest = authored_state(authoring_dir, family)
        counts = needed_counts(authored, family)
        candidates = select_candidates(
            load_candidates(authoring_dir, family),
            exclude=used_query_ids(authoring_dir),
            seed=seed,
            exclude_sections=authored_sections(authoring_dir, family),
            family=family,
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
                family=family,
            )
        )
        paths = write_drafts(authoring_dir, items, failures, family=family)
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


PHARMACIST_DIR = "pharmacist"
VERDICTS_FILE = "verdicts.jsonl"


def _read_verdicts(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@golden_app.command("pharmacist-pack")
def golden_pharmacist_pack(
    ctx: typer.Context,
    golden: Annotated[Path, typer.Option("--golden", dir_okay=False)] = GOLDEN_E2E_PATH,
    bundle: Annotated[Path, typer.Option("--bundle", file_okay=False)] = BUNDLE_DIR,
    authoring_dir: Annotated[
        Path, typer.Option("--authoring-dir", file_okay=False)
    ] = E2E_AUTHORING_DIR,
) -> None:
    """Write the pharmacist's review files of the whole golden set and the verdict sheet,
    keeping the verdicts of items whose content did not change."""

    def handler() -> CommandResult:
        directory = authoring_dir / PHARMACIST_DIR
        directory.mkdir(parents=True, exist_ok=True)
        sheet = directory / VERDICTS_FILE
        previous = {row["item_id"]: row for row in _read_verdicts(sheet)}
        items = {item.item_id: item for item in load_golden(golden)}
        rows = review_rows(list(items.values()), previous)
        sheet.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
        for old in directory.glob("*.md"):
            old.unlink()
        corpus = load_corpus_text(bundle)
        by_tier: dict[str, list[str]] = {}
        for row in rows:
            by_tier.setdefault(row["tier"], []).append(row["item_id"])
        for tier, ids in by_tier.items():
            for start in range(0, len(ids), PACK_SIZE):
                name = f"{tier}-{start // PACK_SIZE + 1:02d}"
                chunk = [items[item_id] for item_id in ids[start : start + PACK_SIZE]]
                (directory / f"{name}.md").write_text(
                    render_pack(name, chunk, corpus), encoding="utf-8"
                )
        pending = sum(1 for row in rows if not row["verdict"])
        return CommandResult(
            "e2e golden pharmacist-pack",
            CommandStatus.COMPLETE,
            directory,
            {"items": len(rows), "to_review": pending},
        )

    run_handler(state_from_context(ctx), handler)


@golden_app.command("pharmacist-score")
def golden_pharmacist_score(
    ctx: typer.Context,
    golden: Annotated[Path, typer.Option("--golden", dir_okay=False)] = GOLDEN_E2E_PATH,
    authoring_dir: Annotated[
        Path, typer.Option("--authoring-dir", file_okay=False)
    ] = E2E_AUTHORING_DIR,
) -> None:
    """Share of golden items the pharmacist fixed or rejected, per tier; complete when
    every current item has a verdict and none is `fail`."""

    def handler() -> CommandResult:
        sheet = authoring_dir / PHARMACIST_DIR / VERDICTS_FILE
        current = review_rows(load_golden(golden), {})
        recorded = {row["item_id"]: row for row in _read_verdicts(sheet)}
        stale = [
            row["item_id"]
            for row in current
            if recorded.get(row["item_id"], {}).get("digest") != row["digest"]
        ]
        if stale:
            raise ValueError(
                f"{len(stale)} item(s) changed or are missing from {sheet}; run "
                f"`e2e golden pharmacist-pack` (first: {stale[0]})"
            )
        rows = [recorded[row["item_id"]] for row in current]
        unreviewed = [row["item_id"] for row in rows if not row.get("verdict")]
        failed = [row["item_id"] for row in rows if row.get("verdict") == "fail"]
        details: dict[str, object] = {
            "unreviewed": len(unreviewed),
            "failed": ",".join(failed),
        }
        if not unreviewed:
            for tier, summary in review_score(rows).items():
                details[f"{tier}_fix_rate"] = summary.mean
                details[f"{tier}_ci"] = f"{summary.ci_low:.3f}-{summary.ci_high:.3f}"
        done = not unreviewed and not failed
        return CommandResult(
            "e2e golden pharmacist-score",
            CommandStatus.COMPLETE if done else CommandStatus.INCOMPLETE,
            sheet,
            details,
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
            benchmark_rows={
                str(row["query_id"]): row
                for row in map(
                    json.loads, evaluation.read_text(encoding="utf-8").splitlines()
                )
            },
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


def kaggle_adapter(
    plan: E2EPlan,
    *,
    budget_seconds: int,
    credentials: CredentialSource | None = None,
    on_merged: Callable[[Sequence[str]], None] | None = None,
) -> E2EShardAdapter:
    """The plan's work as shards, with the real Kaggle stage runner and inputs."""
    from pharma_lab.integrations.kaggle.service import run_kaggle_stage
    from pharma_lab.runtime.runtime_profiles import RuntimeCandidate

    profiles: dict[str, RuntimeCandidate] = {}

    def profile_of(account: str) -> RuntimeCandidate:
        if account not in profiles:
            profiles[account] = reranker_profile(account, budget_seconds)
        return profiles[account]

    return E2EShardAdapter(
        plan,
        golden=load_golden(plan.golden_path),
        run_root=e2e_run_dir(plan.run_name),
        work_dir=E2E_KAGGLE_WORK_DIR / plan.run_name,
        stage_runner=run_kaggle_stage,
        reranker_profile=profile_of,
        build_static=lambda target: build_static_inputs(
            plan.golden_path, target, embedding_model=plan.embedding_model
        ),
        commit=git_commit(Path(__file__).resolve().parent),
        credentials=credentials,
        on_merged=on_merged,
    )


@contextmanager
def judging(
    plan: E2EPlan,
    *,
    enabled: bool,
    backend_env_file: Path,
    golden: Path,
    judge_model: str = JUDGE_MODEL,
    judge_reasoning: str = DEFAULT_JUDGE_REASONING or "medium",
) -> Generator[JudgeFollower | None]:
    """Judge the answers of each shard as it returns (--judge); nothing when off.

    Answers a earlier command left unjudged are picked up first. A command that ends
    in an error does not wait for the judge to catch up."""
    if not enabled:
        yield None
        return
    run_root = e2e_run_dir(plan.run_name)
    follower = JudgeFollower(run_judge, log=lambda line: typer.echo(line, err=True))
    follower.start(
        lambda label: JudgeRequest(
            run_root=run_root,
            config=label,
            golden_path=golden,
            backend_env_file=backend_env_file,
            judge_model=judge_model,
            judge_reasoning=TypeAdapter(ReasoningEffort).validate_python(
                judge_reasoning
            ),
        )
    )
    follower.notify_merged(
        [
            label
            for label in plan.labels
            if (run_root / label / "answers.jsonl").is_file()
        ]
    )
    try:
        yield follower
    except BaseException:
        follower.stop(drain=False)
        raise
    follower.stop()


PROXY_CONFIG_TEMPLATE = PROJECT_ROOT.parent / "devops" / "cli-proxy-api" / "config.yaml"


@contextmanager
def credential_session(
    plan: E2EPlan,
    *,
    names: Sequence[str],
    source: Path | None,
    kaggle_account: str | None,
) -> Generator[CredentialDataset | None]:
    """The run's credential dataset when the preset needs the proxy, else nothing.

    Prints which files go up; they are staged outside the checkout, uploaded to a private
    dataset per account, and deleted from Kaggle when the block ends."""
    from pharma_lab.integrations.kaggle.dataset_service import DatasetService
    from pharma_lab.integrations.kaggle.service import resolve_session_contexts

    if not plan.llm.needs_proxy:
        yield None
        return
    with tempfile.TemporaryDirectory(prefix="pharma-auth-") as exported:
        directory = source
        if directory is None:
            directory = Path(exported) / "auth"
            export_credentials_from_volume(DOCKER_VOLUME, directory)
        files = select_credentials(
            list_credentials(directory), plan.llm.providers, names
        )
        for file in files:
            typer.echo(
                f"credential to upload (private, deleted after): {file.name} ({file.type})"
            )

        def delete(profile: str, reference: str) -> None:
            for context in resolve_session_contexts(kaggle_account or "auto"):
                if context.profile is not None and context.profile.name == profile:
                    DatasetService(
                        context.runner, context.owners.execution
                    ).delete_dataset(reference)
                    return
            raise RuntimeError(f"no Kaggle account {profile} to delete {reference}")

        with CredentialDataset(
            directory,
            files,
            run_name=plan.run_name,
            template=PROXY_CONFIG_TEMPLATE if PROXY_CONFIG_TEMPLATE.is_file() else None,
            deleter=delete,
            say=lambda line: typer.echo(line, err=True),
        ) as dataset:
            # A command killed hard leaves its dataset behind; the name is the same on
            # the next run, so remove it before a new one is uploaded.
            for context in resolve_session_contexts(kaggle_account or "auto"):
                if context.profile is None:
                    continue
                name = context.profile.name
                reference = f"{context.owners.execution}/{dataset.slug(name)}"
                try:
                    left = reference in credential_datasets(context)
                except (OSError, RuntimeError, ValueError):
                    continue  # unreachable account: nothing to sweep, nothing lost
                if left:
                    typer.echo(
                        f"removing a credential dataset left by an earlier run: {reference}",
                        err=True,
                    )
                    delete(name, reference)
            yield dataset


def account_quotas(kaggle_account: str | None) -> list[AccountQuota]:
    from pharma_lab.integrations.kaggle.quota import read_account_quota
    from pharma_lab.integrations.kaggle.service import resolve_session_contexts

    return [
        read_account_quota(context)
        for context in resolve_session_contexts(kaggle_account)
    ]


def kaggle_plan(
    *,
    run_name: str,
    config: list[E2EConfig],
    pipeline_option: list[str] | None,
    golden: Path,
    category: list[Category] | None,
    limit: int | None,
    llm: str,
    concurrency: int,
    deadline_seconds: float | None,
    retry_stuck: bool,
    latency: bool,
    parallel: int | None,
    with_proxy_credentials: bool = False,
    embedding_model: str = E2E_MODELS.embedding,
) -> E2EPlan:
    try:
        preset = preset_named(llm)
        if preset.needs_proxy and not with_proxy_credentials:
            raise ValueError(
                f"--llm {llm} goes through cli-proxy-api in the kernel: add "
                "--with-proxy-credentials to upload your credential files to a "
                "private dataset of this run (deleted when the command ends)"
            )
        if with_proxy_credentials and not preset.needs_proxy:
            raise ValueError(f"--llm {llm} does not use the proxy")
        return make_plan(
            run_name=run_name,
            entries=[Entry(c, tuple(pipeline_option or ())) for c in config],
            golden_path=golden,
            categories=category or None,
            limit=limit,
            llm=preset,
            concurrency=concurrency,
            deadline_seconds=deadline_seconds or 900.0,
            retry_stuck=retry_stuck,
            latency=latency,
            parallel=parallel or 1,
            embedding_model=embedding_model,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error


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
    concurrency: Annotated[int, typer.Option("--concurrency", min=1)] = 8,
    category: Annotated[
        list[Category] | None,
        typer.Option(
            "--category",
            help="Only the items of this golden category; repeatable with kaggle",
        ),
    ] = None,
    retry_errors: Annotated[bool, typer.Option("--retry-errors")] = False,
    deadline_seconds: Annotated[
        float | None,
        typer.Option(
            "--deadline-seconds",
            help="Turn deadline for this run instead of the backend budget",
        ),
    ] = None,
    pipeline_option: Annotated[
        list[str] | None,
        typer.Option(
            "--pipeline-option",
            help="key=value override of PipelineOptions; repeatable",
        ),
    ] = None,
    backend_env_file: Annotated[
        Path, typer.Option("--backend-env-file", dir_okay=False)
    ] = BACKEND_ENV_FILE,
    backend: Annotated[
        RunBackend,
        typer.Option(
            "--backend",
            help="kaggle runs the setting inside Kaggle kernels, resumably",
        ),
    ] = RunBackend.LOCAL,
    kaggle_account: Annotated[
        str | None,
        typer.Option(
            "--kaggle-account",
            help="auto (every account), accN[,accM] or one name; default: .env account",
        ),
    ] = None,
    llm: Annotated[
        str,
        typer.Option("--llm", help="Kaggle: qwen (kernel llama-server), gemini, opus"),
    ] = "qwen",
    parallel: Annotated[
        int | None,
        typer.Option(
            "--parallel", min=1, help="Kaggle: shards at once (default 2 per account)"
        ),
    ] = None,
    budget_seconds: Annotated[
        int, typer.Option("--budget-seconds", min=3600, help="Kaggle: one session")
    ] = DEFAULT_BUDGET_SECONDS,
    max_sessions: Annotated[
        int | None,
        typer.Option("--max-sessions", min=1, help="Kaggle: stop after K kernels"),
    ] = None,
    drain: Annotated[
        bool,
        typer.Option("--drain", help="Kaggle: finish running kernels, start no more"),
    ] = False,
    retry_stuck: Annotated[
        bool,
        typer.Option(
            "--retry-stuck", help="Kaggle: also retry pairs that keep failing"
        ),
    ] = False,
    latency: Annotated[
        bool,
        typer.Option(
            "--latency",
            help="Kaggle: latency run, one kernel at concurrency 1 into <run>-c1",
        ),
    ] = False,
    with_proxy_credentials: Annotated[
        bool,
        typer.Option(
            "--with-proxy-credentials",
            help="Kaggle gemini/opus: upload the proxy credential files to a private "
            "per-run dataset, deleted when the command ends",
        ),
    ] = False,
    proxy_credential: Annotated[
        list[str] | None,
        typer.Option(
            "--proxy-credential", help="Upload only this credential file; repeatable"
        ),
    ] = None,
    judge: Annotated[
        bool,
        typer.Option(
            "--judge",
            help="Kaggle: judge each shard's answers as it returns (no GPU quota)",
        ),
    ] = False,
    embedding_model: Annotated[
        str,
        typer.Option(
            "--embedding-model",
            help="Kaggle: the model that embeds the agent's queries in the kernel "
            "(the corpus bundle must hold its embeddings)",
        ),
    ] = E2E_MODELS.embedding,
    judge_model: Annotated[
        str,
        typer.Option("--judge-model", help="With --judge: model name on the endpoint"),
    ] = JUDGE_MODEL,
    judge_reasoning: Annotated[
        str,
        typer.Option("--judge-reasoning", help="With --judge: none, low, medium"),
    ] = DEFAULT_JUDGE_REASONING or "medium",
    proxy_credentials_dir: Annotated[
        Path | None,
        typer.Option(
            "--proxy-credentials-dir",
            file_okay=False,
            help=f"Directory of credential files (default: Docker volume {DOCKER_VOLUME})",
        ),
    ] = None,
) -> None:
    """Answer the golden set; re-run to resume (Kaggle: only what is missing)."""
    categories = list(category or [])
    if backend is RunBackend.KAGGLE:
        plan = kaggle_plan(
            run_name=run_name,
            config=config,
            pipeline_option=pipeline_option,
            golden=golden,
            category=categories,
            limit=limit,
            llm=llm,
            concurrency=concurrency,
            deadline_seconds=deadline_seconds,
            retry_stuck=retry_stuck,
            latency=latency,
            parallel=parallel,
            with_proxy_credentials=with_proxy_credentials,
            embedding_model=embedding_model,
        )

        def kaggle_handler() -> CommandResult:
            from pharma_lab.integrations.kaggle.service import resolve_session_contexts

            check_no_decision_roles(backend_env_file)
            with (
                # One command per run: two would cut the same missing pairs into
                # different shards and run them twice.
                kaggle_job_lock(E2E_KAGGLE_WORK_DIR / plan.run_name),
                unwind_on_sigterm(),
                credential_session(
                    plan,
                    names=proxy_credential or (),
                    source=proxy_credentials_dir,
                    kaggle_account=kaggle_account,
                ) as credentials,
                judging(
                    plan,
                    enabled=judge,
                    backend_env_file=backend_env_file,
                    golden=golden,
                    judge_model=judge_model,
                    judge_reasoning=judge_reasoning,
                ) as follower,
            ):
                adapter = kaggle_adapter(
                    plan,
                    budget_seconds=budget_seconds,
                    credentials=credentials,
                    on_merged=follower.notify_merged if follower else None,
                )
                outcome = launch(
                    adapter,
                    LaunchOptions(
                        kaggle_account,
                        1 if plan.latency else parallel,
                        budget_seconds,
                        max_sessions,
                        drain,
                    ),
                    resolve_contexts=resolve_session_contexts,
                    registry=registry_for(E2E_KAGGLE_WORK_DIR / plan.run_name),
                )
            for row in outcome.quota_table:
                typer.echo(row)
            return CommandResult(
                "e2e run",
                CommandStatus.COMPLETE
                if outcome.exit_code == 0
                else CommandStatus.INCOMPLETE,
                e2e_run_dir(plan.run_name),
                {
                    "stop": outcome.stop.value if outcome.stop else "nothing-missing",
                    "shards": outcome.shards_run,
                    "merged": outcome.merged_units,
                    "remaining": outcome.remaining,
                    "stuck": outcome.stuck,
                },
                exit_code=outcome.exit_code or None,
            )

        run_handler(state_from_context(ctx), kaggle_handler)
        return
    kaggle_only = {
        "--llm": llm != "qwen",
        "--parallel": parallel is not None,
        "--max-sessions": max_sessions is not None,
        "--drain": drain,
        "--retry-stuck": retry_stuck,
        "--latency": latency,
        "--judge": judge,
    }
    named = [flag for flag, given in kaggle_only.items() if given]
    if named:
        raise typer.BadParameter(f"{', '.join(named)} apply to --backend kaggle")
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
        pipeline_options=tuple(pipeline_option or ()),
    )

    def handler() -> CommandResult:
        summary = run_e2e(request)
        return CommandResult(
            "e2e run",
            CommandStatus.INCOMPLETE if summary.errors else CommandStatus.COMPLETE,
            request.run_root / config_label(config[0], request.pipeline_options),
            {"items": summary.total, "ran": summary.ran, "errors": summary.errors},
        )

    run_handler(state_from_context(ctx), handler)


@e2e_app.command("status")
def status(
    ctx: typer.Context,
    run_name: Annotated[str, typer.Option("--run")],
    config: Annotated[list[E2EConfig], typer.Option("--config")],
    golden: Annotated[Path, typer.Option("--golden", dir_okay=False)] = GOLDEN_E2E_PATH,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
    category: Annotated[list[Category] | None, typer.Option("--category")] = None,
    pipeline_option: Annotated[
        list[str] | None, typer.Option("--pipeline-option")
    ] = None,
    llm: Annotated[str, typer.Option("--llm")] = "qwen",
    kaggle_account: Annotated[str | None, typer.Option("--kaggle-account")] = None,
) -> None:
    """What a Kaggle run still lacks, the kernels running and the quota of each account."""
    plan = kaggle_plan(
        run_name=run_name,
        config=config,
        pipeline_option=pipeline_option,
        golden=golden,
        category=category,
        limit=limit,
        llm="qwen",
        concurrency=8,
        deadline_seconds=None,
        retry_stuck=False,
        latency=False,
        parallel=None,
    )

    def handler() -> CommandResult:
        adapter = kaggle_adapter(plan, budget_seconds=DEFAULT_BUDGET_SECONDS)
        report = run_status(adapter, registry_for(E2E_KAGGLE_WORK_DIR / plan.run_name))
        details: dict[str, object] = {
            f"label.{row.label}": f"{row.done}/{row.total} stuck={row.stuck}"
            for row in report.labels
        }
        for record in report.live:
            details[f"kernel.{record.shard_id}"] = (
                f"{record.profile} units={len(record.unit_keys)} since={record.submitted_at}"
            )
        details["gpu_hours_needed"] = f"{report.gpu_hours_needed:.1f}"
        try:
            for quota in account_quotas(kaggle_account):
                details[f"quota.{quota.profile}"] = (
                    f"{quota.remaining_hours:.1f}h of {quota.total_hours:.1f}h"
                )
        except (OSError, RuntimeError, ValueError) as error:
            details["quota"] = f"unavailable: {error}"
        return CommandResult(
            "e2e status", CommandStatus.COMPLETE, e2e_run_dir(plan.run_name), details
        )

    run_handler(state_from_context(ctx), handler)


@e2e_app.command("judge")
def judge(
    ctx: typer.Context,
    run_name: Annotated[str, typer.Option("--run")],
    config: Annotated[
        str,
        typer.Option(
            "--config",
            help="Configuration directory, e.g. full or full+refine_threshold=0.5",
        ),
    ],
    golden: Annotated[Path, typer.Option("--golden", dir_okay=False)] = GOLDEN_E2E_PATH,
    concurrency: Annotated[int, typer.Option("--concurrency", min=1)] = 8,
    force: Annotated[
        bool, typer.Option("--force", help="Judge every answer again")
    ] = False,
    judge_model: Annotated[
        str,
        typer.Option("--judge-model", help="Model name on the backend LLM endpoint"),
    ] = JUDGE_MODEL,
    judge_reasoning: Annotated[
        str,
        typer.Option(
            "--judge-reasoning", help="Reasoning effort of the judge: none, low, medium"
        ),
    ] = DEFAULT_JUDGE_REASONING or "medium",
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
        judge_reasoning=TypeAdapter(ReasoningEffort).validate_python(judge_reasoning),
        only=frozenset(key.strip() for key in items.split(",") if key.strip()),
        category=category,
    )

    def handler() -> CommandResult:
        summary = run_judge(request)
        return CommandResult(
            "e2e judge",
            CommandStatus.INCOMPLETE if summary.errors else CommandStatus.COMPLETE,
            request.run_root / config,
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


def benchmark_group_counts(golden: Path, evaluation: Path) -> dict[str, int]:
    """Rows per eval group of the benchmark the golden set was built from."""
    manifest = json.loads(manifest_path(golden).read_text(encoding="utf-8"))
    if manifest.get("gold_sha256") != sha256_file(evaluation):
        raise ValueError(f"{golden} was built from another benchmark than {evaluation}")
    return dict(
        Counter(str(row.get("eval_group")) for row in load_query_rows(evaluation))
    )


@e2e_app.command("report")
def report(
    ctx: typer.Context,
    run_name: Annotated[str, typer.Option("--run")],
    golden: Annotated[Path, typer.Option("--golden", dir_okay=False)] = GOLDEN_E2E_PATH,
    evaluation: Annotated[
        Path, typer.Option("--evaluation", dir_okay=False)
    ] = GOLD_PATH,
    latency_run: Annotated[
        str | None,
        typer.Option(
            "--latency-run",
            help="Run whose concurrency-1 answers supply every latency number",
        ),
    ] = None,
) -> None:
    """Write CSV and LaTeX tables for every judged configuration of a run."""
    # `evaluation` is the gold file whose relevance judgments extend citation scoring.

    def handler() -> CommandResult:
        items = {item.item_id: item for item in load_golden(golden)}
        relevance = load_judgments(
            judgments_path(evaluation), evaluation_sha256=sha256_file(evaluation)
        )
        written = write_report(
            e2e_run_dir(run_name),
            items,
            relevance,
            latency_root=None if latency_run is None else e2e_run_dir(latency_run),
            benchmark_counts=benchmark_group_counts(golden, evaluation),
            golden_sha256=sha256_file(golden),
        )
        return CommandResult(
            "e2e report",
            CommandStatus.COMPLETE,
            e2e_run_dir(run_name) / "reports",
            {"files": ",".join(path.name for path in written)},
        )

    run_handler(state_from_context(ctx), handler)


@e2e_app.command("compare")
def compare(
    ctx: typer.Context,
    run_a: Annotated[str, typer.Option("--run-a", help="Baseline run")],
    run_b: Annotated[str, typer.Option("--run-b", help="Run compared with it")],
    config: Annotated[str, typer.Option("--config")] = "full",
    config_b: Annotated[
        str | None,
        typer.Option(
            "--config-b",
            help="Run B's configuration directory when named differently (default: --config)",
        ),
    ] = None,
    golden: Annotated[Path, typer.Option("--golden", dir_okay=False)] = GOLDEN_E2E_PATH,
    evaluation: Annotated[
        Path, typer.Option("--evaluation", dir_okay=False)
    ] = GOLD_PATH,
) -> None:
    """Paired sign-flip test of one configuration between two runs (B minus A)."""

    def handler() -> CommandResult:
        items = {item.item_id: item for item in load_golden(golden)}
        relevance = load_judgments(
            judgments_path(evaluation), evaluation_sha256=sha256_file(evaluation)
        )
        rows = compare_runs(
            e2e_run_dir(run_a),
            e2e_run_dir(run_b),
            config,
            items,
            relevance,
            config_b=config_b,
        )
        return CommandResult(
            "e2e compare",
            CommandStatus.COMPLETE,
            e2e_run_dir(run_b) / "reports",
            {
                row.metric: f"{row.delta:+.3f} p_holm={row.p_holm:.3f}"
                for row in rows
                if row.p_holm < SIGNIFICANCE
            },
        )

    run_handler(state_from_context(ctx), handler)


@e2e_app.command("decision-probe")
def decision_probe(
    ctx: typer.Context,
    chars: Annotated[
        int, typer.Option("--chars", min=1, help="Characters of evidence in the state")
    ] = 60_000,
    bundle: Annotated[Path, typer.Option("--bundle", file_okay=False)] = BUNDLE_DIR,
    backend_env_file: Annotated[
        Path, typer.Option("--backend-env-file", dir_okay=False)
    ] = BACKEND_ENV_FILE,
) -> None:
    """Measure how many Jev tokens a judge state with CHARS of evidence costs."""

    def handler() -> CommandResult:
        decision = SystemOneAdapter(Settings(_env_file=backend_env_file).llm)
        state = probe_state(longest_chunk_texts(read_bundle(bundle)), chars)
        result = asyncio.run(run_probe(decision, state))
        return CommandResult(
            "e2e decision-probe",
            CommandStatus.COMPLETE,
            bundle,
            {
                "input_tokens": result.input_tokens,
                "chars": result.chars,
                "chars_per_token": round(result.chars_per_token, 3),
                "seconds": round(result.seconds, 3),
                "model": result.model,
                "recommended_max_evidence_chars": recommended_evidence_chars(result),
            },
        )

    run_handler(state_from_context(ctx), handler)


@decision_set_app.command("build")
def decision_set_build(
    ctx: typer.Context,
    run_name: Annotated[str, typer.Option("--run", help="Retrieval run of the agent")],
    model: Annotated[str, typer.Option("--model", help="Reranker of that run")],
    size: Annotated[int, typer.Option("--size", min=1)] = 300,
    seed: Annotated[int, typer.Option("--seed")] = 0,
    bundle: Annotated[Path, typer.Option("--bundle", file_okay=False)] = BUNDLE_DIR,
    golden: Annotated[Path, typer.Option("--golden", dir_okay=False)] = GOLDEN_E2E_PATH,
    output: Annotated[Path, typer.Option("--output", dir_okay=False)] = (
        DECISION_CALIBRATION_DIR / "judge_set.jsonl"
    ),
) -> None:
    """Sample judge questions with the run's reranked top-5 evidence, labelled by gold coverage."""

    def handler() -> CommandResult:
        path = build_judge_set(
            run_dir(run_name),
            bundle,
            output=output,
            reranker=model,
            size=size,
            seed=seed,
            golden_sources={
                item.source_query_id
                for item in load_golden(golden)
                if item.source_query_id
            },
        )
        rows = load_rows(path)
        return CommandResult(
            "e2e decision-set build",
            CommandStatus.COMPLETE,
            path,
            {
                "questions": len(rows),
                "sufficient": sum(int(row["sufficient"]) for row in rows),
            },
        )

    run_handler(state_from_context(ctx), handler)


@decision_set_app.command("guard-draft")
def decision_set_guard_draft(
    ctx: typer.Context,
    count: Annotated[int, typer.Option("--count", min=2)] = 100,
    seed: Annotated[int, typer.Option("--seed")] = 0,
    output: Annotated[Path, typer.Option("--output", dir_okay=False)] = (
        DECISION_CALIBRATION_DIR / "guard_set.todo.jsonl"
    ),
    backend_env_file: Annotated[
        Path, typer.Option("--backend-env-file", dir_okay=False)
    ] = BACKEND_ENV_FILE,
) -> None:
    """Draft attack and out-of-scope turns for the author to review, then rename to guard_set.jsonl."""

    def handler() -> CommandResult:
        llm = judge_llm(Settings(_env_file=backend_env_file), GUARD_DRAFT_MODEL, "none")
        path = asyncio.run(draft_guard_set(llm, output, count=count, seed=seed))
        kinds = Counter(str(row["kind"]) for row in load_rows(path))
        return CommandResult(
            "e2e decision-set guard-draft", CommandStatus.COMPLETE, path, dict(kinds)
        )

    run_handler(state_from_context(ctx), handler)


@decision_set_app.command("score")
def decision_set_score(
    ctx: typer.Context,
    repeats: Annotated[int, typer.Option("--repeats", min=1)] = 3,
    judge_set: Annotated[Path, typer.Option("--judge-set", dir_okay=False)] = (
        DECISION_CALIBRATION_DIR / "judge_set.jsonl"
    ),
    guard_set: Annotated[Path, typer.Option("--guard-set", dir_okay=False)] = (
        DECISION_CALIBRATION_DIR / "guard_set.jsonl"
    ),
    output: Annotated[Path, typer.Option("--output", dir_okay=False)] = (
        DECISION_CALIBRATION_DIR / "jev.json"
    ),
    backend_env_file: Annotated[
        Path, typer.Option("--backend-env-file", dir_okay=False)
    ] = BACKEND_ENV_FILE,
) -> None:
    """Score the decision model on the held-out set (resumes from decisions.jsonl) and write jev.json."""

    def handler() -> CommandResult:
        decision = SystemOneAdapter(Settings(_env_file=backend_env_file).llm)
        scores = asyncio.run(
            score_decision_set(
                decision,
                load_rows(judge_set),
                load_rows(guard_set),
                repeats=repeats,
                decisions_path=output.with_name("decisions.jsonl"),
            )
        )
        path = write_scores(scores, output, inputs=score_inputs(judge_set, guard_set))
        return CommandResult(
            "e2e decision-set score",
            CommandStatus.COMPLETE,
            path,
            {
                "model": scores.model,
                "tau": scores.tau,
                "block": scores.block,
                "review": scores.review,
                "judge_auroc": round(scores.judge["auroc"], 3),
            },
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
    judge_reasoning: Annotated[
        str,
        typer.Option(
            "--judge-reasoning",
            help="Must be the reasoning the configuration was judged at",
        ),
    ] = DEFAULT_JUDGE_REASONING or "medium",
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
        judge_reasoning=TypeAdapter(ReasoningEffort).validate_python(judge_reasoning),
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
