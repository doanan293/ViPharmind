from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pharma_lab.runtime.model_profiles import (
    NATIVE_RERANK_PROTOCOL,
    EmbeddingRuntimeProfile,
    EmbeddingWorkloadProfile,
    RerankContract,
    native_rerank_contract,
)
from pharma_lab.runtime.runtime_profiles import (
    EmbeddingRuntimeSearchSpaces,
    RuntimeCandidate,
    RuntimeSearchSpace,
    reranker_candidate,
)


class ModelKind(StrEnum):
    EMBEDDING = "embedding"
    RERANKER = "reranker"
    CHAT = "chat"


# Every model fits one T4 at Q8_0, so a Kaggle kernel runs one replica per GPU.
KAGGLE_TOPOLOGY = "replicated_2x1"


KAGGLE_RERANK_REQUEST_BATCH_SIZE = 30
LOCAL_RERANK_REQUEST_BATCH_SIZE = 15
# Reranker levels as (-np, -ub, requests in flight). Every slot may hold a whole ubatch,
# so -c is -ub x (slots + 1) and -ub alone bounds the longest prompt the server accepts.
# On a T4 (14,806 MiB free) compute takes about 0.6 MiB per ubatch token (2,458 MiB at
# -ub 4096) and KV 0.11 MiB (0.6b) or 0.14 MiB (4b, 8b) per -c token. Q8_0 weights take
# about 0.6 GiB (0.6b), 4.0 GiB (4b) and 7.5 GiB (8b), which leaves room for up to 12
# slots on the 4b and 6 on the 8b.
# A batch carries at most -np whole documents, so a level with too few slots leaves the
# ubatch (and the GPU) half empty; the levels below sweep slots and requests in flight
# over both replicas so the benchmark can measure which one actually wins.
SMALL_MODEL_KAGGLE_RERANK_LEVELS = (
    (8, 4096, 4),
    (16, 4096, 4),
    (16, 4096, 8),
)
MEDIUM_MODEL_KAGGLE_RERANK_LEVELS = (
    (4, 4096, 4),
    (8, 4096, 4),
    (8, 4096, 8),
    (12, 4096, 8),
)
LARGE_MODEL_KAGGLE_RERANK_LEVELS = ((2, 4096, 2), (4, 4096, 4), (6, 4096, 4))
# The local CPU machine serves one request of at most 15 candidates at a time.
LOCAL_RERANK_LEVELS = ((4, 4096, 1),)
# Local CPU llama-reranker levels. The backend sends one request with at most 15
# candidates at a time, so a level has a single client request in flight.
LOCAL_RERANK_SEARCH_SPACE = RuntimeSearchSpace(
    tuple(
        reranker_candidate(
            server_slots=server_slots,
            ubatch=ubatch,
            request_batch_size=LOCAL_RERANK_REQUEST_BATCH_SIZE,
            concurrency=concurrency,
            threads=threads,
        )
        for server_slots, ubatch, concurrency in LOCAL_RERANK_LEVELS
        for threads in (8, 12)
    )
)


@dataclass(frozen=True)
class ModelSpec:
    name: str
    kind: ModelKind
    canonical_filename: str
    byte_size: int
    sha256: str
    kaggle_parallel: int
    kaggle_request_batch_size: int
    local_request_batch_size: int = 1
    kaggle_context_per_slot: int = 2048
    kaggle_logical_batch_size: int = 2048
    kaggle_physical_batch_size: int = 2048
    vector_dimension: int | None = None
    reranker_protocol: str | None = None
    rerank_contract: RerankContract | None = None
    embedding_runtime: EmbeddingRuntimeProfile | None = None
    rerank_search_space: RuntimeSearchSpace | None = None
    local_rerank_search_space: RuntimeSearchSpace | None = None
    embedding_search_space: EmbeddingRuntimeSearchSpaces | None = None
    # Chat models are only served, so their server layout is fixed instead of benchmarked.
    serve_runtime: RuntimeCandidate | None = None

    @property
    def slug(self) -> str:
        return (
            self.name.replace(":", "_")
            .replace("-", "_")
            .replace(".", "_")
            .replace("/", "_")
        )

    @property
    def gguf_dataset_slug(self) -> str:
        return "vector-cache-gguf-" + self.canonical_filename.removesuffix(
            ".gguf"
        ).replace(".", "-")


