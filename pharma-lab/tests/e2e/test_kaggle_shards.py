from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from tests.e2e.test_work_state import done, golden, run_json, tar_of, write_answers
from tests.integrations.kaggle.factories import cloud_artifact, stage_job
from tests.integrations.kaggle.test_scheduler import contexts

from pharma_lab.artifacts.manifest import Completion
from pharma_lab.e2e.configs import E2EConfig
from pharma_lab.e2e.golden import Category
from pharma_lab.e2e.kaggle_shards import (
    DEFAULT_TURN_SECONDS,
    SEPARATOR,
    E2EShardAdapter,
    Entry,
    check_no_decision_roles,
    make_plan,
)
from pharma_lab.e2e.llm_presets import PRESETS
from pharma_lab.e2e.records import AnswerRecord
from pharma_lab.integrations.kaggle.job_registry import ShardRecord
from pharma_lab.integrations.kaggle.models import (
    PipelineResult,
    StageName,
)
from pharma_lab.integrations.kaggle.quota import AccountQuota
from pharma_lab.integrations.kaggle.sessions import ReservedAccount
from pharma_lab.integrations.kaggle.shards import Shard, WorkUnit
from pharma_lab.runtime.runtime_profiles import RuntimeCandidate

ITEMS = [golden(n) for n in range(4)]
FULL = Entry(E2EConfig.FULL)
ONE_STEP = Entry(E2EConfig.ONE_STEP)


class Runner:
    """Stands in for `run_kaggle_stage`: records the call, optionally delivers a tar."""

    def __init__(self, root: Path, deliver: Path | None = None) -> None:
        self.calls: list[dict] = []
        self.deliver = deliver
        self.job = stage_job(root / "runner", stage=StageName.E2E_RUN)

    def __call__(self, **kwargs) -> PipelineResult:
        self.calls.append(kwargs)
        if self.deliver is not None:
            artifact = replace(
                cloud_artifact(Completion(1, 1, 0)), data_path=self.deliver
            )
            kwargs["artifact_sink"](self.job, artifact)
        return PipelineResult(self.job, Completion(1, 1, 0), (), None, 1)


def static_builder(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "golden_e2e.jsonl").write_text("{}\n", encoding="utf-8")


def reserved(profile: str = "acc2", budget: int = 7200) -> ReservedAccount:
    quota = AccountQuota(profile, f"user-{profile}", 20.0, 30.0, None)
    return ReservedAccount(contexts(profile)[0], quota, budget)


def adapter(
    tmp_path: Path,
    runner: Runner | None = None,
    *,
    entries=(FULL,),
    categories=None,
    limit=None,
    latency=False,
    credentials=None,
    on_merged=None,
) -> E2EShardAdapter:
    plan = make_plan(
        run_name="r1",
        entries=entries,
        golden_path=tmp_path / "golden.jsonl",
        categories=categories,
        limit=limit,
        llm=PRESETS["qwen"],
        latency=latency,
    )
    return E2EShardAdapter(
        plan,
        golden=ITEMS,
        run_root=tmp_path / "runs" / plan.run_name,
        work_dir=tmp_path / "work",
        stage_runner=runner or Runner(tmp_path),
        reranker_profile=lambda _profile: RuntimeCandidate(
            server_slots=2,
            concurrency=2,
            request_batch_size=1,
            context_per_slot=4096,
            logical_batch_size=4096,
            physical_batch_size=4096,
        ),
        build_static=static_builder,
        commit="abc1234",
        credentials=credentials,
        on_merged=on_merged,
    )


def shard_of(keys: list[str]) -> Shard:
    return Shard("s1", tuple(WorkUnit(key, 10.0, "A") for key in keys), "A")


def key(label: str, item) -> str:
    return f"{label}{SEPARATOR}{item.item_id}"


def test_missing_units_cost_uses_existing_latencies(tmp_path: Path) -> None:
    subject = adapter(tmp_path)
    write_answers(
        subject.run_root,
        "full",
        [
            AnswerRecord(
                item_id=ITEMS[0].item_id,
                config="full",
                status="completed",
                latency_seconds=40.0,
            )
        ],
    )

    units = {unit.key: unit for unit in subject.missing()}

    assert key("full", ITEMS[0]) not in units
    # Items of the same category cost what the finished one did; the pool runs 8 turns.
    assert units[key("full", ITEMS[1])].seconds == pytest.approx(40.0 / 8)
    fresh = adapter(tmp_path / "other")
    assert next(iter(fresh.missing())).seconds == pytest.approx(
        DEFAULT_TURN_SECONDS / 8
    )


