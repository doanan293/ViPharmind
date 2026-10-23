from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tests.integrations.kaggle.test_scheduler import contexts
from typer.testing import CliRunner

import pharma_lab.cli.commands.kaggle as kaggle_command
from pharma_lab.cli.app import app
from pharma_lab.integrations.kaggle.api import KaggleCommandRunner
from pharma_lab.integrations.kaggle.job_registry import JobRegistry, ShardRecord
from pharma_lab.integrations.kaggle.quota import AccountQuota

runner = CliRunner()
NOW = datetime.now(UTC)


class Listing(KaggleCommandRunner):
    """Fake Kaggle CLI: `datasets list --mine` answers with the account's datasets."""

    def __init__(self, refs: list[str], fail: bool = False) -> None:
        super().__init__(environment={})
        self.refs = refs
        self.fail = fail
        self.calls: list[list[str]] = []

    def run(self, args, capture_output=False, *, live_output=False):
        self.calls.append(list(args))
        if self.fail:
            raise RuntimeError("401 unauthorized")
        page = int(args[args.index("--page") + 1])
        rows = self.refs if page == 1 else []
        if not rows:
            return "No datasets found"
        return "ref,title\n" + "".join(f"{ref},t\n" for ref in rows)


def record(shard: str, stage: str, profile: str, units: int = 3) -> ShardRecord:
    return ShardRecord(
        shard,
        stage,
        profile,
        tuple(f"u{i}" for i in range(units)),
        (NOW - timedelta(minutes=90)).isoformat(),
        10_800,
    )


@pytest.fixture
def work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "work"
    monkeypatch.setattr(kaggle_command, "WORK_DIR", root)
    return root


def wire(monkeypatch, listings: dict[str, Listing], quotas: dict[str, float | None]):
    def resolve(account):
        names = (
            tuple(quotas) if account in (None, "auto") else tuple(account.split(","))
        )
        return tuple(
            replace(context, runner=listings[name])
            for name, context in zip(names, contexts(*names), strict=True)
        )

    def read_quota(context):
        assert context.profile is not None
        remaining = quotas[context.profile.name]
        if remaining is None:
            raise RuntimeError("quota endpoint unreachable")
        return AccountQuota(
            context.profile.name,
            context.profile.username,
            remaining,
            30.0,
            datetime(2026, 10, 24, tzinfo=UTC),
        )

    monkeypatch.setattr(kaggle_command, "resolve_session_contexts", resolve)
    monkeypatch.setattr(kaggle_command, "read_account_quota", read_quota)


def invoke(*extra: str):
    return runner.invoke(app, ["--json", "kaggle", "status", *extra])


def test_status_groups_live_shards_by_stage_and_account(work, monkeypatch) -> None:
    JobRegistry(work / "e2e-kaggle" / "r1" / "jobs.json").register(
        record("a", "e2e-run", "acc1")
    )
    JobRegistry(work / "e2e-kaggle" / "r1" / "jobs.json").register(
        record("b", "e2e-run", "acc1")
    )
    JobRegistry(work / "kaggle-rerank-shards" / "model" / "jobs.json").register(
        record("c", "rerank", "acc2", units=5)
    )
    wire(
        monkeypatch,
        {"acc1": Listing([]), "acc2": Listing([])},
        {"acc1": 12.5, "acc2": 3.0},
    )

    result = invoke()

    assert result.exit_code == 0, result.output
    details = json.loads(result.output)["details"]
    assert details["live.e2e-run.acc1"].startswith("2 kernels, 6 units")
    assert details["live.rerank.acc2"].startswith("1 kernels, 5 units")
    assert details["quota.acc1"] == "12.50h of 30.00h, resets 2026-10-24T00:00:00+00:00"
    assert details["quota.acc2"].startswith("3.00h of 30.00h")


def test_status_reports_leftover_credential_datasets(work, monkeypatch) -> None:
    wire(
        monkeypatch,
        {
            "acc1": Listing(["user-acc1/pipeline-cred-abc", "user-acc1/other-dataset"]),
            "acc2": Listing([]),
        },
        {"acc1": 20.0, "acc2": 20.0},
    )

    result = invoke()

    details = json.loads(result.output)["details"]
    assert details["credential_datasets"] == ["user-acc1/pipeline-cred-abc"]
    assert (
        "kaggle datasets delete user-acc1/pipeline-cred-abc" in details["delete_hint"]
    )


def test_status_without_leftovers_says_so(work, monkeypatch) -> None:
    wire(monkeypatch, {"acc1": Listing([])}, {"acc1": 20.0})

    details = json.loads(invoke("--kaggle-account", "acc1").output)["details"]

    assert details["credential_datasets"] == []
    assert "delete_hint" not in details


def test_status_works_with_one_account_unreachable(work, monkeypatch) -> None:
    wire(
        monkeypatch,
        {"acc1": Listing([], fail=True), "acc2": Listing([])},
        {"acc1": None, "acc2": 8.0},
    )

    result = invoke()

    assert result.exit_code == 0, result.output
    details = json.loads(result.output)["details"]
    assert details["quota.acc1"].startswith("unavailable: ")
    assert details["quota.acc2"].startswith("8.00h of 30.00h")
    assert details["credential_check.acc1"].startswith("unavailable: ")
    assert "credential_check.acc2" not in details


def test_status_never_prints_credential_contents(work, monkeypatch) -> None:
    wire(monkeypatch, {"acc1": Listing([])}, {"acc1": 20.0})

    result = invoke()

    assert "token" not in result.output.lower()
