from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pytest
from tests.e2e.test_kaggle_shards import ITEMS, adapter, key
from tests.e2e.test_work_state import done, write_answers
from typer.testing import CliRunner

import pharma_lab.cli.commands.e2e as e2e_command
from pharma_lab.cli.app import app
from pharma_lab.e2e.kaggle_launch import (
    EXIT_PAUSED,
    EXIT_STUCK,
    LaunchOptions,
    LaunchOutcome,
)
from pharma_lab.e2e.kaggle_shards import E2EShardAdapter
from pharma_lab.integrations.kaggle.job_registry import JobRegistry, ShardRecord
from pharma_lab.integrations.kaggle.quota import AccountQuota
from pharma_lab.integrations.kaggle.scheduler import SchedulerStop

runner = CliRunner()
BASE = [
    "--json",
    "e2e",
    "run",
    "--backend",
    "kaggle",
    "--run",
    "r1",
    "--config",
    "full",
]


@pytest.fixture
def wired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    subject = adapter(tmp_path)
    work = tmp_path / "e2e-kaggle"
    captured: dict[str, object] = {}

    def fake_adapter(
        plan, *, budget_seconds, credentials=None, on_merged=None
    ) -> E2EShardAdapter:
        captured["plan"] = plan
        captured["credentials"] = credentials
        captured["on_merged"] = on_merged
        captured["budget"] = budget_seconds
        return subject

    monkeypatch.setattr(e2e_command, "kaggle_adapter", fake_adapter)
    monkeypatch.setattr(e2e_command, "E2E_KAGGLE_WORK_DIR", work)
    monkeypatch.setattr(e2e_command, "check_no_decision_roles", lambda _env: None)
    captured["adapter"] = subject
    captured["work"] = work
    return captured


class Launcher:
    """Stands in for `launch`: records the options, returns a fixed outcome."""

    def __init__(self, result: LaunchOutcome) -> None:
        self.result = result
        self.options: LaunchOptions | None = None

    def __call__(self, adapter_, options: LaunchOptions, **_kwargs) -> LaunchOutcome:
        self.options = options
        return self.result


def outcome(code: int, stop: SchedulerStop | None = None, stuck: int = 0):
    return LaunchOutcome(code, stop, 2, 7, 3, stuck, ("table-row",))


@pytest.mark.parametrize(
    ("code", "stop"),
    [
        (0, SchedulerStop.COMPLETE),
        (EXIT_PAUSED, SchedulerStop.QUOTA_EXHAUSTED),
        (EXIT_STUCK, SchedulerStop.STUCK),
    ],
)
def test_cli_exit_codes_for_done_paused_and_stuck(wired, monkeypatch, code, stop):
    monkeypatch.setattr(e2e_command, "launch", Launcher(outcome(code, stop)))

    result = runner.invoke(app, BASE)

    assert result.exit_code == code, result.output
    payload = json.loads(result.stdout.splitlines()[-1])
    assert payload["details"]["stop"] == stop.value
    assert payload["details"]["merged"] == 7


def test_run_passes_the_scheduling_flags_through(wired, monkeypatch):
    launcher = Launcher(outcome(0, SchedulerStop.COMPLETE))
    monkeypatch.setattr(e2e_command, "launch", launcher)

    result = runner.invoke(
        app,
        [
            *BASE,
            "--kaggle-account",
            "acc1,acc3",
            "--parallel",
            "3",
            "--budget-seconds",
            "7200",
            "--max-sessions",
            "5",
            "--drain",
            "--retry-stuck",
            "--pipeline-option",
            "guard=false",
        ],
    )

    assert result.exit_code == 0
    options = launcher.options
    assert options is not None
    assert (options.kaggle_account, options.parallel, options.budget_seconds) == (
        "acc1,acc3",
        3,
        7200,
    )
    assert (options.max_sessions, options.drain) == (5, True)
    plan = wired["plan"]
    assert plan.retry_stuck and plan.labels == ("full+guard=false",)


def test_latency_run_lands_in_the_c1_directory(wired, monkeypatch):
    launcher = Launcher(outcome(0, SchedulerStop.COMPLETE))
    monkeypatch.setattr(e2e_command, "launch", launcher)

    result = runner.invoke(app, [*BASE, "--latency"])

    assert result.exit_code == 0
    plan = wired["plan"]
    assert (plan.run_name, plan.concurrency, plan.latency) == ("r1-c1", 1, True)
    assert launcher.options is not None
    assert launcher.options.parallel == 1


