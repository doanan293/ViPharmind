import hashlib
import json
import tarfile
from pathlib import Path

from pharma_lab.e2e.kernel_worker import (
    completed_answers,
    pack_outputs,
    restore_inputs,
)


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
