from __future__ import annotations

import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pharma_lab.config.paths import (
    GGUF_ROOT,
    LOCAL_MODELS_COMPOSE_FILES,
    WORK_DIR,
)
from pharma_lab.embeddings.shards import SECONDS_PER_TEXT, seconds_per_character
from pharma_lab.evaluation.preload_query_embeddings import preload_embeddings
from pharma_lab.evaluation.query_embedding_cache import QueryEmbeddingCache
from pharma_lab.evaluation.query_embedding_shards import (
    SETUP_SECONDS,
    QueryEmbeddingShardAdapter,
    query_keys,
    read_query_rows,
)
from pharma_lab.integrations.kaggle.job_lock import kaggle_job_lock
from pharma_lab.integrations.kaggle.shards import WorkUnit
from pharma_lab.runtime.catalog import ModelKind, require_model
from pharma_lab.runtime.client import LlamaCppClient
from pharma_lab.runtime.compose import LlamaCppComposeManager, resolve_server


@dataclass(frozen=True)
class QueryEmbeddingRequest:
    evaluation_path: Path
    model: str
    output_dir: Path
    force: bool
    dry_run: bool
    budget_seconds: int
    request_timeout_seconds: float
    benchmark: bool = False
    benchmark_items: int = 512
    kaggle_account: str | None = None
    # Kaggle shards at once (default: two sessions per account) and finish-then-stop.
    parallel: int | None = None
    drain: bool = False


@dataclass(frozen=True)
class QueryEmbeddingStageResult:
    cache_path: Path | None
    subset_sha256: str | None
    actions: tuple[str, ...]
    incomplete: bool = False
    benchmark_report: Path | None = None
    benchmark_levels: int = 0
    quota: tuple[str, ...] = ()


class QueryEmbeddingBackend(Protocol):
    def run(self, request: QueryEmbeddingRequest) -> QueryEmbeddingStageResult:
        raise NotImplementedError


class LocalQueryEmbeddingBackend:
    def __init__(
        self,
        *,
        compose_files: Sequence[Path] = LOCAL_MODELS_COMPOSE_FILES,
        gguf_root: Path = GGUF_ROOT,
    ):
        self.compose_files = compose_files
        self.gguf_root = gguf_root

    def run(self, request: QueryEmbeddingRequest) -> QueryEmbeddingStageResult:
        spec = require_model(request.model)
        if spec.kind is not ModelKind.EMBEDDING:
            raise ValueError("--model must select an embedding model")
        if request.benchmark:
            raise ValueError("benchmark requires --backend kaggle")
        if request.dry_run:
            return QueryEmbeddingStageResult(None, None, ("dry-run",))
        manager = LlamaCppComposeManager(self.compose_files)
        endpoint = resolve_server("compose", [], spec, manager, self.gguf_root)[0]
        client = LlamaCppClient(endpoint, timeout=request.request_timeout_seconds)
        expected_dimension = spec.vector_dimension
        if expected_dimension is None:
            raise ValueError(
                f"embedding model has no vector dimension: {request.model}"
            )
        partial_cache = Path(request.output_dir)
        cache = QueryEmbeddingCache(
            partial_cache,
            vector_dim=spec.vector_dimension or 0,
            model_sha256=spec.sha256,
        )
        rows = read_query_rows(request.evaluation_path)
        if request.force:
            cache.replace_keys(query_keys(rows, request.model))
        preload_embeddings(
            eval_path=request.evaluation_path,
            model_name=request.model,
            cache_path=partial_cache,
            embed_batch_fn=lambda queries: client.embed(
                queries, request.model, expected_dimension
            ),
            batch_size=spec.local_request_batch_size,
            force=False,
            vector_dim=spec.vector_dimension,
            model_sha256=spec.sha256,
        )
        cache = QueryEmbeddingCache(
            partial_cache,
            vector_dim=spec.vector_dimension or 0,
            model_sha256=spec.sha256,
        )
        subset = cache.validate_subset(rows, request.model)
        return QueryEmbeddingStageResult(
            partial_cache,
            subset.sha256,
            ("local",),
            incomplete=not subset.is_complete,
        )