def test_latency_run_refuses_parallel_above_one(wired):
    result = runner.invoke(app, [*BASE, "--latency", "--parallel", "2"])

    assert result.exit_code == 2


def test_proxy_preset_without_the_flag_is_refused(wired):
    result = runner.invoke(app, [*BASE, "--llm", "gemini"])

    assert result.exit_code == 2
    assert "--with-proxy-credentials" in " ".join(
        result.output.replace("│", " ").split()
    )


def test_the_proxy_flag_is_refused_for_a_preset_that_does_not_use_it(wired):
    result = runner.invoke(app, [*BASE, "--with-proxy-credentials"])

    assert result.exit_code == 2


def test_the_proxy_flag_hands_the_credential_dataset_to_the_adapter(wired, monkeypatch):
    sentinel = object()
    entered: list[dict[str, object]] = []

    @contextmanager
    def fake_session(plan, **kwargs):
        entered.append(kwargs)
        yield sentinel

    launcher = Launcher(outcome(0, SchedulerStop.COMPLETE))
    monkeypatch.setattr(e2e_command, "credential_session", fake_session)
    monkeypatch.setattr(e2e_command, "launch", launcher)

    result = runner.invoke(
        app,
        [
            *BASE,
            "--llm",
            "opus",
            "--with-proxy-credentials",
            "--proxy-credential",
            "claude-a.json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert wired["credentials"] is sentinel
    assert entered[0]["names"] == ["claude-a.json"]


def test_an_unknown_preset_lists_the_valid_names(wired):
    result = runner.invoke(app, [*BASE, "--llm", "gpt"])

    assert result.exit_code == 2
    assert "gemini, opus, qwen" in " ".join(result.output.replace("│", " ").split())


def test_kaggle_flags_are_refused_for_a_local_run(wired):
    result = runner.invoke(
        app, ["e2e", "run", "--run", "r1", "--config", "full", "--drain"]
    )

    assert result.exit_code == 2


def test_status_lists_live_shards_and_quota(wired, monkeypatch):
    subject = wired["adapter"]
    write_answers(subject.run_root, "full", [done(ITEMS[0].item_id)])
    JobRegistry(wired["work"] / "r1" / "jobs.json").register(
        ShardRecord(
            "s1",
            "e2e-run",
            "acc2",
            (key("full", ITEMS[1]),),
            "2026-10-23T00:00:00+00:00",
            10_800,
        )
    )
    monkeypatch.setattr(
        e2e_command,
        "account_quotas",
        lambda _account: [
            AccountQuota("acc1", "u1", 12.5, 30.0, None),
            AccountQuota("acc2", "u2", 3.0, 30.0, None),
        ],
    )

    result = runner.invoke(
        app, ["--json", "e2e", "status", "--run", "r1", "--config", "full"]
    )

    assert result.exit_code == 0
    details = json.loads(result.stdout)["details"]
    assert details["label.full"] == f"1/{len(ITEMS)} stuck=0"
    assert details["kernel.s1"].startswith("acc2 units=1")
    assert details["quota.acc1"] == "12.5h of 30.0h"
    assert float(details["gpu_hours_needed"]) > 0


def test_credential_session_lists_uploads_and_deletes_the_dataset(
    tmp_path, monkeypatch, capsys
):
    from tests.e2e.test_kaggle_shards import FULL
    from tests.integrations.kaggle.test_scheduler import contexts

    import pharma_lab.integrations.kaggle.service as kaggle_service
    from pharma_lab.e2e.kaggle_shards import make_plan
    from pharma_lab.e2e.llm_presets import PRESETS
    from pharma_lab.integrations.kaggle.dataset_service import DatasetService

    auth = tmp_path / "auth"
    auth.mkdir()
    (auth / "claude-a.json").write_text('{"type": "claude", "t": "SECRET"}')
    (auth / "codex-b.json").write_text('{"type": "codex"}')
    deleted: list[tuple[str, str]] = []
    monkeypatch.setattr(e2e_command, "credential_datasets", lambda _context: [])
    monkeypatch.setattr(
        kaggle_service, "resolve_session_contexts", lambda _a: contexts("acc1")
    )
    monkeypatch.setattr(
        DatasetService,
        "delete_dataset",
        lambda self, reference: deleted.append((self.owner, reference)),
    )
    plan = make_plan(
        run_name="r1",
        entries=[FULL],
        golden_path=tmp_path / "g",
        categories=None,
        limit=None,
        llm=PRESETS["opus"],
    )

    with e2e_command.credential_session(
        plan, names=(), source=auth, kaggle_account=None
    ) as credentials:
        assert credentials is not None
        credentials.used("acc1", "user-acc1/pipeline-cred-z")

    shown = capsys.readouterr()
    assert "claude-a.json (claude)" in shown.out
    assert "codex-b.json" not in shown.out
    assert "SECRET" not in shown.out + shown.err
    assert deleted == [("user-acc1", "user-acc1/pipeline-cred-z")]


def test_no_credential_session_for_a_kernel_llm(tmp_path):
    from tests.e2e.test_kaggle_shards import FULL

    from pharma_lab.e2e.kaggle_shards import make_plan
    from pharma_lab.e2e.llm_presets import PRESETS

    plan = make_plan(
        run_name="r1",
        entries=[FULL],
        golden_path=tmp_path / "g",
        categories=None,
        limit=None,
        llm=PRESETS["qwen"],
    )

    with e2e_command.credential_session(
        plan, names=(), source=None, kaggle_account=None
    ) as credentials:
        assert credentials is None


class Follower:
    def __init__(self) -> None:
        self.notified: list[list[str]] = []

    def notify_merged(self, labels) -> None:
        self.notified.append(list(labels))


def fake_judging(entered: list[tuple], follower: Follower):
    @contextmanager
    def judging(
        plan, *, enabled, backend_env_file, golden, judge_model, judge_reasoning
    ):
        entered.append((enabled, judge_model, judge_reasoning))
        yield follower if enabled else None

    return judging


def test_judge_off_by_default(wired, monkeypatch):
    entered: list[tuple] = []
    monkeypatch.setattr(e2e_command, "judging", fake_judging(entered, Follower()))
    monkeypatch.setattr(
        e2e_command, "launch", Launcher(outcome(0, SchedulerStop.COMPLETE))
    )

    result = runner.invoke(app, BASE)

    assert result.exit_code == 0, result.output
    assert [flag for flag, *_ in entered] == [False]
    assert wired["on_merged"] is None


def test_judge_flag_hands_the_follower_to_the_adapter(wired, monkeypatch):
    entered: list[tuple] = []
    follower = Follower()
    monkeypatch.setattr(e2e_command, "judging", fake_judging(entered, follower))
    monkeypatch.setattr(
        e2e_command, "launch", Launcher(outcome(0, SchedulerStop.COMPLETE))
    )

    result = runner.invoke(
        app,
        [
            *BASE,
            "--judge",
            "--judge-model",
            "gemini-3.1-flash-lite",
            "--judge-reasoning",
            "none",
        ],
    )

    assert result.exit_code == 0, result.output
    assert entered == [(True, "gemini-3.1-flash-lite", "none")]
    wired["on_merged"](["full"])
    assert follower.notified == [["full"]]


def test_judging_context_starts_and_stops_the_follower(tmp_path, monkeypatch):
    from tests.e2e.test_kaggle_shards import FULL

    from pharma_lab.e2e.kaggle_shards import make_plan
    from pharma_lab.e2e.llm_presets import PRESETS

    events: list[str] = []

    class FakeFollower:
        def __init__(self, run_judge, *, log):
            events.append("created")

        def start(self, factory):
            request = factory("full")
            events.append(f"start:{request.config}:{request.judge_model}")

        def notify_merged(self, labels):
            events.append(f"notify:{','.join(labels)}")

        def stop(self, *, drain=True):
            events.append(f"stop:{drain}")

    monkeypatch.setattr(e2e_command, "JudgeFollower", FakeFollower)
    monkeypatch.setattr(e2e_command, "e2e_run_dir", lambda _name: tmp_path / "runs")
    (tmp_path / "runs" / "full").mkdir(parents=True)
    (tmp_path / "runs" / "full" / "answers.jsonl").write_text("{}\n")
    plan = make_plan(
        run_name="r1",
        entries=[FULL],
        golden_path=tmp_path / "g",
        categories=None,
        limit=None,
        llm=PRESETS["qwen"],
    )

    with e2e_command.judging(
        plan,
        enabled=True,
        backend_env_file=tmp_path / ".env",
        golden=tmp_path / "g",
        judge_model="m",
    ):
        pass
    with (
        pytest.raises(KeyError),
        e2e_command.judging(
            plan,
            enabled=True,
            backend_env_file=tmp_path / ".env",
            golden=tmp_path / "g",
            judge_model="m",
        ),
    ):
        raise KeyError("boom")

    assert events == [
        "created",
        "start:full:m",
        "notify:full",
        "stop:True",
        "created",
        "start:full:m",
        "notify:full",
        "stop:False",
    ]


def test_a_second_command_on_the_same_run_is_refused(wired, monkeypatch, tmp_path):
    from pharma_lab.config import paths
    from pharma_lab.integrations.kaggle.job_lock import kaggle_job_lock

    monkeypatch.setattr(paths, "LOCK_DIR", tmp_path / "locks")
    launcher = Launcher(outcome(0, SchedulerStop.COMPLETE))
    monkeypatch.setattr(e2e_command, "launch", launcher)

    with kaggle_job_lock(wired["work"] / "r1"):
        result = runner.invoke(app, BASE)

    assert result.exit_code == 1
    assert launcher.options is None  # nothing was scheduled


def test_kaggle_adapter_hands_on_merged_to_the_adapter(monkeypatch, tmp_path):
    from tests.e2e.test_kaggle_shards import FULL

    from pharma_lab.e2e.kaggle_shards import make_plan
    from pharma_lab.e2e.llm_presets import PRESETS

    captured: dict[str, object] = {}

    class Spy:
        def __init__(self, *_args, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(e2e_command, "E2EShardAdapter", Spy)
    monkeypatch.setattr(e2e_command, "load_golden", lambda _path: [])
    plan = make_plan(
        run_name="r1",
        entries=[FULL],
        golden_path=tmp_path / "g",
        categories=None,
        limit=None,
        llm=PRESETS["qwen"],
    )

    def notify(labels):
        return None

    e2e_command.kaggle_adapter(plan, budget_seconds=3600, on_merged=notify)

    assert captured["on_merged"] is notify


def test_a_dataset_left_by_a_killed_run_is_removed_before_the_new_upload(
    tmp_path, monkeypatch, capsys
):
    from tests.e2e.test_kaggle_shards import FULL
    from tests.integrations.kaggle.test_scheduler import contexts

    import pharma_lab.integrations.kaggle.service as kaggle_service
    from pharma_lab.e2e.kaggle_shards import make_plan
    from pharma_lab.e2e.llm_presets import PRESETS
    from pharma_lab.integrations.kaggle.dataset_service import DatasetService

    auth = tmp_path / "auth"
    auth.mkdir()
    (auth / "claude-a.json").write_text('{"type": "claude"}')
    deleted: list[str] = []
    monkeypatch.setattr(
        kaggle_service, "resolve_session_contexts", lambda _a: contexts("acc1")
    )
    monkeypatch.setattr(
        DatasetService, "delete_dataset", lambda self, ref: deleted.append(ref)
    )
    plan = make_plan(
        run_name="r1",
        entries=[FULL],
        golden_path=tmp_path / "g",
        categories=None,
        limit=None,
        llm=PRESETS["opus"],
    )
    seen: dict[str, str] = {}

    def listing(context):
        # The dataset this run would create is already on the account.
        return [seen["own"]] if "own" in seen else []

    monkeypatch.setattr(e2e_command, "credential_datasets", listing)
    original = e2e_command.CredentialDataset.slug

    def slug(self, profile):
        value = original(self, profile)
        seen["own"] = f"user-{profile}/{value}"
        return value

    monkeypatch.setattr(e2e_command.CredentialDataset, "slug", slug)
    # first call primes the name, second finds it
    with e2e_command.credential_session(
        plan, names=(), source=auth, kaggle_account=None
    ) as credentials:
        assert credentials is not None
        credentials.slug("acc1")

    assert deleted.count(seen["own"]) >= 1
