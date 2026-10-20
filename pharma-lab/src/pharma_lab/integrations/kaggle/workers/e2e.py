"""Kernel side of the e2e-run stage: the whole agent runs here and nothing is served out.

The kernel's own Python only orchestrates. It installs the workspace's locked
dependencies into a venv, starts Postgres, Qdrant and one llama-server per model on
localhost, imports the corpus, and runs the e2e harness in that venv. Internet is used
for downloads only.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from collections.abc import Iterable, Mapping
from contextlib import ExitStack
from pathlib import Path

from pharma_lab.e2e.kernel_env import kernel_backend_env
from pharma_lab.integrations.kaggle.models import CloudArtifact
from pharma_lab.integrations.kaggle.workers.runtime import (
    artifact_from_output,
    identity_from_config,
    managed_model_servers,
    resolve_input_file,
)

OUTPUT_FILE = "e2e_output.tar"
WORK_ROOT = Path("/tmp/e2e")
SOURCE_ZIP = Path("/tmp/source_bundle.zip")
POSTGRES_DSN = "postgresql+psycopg://vipharmind:vipharmind@127.0.0.1:5432/vipharmind"
QDRANT_URL = "http://127.0.0.1:6333"
QDRANT_RELEASE = (
    "https://github.com/qdrant/qdrant/releases/download/{version}/"
    "qdrant-x86_64-unknown-linux-gnu.tar.gz"
)
KEPT_FILES = ("answers.jsonl", "run.json")


def log(message: str) -> None:
    print(f"[e2e] {message}", flush=True)


def restore_inputs(config: Mapping, target: Path) -> Path:
    """Rebuild the job directory (job, golden, requirements, corpus tree) from the
    flat mounted input files."""
    target.mkdir(parents=True, exist_ok=True)
    for key in config["input_files"]:
        source = resolve_input_file(dict(config), key)
        if key == "job":
            destination = target / "e2e_job.json"
        elif key == "golden":
            destination = target / "golden_e2e.jsonl"
        elif key == "requirements":
            destination = target / "backend_requirements.txt"
        else:
            destination = target / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return target


def pack_outputs(run_root: Path, configs: Iterable[str], target: Path) -> None:
    """One tar of `<config>/answers.jsonl` and `<config>/run.json`, nothing else."""
    with tarfile.open(target, "w") as archive:
        for config in configs:
            for name in KEPT_FILES:
                path = run_root / config / name
                if path.is_file():
                    archive.add(path, arcname=f"{config}/{name}")


def completed_answers(run_root: Path, configs: Iterable[str]) -> int:
    """Items whose latest answer completed, over every configuration."""
    count = 0
    for config in configs:
        path = run_root / config / "answers.jsonl"
        if not path.is_file():
            continue
        latest: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                latest[record["item_id"]] = record["status"]
        count += sum(1 for status in latest.values() if status != "error")
    return count


def _run(command: list[str], *, env: Mapping[str, str] | None = None) -> None:
    log("$ " + " ".join(command))
    subprocess.run(command, check=True, env=None if env is None else dict(env))


def _wait_http(url: str, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while True:
        try:
            with urllib.request.urlopen(url, timeout=5):
                return
        except OSError as error:
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"{url} did not answer within {seconds:.0f} s"
                ) from error
            time.sleep(2)


def install_venv(requirements: Path, venv: Path) -> Path:
    _run([sys.executable, "-m", "pip", "install", "--quiet", "uv"])
    _run([sys.executable, "-m", "uv", "venv", str(venv), "--python", "3.12"])
    python = venv / "bin/python"
    _run(
        [
            sys.executable,
            "-m",
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "-r",
            str(requirements),
        ]
    )
    return python


def start_postgres() -> None:
    _run(["apt-get", "update", "-qq"])
    _run(["apt-get", "install", "-y", "-qq", "postgresql"])
    _run(["service", "postgresql", "start"])
    for sql in (
        "CREATE USER vipharmind WITH PASSWORD 'vipharmind';",
        "CREATE DATABASE vipharmind OWNER vipharmind;",
    ):
        _run(["su", "postgres", "-c", f'psql -c "{sql}"'])


def start_qdrant(version: str, work: Path) -> subprocess.Popen:
    work.mkdir(parents=True, exist_ok=True)
    archive = work / "qdrant.tar.gz"
    urllib.request.urlretrieve(QDRANT_RELEASE.format(version=version), archive)
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter="data")
    process = subprocess.Popen(
        [str(work / "qdrant")],
        cwd=work,
        env=os.environ | {"QDRANT__STORAGE__STORAGE_PATH": str(work / "storage")},
    )
    _wait_http(f"{QDRANT_URL}/readyz", 120)
    return process


def _backend(python: Path, env: Mapping[str, str], *args: str) -> None:
    _run(
        [
            str(python),
            "-c",
            "from pharma_agent.cli import app; app(prog_name='pharma-agent')",
            *args,
        ],
        env=env,
    )


def _server_config(server: Mapping, config: Mapping) -> dict:
    return {
        "model": server["model"],
        "model_filename": server["model_filename"],
        "visible_devices": server["visible_devices"],
        "server_port": server["port"],
        "runtime_overrides": server["runtime_overrides"],
        "output_dir": config.get("output_dir", "/kaggle/working/artifact"),
        "server_start_timeout": 900,
    }


def run_e2e_worker(config: dict) -> CloudArtifact:
    identity = identity_from_config(config)
    output_dir = Path(config.get("output_dir", "/kaggle/working/artifact"))
    output_dir.mkdir(parents=True, exist_ok=True)
    work = WORK_ROOT
    job_dir = restore_inputs(config, work / "job")
    job = json.loads((job_dir / "e2e_job.json").read_text(encoding="utf-8"))
    source = work / "source"
    with zipfile.ZipFile(SOURCE_ZIP) as archive:
        archive.extractall(source)
    python = install_venv(job_dir / "backend_requirements.txt", work / "venv")
    start_postgres()
    qdrant = start_qdrant(str(config["qdrant_version"]), work / "qdrant")
    workspace = work / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "pyproject.toml").write_text("[project]\nname = 'kernel'\n")
    ports = {server["model"]: int(server["port"]) for server in config["servers"]}
    models = config["models"]
    env = (
        os.environ
        | kernel_backend_env(
            llm_port=ports[models[0]],
            rerank_port=ports[models[1]],
            embedding_port=ports[models[2]],
            postgres_dsn=POSTGRES_DSN,
            qdrant_url=QDRANT_URL,
        )
        | {"PYTHONPATH": str(source), "PHARMA_LAB_ROOT": str(workspace)}
    )
    run_root = work / "runs" / str(job["run"])
    try:
        with ExitStack() as stack:
            for server in config["servers"]:
                stack.enter_context(
                    managed_model_servers(_server_config(server, config))
                )
            log("model servers are healthy")
            _backend(python, env, "migrate")
            _backend(
                python,
                env,
                "corpus",
                "import",
                str(job_dir / "corpus"),
                "--collection",
                "formulary",
                "--publish",
            )
            _run(
                [
                    str(python),
                    "-m",
                    "pharma_lab.integrations.kaggle.workers.e2e_harness",
                    str(job_dir / "e2e_job.json"),
                    str(job_dir / "golden_e2e.jsonl"),
                    str(run_root),
                ],
                env=env,
            )
    finally:
        qdrant.terminate()
    configs = list(job["configs"])
    data_path = output_dir / OUTPUT_FILE
    pack_outputs(run_root, configs, data_path)
    return artifact_from_output(
        data_path,
        artifact_type="e2e_run",
        identity=identity,
        total=len(job["item_ids"]) * len(configs),
        complete=completed_answers(run_root, configs),
    )


def main() -> None:
    config_path = Path(os.environ["KAGGLE_PIPELINE_CONFIG"])
    artifact = run_e2e_worker(json.loads(config_path.read_text(encoding="utf-8")))
    log(f"artifact={artifact.data_path} completion={artifact.completion}")


if __name__ == "__main__":
    main()