class KaggleQueryEmbeddingBackend:
    def __init__(
        self,
        runner: Callable[[QueryEmbeddingRequest], QueryEmbeddingStageResult]
        | None = None,
    ):
        self.runner = runner or self._run_kaggle_orchestrator

    def run(self, request: QueryEmbeddingRequest) -> QueryEmbeddingStageResult:
        return self.runner(request)

    @staticmethod
    def _run_kaggle_orchestrator(
        request: QueryEmbeddingRequest,
    ) -> QueryEmbeddingStageResult:
        with kaggle_job_lock(request.output_dir):
            return KaggleQueryEmbeddingBackend._run_kaggle_unlocked(request)

    @staticmethod
    def _run_kaggle_unlocked(
        request: QueryEmbeddingRequest,
    ) -> QueryEmbeddingStageResult:
        from pharma_lab.integrations.kaggle.auto_profile import (
            ensure_runtime_profile,
        )
        from pharma_lab.integrations.kaggle.job_registry import shared_registry
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
        work_dir = WORK_DIR / "kaggle-query-embeddings" / spec.slug
        rows = read_query_rows(request.evaluation_path)
        cached = QueryEmbeddingCache(
            request.output_dir,
            vector_dim=spec.vector_dimension,
            model_sha256=spec.sha256,
        )
        # Only the questions the local cache lacks go to Kaggle: a recomputed vector
        # differs from the cached one in the last digits, and the cache keeps one.
        missing = [
            row
            for row in rows
            if request.force
            or cached.get(
                request.model, str(row.get("query_id")), str(row.get("query") or "")
            )
            is None
        ]
        if not missing:
            subset = cached.validate_subset(rows, request.model)
            return QueryEmbeddingStageResult(
                request.output_dir, subset.sha256, ("cache=complete",)
            )
        input_path = request.output_dir.with_name(
            f"{request.output_dir.stem}.{spec.slug}.missing.jsonl"
        )
        input_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in missing),
            encoding="utf-8",
        )
        resolution = ensure_runtime_profile(
            workload="query-embed",
            benchmark_stage=StageName.QUERY_EMBED_BENCHMARK.value,
            model=request.model,
            input_path=input_path,
            gguf_root=GGUF_ROOT,
            budget_seconds=request.budget_seconds,
            dry_run=request.dry_run,
            force=request.force,
            kaggle_account=request.kaggle_account,
        )
        if resolution.profile is None:
            return QueryEmbeddingStageResult(
                None, None, (f"profile={resolution.action}",), incomplete=True
            )
        selected = resolution.profile.selected
        contexts = resolve_session_contexts(request.kaggle_account or "auto")
        margin = shard_margin_seconds(request.budget_seconds)
        per_character = seconds_per_character(
            selected.to_dict(), resolution.profile.measurements
        )
        if request.dry_run:
            # Planned from the same costs the adapter uses, without clearing anything.
            units = [
                WorkUnit(
                    str(row["query_id"]),
                    SECONDS_PER_TEXT + len(str(row.get("query") or "")) * per_character,
                )
                for row in missing
            ]
            shards = plan_shards(
                units,
                setup_seconds=SETUP_SECONDS,
                budget_seconds=request.budget_seconds,
                margin_seconds=margin,
                slots=2 * len(contexts),
            )
            hours = (
                sum(unit.seconds for unit in units) + len(shards) * SETUP_SECONDS
            ) / 3600
            return QueryEmbeddingStageResult(
                None,
                None,
                (
                    f"missing_queries={len(units)}",
                    f"planned_shards={len(shards)}",
                    f"estimated_gpu_hours={hours:.1f}",
                ),
                incomplete=True,
            )
        adapter = QueryEmbeddingShardAdapter(
            model=request.model,
            evaluation_path=request.evaluation_path,
            cache_path=request.output_dir,
            work_dir=work_dir,
            remote_dir=work_dir,
            stage_runner=run_kaggle_stage,
            runtime_profile=selected,
            seconds_per_character=per_character,
            force=request.force,
        )
        report = run_shards(
            adapter,
            contexts,
            shared_registry(work_dir / "jobs.json", WORK_DIR),
            SchedulerSettings(
                parallel=request.parallel or 2 * len(contexts),
                budget_seconds=request.budget_seconds,
                margin_seconds=margin,
                max_sessions=None,
                drain=request.drain,
            ),
            log=lambda line: print(line, file=sys.stderr, flush=True),
        )
        local = QueryEmbeddingCache(
            request.output_dir,
            vector_dim=spec.vector_dimension,
            model_sha256=spec.sha256,
        )
        subset = local.validate_subset(rows, request.model)
        return QueryEmbeddingStageResult(
            request.output_dir,
            subset.sha256,
            (
                f"missing_queries={subset.missing}",
                f"sessions={report.shards_run}",
                f"stop={report.stop.value}",
            ),
            incomplete=not subset.is_complete,
            quota=report.quota_table,
        )
