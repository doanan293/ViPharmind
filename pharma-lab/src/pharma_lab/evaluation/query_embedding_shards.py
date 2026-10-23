"""The query-embedding step as shards for the Kaggle scheduler.

The unit of work is one evaluation query. What is missing is read from the local query
cache (the source of truth). A vector already in the cache is the only one for its
query: a recomputed vector differs in the last digits, so the cache never takes a second
one and a cached query is never sent again. Partial artifacts merge as they arrive.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path

from pharma_lab.cache.jsonl_records import merge_records
from pharma_lab.config.paths import GGUF_ROOT
from pharma_lab.embeddings.shards import SECONDS_PER_TEXT
from pharma_lab.evaluation.query_embedding_cache import QueryEmbeddingCache
from pharma_lab.hashing import query_hash
from pharma_lab.integrations.kaggle.job_lock import kaggle_cache_lock
from pharma_lab.integrations.kaggle.job_registry import ShardRecord
from pharma_lab.integrations.kaggle.models import (
    CloudArtifact,
    PipelineResult,
    StageJob,
    StageName,
)
from pharma_lab.integrations.kaggle.sessions import ReservedAccount
from pharma_lab.integrations.kaggle.shards import Shard, WorkUnit
from pharma_lab.runtime.catalog import require_model
from pharma_lab.runtime.runtime_profiles import RuntimeCandidate

# Starting an embedding kernel: boot, runtime dataset, model load.
SETUP_SECONDS = 300.0

StageRunner = Callable[..., PipelineResult]


def read_query_rows(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def query_keys(rows: Sequence[dict], model: str) -> set[tuple[str, str, str]]:
    return {
        (
            model,
            str(row.get("query_id") or ""),
            query_hash(str(row.get("query") or "")),
        )
        for row in rows
    }


class QueryEmbeddingShardAdapter:
    stage = "query-embed"

    def __init__(
        self,
        *,
        model: str,
        evaluation_path: Path,
        cache_path: Path,
        work_dir: Path,
        remote_dir: Path,
        stage_runner: StageRunner,
        runtime_profile: RuntimeCandidate,
        seconds_per_character: float,
        force: bool = False,
    ) -> None:
        spec = require_model(model)
        self.model = model
        self._vector_dim = spec.vector_dimension
        self._model_sha256 = spec.sha256
        self._slug = spec.slug
        self._rows = read_query_rows(evaluation_path)
        self._cache_path = cache_path
        self._work_dir = work_dir
        self._remote_dir = remote_dir
        self._stage_runner = stage_runner
        self._profile = runtime_profile
        self._seconds_per_character = seconds_per_character
        self._attach: set[str] = set()
        self._force_flag = force
        if force:
            # The old vectors are what this run replaces; an interrupted run is
            # finished by running the command again, which recomputes what is gone.
            with kaggle_cache_lock(cache_path):
                self._cache().replace_keys(query_keys(self._rows, model))

    def _cache(self, path: Path | None = None) -> QueryEmbeddingCache:
        return QueryEmbeddingCache(
            path or self._cache_path,
            vector_dim=self._vector_dim,
            model_sha256=self._model_sha256,
        )

    def _missing_rows(self) -> list[dict]:
        cache = self._cache()
        return [
            row
            for row in self._rows
            if cache.get(self.model, str(row["query_id"]), str(row.get("query") or ""))
            is None
        ]

    def missing(self) -> Sequence[WorkUnit]:
        return [
            WorkUnit(
                str(row["query_id"]),
                SECONDS_PER_TEXT
                + len(str(row.get("query") or "")) * self._seconds_per_character,
            )
            for row in self._missing_rows()
        ]

    def setup_seconds(self) -> float:
        return SETUP_SECONDS

    def preferred_profile(self, shard: Shard, record: ShardRecord | None) -> str | None:
        if record is None:
            return None
        self._attach.add(shard.shard_id)
        return record.profile

    def run_shard(self, shard: Shard, reserved: ReservedAccount) -> PipelineResult:
        wanted = {unit.key for unit in shard.units}
        path = self._work_dir / f"queries.{self._slug}.shard-{shard.shard_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False) + "\n"
                for row in self._rows
                if str(row["query_id"]) in wanted
            ),
            encoding="utf-8",
        )

        def sink(_job: StageJob, artifact: CloudArtifact) -> None:
            self._merge(artifact.data_path)

        return self._stage_runner(
            stage=StageName.QUERY_EMBED,
            model=self.model,
            input_path=path,
            output_dir=self._remote_dir,
            gguf_root=GGUF_ROOT,
            force=False,
            check_only=False,
            max_runs=1,
            budget_seconds=reserved.budget_seconds,
            runtime_profile=self._profile,
            kaggle_account=reserved.profile,
            resume_remote=(not self._force_flag) or shard.shard_id in self._attach,
            artifact_sink=sink,
        )

    def merge(self, shard: Shard, result: PipelineResult) -> int:
        if result.artifact_path is not None:
            self._merge(result.artifact_path)
        still = {unit.key for unit in self.missing()}
        return sum(1 for unit in shard.units if unit.key not in still)

    def _merge(self, artifact_path: Path) -> None:
        remote = self._cache(artifact_path)
        with kaggle_cache_lock(self._cache_path):
            local = self._cache()
            # A vector already cached is the only one: skip, never compare or replace.
            fresh = [
                record
                for key, record in remote.record_metadata.items()
                if key not in local.record_metadata
            ]
            merge_records(
                self._cache_path,
                fresh,
                key=lambda record: (
                    str(record["model"]),
                    str(record["query_id"]),
                    str(record["query_hash"]),
                ),
                equivalent=lambda left, right: left["embedding"] == right["embedding"],
            )
