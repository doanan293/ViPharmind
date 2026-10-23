import hashlib
import json
import tarfile
from pathlib import Path

import pytest
from tests.integrations.kaggle.factories import job_identity

from pharma_lab.e2e.configs import E2EConfig, config_label
from pharma_lab.e2e.kernel_worker import (
    OUTPUT_FILE,
    PhaseLog,
    completed_answers,
    llama_server_fingerprint,
    llm_preset_of,
    pack_outputs,
    restore_inputs,
    run_with_snapshots,
    shard_label,
    stop_at_from_config,
    write_snapshot,
)
from pharma_lab.integrations.kaggle.artifacts import load_cloud_artifact
from pharma_lab.integrations.kaggle.models import StageName
from pharma_lab.integrations.kaggle.workers.runtime import (
    WORKER_MARGIN_FLOOR_SECONDS,
    WORKER_MARGIN_FRACTION,
)

IDENTITY = job_identity(StageName.E2E_RUN, "qwen3.5:9b-q8_0")


def descriptor(path: Path) -> dict[str, str]:
    return {
        "path": str(path),
        "filename": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def test_restore_inputs_rebuilds_the_job_directory(tmp_path):
    mounted = tmp_path / "input"
    mounted.mkdir()
    files = {
        "job": "e2e_job.json",
        "golden": "golden_e2e.jsonl",
        "requirements": "backend_requirements.txt",
        "corpus/manifest.json": "corpus__manifest.json",
        "corpus/embeddings/q.jsonl": "corpus__embeddings__q.jsonl",
    }
    for key, name in files.items():
        (mounted / name).write_text(key, encoding="utf-8")
    config = {
        "input_files": {key: descriptor(mounted / name) for key, name in files.items()}
    }

    job_dir = restore_inputs(config, tmp_path / "job")

    assert (job_dir / "e2e_job.json").read_text(encoding="utf-8") == "job"
    assert (job_dir / "backend_requirements.txt").is_file()
    assert (job_dir / "corpus/embeddings/q.jsonl").read_text(encoding="utf-8") == (
        "corpus/embeddings/q.jsonl"
    )


def test_worker_restores_files_from_both_roots(tmp_path):
    static, dynamic = tmp_path / "pipeline-static-x", tmp_path / "pipeline-input-y"
    static.mkdir()
    dynamic.mkdir()
    (static / "corpus__manifest.json").write_text("corpus", encoding="utf-8")
    (static / "golden_e2e.jsonl").write_text("golden", encoding="utf-8")
    (dynamic / "e2e_job.json").write_text("job", encoding="utf-8")
    config = {
        "input_files": {
            "corpus/manifest.json": descriptor(static / "corpus__manifest.json"),
            "golden": descriptor(static / "golden_e2e.jsonl"),
            "job": descriptor(dynamic / "e2e_job.json"),
        }
    }

    job_dir = restore_inputs(config, tmp_path / "job")

    assert (job_dir / "corpus/manifest.json").read_text(encoding="utf-8") == "corpus"
    assert (job_dir / "golden_e2e.jsonl").read_text(encoding="utf-8") == "golden"
    assert (job_dir / "e2e_job.json").read_text(encoding="utf-8") == "job"


def write_answers(directory: Path, statuses: list[tuple[str, str]]) -> None:
    directory.mkdir(parents=True)
    (directory / "answers.jsonl").write_text(
        "".join(
            json.dumps({"item_id": item, "status": status}) + "\n"
            for item, status in statuses
        ),
        encoding="utf-8",
    )
    (directory / "run.json").write_text("{}\n", encoding="utf-8")
    (directory / "other.log").write_text("x", encoding="utf-8")


def test_outputs_keep_only_answers_and_run_files(tmp_path):
    write_answers(tmp_path / "no-rerank", [("a", "completed")])
    target = tmp_path / "out.tar"

    pack_outputs(tmp_path, ["no-rerank", "missing"], target)

    with tarfile.open(target) as archive:
        assert sorted(archive.getnames()) == [
            "no-rerank/answers.jsonl",
            "no-rerank/run.json",
        ]


def test_completed_answers_counts_the_latest_record_per_item(tmp_path):
    write_answers(
        tmp_path / "no-rerank",
        [("a", "error"), ("a", "completed"), ("b", "blocked"), ("c", "error")],
    )
    write_answers(tmp_path / "no-guard-no-rerank", [("a", "redirected")])

    assert completed_answers(tmp_path, ["no-rerank", "no-guard-no-rerank"]) == 3


def test_completed_answers_skips_a_cut_off_last_line(tmp_path):
    write_answers(tmp_path / "full", [("a", "completed")])
    with (tmp_path / "full" / "answers.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"item_id": "b", "sta')

    assert completed_answers(tmp_path, ["full"]) == 1


def snapshot_arguments(run_root: Path, output_dir: Path, total: int = 10):
    return {
        "run_root": run_root,
        "labels": ["full", "one-step"],
        "output_dir": output_dir,
        "total": total,
        "identity": IDENTITY,
    }


def test_snapshot_is_written_atomically_and_matches_its_manifest(tmp_path):
    run_root, out = tmp_path / "runs", tmp_path / "artifact"
    write_answers(run_root / "full", [("a", "completed"), ("b", "error")])
    write_answers(run_root / "one-step", [("a", "completed")])

    artifact = write_snapshot(**snapshot_arguments(run_root, out))

    assert sorted(p.name for p in out.iterdir()) == ["e2e_output.tar", "manifest.json"]
    loaded = load_cloud_artifact(
        out / OUTPUT_FILE, out / "manifest.json", IDENTITY, allow_partial=True
    )
    assert (loaded.completion.total, loaded.completion.complete) == (10, 2)
    assert artifact.completion == loaded.completion


def test_a_later_snapshot_replaces_the_earlier_one(tmp_path):
    run_root, out = tmp_path / "runs", tmp_path / "artifact"
    write_answers(run_root / "full", [("a", "completed")])
    write_snapshot(**snapshot_arguments(run_root, out))
    (run_root / "full" / "answers.jsonl").write_text(
        "".join(
            json.dumps({"item_id": item, "status": "completed"}) + "\n"
            for item in ("a", "b", "c")
        ),
        encoding="utf-8",
    )

    write_snapshot(**snapshot_arguments(run_root, out))

    loaded = load_cloud_artifact(
        out / OUTPUT_FILE, out / "manifest.json", IDENTITY, allow_partial=True
    )
    assert loaded.completion.complete == 3
    assert sorted(p.name for p in out.iterdir()) == ["e2e_output.tar", "manifest.json"]


class FakeProcess:
    def __init__(self, polls: list[int | None]) -> None:
        self.polls = list(polls)

    def poll(self) -> int | None:
        return self.polls.pop(0)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def run_fake(tmp_path, polls, *, snapshot_seconds, writes):
    clock = FakeClock()
    code = run_with_snapshots(
        ["harness"],
        env={},
        snapshot_seconds=snapshot_seconds,
        popen=lambda command, env: FakeProcess(polls),
        writer=lambda **_: writes.append(clock.now),
        clock=clock,
        sleep=clock.sleep,
        poll_seconds=100.0,
        **snapshot_arguments(tmp_path / "runs", tmp_path / "artifact"),
    )
    return code


def test_a_snapshot_is_written_every_interval(tmp_path):
    writes: list[float] = []

    code = run_fake(tmp_path, [None] * 6 + [0], snapshot_seconds=250.0, writes=writes)

    assert code == 0
    assert writes == [300.0, 600.0]


def test_snapshot_zero_disables_the_snapshots(tmp_path):
    writes: list[float] = []

    run_fake(tmp_path, [None] * 6 + [0], snapshot_seconds=0.0, writes=writes)

    assert writes == []


def test_a_killed_harness_leaves_a_readable_snapshot_behind(tmp_path):
    run_root, out = tmp_path / "runs", tmp_path / "artifact"
    write_answers(run_root / "full", [("a", "completed")])
    clock = FakeClock()

    code = run_with_snapshots(
        ["harness"],
        env={},
        snapshot_seconds=150.0,
        popen=lambda command, env: FakeProcess([None, None, -9]),
        clock=clock,
        sleep=clock.sleep,
        poll_seconds=100.0,
        **snapshot_arguments(run_root, out),
    )

    assert code == -9
    loaded = load_cloud_artifact(
        out / OUTPUT_FILE, out / "manifest.json", IDENTITY, allow_partial=True
    )
    assert loaded.completion.complete == 1


def test_a_failing_snapshot_does_not_stop_the_run(tmp_path):
    clock = FakeClock()

    def broken(**_):
        raise OSError("disk full")

    code = run_with_snapshots(
        ["harness"],
        env={},
        snapshot_seconds=50.0,
        popen=lambda command, env: FakeProcess([None, None, 0]),
        writer=broken,
        clock=clock,
        sleep=clock.sleep,
        poll_seconds=100.0,
        **snapshot_arguments(tmp_path / "runs", tmp_path / "artifact"),
    )

    assert code == 0


def test_phase_log_reports_the_seconds_of_every_phase():
    clock = FakeClock()
    lines: list[str] = []
    phases = PhaseLog(clock=clock, emit=lines.append)

    for name, seconds in (("install_venv", 90.0), ("postgres", 12.5)):
        with phases.phase(name):
            clock.sleep(seconds)

    assert lines == ["phase=install_venv seconds=90.0", "phase=postgres seconds=12.5"]


def test_phase_log_reports_a_phase_that_failed():
    clock = FakeClock()
    lines: list[str] = []
    phases = PhaseLog(clock=clock, emit=lines.append)

    with pytest.raises(RuntimeError), phases.phase("qdrant"):
        clock.sleep(3.0)
        raise RuntimeError("download failed")

    assert lines == ["phase=qdrant seconds=3.0"]


def test_stop_at_uses_the_session_budget_and_margin():
    config = {"budget_seconds": 7200}
    margin = max(WORKER_MARGIN_FLOOR_SECONDS, 7200 * WORKER_MARGIN_FRACTION)

    assert stop_at_from_config(config, clock=lambda: 1000.0) == 1000.0 + 7200 - margin
    explicit = {"budget_seconds": 7200, "budget_margin_seconds": 600}
    assert stop_at_from_config(explicit, clock=lambda: 1000.0) == 1000.0 + 6600


def test_shard_label_matches_the_label_the_harness_uses():
    assert shard_label("full", []) == config_label(E2EConfig.FULL, [])
    assert shard_label("full", ["guard=false", " refine_mode=template "]) == (
        config_label(E2EConfig.FULL, ["guard=false", " refine_mode=template "])
    )


def test_llama_server_fingerprint_reads_the_runtime_manifest(tmp_path):
    runtime = tmp_path / "input" / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "runtime_manifest.json").write_text(
        json.dumps({"files": {"bin/llama-server": {"sha256": "c" * 64}}}),
        encoding="utf-8",
    )

    assert llama_server_fingerprint(tmp_path / "input") == "c" * 64
    assert llama_server_fingerprint(tmp_path / "empty") is None


def test_the_job_names_its_llm_preset_and_defaults_to_qwen():
    assert llm_preset_of({}).name == "qwen"
    assert llm_preset_of({"llm": "opus"}).name == "opus"
    with pytest.raises(ValueError, match="unknown LLM preset"):
        llm_preset_of({"llm": "gpt"})
