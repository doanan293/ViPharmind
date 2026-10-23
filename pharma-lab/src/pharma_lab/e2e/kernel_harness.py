"""Run the e2e harness inside the kernel's venv: every shard entry (a configuration with
its pipeline options and the golden items to answer), then one retry pass for failed turns.

Usage: python -m pharma_lab.e2e.kernel_harness JOB GOLDEN RUN_ROOT
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pharma_lab.e2e.configs import E2EConfig
from pharma_lab.e2e.harness import E2ERunRequest, run_e2e

DEADLINE_SECONDS = 900.0
DEFAULT_CONCURRENCY = 8


def run_job(job_path: Path, golden_path: Path, run_root: Path) -> None:
    job = json.loads(job_path.read_text(encoding="utf-8"))
    # No env file: the kernel's settings come from the environment only.
    env_file = run_root.parent / "no-backend.env"
    for entry in job["shards"]:
        for retry_errors in (False, True):
            summary = run_e2e(
                E2ERunRequest(
                    run_root=run_root,
                    config=E2EConfig(entry["config"]),
                    golden_path=golden_path,
                    backend_env_file=env_file,
                    retry_errors=retry_errors,
                    concurrency=int(job.get("concurrency", DEFAULT_CONCURRENCY)),
                    only_ids=frozenset(entry["item_ids"]),
                    deadline_seconds=float(
                        job.get("deadline_seconds", DEADLINE_SECONDS)
                    ),
                    pipeline_options=tuple(entry.get("pipeline_options", ())),
                    commit=job.get("commit"),
                    stop_at=job.get("stop_at"),
                    software=job.get("software") or {},
                )
            )
            print(
                f"[e2e] {entry['config']} {' '.join(entry.get('pipeline_options', ()))} "
                f"retry={retry_errors} items={summary.total} ran={summary.ran} "
                f"errors={summary.errors}",
                flush=True,
            )


if __name__ == "__main__":
    run_job(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
