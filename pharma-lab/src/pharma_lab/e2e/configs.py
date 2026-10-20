"""The E2E configurations: five pipeline variants and a closed-book baseline."""

from __future__ import annotations

from dataclasses import asdict
from enum import StrEnum

from pharma_agent.application.chat.context import PipelineOptions
from pharma_agent.infrastructure.settings import Settings


class E2EConfig(StrEnum):
    FULL = "full"
    ONE_STEP = "one-step"
    # One-step RAG whose search query is the earlier user questions plus the turn.
    ONE_STEP_HISTORY = "one-step-history"
    NO_JUDGE_REFINE = "no-judge-refine"
    NO_REPHRASE = "no-rephrase"
    NO_RERANK = "no-rerank"
    # No-rerank without the guard step: every turn goes on to retrieval. Compared with
    # no-rerank, so that it measures the guard and needs no reranker server.
    NO_GUARD_NO_RERANK = "no-guard-no-rerank"
    # The answer model alone, with no retrieval: what the corpus and pipeline add.
    CLOSED_BOOK = "closed-book"


_PIPELINES: dict[E2EConfig, PipelineOptions] = {
    E2EConfig.FULL: PipelineOptions(),
    E2EConfig.ONE_STEP: PipelineOptions(rephrase=False, judge_refine=False),
    E2EConfig.ONE_STEP_HISTORY: PipelineOptions(
        rephrase=False, judge_refine=False, history_query=True
    ),
    E2EConfig.NO_JUDGE_REFINE: PipelineOptions(judge_refine=False),
    E2EConfig.NO_REPHRASE: PipelineOptions(rephrase=False),
    E2EConfig.NO_RERANK: PipelineOptions(),
    E2EConfig.NO_GUARD_NO_RERANK: PipelineOptions(guard=False),
    E2EConfig.CLOSED_BOOK: PipelineOptions(rephrase=False, judge_refine=False),
}


def pipeline_for(config: E2EConfig) -> PipelineOptions:
    return _PIPELINES[config]


# Options added after the v1 runs, with their default: they are recorded only when a
# configuration changes them, so the identity of earlier runs stays unchanged.
_LATER_OPTIONS = {"history_query": False, "guard": True}


def pipeline_record(options: PipelineOptions) -> dict[str, bool]:
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
    langfuse = base.langfuse.model_copy(update={"public_key": None, "secret_key": None})
    return base.model_copy(update={"retrieval": retrieval, "langfuse": langfuse})
