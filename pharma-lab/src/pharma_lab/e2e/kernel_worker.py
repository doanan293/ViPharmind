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
import tempfile
import time
import urllib.request
import uuid
import zipfile
from collections.abc import Callable, Generator, Iterable, Mapping
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any

from pharma_lab.e2e.kernel_env import kernel_backend_env
from pharma_lab.e2e.llm_presets import LlmPreset, preset_named
from pharma_lab.e2e.proxy_kernel import (
    CONFIG_NAME,
    fetch_proxy,
    install_credentials,
    start_proxy,
    write_proxy_config,
)
from pharma_lab.integrations.kaggle.models import CloudArtifact, JobIdentity
from pharma_lab.integrations.kaggle.workers.runtime import (
    artifact_from_output,
    identity_from_config,
    managed_model_servers,
    resolve_input_file,
    worker_deadline,
)
from pharma_lab.runtime.catalog import require_model

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
# Seconds between the snapshots of the answers so far (the job may change or switch off with 0).
SNAPSHOT_SECONDS = 300.0
POLL_SECONDS = 5.0


def log(message: str) -> None:
    print(f"[e2e] {message}", flush=True)


class PhaseLog:
    """Seconds spent in each setup phase, so that speeding the setup up starts from numbers."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        emit: Callable[[str], None] = log,
    ) -> None:
        self._clock = clock
        self._emit = emit

    @contextmanager
    def phase(self, name: str) -> Generator[None]:
        started = self._clock()
        try:
            yield
        finally:
            self._emit(f"phase={name} seconds={self._clock() - started:.1f}")


def shard_label(config: str, pipeline_options: Iterable[str]) -> str:
    """Directory name of a configuration with its options, e.g. `full+guard=false`.

    The rule of `configs.config_label`, repeated because this module runs before the
    backend (and so `configs`) is installed; a test keeps the two equal."""
    return "+".join([config, *(option.strip() for option in pipeline_options)])


def shard_entries(job: Mapping) -> list[dict]:
    """The `(config, pipeline_options, item_ids)` entries of a job, old or new layout."""
    shards = job.get("shards")
    if shards:
        return [dict(entry) for entry in shards]
    return [
        {"config": config, "pipeline_options": [], "item_ids": job["item_ids"]}
        for config in job["configs"]
    ]


def stop_at_from_config(
    config: Mapping, clock: Callable[[], float] = time.time
) -> float:
    """The `time.time()` reading from which the harness starts no new item."""
    return worker_deadline(dict(config), clock)


def llama_server_fingerprint(input_root: Path) -> str | None:
    """sha256 of the llama-server binary the runtime dataset ships, if it names one."""
    manifests = [
        p for p in Path(input_root).rglob("runtime_manifest.json") if p.is_file()
    ]
    if len(manifests) != 1:
        return None
    files = json.loads(manifests[0].read_text(encoding="utf-8")).get("files", {})
    record = files.get("bin/llama-server")
    return None if record is None else str(record["sha256"])


def software_info(config: Mapping) -> dict[str, object]:
    """What produced the answers; merging refuses answers of other weights or builds."""
    info: dict[str, object] = {
        "model_sha256": {
            str(name): require_model(str(name)).sha256
            for name in config.get("models", [])
        }
    }
    server = llama_server_fingerprint(
        Path(config.get("kaggle_input_root", "/kaggle/input"))
    )
    if server is not None:
        info["llama_server"] = server
    return info


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
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue  # the line the harness is writing right now
            latest[record["item_id"]] = record["status"]
        count += sum(1 for status in latest.values() if status != "error")
    return count


def write_snapshot(
    *,
    run_root: Path,
    labels: Iterable[str],
    output_dir: Path,
    total: int,
    identity: JobIdentity,
) -> CloudArtifact:
    """Write the answers so far as the kernel's output artifact, replacing the last one.

    The tar and its manifest are built beside the output and moved in one after the
    other, so a kernel killed at any moment leaves a complete artifact (a kill between the
    two moves leaves a mismatch that the download rejects, and nothing else)."""
    labels = list(labels)
    output_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".snapshot-", dir=output_dir))
    try:
        pack_outputs(run_root, labels, staging / OUTPUT_FILE)
        built = artifact_from_output(
            staging / OUTPUT_FILE,
            artifact_type="e2e_run",
            identity=identity,
            total=total,
            complete=completed_answers(run_root, labels),
        )
        os.replace(staging / OUTPUT_FILE, output_dir / OUTPUT_FILE)
        os.replace(built.manifest_path, output_dir / "manifest.json")
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return CloudArtifact(
        output_dir / OUTPUT_FILE,
        output_dir / "manifest.json",
        identity,
        built.completion,
    )


def run_with_snapshots(
    command: list[str],
    *,
    env: Mapping[str, str],
    run_root: Path,
    labels: Iterable[str],
    output_dir: Path,
    total: int,
    identity: JobIdentity,
    snapshot_seconds: float,
    popen=subprocess.Popen,
    writer=write_snapshot,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    poll_seconds: float = POLL_SECONDS,
) -> int:
    """Run the harness; every `snapshot_seconds` write what it has answered so far.

    A failing snapshot is logged and the run goes on. `snapshot_seconds <= 0` writes none.
    Returns the harness's exit code."""
    labels = list(labels)
    log("$ " + " ".join(command))
    process = popen(command, env=dict(env))
    last = clock()
    while (code := process.poll()) is None:
        sleep(poll_seconds)
        if snapshot_seconds > 0 and clock() - last >= snapshot_seconds:
            try:
                writer(
                    run_root=run_root,
                    labels=labels,
                    output_dir=output_dir,
                    total=total,
                    identity=identity,
                )
            except Exception as error:
                log(f"snapshot failed, the run goes on: {error}")
            last = clock()
    return code


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


