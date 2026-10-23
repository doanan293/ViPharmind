"""The corpus-embedding step as shards for the Kaggle scheduler.

The unit of work is one text, named by its digest. What is missing is read from the local
text cache (the source of truth); a shard is a file of the texts it embeds, so the same
texts always give the same job and a relaunched command attaches to the running kernel.
Every artifact, partial ones included, is merged into the cache as it arrives.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from pharma_lab.cache.jsonl_records import merge_records
from pharma_lab.cache.text_embeddings import (
    EmbeddingInput,
    cache_record_key,
    read_embedding_inputs,
    write_embedding_inputs,
)
from pharma_lab.config.paths import GGUF_ROOT
from pharma_lab.embeddings.service import open_text_cache
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
from pharma_lab.runtime.runtime_profiles import RuntimeCandidate

# Starting an embedding kernel: boot, runtime dataset, model load.
SETUP_SECONDS = 300.0
DEFAULT_SECONDS_PER_CHARACTER = 0.0002
# Every text also costs a request slot, whatever its length.
SECONDS_PER_TEXT = 0.01

StageRunner = Callable[..., PipelineResult]


def seconds_per_character(
    selected: Mapping[str, object], measurements: Sequence[Mapping[str, object]]
) -> float:
    """Seconds one input character takes at the profile's chosen runtime level."""
    for measurement in measurements:
        characters = measurement.get("input_characters")
        elapsed = measurement.get("elapsed_seconds")
        if (
            measurement.get("status") == "ok"
            and measurement.get("candidate") == selected
            and isinstance(characters, int)
            and isinstance(elapsed, float)
            and characters > 0
        ):
            return elapsed / characters
    return DEFAULT_SECONDS_PER_CHARACTER


class TextEmbeddingShardAdapter:
    stage = "corpus-embed"

    def __init__(
        self,
        *,
        model: str,
        inputs_path: Path,
        cache_path: Path,
        work_dir: Path,
        remote_dir: Path,
        stage_runner: StageRunner,
        runtime_profile: RuntimeCandidate,
        seconds_per_character: float,
        force: bool = False,
    ) -> None:
        self.model = model
        self._inputs_path = inputs_path
        self._cache_path = cache_path
        self._work_dir = work_dir
        self._remote_dir = remote_dir
        self._stage_runner = stage_runner
        self._profile = runtime_profile
        self._seconds_per_character = seconds_per_character
        self._force = force
        self._attach: set[str] = set()
        self._inputs: dict[str, EmbeddingInput] | None = None
        # Digests the cache holds, read once: loading a cache of 2,560-dimension vectors
        # takes seconds, and only this command adds to it. With --force the cache's
        # vectors do not count; a text is done once this command has merged it.
        self._done: set[str] | None = None

    def _all(self) -> dict[str, EmbeddingInput]:
        if self._inputs is None:
            self._inputs = {
                item.embedding_text_sha256: item
                for item in read_embedding_inputs(self._inputs_path)
            }
        return self._inputs

    def _finished(self) -> set[str]:
        if self._done is None:
            self._done = (
                set()
                if self._force
                else set(open_text_cache(self._cache_path, self.model).digests())
            )
        return self._done

    def missing(self) -> Sequence[WorkUnit]:
        finished = self._finished()
        return [
            WorkUnit(
                digest,
                SECONDS_PER_TEXT
                + len(item.embedding_text) * self._seconds_per_character,
            )
            for digest, item in sorted(self._all().items())
            if digest not in finished
        ]

    def setup_seconds(self) -> float:
        return SETUP_SECONDS

    def preferred_profile(self, shard: Shard, record: ShardRecord | None) -> str | None:
        if record is None:
            return None
        self._attach.add(shard.shard_id)
        return record.profile

    def run_shard(self, shard: Shard, reserved: ReservedAccount) -> PipelineResult:
        inputs = self._all()
        path = self._work_dir / f"missing_inputs.shard-{shard.shard_id}.jsonl"
        write_embedding_inputs((inputs[unit.key] for unit in shard.units), path)

        def sink(_job: StageJob, artifact: CloudArtifact) -> None:
            self._merge(artifact.data_path)

        return self._stage_runner(
            stage=StageName.CORPUS_EMBED,
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
            # After --force the account's old vectors are what is being replaced.
            resume_remote=(not self._force) or shard.shard_id in self._attach,
            artifact_sink=sink,
        )

    def merge(self, shard: Shard, result: PipelineResult) -> int:
        if result.artifact_path is not None:
            self._merge(result.artifact_path)
        finished = self._finished()
        return sum(1 for unit in shard.units if unit.key in finished)

    def _merge(self, artifact_path: Path) -> None:
        remote = open_text_cache(artifact_path, self.model)
        digests = remote.digests()
        with kaggle_cache_lock(self._cache_path):
            merge_records(
                self._cache_path,
                remote.records_for(digests),
                key=cache_record_key,
                equivalent=lambda left, right: left["embedding"] == right["embedding"],
            )
        self._finished().update(digests)
