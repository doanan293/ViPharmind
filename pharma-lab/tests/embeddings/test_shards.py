from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from tests.integrations.kaggle.factories import cloud_artifact, stage_job
from tests.integrations.kaggle.test_scheduler import contexts

from pharma_lab.artifacts.manifest import Completion
from pharma_lab.cache.text_embeddings import (
    EmbeddingInput,
    text_sha256,
    write_embedding_inputs,
)
from pharma_lab.embeddings.service import open_text_cache
from pharma_lab.embeddings.shards import (
    TextEmbeddingShardAdapter,
    seconds_per_character,
)
from pharma_lab.integrations.kaggle.job_registry import ShardRecord
from pharma_lab.integrations.kaggle.models import PipelineResult, StageName
from pharma_lab.integrations.kaggle.quota import AccountQuota
from pharma_lab.integrations.kaggle.scheduler import shard_margin_seconds
from pharma_lab.integrations.kaggle.sessions import ReservedAccount
from pharma_lab.integrations.kaggle.shards import Shard, WorkUnit, plan_shards
from pharma_lab.runtime.catalog import require_model
from pharma_lab.runtime.runtime_profiles import RuntimeCandidate

MODEL = "qwen3-embedding:4b-q8_0"
DIMS = require_model(MODEL).vector_dimension or 0
TEXTS = ["alpha", "bravo bravo", "charlie charlie charlie", "delta"]


def item(text: str) -> EmbeddingInput:
    return EmbeddingInput(text_sha256(text), text)


def vector(seed: float) -> list[float]:
    return [seed] * DIMS


class Runner:
    """Stands in for `run_kaggle_stage`: embeds the shard's file into a remote cache."""

    def __init__(self, root: Path, fixed: float | None = None) -> None:
        self.calls: list[dict] = []
        self.root = root
        self.fixed = fixed
        self.job = stage_job(root / "runner", stage=StageName.CORPUS_EMBED)

    def __call__(self, **kwargs) -> PipelineResult:
        self.calls.append(kwargs)
        rows = [
            json.loads(line)
            for line in Path(kwargs["input_path"]).read_text().splitlines()
        ]
        remote = open_text_cache(
            self.root / f"remote-{len(self.calls)}" / "text_embeddings.jsonl", MODEL
        )
        for row in rows:
            seed = self.fixed if self.fixed is not None else len(row["embedding_text"])
            remote.set(row["embedding_text_sha256"], vector(float(seed)))
        return PipelineResult(
            self.job, Completion(len(rows), len(rows), 0), (), remote.path, 1
        )


def profile() -> RuntimeCandidate:
    space = require_model(MODEL).embedding_search_space
    assert space is not None
    return space.corpus.candidates[0]


def reserved(name: str = "acc1") -> ReservedAccount:
    quota = AccountQuota(name, f"user-{name}", 20.0, 30.0, None)
    return ReservedAccount(contexts(name)[0], quota, 7200)


def make(
    tmp_path: Path,
    *,
    force: bool = False,
    cached: tuple[str, ...] = (),
    runner: Runner | None = None,
):
    inputs = tmp_path / "embedding_inputs.jsonl"
    write_embedding_inputs([item(t) for t in TEXTS], inputs)
    cache_path = tmp_path / "cache.jsonl"
    cache = open_text_cache(cache_path, MODEL)
    for text in cached:
        cache.set(text_sha256(text), vector(0.5))
    runner = runner or Runner(tmp_path)
    adapter = TextEmbeddingShardAdapter(
        model=MODEL,
        inputs_path=inputs,
        cache_path=cache_path,
        work_dir=tmp_path / "work",
        remote_dir=tmp_path / "remote",
        stage_runner=runner,
        runtime_profile=profile(),
        seconds_per_character=0.01,
        force=force,
    )
    return adapter, runner, cache_path


def test_missing_texts_only_are_units(tmp_path: Path) -> None:
    adapter, _, _ = make(tmp_path, cached=("alpha", "delta"))

    units = adapter.missing()

    assert {unit.key for unit in units} == {
        text_sha256("bravo bravo"),
        text_sha256("charlie charlie charlie"),
    }
    by_key = {unit.key: unit.seconds for unit in units}
    assert by_key[text_sha256("bravo bravo")] == pytest.approx(0.12)
    assert by_key[text_sha256("charlie charlie charlie")] == pytest.approx(0.24)


def test_shards_cover_all_missing_texts_once(tmp_path: Path) -> None:
    adapter, _, _ = make(tmp_path)
    units = adapter.missing()
    shards = plan_shards(
        [WorkUnit(u.key, 4000.0, u.group) for u in units],  # long enough to split
        setup_seconds=adapter.setup_seconds(),
        budget_seconds=21_600,
        margin_seconds=shard_margin_seconds(21_600),
        slots=4,
    )

    covered = [unit.key for shard in shards for unit in shard.units]

    assert len(shards) > 1
    assert sorted(covered) == sorted(unit.key for unit in units)