def qdrant_environment(storage: Path) -> dict[str, str]:
    """Qdrant defaults to every interface; in a kernel it must answer on localhost only."""
    return {
        "QDRANT__STORAGE__STORAGE_PATH": str(storage),
        "QDRANT__SERVICE__HOST": "127.0.0.1",
    }


def start_qdrant(version: str, work: Path) -> subprocess.Popen:
    work.mkdir(parents=True, exist_ok=True)
    archive = work / "qdrant.tar.gz"
    urllib.request.urlretrieve(QDRANT_RELEASE.format(version=version), archive)
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter="data")
    process = subprocess.Popen(
        [str(work / "qdrant")],
        cwd=work,
        env=os.environ | qdrant_environment(work / "storage"),
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


def job_software(config: Mapping, job: Mapping) -> dict[str, object]:
    """What produced the answers, plus the server layout the job asked for."""
    return software_info(config) | {"layout": job.get("layout", "A")}


def _dimension(model: str) -> int:
    dimension = require_model(model).vector_dimension
    if dimension is None:
        raise ValueError(f"{model} has no vector dimension")
    return dimension


def llm_preset_of(job: Mapping) -> LlmPreset:
    """The LLM preset a job asks for; jobs written before presets run Qwen."""
    return preset_named(str(job.get("llm", "qwen")))


@contextmanager
def running_proxy(
    config: Mapping,
    *,
    fetch: Callable[[Path], Path] = fetch_proxy,
    start: Callable[..., Any] = start_proxy,
    work_root: Path | None = None,
) -> Generator[None]:
    """`cli-proxy-api` on 127.0.0.1 with the run's credential dataset, for the Gemini and
    Claude presets. The credentials live in a private directory outside the artifact and
    are removed when the proxy stops; only how many files there are is ever logged."""
    slug = config.get("credentials_slug")
    if not slug:
        raise RuntimeError("this LLM preset needs the run's proxy credentials dataset")
    mounted = Path(config.get("kaggle_input_root", "/kaggle/input")) / str(slug)
    work = Path(tempfile.mkdtemp(prefix="proxy-", dir=work_root))
    work.chmod(0o700)
    process = None
    try:
        binary = fetch(work / "bin")
        names = install_credentials(mounted, work / "auth")
        if not names:
            seen = (
                sorted(path.name for path in mounted.parent.iterdir())
                if mounted.parent.is_dir()
                else []
            )
            raise RuntimeError(
                f"no credential file under {mounted}; the input directory holds {seen}"
            )
        template = mounted / CONFIG_NAME
        proxy_config = write_proxy_config(
            template if template.is_file() else None,
            work / "config.yaml",
            work / "auth",
        )
        process = start(binary, proxy_config)
        log(f"cli-proxy-api is up with {len(names)} credential file(s)")
        yield
    finally:
        if process is not None:
            process.terminate()
        shutil.rmtree(work, ignore_errors=True)


def run_e2e_worker(config: dict) -> CloudArtifact:
    identity = identity_from_config(config)
    output_dir = Path(config.get("output_dir", "/kaggle/working/artifact"))
    output_dir.mkdir(parents=True, exist_ok=True)
    phases = PhaseLog()
    work = WORK_ROOT
    job_dir = restore_inputs(config, work / "job")
    job_path = job_dir / "e2e_job.json"
    job = json.loads(job_path.read_text(encoding="utf-8"))
    entries = shard_entries(job)
    labels = [shard_label(e["config"], e.get("pipeline_options", ())) for e in entries]
    total = sum(len(entry["item_ids"]) for entry in entries)
    job.update(
        shards=entries,
        stop_at=stop_at_from_config(config),
        session=uuid.uuid4().hex,
        commit=config.get("commit") or job.get("commit"),
        software=job_software(config, job),
    )
    job_path.write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")
    source = work / "source"
    with zipfile.ZipFile(SOURCE_ZIP) as archive:
        archive.extractall(source)
    with phases.phase("install_venv"):
        python = install_venv(job_dir / "backend_requirements.txt", work / "venv")
    with phases.phase("postgres"):
        start_postgres()
    with phases.phase("qdrant"):
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
            preset=llm_preset_of(job),
            embedding_model=models[2],
            embedding_dimension=_dimension(models[2]),
        )
        | {"PYTHONPATH": str(source), "PHARMA_LAB_ROOT": str(workspace)}
    )
    run_root = work / "runs" / str(job["run"])
    exit_code = 1
    artifact: CloudArtifact | None = None
    try:
        with ExitStack() as stack:
            if llm_preset_of(job).needs_proxy:
                with phases.phase("proxy"):
                    stack.enter_context(running_proxy(config))
            with phases.phase("servers"):
                for server in config["servers"]:
                    stack.enter_context(
                        managed_model_servers(_server_config(server, config))
                    )
            log("model servers are healthy")
            with phases.phase("corpus_import"):
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
            with phases.phase("harness"):
                exit_code = run_with_snapshots(
                    [
                        str(python),
                        "-m",
                        "pharma_lab.e2e.kernel_harness",
                        str(job_path),
                        str(job_dir / "golden_e2e.jsonl"),
                        str(run_root),
                    ],
                    env=env,
                    run_root=run_root,
                    labels=labels,
                    output_dir=output_dir,
                    total=total,
                    identity=identity,
                    snapshot_seconds=float(
                        config.get("snapshot_seconds", SNAPSHOT_SECONDS)
                    ),
                )
    finally:
        qdrant.terminate()
        if run_root.exists():
            # Keep whatever was answered, even when something above failed.
            try:
                artifact = write_snapshot(
                    run_root=run_root,
                    labels=labels,
                    output_dir=output_dir,
                    total=total,
                    identity=identity,
                )
            except Exception as error:
                log(f"final snapshot failed: {error}")
    if artifact is None or exit_code != 0:
        kept = "none" if artifact is None else f"{artifact.completion.complete}/{total}"
        raise RuntimeError(
            f"the e2e harness exited with {exit_code}; answers kept: {kept}"
        )
    return artifact


def main() -> None:
    config_path = Path(os.environ["KAGGLE_PIPELINE_CONFIG"])
    artifact = run_e2e_worker(json.loads(config_path.read_text(encoding="utf-8")))
    log(f"artifact={artifact.data_path} completion={artifact.completion}")


if __name__ == "__main__":
    main()
