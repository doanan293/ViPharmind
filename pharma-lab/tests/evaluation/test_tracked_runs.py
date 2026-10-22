import subprocess
from pathlib import Path

import pytest

from pharma_lab.config.paths import RUNS_DIR
from pharma_lab.evaluation.run_workspace import load_run_record
from pharma_lab.runtime.catalog import RERANKER_MODELS


def _tracked_run_records() -> list[Path]:
    """The run.json files Git tracks: records restored from an archive of an earlier
    version, or not committed yet, are not held to this version's catalog."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", "*/run.json"],
        cwd=RUNS_DIR,
        capture_output=True,
        check=False,
    ).stdout
    names = [Path(name) for name in listed.decode("utf-8").split("\0") if name]
    return sorted(RUNS_DIR / name for name in names if len(name.parts) == 2)


@pytest.mark.parametrize(
    "record_path", _tracked_run_records(), ids=lambda path: path.parent.name
)
def test_tracked_runs_register_only_catalog_rerankers(record_path: Path) -> None:
    record = load_run_record(record_path)

    assert {variant.model for variant in record.rerank_variants.values()} <= set(
        RERANKER_MODELS
    )