def test_shard_file_holds_exactly_the_shard_texts(tmp_path: Path) -> None:
    adapter, runner, _ = make(tmp_path)
    shard = Shard(
        "abc",
        tuple(WorkUnit(text_sha256(t), 1.0) for t in ("delta", "alpha")),
        "",
    )

    adapter.run_shard(shard, reserved("acc2"))

    call = runner.calls[0]
    path = Path(call["input_path"])
    assert path.name == "missing_inputs.shard-abc.jsonl"
    texts = [
        json.loads(line)["embedding_text"] for line in path.read_text().splitlines()
    ]
    assert sorted(texts) == ["alpha", "delta"]
    assert call["stage"] is StageName.CORPUS_EMBED
    assert call["kaggle_account"] == "acc2"
    assert call["budget_seconds"] == 7200
    assert (call["force"], call["resume_remote"], call["max_runs"]) == (False, True, 1)


def test_merge_keeps_one_vector_per_text(tmp_path: Path) -> None:
    adapter, runner, cache_path = make(tmp_path)
    shard = Shard("abc", tuple(WorkUnit(text_sha256(t), 1.0) for t in TEXTS[:2]), "")
    result = adapter.run_shard(shard, reserved())

    first = adapter.merge(shard, result)
    second = adapter.merge(shard, result)

    assert first == second == 2
    lines = cache_path.read_text().splitlines()
    assert len(lines) == 2
    cache = open_text_cache(cache_path, MODEL)
    assert cache.get(text_sha256("alpha")) == vector(5.0)
    assert {unit.key for unit in adapter.missing()} == {
        text_sha256(t) for t in TEXTS[2:]
    }
    assert len(runner.calls) == 1


def test_partial_artifacts_are_merged_as_they_arrive(tmp_path: Path) -> None:
    partial = open_text_cache(tmp_path / "partial" / "text_embeddings.jsonl", MODEL)
    partial.set(text_sha256("alpha"), vector(9.0))

    class Sinking(Runner):
        def __call__(self, **kwargs) -> PipelineResult:
            artifact = replace(
                cloud_artifact(Completion(4, 1, 3)), data_path=partial.path
            )
            kwargs["artifact_sink"](self.job, artifact)
            return PipelineResult(self.job, Completion(4, 1, 3), (), None, 1)

    adapter, _, cache_path = make(tmp_path, runner=Sinking(tmp_path))
    shard = Shard("abc", tuple(WorkUnit(text_sha256(t), 1.0) for t in TEXTS), "")
    result = adapter.run_shard(shard, reserved())

    assert adapter.merge(shard, result) == 1
    assert open_text_cache(cache_path, MODEL).get(text_sha256("alpha")) == vector(9.0)
    assert text_sha256("alpha") not in {u.key for u in adapter.missing()}


def test_force_sends_everything(tmp_path: Path) -> None:
    adapter, _, _ = make(
        tmp_path, force=True, cached=("alpha", "delta"), runner=Runner(tmp_path, 0.5)
    )

    units = adapter.missing()

    assert len(units) == len(TEXTS)
    shard = Shard("abc", tuple(units[:1]), "")
    result = adapter.run_shard(shard, reserved())
    adapter.merge(shard, result)
    assert len(adapter.missing()) == len(TEXTS) - 1  # done in this command


def test_a_recorded_kernel_makes_the_shard_attach_even_when_forced(
    tmp_path: Path,
) -> None:
    adapter, runner, _ = make(tmp_path, force=True)
    shard = Shard("abc", (WorkUnit(text_sha256("alpha"), 1.0),), "")
    record = ShardRecord(
        "abc",
        "corpus-embed",
        "acc3",
        (text_sha256("alpha"),),
        "2026-10-23T00:00:00+00:00",
        60,
    )

    adapter.run_shard(shard, reserved())
    assert adapter.preferred_profile(shard, record) == "acc3"
    adapter.run_shard(shard, reserved())

    assert [c["resume_remote"] for c in runner.calls] == [False, True]


def test_cost_per_character_comes_from_the_profile_measurements() -> None:
    selected = {"concurrency": 2}
    measurements = (
        {
            "candidate": selected,
            "status": "ok",
            "items": 10,
            "input_characters": 1000,
            "elapsed_seconds": 5.0,
        },
    )

    assert seconds_per_character(selected, measurements) == pytest.approx(0.005)
    assert seconds_per_character(selected, ()) > 0
