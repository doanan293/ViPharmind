from collections.abc import Mapping
from dataclasses import dataclass, field

from pharma_agent.domain.conversation.models import ConversationContext
from pharma_agent.domain.guardrail.service import GuardrailService
from pharma_agent.domain.llm.decision import DecisionPort
from pharma_agent.domain.llm.models import LlmRole
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
    # Roles served by the decision model (spec v2 §2.1); empty means the LLM serves them.
    decisions: Mapping[LlmRole, DecisionPort] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineOptions:
    """Steps of the agent loop. Only the evaluation harness turns any of them off."""

    rephrase: bool = True
    judge_refine: bool = True
    guard: bool = True
    # Refinement by confidence (spec v2 §2.3): None keeps the judge's categorical decision;
    # otherwise search more only while the judge's confidence is below the threshold.
    refine_threshold: float | None = None
    # "llm" (a refine call) or "template" ("<subject> <intent phrase>", no LLM; spec v2 §2.2).
    refine_mode: str = "llm"


@dataclass(frozen=True)
class TurnContext:
    """LangGraph runtime context for one turn (not part of the graph state)."""

    deps: TurnDeps
    conversation: ConversationContext
    pipeline: PipelineOptions = PipelineOptions()
    # What this turn may search; None uses the retrieval service's default scope
    # (runs without a user, such as the evaluation harness).
    scope: ReleaseScope | None = None
