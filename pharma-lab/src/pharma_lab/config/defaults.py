from __future__ import annotations

DEFAULT_EMBEDDING_MODEL = "qwen3-embedding:4b-q8_0"
DEFAULT_RERANKER_MODEL = "qwen3-reranker:4b-q8_0"
DEFAULT_RETRIEVER = "hybrid"
# Same as the backend's retrieval.candidate_k, so evaluation reranks what the agent reranks.
DEFAULT_CANDIDATE_K = 20
DEFAULT_RRF_K = 2
DEFAULT_TOP_K = 10
DEFAULT_REQUEST_TIMEOUT_SECONDS = 900.0
DEFAULT_BUDGET_SECONDS = 21_600
