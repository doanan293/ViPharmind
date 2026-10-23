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


SHARD_ITEMS = (["e2e-inj-0001", "e2e-inj-0002"], ["e2e-inj-0002"])


def write_job(tmp_path: Path, configs: list[str]) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
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
                "shards": [
                    {"config": c, "pipeline_options": [], "item_ids": ids}
                    for c, ids in zip(configs, SHARD_ITEMS, strict=False)
                ],
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
    assert job.expected_total == 3
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


def test_golden_requirements_and_corpus_are_static_and_the_job_is_not(tmp_path):
    job = build(tmp_path, ["no-rerank"])
    static = set(json.loads(json.dumps(job.worker_config))["static_input_keys"])

    assert static == {
        "golden",
        "requirements",
        "corpus/manifest.json",
        "corpus/embeddings/qwen3_embedding_4b_fp16.jsonl",
    }
    assert "job" not in static


def test_proxy_credentials_sidecar_reaches_the_worker_config_without_secrets(tmp_path):
    job_path = write_job(tmp_path, ["no-rerank"])
    (job_path.parent / "proxy_credentials.json").write_text(
        json.dumps(
            {
                "local_dir": "/tmp/pharma-cred-x",
                "slug": "pipeline-cred-1",
                "sha256": "ab",
            }
        ),
        encoding="utf-8",
    )

    job = E2ERunStage().build_job(
        stage_request(
            StageName.E2E_RUN,
            E2E_MODELS.llm,
            job_path,
            runtime_profile=rerank_runtime_profile(RERANKER),
        )
    )

    config = json.loads(json.dumps(job.worker_config))
    assert config["local_credentials_dir"] == "/tmp/pharma-cred-x"
    assert config["credentials_slug"] == "pipeline-cred-1"
    assert config["credentials_sha256"] == "ab"
    assert not any("proxy_credentials" in key for key in job.input_bundle.descriptors())


def test_the_commit_of_a_shard_reaches_the_worker_config_not_the_identity(tmp_path):
    first = write_job(tmp_path / "a", ["no-rerank"])
    second = write_job(tmp_path / "b", ["no-rerank"])
    for path, commit in ((first, "aaa"), (second, "bbb")):
        (path.parent / "shard_meta.json").write_text(json.dumps({"commit": commit}))

    jobs = [
        E2ERunStage().build_job(
            stage_request(
                StageName.E2E_RUN,
                E2E_MODELS.llm,
                path,
                runtime_profile=rerank_runtime_profile(RERANKER),
            )
        )
        for path in (first, second)
    ]

    assert [job.worker_config["commit"] for job in jobs] == ["aaa", "bbb"]
    assert jobs[0].identity.sha256 == jobs[1].identity.sha256


def test_the_job_can_choose_the_embedding_model_of_the_kernel(tmp_path):
    path = write_job(tmp_path, ["no-rerank"])
    job = json.loads(path.read_text())
    job["embedding_model"] = "qwen3-embedding:8b-q8_0"
    path.write_text(json.dumps(job), encoding="utf-8")

    built = E2ERunStage().build_job(
        stage_request(
            StageName.E2E_RUN,
            E2E_MODELS.llm,
            path,
            runtime_profile=rerank_runtime_profile(RERANKER),
        )
    )

    config = json.loads(json.dumps(built.worker_config))
    assert config["models"][2] == "qwen3-embedding:8b-q8_0"
    assert [s["model"] for s in config["servers"]][2] == "qwen3-embedding:8b-q8_0"
    default = json.loads(
        json.dumps(build(tmp_path / "other", ["no-rerank"]).worker_config)
    )
    assert default["models"][2] == E2E_MODELS.embedding


def test_a_model_that_is_not_an_embedding_model_is_refused(tmp_path):
    path = write_job(tmp_path, ["no-rerank"])
    job = json.loads(path.read_text())
    job["embedding_model"] = "qwen3-reranker:4b-q8_0"
    path.write_text(json.dumps(job), encoding="utf-8")

    with pytest.raises(ValueError, match="embedding"):
        E2ERunStage().build_job(
            stage_request(
                StageName.E2E_RUN,
                E2E_MODELS.llm,
                path,
                runtime_profile=rerank_runtime_profile(RERANKER),
            )
        )
