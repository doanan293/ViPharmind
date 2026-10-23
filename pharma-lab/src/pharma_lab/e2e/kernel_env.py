"""Backend settings of the agent that runs inside one Kaggle e2e kernel.

Pure values only: the kernel's orchestrating process imports this module before the
backend's dependencies are installed.
"""

from __future__ import annotations

import json

from pharma_lab.e2e.llm_presets import PRESETS, LlmPreset, RoleEndpoint

RERANK_MODEL = "qwen3-reranker:4b-q8_0"
EMBEDDING_MODEL = "qwen3-embedding:4b-q8_0"
EMBEDDING_DIMENSION = 2560
# A 9B model on a T4 generates a long answer in well over the backend's 60 s default.
CHAT_TIMEOUT_SECONDS = 600


def kernel_backend_env(
    *,
    llm_port: int,
    rerank_port: int,
    embedding_port: int,
    postgres_dsn: str,
    qdrant_url: str,
    preset: LlmPreset = PRESETS["qwen"],
    embedding_model: str = EMBEDDING_MODEL,
    embedding_dimension: int = EMBEDDING_DIMENSION,
) -> dict[str, str]:
    values = {
        "PHARMA_LLM__TIMEOUT_SECONDS": str(CHAT_TIMEOUT_SECONDS),
        "PHARMA_RETRIEVAL__RERANK__PROTOCOL": "native_rerank",
        "PHARMA_RETRIEVAL__RERANK__BASE_URL": f"http://127.0.0.1:{rerank_port}",
        "PHARMA_RETRIEVAL__RERANK__API_KEY": "kernel",
        "PHARMA_RETRIEVAL__RERANK__MODEL": RERANK_MODEL,
        "PHARMA_RETRIEVAL__RERANK__TIMEOUT_SECONDS": "300",
        "PHARMA_RETRIEVAL__EMBEDDING__BASE_URL": f"http://127.0.0.1:{embedding_port}/v1",
        "PHARMA_RETRIEVAL__EMBEDDING__API_KEY": "kernel",
        "PHARMA_RETRIEVAL__EMBEDDING__MODEL": embedding_model,
        "PHARMA_RETRIEVAL__EMBEDDING__DIMENSION": str(embedding_dimension),
        "PHARMA_POSTGRES__DSN": postgres_dsn,
        "PHARMA_QDRANT__URL": qdrant_url,
    }
    local = f"http://127.0.0.1:{llm_port}/v1"
    default = preset.roles["ANSWER"]
    # The default carries only the connection; every role sets its own body and effort.
    values |= {
        key: value
        for key, value in _endpoint_env("PHARMA_LLM__DEFAULT__", default, local).items()
        if key.rsplit("__", 1)[1] in ("BASE_URL", "API_KEY", "MODEL")
    }
    for role, endpoint in preset.roles.items():
        values |= _endpoint_env(f"PHARMA_LLM__ROLES__{role}__", endpoint, local)
    return values


def _endpoint_env(prefix: str, endpoint: RoleEndpoint, local: str) -> dict[str, str]:
    values = {
        prefix + "BASE_URL": endpoint.base_url or local,
        prefix + "API_KEY": endpoint.api_key,
        prefix + "MODEL": endpoint.model,
    }
    if endpoint.extra_body:
        values[prefix + "EXTRA_BODY"] = json.dumps(endpoint.extra_body)
    if endpoint.reasoning_effort:
        values[prefix + "REASONING_EFFORT"] = endpoint.reasoning_effort
    return values
