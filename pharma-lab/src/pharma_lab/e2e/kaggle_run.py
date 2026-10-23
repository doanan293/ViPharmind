"""Inputs of an e2e kernel that do not depend on the shard: the golden set, the backend's
requirements and the corpus bundle with one embedding model."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from pharma_lab.config.paths import BUNDLE_DIR, GGUF_ROOT, WORK_DIR
from pharma_lab.integrations.kaggle.e2e_stage import (
    CORPUS_DIR,
    E2E_MODELS,
    GOLDEN_FILE,
    REQUIREMENTS_FILE,
)
from pharma_lab.integrations.kaggle.models import StageName
from pharma_lab.runtime.runtime_profiles import RuntimeCandidate

E2E_KAGGLE_WORK_DIR = WORK_DIR / "e2e-kaggle"
# Setup (apt, venv, model loading, corpus import) takes about half an hour.
DEFAULT_BUDGET_SECONDS = 3 * 3600


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


def build_static_inputs(golden_path: Path, target: Path) -> None:
    """The files every shard of a run shares; their content decides the static dataset."""
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(golden_path, target / GOLDEN_FILE)
    _requirements(target / REQUIREMENTS_FILE)
    trimmed_corpus(
        BUNDLE_DIR, target / CORPUS_DIR, embedding_model=E2E_MODELS.embedding
    )


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
