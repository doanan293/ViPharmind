"""The e2e-run stage: the whole agent and its models run inside one Kaggle kernel.

Nothing is served to outside callers. The kernel installs Postgres and Qdrant, imports
the corpus, starts one llama-server per model on localhost and runs the e2e harness;
the answers come back as one tar of configuration directories.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pharma_lab.integrations.kaggle.models import (
    InputBundle,
    InputFile,
    JobIdentity,
    JSONValue,
    StageJob,
    StageName,
    StageRequest,
)
from pharma_lab.runtime.catalog import require_model
from pharma_lab.runtime.runtime_profiles import RuntimeCandidate

JOB_FILE = "e2e_job.json"
GOLDEN_FILE = "golden_e2e.jsonl"
REQUIREMENTS_FILE = "backend_requirements.txt"
CORPUS_DIR = "corpus"
OUTPUT_FILE = "e2e_output.tar"
QDRANT_VERSION = "v1.19.1"
LLM_PORT = 11434
RERANK_PORT = 11435
EMBEDDING_PORT = 11436


@dataclass(frozen=True)
class E2EModels:
    llm: str
    reranker: str
    embedding: str


# Q8_0 so that the LLM fits one T4 and the reranker the other; the F16 embedder, which
# only embeds a few short queries per turn, runs on the CPU (no visible GPU).
E2E_MODELS = E2EModels(
    llm="qwen3.5:9b-q8_0",
    reranker="qwen3-reranker:4b-q8_0",
    embedding="qwen3-embedding:4b-fp16",
)
# Queries are short, so two slots of 4,096 tokens embed every search of a turn.
EMBEDDING_RUNTIME = RuntimeCandidate(
    server_slots=2,
    concurrency=2,
    request_batch_size=1,
    context_per_slot=4096,
    logical_batch_size=4096,
    physical_batch_size=4096,
)


def _corpus_files(corpus: Path) -> list[InputFile]:
    return [
        InputFile.create(
            f"{CORPUS_DIR}/{path.relative_to(corpus).as_posix()}",
            path,
            filename=f"{CORPUS_DIR}__"
            + path.relative_to(corpus).as_posix().replace("/", "__"),
        )
        for path in sorted(corpus.rglob("*"))
        if path.is_file()
    ]


def _server(model: str, port: int, devices: str, runtime: RuntimeCandidate) -> dict:
    return {
        "model": model,
        "model_filename": require_model(model).canonical_filename,
        "port": port,
        "visible_devices": devices,
        "runtime_overrides": runtime.to_dict(),
    }


@dataclass(frozen=True)
class E2ERunStage:
    """`input_path` is `e2e_job.json`; the golden set, the backend requirements and a
    corpus bundle directory lie next to it. `runtime_profile` is the reranker's."""

    name: StageName = StageName.E2E_RUN
    contract_version: int = 1

    def build_job(self, request: StageRequest) -> StageJob:
        if request.model != E2E_MODELS.llm:
            raise ValueError(f"e2e-run runs {E2E_MODELS.llm}, not {request.model}")
        if request.runtime_profile is None:
            raise ValueError("e2e-run needs the reranker's runtime profile")
        reranker_runtime = (
            request.runtime_profile
            if isinstance(request.runtime_profile, RuntimeCandidate)
            else RuntimeCandidate.from_dict(request.runtime_profile)
        )
        llm_runtime = require_model(E2E_MODELS.llm).serve_runtime
        if llm_runtime is None:
            raise ValueError(f"{E2E_MODELS.llm} has no fixed kernel runtime")
        directory = Path(request.input_path).parent
        job = json.loads(Path(request.input_path).read_text(encoding="utf-8"))
        input_bundle = InputBundle.create(
            (
                InputFile.create("job", request.input_path),
                InputFile.create("golden", directory / GOLDEN_FILE),
                InputFile.create("requirements", directory / REQUIREMENTS_FILE),
                *_corpus_files(directory / CORPUS_DIR),
            )
        )
        models = [E2E_MODELS.llm, E2E_MODELS.reranker, E2E_MODELS.embedding]
        servers: list[JSONValue] = [
            _server(E2E_MODELS.llm, LLM_PORT, "0", llm_runtime),
            _server(E2E_MODELS.reranker, RERANK_PORT, "1", reranker_runtime),
            _server(E2E_MODELS.embedding, EMBEDDING_PORT, "", EMBEDDING_RUNTIME),
        ]
        identity = JobIdentity.create(
            stage=self.name,
            contract_version=self.contract_version,
            model=E2E_MODELS.llm,
            model_sha256=require_model(E2E_MODELS.llm).sha256,
            input_sha256=input_bundle.sha256,
            runtime_parameters={
                "models": {name: require_model(name).sha256 for name in models},
                "servers": servers,
                "qdrant_version": QDRANT_VERSION,
            },
        )
        output_dir = request.output_dir / self.name.value / identity.sha256[:12]
        return StageJob(
            self.name,
            self.contract_version,
            E2E_MODELS.llm,
            identity,
            input_bundle,
            output_dir,
            output_dir / OUTPUT_FILE,
            OUTPUT_FILE,
            len(job["item_ids"]) * len(job["configs"]),
            "pharma_lab.integrations.kaggle.workers.e2e",
            {
                "models": list(models),
                "servers": servers,
                "gguf_root": str(request.gguf_root),
                "job_sha256": identity.sha256,
                "bundle_backend": True,
                "enable_internet": True,
                "qdrant_version": QDRANT_VERSION,
            },
        )
