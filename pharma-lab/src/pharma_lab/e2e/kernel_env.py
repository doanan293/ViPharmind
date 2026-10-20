"""Backend settings of the agent that runs inside one Kaggle e2e kernel.

Pure values only: the kernel's orchestrating process imports this module before the
backend's dependencies are installed.
"""

from __future__ import annotations

import json

LLM_MODEL = "qwen3.5:9b-q8_0"
RERANK_MODEL = "qwen3-reranker:4b-q8_0"
EMBEDDING_MODEL = "qwen3-embedding:4b-fp16"
EMBEDDING_DIMENSION = 2560
# Every role of the agent (LlmRole names); a test keeps the two in step.
LLM_ROLES = ("GUARDRAIL", "REPHRASE", "JUDGE", "REFINE", "ANSWER", "SUMMARIZER")
# Qwen3.5 thinks by default; the pipeline wants one structured decision per call.
CHAT_EXTRA_BODY = {"chat_template_kwargs": {"enable_thinking": False}}
# A 9B model on a T4 generates a long answer in well over the backend's 60 s default.
CHAT_TIMEOUT_SECONDS = 600


def kernel_backend_env(
    *,
    llm_port: int,
    rerank_port: int,
    embedding_port: int,
    postgres_dsn: str,
    qdrant_url: str,
) -> dict[str, str]:
    values = {
        "PHARMA_LLM__TIMEOUT_SECONDS": str(CHAT_TIMEOUT_SECONDS),
        "PHARMA_LLM__DEFAULT__BASE_URL": f"http://127.0.0.1:{llm_port}/v1",
        "PHARMA_LLM__DEFAULT__API_KEY": "kernel",
        "PHARMA_LLM__DEFAULT__MODEL": LLM_MODEL,
        "PHARMA_RETRIEVAL__RERANK__PROTOCOL": "native_rerank",
        "PHARMA_RETRIEVAL__RERANK__BASE_URL": f"http://127.0.0.1:{rerank_port}",
        "PHARMA_RETRIEVAL__RERANK__API_KEY": "kernel",
        "PHARMA_RETRIEVAL__RERANK__MODEL": RERANK_MODEL,
        "PHARMA_RETRIEVAL__RERANK__TIMEOUT_SECONDS": "300",
        "PHARMA_RETRIEVAL__EMBEDDING__BASE_URL": f"http://127.0.0.1:{embedding_port}/v1",
        "PHARMA_RETRIEVAL__EMBEDDING__API_KEY": "kernel",
        "PHARMA_RETRIEVAL__EMBEDDING__MODEL": EMBEDDING_MODEL,
        "PHARMA_RETRIEVAL__EMBEDDING__DIMENSION": str(EMBEDDING_DIMENSION),
        "PHARMA_POSTGRES__DSN": postgres_dsn,
        "PHARMA_QDRANT__URL": qdrant_url,
    }
    for role in LLM_ROLES:
        prefix = f"PHARMA_LLM__ROLES__{role}__"
        values |= {
            prefix + "BASE_URL": f"http://127.0.0.1:{llm_port}/v1",
            prefix + "API_KEY": "kernel",
            prefix + "MODEL": LLM_MODEL,
            prefix + "EXTRA_BODY": json.dumps(CHAT_EXTRA_BODY),
        }
    return values
