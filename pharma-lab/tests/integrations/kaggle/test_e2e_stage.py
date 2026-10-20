import json
from pathlib import Path

import pytest
from tests.integrations.kaggle.factories import rerank_runtime_profile, stage_request

from pharma_lab.integrations.kaggle.e2e_stage import (
    E2E_MODELS,
    EMBEDDING_PORT,
    JOB_FILE,
    LLM_PORT,
    OUTPUT_FILE,
    RERANK_PORT,
    E2ERunStage,
)
from pharma_lab.integrations.kaggle.models import StageName

RERANKER = E2E_MODELS.reranker


def write_job(tmp_path: Path, configs: list[str]) -> Path:
    directory = tmp_path / "job"
    corpus = directory / "corpus"
    (corpus / "embeddings").mkdir(parents=True)
    (corpus / "manifest.json").write_text("{}\n", encoding="utf-8")
    (corpus / "embeddings/qwen3_embedding_4b_fp16.jsonl").write_text(
        "{}\n", encoding="utf-8"
    )
    (directory / "golden_e2e.jsonl").write_text("{}\n", encoding="utf-8")
    (directory / "backend_requirements.txt").write_text("x==1\n", encoding="utf-8")
    job = directory / JOB_FILE
    job.write_text(
        json.dumps(
            {
                "run": "e2e-qwen35-9b-cr",
                "configs": configs,
                "categories": ["injection"],
                "item_ids": ["e2e-inj-0001", "e2e-inj-0002"],
            }
        ),
        encoding="utf-8",
    )
    return job


def build(tmp_path: Path, configs: list[str]):
    return E2ERunStage().build_job(
        stage_request(
            StageName.E2E_RUN,
            E2E_MODELS.llm,
            write_job(tmp_path, configs),
            runtime_profile=rerank_runtime_profile(RERANKER),
        )
    )


def test_e2e_job_carries_its_inputs_models_and_servers(tmp_path):
    job = build(tmp_path, ["no-rerank", "no-guard-no-rerank"])
    descriptors = job.input_bundle.descriptors()
    config = json.loads(json.dumps(job.worker_config))

    assert {"job", "golden", "requirements"} <= set(descriptors)
    assert descriptors["corpus/manifest.json"]["filename"] == "corpus__manifest.json"
    assert (
        descriptors["corpus/embeddings/qwen3_embedding_4b_fp16.jsonl"]["filename"]
        == "corpus__embeddings__qwen3_embedding_4b_fp16.jsonl"
    )
    assert job.expected_total == 4
    assert job.data_filename == OUTPUT_FILE
    assert config["models"] == [E2E_MODELS.llm, RERANKER, E2E_MODELS.embedding]
    assert config["bundle_backend"] is True
    assert config["enable_internet"] is True
    assert config["qdrant_version"] == "v1.19.1"
    servers = {server["model"]: server for server in config["servers"]}
    assert servers[E2E_MODELS.llm]["port"] == LLM_PORT
    assert servers[E2E_MODELS.llm]["visible_devices"] == "0"
    assert servers[RERANKER]["port"] == RERANK_PORT
    assert servers[RERANKER]["visible_devices"] == "1"
    assert servers[E2E_MODELS.embedding]["port"] == EMBEDDING_PORT
    assert servers[E2E_MODELS.embedding]["visible_devices"] == ""


def test_other_configs_make_another_job(tmp_path):
    first = build(tmp_path / "a", ["no-rerank"])
    second = build(tmp_path / "b", ["no-rerank", "no-guard-no-rerank"])

    assert first.identity.sha256 != second.identity.sha256


def test_the_e2e_job_runs_its_own_llm(tmp_path):
    with pytest.raises(ValueError, match="e2e-run runs"):
        E2ERunStage().build_job(
            stage_request(
                StageName.E2E_RUN,
                "qwen3.5:9b-f16",
                write_job(tmp_path, ["no-rerank"]),
                runtime_profile=rerank_runtime_profile(RERANKER),
            )
        )
