"""Run text embedding for bundle inputs locally (llama.cpp) or on Kaggle."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pharma_lab.cache.text_embeddings import (
    TextEmbeddingCache,
    embed_missing,
    read_embedding_inputs,
    write_embedding_inputs,
)
from pharma_lab.config.paths import GGUF_ROOT, LOCAL_MODELS_COMPOSE_FILES, WORK_DIR
from pharma_lab.integrations.kaggle.job_lock import kaggle_job_lock
from pharma_lab.runtime.catalog import ModelKind, require_model
from pharma_lab.runtime.client import LlamaCppClient
from pharma_lab.runtime.compose import LlamaCppComposeManager, resolve_server


@dataclass(frozen=True)
class TextEmbeddingRequest:
    inputs_path: Path
    model: str
    cache_path: Path
    force: bool
    dry_run: bool
    budget_seconds: int
    request_timeout_seconds: float
    kaggle_account: str | None = None
    # Kaggle shards at once (default: two sessions per account) and finish-then-stop.
    parallel: int | None = None
    drain: bool = False


@dataclass(frozen=True)
class TextEmbeddingResult:
    cache_path: Path | None
    actions: tuple[str, ...]
    incomplete: bool = False
    quota: tuple[str, ...] = ()


class TextEmbeddingBackend(Protocol):
    def run(self, request: TextEmbeddingRequest) -> TextEmbeddingResult: ...


def open_text_cache(path: Path, model: str) -> TextEmbeddingCache:
    spec = require_model(model)
    if spec.kind is not ModelKind.EMBEDDING or spec.vector_dimension is None:
        raise ValueError(f"--model must select an embedding model: {model}")
    return TextEmbeddingCache(
        path, model=model, model_sha256=spec.sha256, vector_dim=spec.vector_dimension
    )


class LocalTextEmbeddingBackend:
    def __init__(
        self,
        *,
        compose_files: Sequence[Path] = LOCAL_MODELS_COMPOSE_FILES,
        gguf_root: Path = GGUF_ROOT,
        server_mode: str = "compose",
        server_urls: Sequence[str] = (),
    ) -> None:
        self.compose_files = compose_files
        self.gguf_root = gguf_root
        self.server_mode = server_mode
        self.server_urls = list(server_urls)

    def run(self, request: TextEmbeddingRequest) -> TextEmbeddingResult:
        spec = require_model(request.model)
        if request.dry_run:
            open_text_cache(request.cache_path, request.model)
            return TextEmbeddingResult(None, ("dry-run",))
        if request.force:
            request.cache_path.unlink(missing_ok=True)
        cache = open_text_cache(request.cache_path, request.model)
        inputs = read_embedding_inputs(request.inputs_path)
        if not cache.missing(inputs):
            return TextEmbeddingResult(request.cache_path, ("cached",))
        endpoints = resolve_server(
            self.server_mode,
            self.server_urls,
            spec,
            LlamaCppComposeManager(self.compose_files),
            self.gguf_root,
        )
        run = embed_missing(
            inputs,
            cache,
            [
                LlamaCppClient(endpoint, timeout=request.request_timeout_seconds)
                for endpoint in endpoints
            ],
            batch_size=spec.local_request_batch_size,
        )
        return TextEmbeddingResult(
            request.cache_path,
            (f"cached={run.cached}", f"embedded={run.embedded}"),
            incomplete=run.stopped_early,
        )


class KaggleTextEmbeddingBackend:
    def run(self, request: TextEmbeddingRequest) -> TextEmbeddingResult:
        with kaggle_job_lock(request.cache_path):
            return self._run_unlocked(request)

    @staticmethod
    def _run_unlocked(request: TextEmbeddingRequest) -> TextEmbeddingResult:
        from pharma_lab.embeddings.shards import (
            TextEmbeddingShardAdapter,
            seconds_per_character,
        )
        from pharma_lab.integrations.kaggle.auto_profile import (
            ensure_runtime_profile,
        )
        from pharma_lab.integrations.kaggle.job_registry import JobRegistry
        from pharma_lab.integrations.kaggle.models import StageName
        from pharma_lab.integrations.kaggle.scheduler import (
            SchedulerSettings,
            run_shards,
            shard_margin_seconds,
        )
        from pharma_lab.integrations.kaggle.service import (
            resolve_session_contexts,
            run_kaggle_stage,
        )
        from pharma_lab.integrations.kaggle.shards import plan_shards

        spec = require_model(request.model)
        # Kaggle GPU time is the scarce resource: send only texts the cache lacks.
        missing = open_text_cache(request.cache_path, request.model).missing(
            read_embedding_inputs(request.inputs_path)
        )
        if not missing and not request.force:
            return TextEmbeddingResult(request.cache_path, ("cached",))
        work_dir = WORK_DIR / "kaggle-text-embeddings" / spec.slug
        inputs_path = request.inputs_path
        if not request.force:
            inputs_path = work_dir / "missing_inputs.jsonl"
            write_embedding_inputs(missing, inputs_path)
        resolution = ensure_runtime_profile(
            workload="corpus-embed",
            benchmark_stage=StageName.CORPUS_EMBED_BENCHMARK.value,
            model=request.model,
            input_path=inputs_path,
            gguf_root=GGUF_ROOT,
            budget_seconds=request.budget_seconds,
            dry_run=request.dry_run,
            force=request.force,
            kaggle_account=request.kaggle_account,
        )
        if resolution.profile is None:
            return TextEmbeddingResult(
                None, (f"profile={resolution.action}",), incomplete=True
            )
        selected = resolution.profile.selected
        contexts = resolve_session_contexts(request.kaggle_account or "auto")
        adapter = TextEmbeddingShardAdapter(
            model=request.model,
            inputs_path=request.inputs_path,
            cache_path=request.cache_path,
            work_dir=work_dir,
            remote_dir=work_dir,
            stage_runner=run_kaggle_stage,
            runtime_profile=selected,
            seconds_per_character=seconds_per_character(
                selected.to_dict(), resolution.profile.measurements
            ),
            force=request.force,
        )
        margin = shard_margin_seconds(request.budget_seconds)
        if request.dry_run:
            units = adapter.missing()
            shards = plan_shards(
                units,
                setup_seconds=adapter.setup_seconds(),
                budget_seconds=request.budget_seconds,
                margin_seconds=margin,
                slots=2 * len(contexts),
            )
            hours = (
                sum(unit.seconds for unit in units)
                + len(shards) * adapter.setup_seconds()
            ) / 3600
            return TextEmbeddingResult(
                None,
                (
                    f"missing_texts={len(units)}",
                    f"planned_shards={len(shards)}",
                    f"estimated_gpu_hours={hours:.1f}",
                ),
                incomplete=True,
            )
        report = run_shards(
            adapter,
            contexts,
            JobRegistry(work_dir / "jobs.json"),
            SchedulerSettings(
                parallel=request.parallel or 2 * len(contexts),
                budget_seconds=request.budget_seconds,
                margin_seconds=margin,
                max_sessions=None,
                drain=request.drain,
            ),
            log=lambda line: print(line, file=sys.stderr, flush=True),
        )
        left = len(adapter.missing())
        return TextEmbeddingResult(
            request.cache_path,
            (
                f"missing_texts={left}",
                f"sessions={report.shards_run}",
                f"stop={report.stop.value}",
            ),
            incomplete=bool(left),
            quota=report.quota_table,
        )
