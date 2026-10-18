"""The ReAct agent (spec v2 §2.4): one model loop over a single search tool.

guard → agent → finalize, with the pipeline's answer node for blocked and out-of-scope
verdicts and its fallback for failures. The agent node runs LangChain's `create_agent`
(react_agent.py): the model decides when to search and when to answer, and a middleware
enforces the round cap, the LLM-call budget, the evidence budget and the duplicate-query
guard. Finalize numbers and cites the chunks the agent was shown.
"""

from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from pharma_agent.application.chat import nodes, routing
from pharma_agent.application.chat.context import TurnContext
from pharma_agent.application.chat.graph import ChatGraph
from pharma_agent.application.chat.nodes import NodeUpdate, emit, guarded
from pharma_agent.application.chat.react_agent import ReactSession
from pharma_agent.application.chat.state import ChatTurnState, ReactAnswer
from pharma_agent.application.progress import Phase, ProgressEvent
from pharma_agent.domain.agent.actions import ActionKind
from pharma_agent.domain.agent.citations import CitationSanitizer, citations_from
from pharma_agent.domain.agent.react import react_history
from pharma_agent.domain.agent.run import (
    AnswerMode,
    AnswerPlan,
    ErrorCode,
    InvalidTransition,
    ReactStats,
)


def _answer(state: ChatTurnState) -> tuple[ReactAnswer, ReactStats]:
    if state.react is None or state.run.react is None:
        raise InvalidTransition("the ReAct agent has not answered")
    return state.react, state.run.react


@guarded(ErrorCode.ANSWER_FAILED)
async def agent_node(
    state: ChatTurnState, *, runtime: Runtime[TurnContext]
) -> NodeUpdate:
    """Run the agent to its final answer; any model error fails the turn (guarded)."""
    run, deps = state.run, runtime.context.deps
    emit(ProgressEvent.phase(Phase.UNDERSTANDING))
    session = ReactSession(
        run, deps, scope=runtime.context.scope, notify=nodes.emitter()
    )
    final = await session.answer(
        react_history(runtime.context.conversation, run.original_query)
    )
    text = final.text
    if not text.strip():
        reason = final.response_metadata.get("finish_reason") or "none"
        run.fail(
            ErrorCode.ANSWER_FAILED, detail=f"empty answer (finish_reason={reason})"
        )
        return {"run": run}
    return {"run": run, "react": ReactAnswer(shown=session.shown, final_text=text)}


@guarded(ErrorCode.ANSWER_FAILED)
async def finalize_node(
    state: ChatTurnState, *, runtime: Runtime[TurnContext]
) -> NodeUpdate:
    run, deps = state.run, runtime.context.deps
    answer, stats = _answer(state)
    emit(ProgressEvent.phase(Phase.ANSWERING))
    by_chunk = {e.hit.chunk_version_id: e for e in run.evidence.items}
    shown = sorted(answer.shown.numbers.items(), key=lambda item: item[1])
    # Numbers run 1..n in first-shown order, so the context view numbers them the same.
    context_text, numbered = run.evidence.context_view(
        [by_chunk[chunk_id] for chunk_id, _ in shown]
    )
    stats.answered_without_search = stats.tool_calls == 0
    if run.actions.last_of(ActionKind.SEARCH) is None:
        plan = AnswerPlan(mode=AnswerMode.NO_RETRIEVAL)
    elif not numbered:
        plan = AnswerPlan(mode=AnswerMode.ABSTAIN)
    else:
        partial = stats.round_cap_hit or stats.budget_forced or stats.budget_hits > 0
        plan = AnswerPlan(mode=AnswerMode.GROUNDED, partial=partial)
    run.submit_plan(plan, now=deps.clock.now())
    nodes.emit_evidence(numbered)

    sanitizer = CitationSanitizer(index for index, _ in numbered)
    text = sanitizer.feed(answer.final_text) + sanitizer.flush()
    if text:
        emit(ProgressEvent.token(text))
    citations = citations_from(numbered, sanitizer.used)
    nodes.emit_citations(citations)
    run.complete()
    return {
        "run": run,
        "answer_text": text,
        "citations": citations,
        "context_text": context_text,
    }


def route_after_guard(state: ChatTurnState) -> Literal["agent", "answer", "fallback"]:
    if routing.failed(state):
        return "fallback"
    verdict = state.run.guard_verdict
    return "agent" if verdict is not None and verdict.allows_processing else "answer"


def route_after_agent(state: ChatTurnState) -> Literal["finalize", "fallback"]:
    return "fallback" if routing.failed(state) else "finalize"


def build_react_graph() -> ChatGraph:
    """guard → agent → finalize, with answer (blocked, redirect) and fallback."""
    builder = StateGraph(ChatTurnState, context_schema=TurnContext)
    builder.add_node("guard", nodes.guard_node)
    builder.add_node("agent", agent_node)
    builder.add_node("finalize", finalize_node)
    builder.add_node("answer", nodes.answer_node)
    builder.add_node("fallback", nodes.fallback_node)

    builder.add_edge(START, "guard")
    builder.add_conditional_edges("guard", route_after_guard)
    builder.add_conditional_edges("agent", route_after_agent)
    builder.add_conditional_edges("finalize", routing.route_after_answer)
    builder.add_conditional_edges("answer", routing.route_after_answer)
    builder.add_edge("fallback", END)
    return builder.compile()
