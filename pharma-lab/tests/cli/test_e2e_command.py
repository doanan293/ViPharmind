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

    def fake_adapter(plan, *, budget_seconds, credentials=None) -> E2EShardAdapter:
        captured["plan"] = plan
        captured["credentials"] = credentials
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
