"""Local side of `e2e run --backend kaggle`: prepare one e2e-run job, run it in a
Kaggle kernel and put its answers into the run directory."""

from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pharma_lab.config.paths import BUNDLE_DIR, GGUF_ROOT, WORK_DIR, e2e_run_dir
from pharma_lab.e2e.configs import E2EConfig
from pharma_lab.e2e.golden import Category, GoldenItem, load_golden
from pharma_lab.e2e.records import ANSWERS_FILE
from pharma_lab.e2e.run_identity import RUN_FILE, git_commit
from pharma_lab.integrations.kaggle.e2e_stage import (
    CORPUS_DIR,
    E2E_MODELS,
    GOLDEN_FILE,
    JOB_FILE,
    REQUIREMENTS_FILE,
)
from pharma_lab.integrations.kaggle.models import StageName
from pharma_lab.runtime.runtime_profiles import RuntimeCandidate

E2E_KAGGLE_WORK_DIR = WORK_DIR / "e2e-kaggle"
KEPT_FILES = (ANSWERS_FILE, RUN_FILE)
# Setup (apt, venv, model loading, corpus import) takes about half an hour.
DEFAULT_BUDGET_SECONDS = 3 * 3600


def job_items(items: Sequence[GoldenItem], categories: Sequence[Category]) -> list[str]:
    chosen = [item.item_id for item in items if item.category in set(categories)]
    if not chosen:
        raise ValueError(
            f"no golden item in categories {[c.value for c in categories]}"
        )
    return chosen


def trimmed_corpus(bundle: Path, target: Path, *, embedding_model: str) -> Path:
    """A copy of the corpus bundle with only `embedding_model`'s embeddings, so the
    kernel input stays small; the manifest lists exactly the files that are kept."""
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    embeddings = [
        entry for entry in manifest["embeddings"] if entry["model"] == embedding_model
    ]
    dropped = {
        entry["file"] for entry in manifest["embeddings"] if entry not in embeddings
    }
    manifest["embeddings"] = embeddings
    manifest["files"] = {
        name: entry for name, entry in manifest["files"].items() if name not in dropped
    }
    shutil.rmtree(target, ignore_errors=True)
    for name in manifest["files"]:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bundle / name, destination)
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target


def check_targets(run_root: Path, configs: Sequence[str]) -> None:
    for config in configs:
        if (run_root / config / ANSWERS_FILE).is_file():
            raise ValueError(
                f"{run_root / config} already has answers; a Kaggle job writes new "
                "configuration directories only"
            )


def extract_outputs(
    archive: Path, run_root: Path, configs: Sequence[str]
) -> list[Path]:
    """Extract `<config>/answers.jsonl|run.json`; any other member refuses the tar
    before anything is written."""
    allowed = {f"{config}/{name}" for config in configs for name in KEPT_FILES}
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        unexpected = [
            m.name for m in members if m.name not in allowed or not m.isfile()
        ]
        if unexpected:
            raise ValueError(f"unexpected files in the kernel output: {unexpected}")
        written = []
        for member in members:
            source = tar.extractfile(member)
            assert source is not None
            destination = run_root / member.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read())
            written.append(destination)
    return written


@dataclass(frozen=True)
class KaggleE2ERequest:
    run_name: str
    configs: tuple[E2EConfig, ...]
    categories: tuple[Category, ...]
    golden_path: Path
    kaggle_account: str | None
    deadline_seconds: float = 900.0
    budget_seconds: int = DEFAULT_BUDGET_SECONDS


def _requirements(target: Path) -> None:
    workspace = Path(__file__).resolve().parents[4]
    text = subprocess.run(
        [
            "uv",
            "export",
            "--frozen",
            "--no-dev",
            "--no-hashes",
            "--no-emit-workspace",
            "--package",
            "pharma-lab",
        ],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    target.write_text(text, encoding="utf-8")


def prepare_job(request: KaggleE2ERequest, directory: Path) -> Path:
    items = job_items(load_golden(request.golden_path), request.categories)
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(request.golden_path, directory / GOLDEN_FILE)
    _requirements(directory / REQUIREMENTS_FILE)
    trimmed_corpus(
        BUNDLE_DIR, directory / CORPUS_DIR, embedding_model=E2E_MODELS.embedding
    )
    job_path = directory / JOB_FILE
    job_path.write_text(
        json.dumps(
            {
                "run": request.run_name,
                "configs": [config.value for config in request.configs],
                "categories": [category.value for category in request.categories],
                "item_ids": items,
                "deadline_seconds": request.deadline_seconds,
                "commit": git_commit(Path(__file__).resolve().parent),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return job_path


def reranker_profile(kaggle_account: str | None, budget: int) -> RuntimeCandidate:
    """The benchmarked Kaggle profile of the e2e reranker."""
    from pharma_lab.integrations.kaggle.auto_profile import ensure_runtime_profile
    from pharma_lab.integrations.kaggle.service import (
        resolve_execution_context,
        runtime_manifest_sha256,
    )

    context = resolve_execution_context(kaggle_account)

    def no_benchmark(**_: object) -> object:
        raise RuntimeError(f"no Kaggle runtime profile for {E2E_MODELS.reranker}")

    resolution = ensure_runtime_profile(
        workload="rerank",
        benchmark_stage=StageName.RERANK_BENCHMARK.value,
        model=E2E_MODELS.reranker,
        input_path=Path("unused"),
        gguf_root=GGUF_ROOT,
        budget_seconds=budget,
        dry_run=False,
        force=False,
        kaggle_account=kaggle_account,
        runtime_sha256=runtime_manifest_sha256(context.runner, context.owners),
        benchmark_runner=no_benchmark,
    )
    if resolution.profile is None:
        raise RuntimeError(f"no Kaggle runtime profile for {E2E_MODELS.reranker}")
    return resolution.profile.selected


def run_on_kaggle(
    request: KaggleE2ERequest, *, log: Callable[[str], None] = print
) -> list[Path]:
    from pharma_lab.integrations.kaggle.service import run_kaggle_stage

    run_root = e2e_run_dir(request.run_name)
    configs = [config.value for config in request.configs]
    check_targets(run_root, configs)
    directory = E2E_KAGGLE_WORK_DIR / request.run_name
    job_path = prepare_job(request, directory)
    profile = reranker_profile(request.kaggle_account, request.budget_seconds)
    log(f"e2e-run job {job_path} account={request.kaggle_account}")
    result = run_kaggle_stage(
        stage=StageName.E2E_RUN,
        model=E2E_MODELS.llm,
        input_path=job_path,
        output_dir=directory / "kernels",
        max_runs=1,
        budget_seconds=request.budget_seconds,
        runtime_profile=profile,
        kaggle_account=request.kaggle_account,
        # A job runs in one session and never resumes from a checkpoint.
        resume_remote=False,
    )
    if result.artifact_path is None or not result.completion.is_complete:
        raise RuntimeError(
            f"the kernel finished {result.completion} answers; nothing was written"
        )
    return extract_outputs(result.artifact_path, run_root, configs)
