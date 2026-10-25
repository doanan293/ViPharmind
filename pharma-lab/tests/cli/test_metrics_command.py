import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import pharma_lab.cli.commands.metrics as metrics_command
from pharma_lab.cli.app import app
from pharma_lab.config.paths import run_dir
from pharma_lab.evaluation.config_selection import (
    ConfigReport,
    Selection,
    StageResult,
)
from pharma_lab.evaluation.metrics_artifacts import MetricsArtifactResult
from pharma_lab.evaluation.metrics_service import MetricsRequest, MetricsResult

runner = CliRunner()


def fake_metrics_result() -> MetricsResult:
    baseline = Path("reports/baseline/top10-window3")
    rerank = Path("reports/rerank/model_a/top10-window3")
    return MetricsResult(
        baseline=MetricsArtifactResult(
            baseline, baseline / "report.md", baseline / "metrics.jsonl", "base"
        ),
        reranked=(
            MetricsArtifactResult(
                rerank,
                rerank / "report.md",
                rerank / "metrics.jsonl",
                "reranked",
                model="model-a",
                variant_sha256="variant",
            ),
        ),
    )


def capture_request(
    monkeypatch: pytest.MonkeyPatch, captured: dict[str, MetricsRequest]
) -> None:
    def fake_run(request: MetricsRequest) -> MetricsResult:
        captured["request"] = request
        return fake_metrics_result()

    monkeypatch.setattr(metrics_command, "run_metrics", fake_run)


def test_metrics_reads_the_run_tree_and_lists_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, MetricsRequest] = {}
    capture_request(monkeypatch, captured)

    result = runner.invoke(
        app, ["--json", "metrics", "--run", "experiment", "--model", "model-a"]
    )

    assert result.exit_code == 0, result.output
    request = captured["request"]
    assert (request.run_root, request.model, request.force) == (
        run_dir("experiment"),
        "model-a",
        False,
    )
    assert len(json.loads(result.stdout)["details"]["reranked"]) == 1


def test_metrics_force_is_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, MetricsRequest] = {}
    capture_request(monkeypatch, captured)

    result = runner.invoke(app, ["metrics", "--run", "experiment", "--force"])

    assert result.exit_code == 0, result.output
    assert captured["request"].force is True


@pytest.mark.parametrize(
    "option", [["--variant", "abcd"], ["--output-dir", "/tmp/reports"]]
)
def test_metrics_rejects_removed_options(option: list[str]) -> None:
    result = runner.invoke(app, ["metrics", "--run", "experiment", *option])

    assert result.exit_code == 2


def fake_selection(
    monkeypatch: pytest.MonkeyPatch, captured: dict[str, object]
) -> None:
    stage = StageResult(
        "hit@20", "hybrid", {"bm25": 0.8, "hybrid": 0.9}, (), ("hybrid",)
    )

    def fake_select(configs: list[ConfigReport], **kwargs: object) -> Selection:
        captured["configs"] = configs
        captured.update(kwargs)
        return Selection("hybrid", "primary", stage, None, 8470, ("conversational",))

    monkeypatch.setattr(metrics_command, "select_config", fake_select)
    monkeypatch.setattr(
        metrics_command, "run_evaluation_path", lambda run: Path(f"/gold/{run.name}")
    )


SELECT = [
    "--json",
    "metrics",
    "select",
    "--top-k",
    "20",
    "--metric",
    "hit@20",
    "--secondary",
    "hit@5",
    "--exclude-group",
    "conversational",
    "--config",
    "bm25=bm25-v3-k20",
    "--config",
    "hybrid=hybrid-qwen8b@qwen3-reranker:4b-q8_0",
]


def test_metrics_select_parses_configs_in_cost_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    fake_selection(monkeypatch, captured)

    result = runner.invoke(app, SELECT)

    assert result.exit_code == 0, result.output
    assert captured["configs"] == [
        ConfigReport("bm25", run_dir("bm25-v3-k20"), None),
        ConfigReport("hybrid", run_dir("hybrid-qwen8b"), "qwen3-reranker:4b-q8_0"),
    ]
    assert captured["primary"] == "hit@20"
    assert captured["secondary"] == "hit@5"
    assert captured["top_k"] == 20
    assert captured["exclude_groups"] == ("conversational",)
    assert captured["evaluation_path"] == Path("/gold/bm25-v3-k20")
    details = json.loads(result.stdout)["details"]
    assert (details["chosen"], details["reason"]) == ("hybrid", "primary")
    assert details["primary"]["means"] == {"bm25": 0.8, "hybrid": 0.9}


def test_metrics_select_rejects_a_config_without_a_label() -> None:
    result = runner.invoke(app, ["metrics", "select", "--config", "bm25-v3-k20"])

    assert result.exit_code != 0


def test_metrics_without_run_or_subcommand_is_a_usage_error() -> None:
    result = runner.invoke(app, ["metrics"])

    assert result.exit_code == 2


def test_metrics_gold_only_flag_reaches_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, MetricsRequest] = {}
    capture_request(monkeypatch, captured)

    result = runner.invoke(
        app, ["--json", "metrics", "--run", "experiment", "--gold-only"]
    )

    assert result.exit_code == 0, result.output
    assert captured["request"].gold_only is True
