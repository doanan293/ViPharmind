from typing import Literal

from pharma_agent.application.chat.state import ChatTurnState
from pharma_agent.domain.agent.run import RunStatus, Step

FALLBACK = "fallback"


def failed(state: ChatTurnState) -> bool:
    """Whether the run ended in an error or a timeout."""
    return state.run.status in (RunStatus.ERROR, RunStatus.TIMEOUT)


def route_after_guard(
    state: ChatTurnState,
) -> Literal["rephrase", "answer", "fallback"]:
    """Go to rephrase when the guard allows processing, else straight to answer."""
    if failed(state):
        return FALLBACK
    verdict = state.run.guard_verdict
    return "rephrase" if verdict is not None and verdict.allows_processing else "answer"


def route_after_rephrase(
    state: ChatTurnState,
) -> Literal["search", "answer", "fallback"]:
    """Answer directly when the run allows it, else search."""
    if failed(state):
        return FALLBACK
    return "answer" if Step.ANSWER in state.run.allowed_steps() else "search"


def route_after_search(state: ChatTurnState) -> Literal["judge", "fallback"]:
    """Go to judge unless the run failed."""
    return FALLBACK if failed(state) else "judge"


def route_after_judge(state: ChatTurnState) -> Literal["refine", "answer", "fallback"]:
    """Refine when the run allows another round, else answer."""
    if failed(state):
        return FALLBACK
    return "refine" if Step.REFINE in state.run.allowed_steps() else "answer"


def route_after_refine(state: ChatTurnState) -> Literal["search", "answer", "fallback"]:
    """Search the refined queries when the run allows it, else answer."""
    if failed(state):
        return FALLBACK
    return "search" if Step.SEARCH in state.run.allowed_steps() else "answer"


def route_after_answer(state: ChatTurnState) -> Literal["fallback", "__end__"]:
    """End the turn, or go to fallback when the run failed."""
    return "fallback" if failed(state) else "__end__"
