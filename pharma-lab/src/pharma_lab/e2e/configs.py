"""The E2E configurations: pipeline variants, retriever variants and a closed-book baseline."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, fields
from enum import StrEnum

from pharma_agent.application.chat.context import PipelineOptions
from pharma_agent.application.chat.graph import ChatGraph, build_chat_graph
from pharma_agent.application.chat.react_graph import build_react_graph
from pharma_agent.infrastructure.settings import Settings
from pydantic import TypeAdapter


class E2EConfig(StrEnum):
    FULL = "full"
    ONE_STEP = "one-step"
    # One-step RAG whose search query is the earlier user questions plus the turn.
    ONE_STEP_HISTORY = "one-step-history"
    NO_JUDGE_REFINE = "no-judge-refine"
    NO_REPHRASE = "no-rephrase"
    NO_RERANK = "no-rerank"
    NO_GUARD = "no-guard"
    # Retriever variants of the full agent (spec v2 §2.6, §4.D D6).
    BM25 = "bm25"
    DENSE = "dense"
    HYBRID_K60 = "hybrid-k60"
    # No-rerank without the guard step: every turn goes on to retrieval. Compared with
    # no-rerank, so that it measures the guard and needs no reranker server.
    NO_GUARD_NO_RERANK = "no-guard-no-rerank"
    # The answer model alone, with no retrieval: what the corpus and pipeline add.
    CLOSED_BOOK = "closed-book"
    # One model loop over a search tool instead of the pipeline (spec v2 §2.4).
    REACT = "react"


_PIPELINES: dict[E2EConfig, PipelineOptions] = {
    E2EConfig.FULL: PipelineOptions(),
    E2EConfig.ONE_STEP: PipelineOptions(rephrase=False, judge_refine=False),
    E2EConfig.ONE_STEP_HISTORY: PipelineOptions(
        rephrase=False, judge_refine=False, history_query=True
    ),
    E2EConfig.NO_JUDGE_REFINE: PipelineOptions(judge_refine=False),
    E2EConfig.NO_REPHRASE: PipelineOptions(rephrase=False),
    E2EConfig.NO_RERANK: PipelineOptions(),
    E2EConfig.NO_GUARD: PipelineOptions(guard=False),
    E2EConfig.BM25: PipelineOptions(),
    E2EConfig.DENSE: PipelineOptions(),
    E2EConfig.HYBRID_K60: PipelineOptions(),
    E2EConfig.NO_GUARD_NO_RERANK: PipelineOptions(guard=False),
    E2EConfig.CLOSED_BOOK: PipelineOptions(rephrase=False, judge_refine=False),
    # The ReAct graph runs only the guard of these steps.
    E2EConfig.REACT: PipelineOptions(),
}


def pipeline_for(config: E2EConfig) -> PipelineOptions:
    return _PIPELINES[config]


def graph_for(config: E2EConfig) -> ChatGraph:
    return build_react_graph() if config is E2EConfig.REACT else build_chat_graph()


# Options added after the v2 runs, with their default: they are recorded only when a
# configuration changes them, so the identity of earlier runs stays unchanged.
_LATER_OPTIONS: dict[str, object] = {"history_query": False}


def pipeline_record(options: PipelineOptions) -> dict[str, object]:
    """The pipeline as recorded in run.json."""
    return {
        name: value
        for name, value in asdict(options).items()
        if name not in _LATER_OPTIONS or value != _LATER_OPTIONS[name]
    }


def uses_retrieval(config: E2EConfig) -> bool:
    return config is not E2EConfig.CLOSED_BOOK


def settings_for(base: Settings, config: E2EConfig) -> Settings:
    """Backend settings for one configuration; the environment is never changed."""
    retrieval = base.retrieval
    if config in (E2EConfig.NO_RERANK, E2EConfig.NO_GUARD_NO_RERANK):
        rerank = retrieval.rerank.model_copy(update={"protocol": "none"})
        retrieval = retrieval.model_copy(update={"rerank": rerank})
    elif config is E2EConfig.BM25:
        retrieval = retrieval.model_copy(update={"mode": "bm25"})
    elif config is E2EConfig.DENSE:
        retrieval = retrieval.model_copy(update={"mode": "dense"})
    elif config is E2EConfig.HYBRID_K60:
        retrieval = retrieval.model_copy(update={"mode": "hybrid", "rrf_k": 60})
    langfuse = base.langfuse.model_copy(update={"public_key": None, "secret_key": None})
    return base.model_copy(update={"retrieval": retrieval, "langfuse": langfuse})


def parse_pipeline_options(
    base: PipelineOptions, pairs: Sequence[str]
) -> PipelineOptions:
    """`key=value` overrides of PipelineOptions, validated by the field types
    (bools true/false, numbers, none for optional values)."""
    known = [field.name for field in fields(PipelineOptions)]
    updates: dict[str, str | None] = {}
    for pair in pairs:
        key, sep, raw = pair.partition("=")
        if not sep:
            raise ValueError(f"pipeline option {pair!r} must be key=value")
        if key not in known:
            raise ValueError(
                f"unknown pipeline option {key!r}; known: {', '.join(known)}"
            )
        value = raw.strip()
        updates[key] = None if value.lower() == "none" else value
    if not updates:
        return base
    return _OPTIONS.validate_python({**asdict(base), **updates})


_OPTIONS = TypeAdapter(PipelineOptions)


def config_label(config: E2EConfig, pairs: Sequence[str]) -> str:
    """Directory name of a configuration with its options, e.g. full+guard=false."""
    return "+".join([str(config), *(pair.strip() for pair in pairs)])