def test_limit_and_category_define_the_universe(tmp_path: Path) -> None:
    subject = adapter(tmp_path, limit=2)
    assert len(subject.missing()) == 2

    nothing = adapter(tmp_path / "x", categories=[Category.INJECTION])
    assert nothing.missing() == []


def test_job_json_is_deterministic_for_the_same_pairs(tmp_path: Path) -> None:
    runner = Runner(tmp_path)
    subject = adapter(tmp_path, runner, entries=(FULL, ONE_STEP))
    keys = [key("one-step", ITEMS[1]), key("full", ITEMS[2]), key("full", ITEMS[0])]

    subject.run_shard(shard_of(keys), reserved())
    first = Path(runner.calls[0]["input_path"]).read_bytes()
    subject.run_shard(shard_of(list(reversed(keys))), reserved())
    second = Path(runner.calls[1]["input_path"]).read_bytes()

    assert first == second
    job = json.loads(first)
    assert job["llm"] == "qwen"
    assert [(e["config"], e["item_ids"]) for e in job["shards"]] == [
        ("full", [ITEMS[0].item_id, ITEMS[2].item_id]),
        ("one-step", [ITEMS[1].item_id]),
    ]


def test_run_shard_calls_the_stage_with_the_reserved_account(tmp_path: Path) -> None:
    runner = Runner(tmp_path)
    subject = adapter(tmp_path, runner)

    subject.run_shard(shard_of([key("full", ITEMS[0])]), reserved("acc3", 5400))

    call = runner.calls[0]
    assert call["stage"] is StageName.E2E_RUN
    assert call["kaggle_account"] == "acc3"
    assert call["budget_seconds"] == 5400
    assert call["max_runs"] == 1
    assert call["resume_remote"] is False
    assert (Path(call["input_path"]).parent / "golden_e2e.jsonl").is_file()


def test_a_shard_with_a_recorded_kernel_attaches_to_it(tmp_path: Path) -> None:
    runner = Runner(tmp_path)
    subject = adapter(tmp_path, runner)
    shard = shard_of([key("full", ITEMS[0])])
    record = ShardRecord("s1", "e2e-run", "acc2", (), "2026-10-23T00:00:00+00:00", 60)

    assert subject.preferred_profile(shard, record) == "acc2"
    assert subject.preferred_profile(shard, None) is None
    subject.run_shard(shard, reserved("acc2"))

    assert runner.calls[0]["resume_remote"] is True


