"""Run the e2e harness inside the kernel's venv: every configuration and category of
one e2e-run job, then one retry pass for failed turns.

Usage: python -m pharma_lab.integrations.kaggle.workers.e2e_harness JOB GOLDEN RUN_ROOT
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pharma_lab.e2e.configs import E2EConfig
from pharma_lab.e2e.golden import Category
from pharma_lab.e2e.harness import E2ERunRequest, run_e2e

DEADLINE_SECONDS = 900.0


def run_job(job_path: Path, golden_path: Path, run_root: Path) -> None:
    job = json.loads(job_path.read_text(encoding="utf-8"))
    # No env file: the kernel's settings come from the environment only.
    env_file = run_root.parent / "no-backend.env"
    for config in job["configs"]:
        for category in job["categories"]:
            for retry_errors in (False, True):
                summary = run_e2e(
                    E2ERunRequest(
                        run_root=run_root,
                        config=E2EConfig(config),
                        golden_path=golden_path,
                        backend_env_file=env_file,
                        retry_errors=retry_errors,
                        category=Category(category),
                        deadline_seconds=float(
                            job.get("deadline_seconds", DEADLINE_SECONDS)
                        ),
                        commit=job.get("commit"),
                    )
                )
                print(
                    f"[e2e] {config} {category} retry={retry_errors} "
                    f"items={summary.total} ran={summary.ran} errors={summary.errors}",
                    flush=True,
                )


if __name__ == "__main__":
    run_job(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
