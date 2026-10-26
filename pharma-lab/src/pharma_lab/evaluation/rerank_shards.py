"""The rerank step as shards for the Kaggle scheduler.

The unit of work is a query: its candidates are scored together or not at all. What is
missing is read from the local score cache (the source of truth); a shard is a subset of
the candidate file with a manifest that matches the subset, so the same queries always
give the same job and a relaunched command attaches to the kernel already running.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from pharma_lab.artifacts.manifest import (
    ArtifactManifest,
    load_manifest,
    write_json,
)
from pharma_lab.config.paths import GGUF_ROOT
from pharma_lab.evaluation.rerank_cache_checkpoint import RerankCacheCheckpoint
from pharma_lab.evaluation.rerank_score_cache import RerankKey, RerankScoreCache
from pharma_lab.evaluation.retrieval_candidate_artifact import CandidateArtifactReader
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

# Starting a rerank kernel: boot, runtime dataset, model load.
SETUP_SECONDS = 300.0
DEFAULT_SECONDS_PER_PAIR = 1.0

StageRunner = Callable[..., PipelineResult]


def seconds_per_pair(
    selected: Mapping[str, object], measurements: Sequence[Mapping[str, object]]
) -> float:
    """Seconds one candidate pair takes at the profile's chosen runtime level."""
    for measurement in measurements:
        items = measurement.get("items")
        elapsed = measurement.get("elapsed_seconds")
        if (
            measurement.get("status") == "ok"
            and measurement.get("candidate") == selected
            and isinstance(items, int)
            and isinstance(elapsed, float)
            and items > 0
        ):
            return elapsed / items
    return DEFAULT_SECONDS_PER_PAIR


class RerankShardAdapter:
    stage = "rerank"

    def __init__(
        self,
        *,
        model: str,
        candidates: Path,
        cache_path: Path,
        work_dir: Path,
        remote_dir: Path,
        stage_runner: StageRunner,
        runtime_profile: RuntimeCandidate,
        seconds_per_pair: float,
        merge_scores: Callable[[Path], None],
        force: bool = False,
    ) -> None:
        spec = require_model(model)
        if spec.rerank_contract is None:
            raise ValueError(f"Reranker {model} has no scoring contract")
        self.model = model
        self._spec_sha256 = spec.sha256
        self._contract = spec.rerank_contract.sha256
        self._candidates = candidates
        self._cache_path = cache_path
        self._work_dir = work_dir
        self._remote_dir = remote_dir
        self._stage_runner = stage_runner
        self._profile = runtime_profile
        self._seconds_per_pair = seconds_per_pair
        self._merge_scores = merge_scores
        self._force = force
        self._attach: set[str] = set()
        self._expected: dict[str, set[RerankKey]] | None = None
        self._order: list[str] = []

    def _expected_by_query(self) -> dict[str, set[RerankKey]]:
        if self._expected is None:
            cache = self._cache()
            expected: dict[str, set[RerankKey]] = {}
            for key in sorted(
                cache.expected_keys_from_candidates(self._candidates, self.model)
            ):
                expected.setdefault(key.query_id, set()).add(key)
            self._order = [
                str(row["query_id"])
                for row in CandidateArtifactReader.from_data_path(self._candidates)
            ]
            self._expected = expected
        return self._expected

    def _cache(self) -> RerankScoreCache:
        with kaggle_cache_lock(self._cache_path):
            return RerankScoreCache(
                self._cache_path,
                model_sha256=self._spec_sha256,
                request_contract_sha256=self._contract,
            )

    def _missing_pairs(self) -> Counter[str]:
        have = self._cache().records
        return Counter(
            query
            for query, keys in self._expected_by_query().items()
            for key in keys
            if key not in have
        )

    def missing(self) -> Sequence[WorkUnit]:
        missing = self._missing_pairs()
        return [
            WorkUnit(query, missing[query] * self._seconds_per_pair)
            for query in self._order_or_load()
            if missing[query]
        ]

    def _order_or_load(self) -> list[str]:
        self._expected_by_query()
        return self._order

    def setup_seconds(self) -> float:
        return SETUP_SECONDS

    def preferred_profile(self, shard: Shard, record: ShardRecord | None) -> str | None:
        if record is None:
            return None
        self._attach.add(shard.shard_id)
        return record.profile

    def run_shard(self, shard: Shard, reserved: ReservedAccount) -> PipelineResult:
        subset = self._write_subset(shard)

        def sink(_job: StageJob, artifact: CloudArtifact) -> None:
            self._merge_scores(artifact.data_path)

        return self._stage_runner(
            stage=StageName.RERANK,
            model=self.model,
            input_path=subset,
            output_dir=self._remote_dir,
            gguf_root=GGUF_ROOT,
            force=False,
            # After --force the account's old scores are the very thing being replaced.
            resume_remote=(not self._force) or shard.shard_id in self._attach,
            check_only=False,
            max_runs=1,
            budget_seconds=reserved.budget_seconds,
            runtime_profile=self._profile,
            kaggle_account=reserved.profile,
            artifact_sink=sink,
            local_checkpoint=RerankCacheCheckpoint(self._cache_path),
        )

    def merge(self, shard: Shard, result: PipelineResult) -> int:
        if result.artifact_path is not None:
            self._merge_scores(result.artifact_path)
            self._discard(result.artifact_path)
        still = self._missing_pairs()
        return sum(1 for unit in shard.units if not still[unit.key])

    def _discard(self, artifact_path: Path) -> None:
        """Remove a merged complete job directory; never anything outside the staging root."""
        root = self._remote_dir.resolve()
        directory = artifact_path.resolve().parent
        if directory == root or not directory.is_relative_to(root):
            raise ValueError(
                f"completed artifact is outside Kaggle rerank staging root: {directory}"
            )
        shutil.rmtree(directory)

    def _write_subset(self, shard: Shard) -> Path:
        wanted = {unit.key for unit in shard.units}
        directory = self._work_dir / f"shard-{shard.shard_id}"
        directory.mkdir(parents=True, exist_ok=True)
        cache = self._cache()
        have = cache.records
        lines: list[str] = []
        pairs = 0
        for raw in self._candidates.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            if str(row["query_id"]) not in wanted:
                continue
            # The kernel scores every pair it receives; pairs are scored one by one, so
            # only the ones the cache lacks are sent.
            missing = [
                item
                for item in row["candidates"]
                if cache.item_key(self.model, row, item) not in have
            ]
            if missing:
                lines.append(
                    json.dumps({**row, "candidates": missing}, ensure_ascii=False)
                )
                pairs += len(missing)
        data = directory / self._candidates.name
        data.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
        source = load_manifest(self._candidates.with_name("manifest.json"))
        manifest = ArtifactManifest.create(
            artifact_type=source.artifact_type,
            data_path=data,
            record_count=len(lines),
            identity={**source.identity, "pair_count": pairs},
        )
        # The source's timestamp keeps the file, and so the job identity, stable.
        write_json(
            directory / "manifest.json",
            replace(manifest, created_at=source.created_at).to_dict(),
        )
        return data
