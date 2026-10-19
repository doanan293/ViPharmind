from dataclasses import dataclass

from pharma_agent.domain.conversation.models import ConversationContext
from pharma_agent.domain.guardrail.service import GuardrailService
from pharma_agent.domain.llm.port import LlmPort
from pharma_agent.domain.retrieval.models import ReleaseScope
from pharma_agent.domain.retrieval.service import RetrievalService
from pharma_agent.domain.shared.clock import Clock


@dataclass(frozen=True)
class TurnDeps:
    """Ports a chat turn needs. Built once by the composition root."""

    llm: LlmPort
    guardrail: GuardrailService
    retrieval: RetrievalService
    clock: Clock


@dataclass(frozen=True)
class PipelineOptions:
    """Steps of the agent loop. Only the evaluation harness turns any of them off."""

    rephrase: bool = True
    judge_refine: bool = True
    # The first search uses the earlier user questions plus this one (a baseline without rephrase).
    history_query: bool = False


@dataclass(frozen=True)
class TurnContext:
    """LangGraph runtime context for one turn (not part of the graph state)."""

    deps: TurnDeps
    conversation: ConversationContext
    pipeline: PipelineOptions = PipelineOptions()
    # What this turn may search; None uses the retrieval service's default scope
    # (runs without a user, such as the evaluation harness).
    scope: ReleaseScope | None = None