def _embedding(
    name: str,
    filename: str,
    size: int,
    sha256: str,
    dimension: int,
    *,
    parallel: int,
    batch: int,
) -> ModelSpec:
    # Two replicas, each with `parallel` slots: sweep requests in flight up to every slot.
    benchmark_concurrency = tuple(sorted({2, parallel, 2 * parallel}))
    embedding_profile = EmbeddingRuntimeProfile(
        query=EmbeddingWorkloadProfile(
            production_batch_size=batch,
            production_concurrency=1,
            benchmark_batch_sizes=tuple(sorted({max(1, batch // 2), batch, batch * 2})),
            benchmark_concurrency=benchmark_concurrency,
        ),
        corpus=EmbeddingWorkloadProfile(
            production_batch_size=batch,
            production_concurrency=1,
            benchmark_batch_sizes=tuple(sorted({max(1, batch // 2), batch, batch * 2})),
            benchmark_concurrency=benchmark_concurrency,
        ),
        context_per_slot=4096,
        logical_batch_size=4096,
        physical_batch_size=4096,
    )

    def candidates(batch_sizes: tuple[int, ...]) -> RuntimeSearchSpace:
        return RuntimeSearchSpace(
            tuple(
                RuntimeCandidate(
                    server_slots=parallel,
                    concurrency=concurrency,
                    request_batch_size=batch_size,
                    context_per_slot=4096,
                    logical_batch_size=4096,
                    physical_batch_size=4096,
                )
                for batch_size in batch_sizes
                for concurrency in benchmark_concurrency
            )
        )

    return ModelSpec(
        name=name,
        kind=ModelKind.EMBEDDING,
        canonical_filename=filename,
        byte_size=size,
        sha256=sha256,
        kaggle_parallel=parallel,
        kaggle_request_batch_size=batch,
        vector_dimension=dimension,
        embedding_runtime=embedding_profile,
        embedding_search_space=EmbeddingRuntimeSearchSpaces(
            query=candidates(tuple(sorted({max(1, batch // 2), batch}))),
            corpus=candidates(tuple(sorted({batch, batch * 2}))),
        ),
    )


def _reranker(
    name: str,
    filename: str,
    size: int,
    sha256: str,
    *,
    levels: tuple[tuple[int, int, int], ...],
) -> ModelSpec:
    search_space = RuntimeSearchSpace(
        tuple(
            reranker_candidate(
                server_slots=server_slots,
                ubatch=ubatch,
                request_batch_size=KAGGLE_RERANK_REQUEST_BATCH_SIZE,
                concurrency=concurrency,
            )
            for server_slots, ubatch, concurrency in levels
        )
    )
    smallest = search_space.candidates[0]
    return ModelSpec(
        name=name,
        kind=ModelKind.RERANKER,
        canonical_filename=filename,
        byte_size=size,
        sha256=sha256,
        kaggle_parallel=smallest.server_slots,
        kaggle_request_batch_size=KAGGLE_RERANK_REQUEST_BATCH_SIZE,
        kaggle_context_per_slot=smallest.context_per_slot,
        kaggle_logical_batch_size=smallest.logical_batch_size,
        kaggle_physical_batch_size=smallest.physical_batch_size,
        reranker_protocol=NATIVE_RERANK_PROTOCOL,
        rerank_contract=native_rerank_contract(),
        rerank_search_space=search_space,
        local_rerank_search_space=LOCAL_RERANK_SEARCH_SPACE,
    )


# Published Q8_0 GGUFs, pinned by Hugging Face commit and sha256 (docs/guides/evaluation.md).
# Q8_0 halves the weights of F16 at near-identical quality, and decoding on a T4 is bound by
# memory bandwidth, so every model fits one T4 and runs as one replica per GPU.
EMBEDDING_MODELS = {
    "embeddinggemma:300m-q8_0": _embedding(
        "embeddinggemma:300m-q8_0",
        "embeddinggemma-300m-q8_0.gguf",
        333_590_944,
        "b5ce9d77a3fc4b3b39ccb5643c36777911cc4eb46a66962eadfa3f5f60490d63",
        768,
        parallel=8,
        batch=32,
    ),
    "bge-m3:567m-q8_0": _embedding(
        "bge-m3:567m-q8_0",
        "bge-m3-567m-q8_0.gguf",
        634_553_760,
        "950f4a8e5e19477a6d3c26d2f162233c20002c601f75e4b002e3239997821167",
        1024,
        parallel=8,
        batch=32,
    ),
    "qwen3-embedding:0.6b-q8_0": _embedding(
        "qwen3-embedding:0.6b-q8_0",
        "qwen3-embedding-0.6b-q8_0.gguf",
        639_150_592,
        "06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439",
        1024,
        parallel=8,
        batch=32,
    ),
    "qwen3-embedding:4b-q8_0": _embedding(
        "qwen3-embedding:4b-q8_0",
        "qwen3-embedding-4b-q8_0.gguf",
        4_279_660_224,
        "b60ae5ce2dd6a0b77f82cadf21def1f310a3e10cde380ad0081b07a9d416949d",
        2560,
        parallel=4,
        batch=16,
    ),
    "qwen3-embedding:8b-q8_0": _embedding(
        "qwen3-embedding:8b-q8_0",
        "qwen3-embedding-8b-q8_0.gguf",
        8_047_105_824,
        "d20ddc71e8a5c4344f2343481e242233a997dc5eaff442427a945836c97b4deb",
        4096,
        parallel=2,
        batch=8,
    ),
}


RERANKER_MODELS = {
    # The Qwen3 files carry the Vietnamese medical rerank instruction; the instruction
    # decision and the derivation are in docs/guides/evaluation.md.
    "qwen3-reranker:0.6b-q8_0": _reranker(
        "qwen3-reranker:0.6b-q8_0",
        "qwen3-reranker-0.6b-q8_0-vimed.gguf",
        639_153_216,
        "ec7dc43df4b778258631125d3366d1b4bc8543d9594fbd02650a0332db95180e",
        levels=SMALL_MODEL_KAGGLE_RERANK_LEVELS,
    ),
    "qwen3-reranker:4b-q8_0": _reranker(
        "qwen3-reranker:4b-q8_0",
        "qwen3-reranker-4b-q8_0-vimed.gguf",
        4_279_678_912,
        "424c3a97b813b53760ffce9fe266fc85cc092c215a5adfef543200f7bde5e526",
        levels=MEDIUM_MODEL_KAGGLE_RERANK_LEVELS,
    ),
    "qwen3-reranker:8b-q8_0": _reranker(
        "qwen3-reranker:8b-q8_0",
        "qwen3-reranker-8b-q8_0-vimed.gguf",
        8_047_134_176,
        "79011330370fdf760fd2d0bd87688826396e06843e682f58f51f60fc43969aef",
        levels=LARGE_MODEL_KAGGLE_RERANK_LEVELS,
    ),
    # XLM-R cross-encoder (568M, 8,192 positions) in the 0.6b size class; its inputs carry
    # no chat template, so it takes the 0.6b levels.
    "bge-reranker-v2-m3:q8_0": _reranker(
        "bge-reranker-v2-m3:q8_0",
        "bge-reranker-v2-m3-q8_0.gguf",
        635_676_416,
        "a43c7c9b11a4c1517e5bf95151960e1621d1b72f7a493364b01e386cf1aaa1d3",
        levels=SMALL_MODEL_KAGGLE_RERANK_LEVELS,
    ),
}

CHAT_MODELS = {
    # Qwen3.5-9B (Apache 2.0), the Q8_0 GGUF published by Unsloth. At 9.5 GB it fits one T4,
    # so each GPU serves its own replica. Only 8 of its 32 layers keep a KV cache (32 KiB per
    # token), so four 32k-token slots take 4 GiB per GPU next to the weights. 32k leaves
    # room for a ReAct conversation, whose tool results accumulate in one request; the two
    # replicas take eight requests at once.
    "qwen3.5:9b-q8_0": ModelSpec(
        name="qwen3.5:9b-q8_0",
        kind=ModelKind.CHAT,
        canonical_filename="qwen3.5-9b-q8_0.gguf",
        byte_size=9_527_502_048,
        sha256="809626574d0cb43d4becfa56169980da2bb448f2299270f7be443cb89d0a6ae4",
        kaggle_parallel=4,
        kaggle_request_batch_size=1,
        serve_runtime=RuntimeCandidate(
            server_slots=4,
            concurrency=8,
            request_batch_size=1,
            context_per_slot=32768,
            logical_batch_size=2048,
            physical_batch_size=512,
        ),
    ),
}

MODEL_CATALOG = {**EMBEDDING_MODELS, **RERANKER_MODELS, **CHAT_MODELS}


def require_model(name: str) -> ModelSpec:
    try:
        return MODEL_CATALOG[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported model: {name}") from exc