def test_rerun_merges_into_existing_answers_instead_of_refusing(tmp_path: Path) -> None:
    archive = tar_of(
        tmp_path / "out.tar",
        {
            "full/answers.jsonl": (
                done(ITEMS[1].item_id).model_dump_json() + "\n"
            ).encode(),
            "full/run.json": json.dumps(run_json()).encode(),
        },
    )
    runner = Runner(tmp_path, deliver=archive)
    subject = adapter(tmp_path, runner)
    write_answers(subject.run_root, "full", [done(ITEMS[0].item_id)])
    (subject.run_root / "full" / "run.json").write_text(
        json.dumps(run_json()), encoding="utf-8"
    )
    shard = shard_of([key("full", ITEMS[1])])

    result = subject.run_shard(shard, reserved())
    merged = subject.merge(shard, result)

    ids = [
        json.loads(line)["item_id"]
        for line in (subject.run_root / "full" / "answers.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert ids == [ITEMS[0].item_id, ITEMS[1].item_id]
    assert merged == 1
    assert key("full", ITEMS[1]) not in {u.key for u in subject.missing()}


def test_latency_mode_forces_one_shard_with_concurrency_one(tmp_path: Path) -> None:
    subject = adapter(tmp_path, latency=True)

    assert subject.plan.run_name == "r1-c1"
    assert subject.plan.concurrency == 1
    assert subject.run_root.name == "r1-c1"
    assert next(iter(subject.missing())).seconds == pytest.approx(DEFAULT_TURN_SECONDS)


def test_latency_mode_rejects_parallel_above_one(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="--parallel 1"):
        make_plan(
            run_name="r",
            entries=[FULL],
            golden_path=tmp_path / "g",
            categories=None,
            limit=None,
            llm=PRESETS["qwen"],
            latency=True,
            parallel=2,
        )


def test_latency_mode_rejects_several_configurations(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="one configuration"):
        make_plan(
            run_name="r",
            entries=[FULL, ONE_STEP],
            golden_path=tmp_path / "g",
            categories=None,
            limit=None,
            llm=PRESETS["qwen"],
            latency=True,
        )


def test_decision_roles_in_local_env_stop_the_command(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "PHARMA_LLM__DEFAULT__API_KEY=x\nPHARMA_LLM__DEFAULT__MODEL=m\nPHARMA_LLM__ROLES__GUARDRAIL__PROVIDER=systemone\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"guardrail.*systemone"):
        check_no_decision_roles(env)
    quiet = tmp_path / "quiet.env"
    quiet.write_text("", encoding="utf-8")
    check_no_decision_roles(quiet)


def test_nothing_missing_means_no_units_and_no_stage_call(tmp_path: Path) -> None:
    runner = Runner(tmp_path)
    subject = adapter(tmp_path, runner)
    write_answers(subject.run_root, "full", [done(item.item_id) for item in ITEMS])

    assert subject.missing() == []
    assert runner.calls == []
    assert subject.report().done == len(ITEMS)


def test_credentials_go_to_the_job_directory_as_a_sidecar_without_secrets(
    tmp_path: Path,
) -> None:
    secrets = tmp_path / "auth"
    secrets.mkdir()
    (secrets / "claude-a.json").write_text('{"type": "claude", "k": "SECRET-TOKEN"}')
    used: list[tuple[str, str]] = []

    class Credentials:
        fingerprint = "ab" * 32
        stage_dir = secrets

        def slug(self, profile: str) -> str:
            return f"pipeline-cred-{profile}"

        def used(self, profile: str, reference: str) -> None:
            used.append((profile, reference))

    runner = Runner(tmp_path)
    subject = adapter(tmp_path, runner, credentials=Credentials())

    subject.run_shard(shard_of([key("full", ITEMS[0])]), reserved("acc2"))

    directory = Path(runner.calls[0]["input_path"]).parent
    sidecar = json.loads((directory / "proxy_credentials.json").read_text())
    assert sidecar == {
        "local_dir": str(secrets),
        "slug": "pipeline-cred-acc2",
        "sha256": "ab" * 32,
    }
    assert used == [("acc2", "user-acc2/pipeline-cred-acc2")]
    assert "SECRET-TOKEN" not in (directory / "e2e_job.json").read_text()
    assert "SECRET-TOKEN" not in (directory / "proxy_credentials.json").read_text()


def test_without_credentials_there_is_no_sidecar(tmp_path: Path) -> None:
    runner = Runner(tmp_path)
    subject = adapter(tmp_path, runner)

    subject.run_shard(shard_of([key("full", ITEMS[0])]), reserved())

    directory = Path(runner.calls[0]["input_path"]).parent
    assert not (directory / "proxy_credentials.json").exists()


def test_a_stale_sidecar_from_an_earlier_run_is_removed(tmp_path: Path) -> None:
    runner = Runner(tmp_path)
    subject = adapter(tmp_path, runner)
    directory = tmp_path / "work" / "s1"
    directory.mkdir(parents=True)
    (directory / "proxy_credentials.json").write_text("{}", encoding="utf-8")

    subject.run_shard(shard_of([key("full", ITEMS[0])]), reserved())

    assert not (directory / "proxy_credentials.json").exists()


def test_merged_answers_notify_the_follower_with_the_shard_labels(
    tmp_path: Path,
) -> None:
    archive = tar_of(
        tmp_path / "out.tar",
        {
            "full/answers.jsonl": (
                done(ITEMS[1].item_id).model_dump_json() + "\n"
            ).encode(),
            "full/run.json": json.dumps(run_json()).encode(),
        },
    )
    notified: list[list[str]] = []
    subject = adapter(
        tmp_path,
        Runner(tmp_path, deliver=archive),
        on_merged=lambda labels: notified.append(list(labels)),
    )
    shard = shard_of([key("full", ITEMS[1])])

    result = subject.run_shard(shard, reserved())
    subject.merge(shard, result)
    subject.merge(shard, result)  # nothing new the second time

    assert notified == [["full"]]
