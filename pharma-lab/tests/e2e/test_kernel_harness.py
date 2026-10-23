import json
from pathlib import Path

import pytest

from pharma_lab.e2e import kernel_harness
from pharma_lab.e2e.harness import E2ERunRequest, RunSummary


def test_each_shard_entry_runs_twice_under_its_own_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = {
        "run": "r1",
        "shards": [
            {
                "config": "full",
                "pipeline_options": ["guard=false"],
                "item_ids": ["a", "b"],
            },
            {"config": "one-step", "pipeline_options": [], "item_ids": ["c"]},
        ],
        "deadline_seconds": 900.0,
        "commit": "abc1234",
        "stop_at": 123.0,
        "software": {"llama_server": "b1"},
    }
    job_path = tmp_path / "e2e_job.json"
    job_path.write_text(json.dumps(job), encoding="utf-8")
    requests: list[E2ERunRequest] = []

    def fake_run(request: E2ERunRequest) -> RunSummary:
        requests.append(request)
        return RunSummary(total=len(request.only_ids or ()), ran=0, errors=0)

    monkeypatch.setattr(kernel_harness, "run_e2e", fake_run)

    kernel_harness.run_job(
        job_path, tmp_path / "golden.jsonl", tmp_path / "runs" / "r1"
    )

    assert [(r.config.value, r.pipeline_options, r.retry_errors) for r in requests] == [
        ("full", ("guard=false",), False),
        ("full", ("guard=false",), True),
        ("one-step", (), False),
        ("one-step", (), True),
    ]
    first = requests[0]
    assert first.only_ids == frozenset({"a", "b"})
    assert first.stop_at == 123.0
    assert first.software == {"llama_server": "b1"}
    assert first.commit == "abc1234"
    assert first.deadline_seconds == 900.0
    assert first.run_root == tmp_path / "runs" / "r1"
