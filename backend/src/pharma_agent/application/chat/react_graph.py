"""The ReAct agent (spec v2 §2.4): one model loop over a single search tool.

guard → agent ⇄ tools → finalize, with the pipeline's answer node for blocked and
out-of-scope verdicts and its fallback for failures. The model decides when to search
and when to answer; the graph enforces the round cap, the LLM-call budget, the evidence
budget and the duplicate-query guard.
"""

import asyncio
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from pharma_agent.application.chat import nodes, routing
from pharma_agent.application.chat.context import TurnContext
from pharma_agent.application.chat.graph import ChatGraph
from pharma_agent.application.chat.nodes import NodeUpdate, emit, guarded
from pharma_agent.application.chat.state import ChatTurnState, ReactLoop
from pharma_agent.application.progress import Phase, ProgressEvent
from pharma_agent.domain.agent.actions import ActionKind
from pharma_agent.domain.agent.budget import BudgetExhausted
from pharma_agent.domain.agent.citations import CitationSanitizer, citations_from
from pharma_agent.domain.agent.react import (
    DUPLICATE_NOTE,
    MAX_TOOL_ROUNDS,
    ROUND_CAP_NOTE,
    SEARCH_TOOL,
    normalize_query,
    parse_query,
    react_messages,
    render_result,
)
from pharma_agent.domain.agent.run import (
    AgentRun,
    AnswerMode,
    AnswerPlan,
    ErrorCode,
    InvalidTransition,
    ReactStats,
)
from pharma_agent.domain.llm.models import (
    ChatMessage,
    ChatRole,
    LlmRole,
    ToolCall,
    user,
)
from pharma_agent.domain.llm.port import LlmError
from pharma_agent.domain.retrieval.models import Query, QueryOrigin
from pharma_agent.domain.retrieval.service import SearchResult


def _loop(state: ChatTurnState) -> ReactLoop:
    if state.react is None:
        raise InvalidTransition("the ReAct loop has not started")
    return state.react


def _stats(run: AgentRun) -> ReactStats:
    if run.react is None:
        run.react = ReactStats()
    return run.react


def _parse(call: ToolCall) -> str | ValueError:
    try:
        return parse_query(call)
    except ValueError as exc:
        return exc


@guarded(ErrorCode.ANSWER_FAILED)
async def agent_node(
    state: ChatTurnState, *, runtime: Runtime[TurnContext]
) -> NodeUpdate:
    run, deps = state.run, runtime.context.deps
    stats = _stats(run)
    if state.react is None:
        emit(ProgressEvent.phase(Phase.UNDERSTANDING))
        loop = ReactLoop(
            messages=react_messages(runtime.context.conversation, run.original_query)
        )
    else:
        loop = state.react
    capped = stats.rounds >= MAX_TOOL_ROUNDS
    final = loop.forced or capped or run.calls_left < 2
    if final:
        loop.messages.append(user(ROUND_CAP_NOTE))
        if capped:
            stats.round_cap_hit = True
        else:
            stats.budget_forced = True
    try:
        # The final call keeps the tool declared: a history with tool calls needs it.
        turn, usage = await deps.llm.tool_call(
            LlmRole.AGENT,
            loop.messages,
            [SEARCH_TOOL],
            tool_choice="none" if final else "auto",
        )
    except LlmError as exc:
        run.fail(ErrorCode.ANSWER_FAILED, detail=str(exc))
        return {"run": run, "react": loop}
    calls = () if final else turn.tool_calls
    over_budget = False
    try:
        run.charge(usage)
    except BudgetExhausted:
        over_budget = True
    run.record_tool_round(
        calls,
        now=deps.clock.now(),
        malformed=[isinstance(_parse(call), ValueError) for call in calls],
        finish_reason=turn.finish_reason,
    )
    if calls and over_budget:
        # No budget left for the searches it asked for: one last call answers without tools.
        loop.forced = True
    elif calls:
        loop.messages.append(
            ChatMessage(role=ChatRole.ASSISTANT, content=turn.text, tool_calls=calls)
        )
        loop.pending_calls = list(calls)
        stats.rounds += 1
    elif not turn.text.strip():
        run.fail(
            ErrorCode.ANSWER_FAILED,
            detail=f"empty answer (finish_reason={turn.finish_reason or 'none'})",
        )
    else:
        loop.final_text = turn.text
        loop.answered = True
    return {"run": run, "react": loop}


@guarded(ErrorCode.SEARCH_FAILED)
async def tools_node(
    state: ChatTurnState, *, runtime: Runtime[TurnContext]
) -> NodeUpdate:
    run, deps, loop = state.run, runtime.context.deps, _loop(state)
    stats, shown = _stats(run), loop.shown
    calls = loop.pending_calls
    parsed = [_parse(call) for call in calls]
    emit(ProgressEvent.phase(Phase.SEARCHING, round=stats.rounds))

    # Each new query is searched once, all of them at the same time.
    fresh: dict[str, Query] = {}
    first = run.actions.last_of(ActionKind.SEARCH) is None
    for item in parsed:
        if isinstance(item, ValueError):
            continue
        key = normalize_query(item)
        if key not in shown.results and key not in fresh:
            origin = QueryOrigin.INITIAL if first and not fresh else QueryOrigin.REFINED
            fresh[key] = Query(text=item, origin=origin)
    results: list[SearchResult] = await asyncio.gather(
        *(
            deps.retrieval.search(
                [query], rerank_query=query.text, scope=runtime.context.scope
            )
            for query in fresh.values()
        )
    )
    searched = dict(zip(fresh, results, strict=True))

    # Rendered in call order, so chunk numbers follow the order the model asked in.
    any_shown = False
    for call, item in zip(calls, parsed, strict=True):
        if isinstance(item, ValueError):
            text = f"Error: {item}"
            stats.malformed_calls += 1
        elif (key := normalize_query(item)) in shown.results:
            text = f"{shown.results[key]}\n{DUPLICATE_NOTE}"
            stats.duplicate_calls += 1
        else:
            result = searched[key]
            if result.succeeded:
                text, new, budget_hit = render_result(
                    result.items, shown, max_chars=run.limits.max_evidence_chars
                )
                shown.results[key] = text
                stats.budget_hits += budget_hit
                any_shown = any_shown or bool(new)
            else:
                text, new = f"Error: tìm kiếm thất bại ({result.error})", []
            run.record_tool_search(fresh[key], result, new, now=deps.clock.now())
        loop.messages.append(
            ChatMessage(role=ChatRole.TOOL, content=text, tool_call_id=call.id)
        )
    stats.tool_calls += len(calls)
    loop.pending_calls = []
    if any_shown:
        emit(ProgressEvent.phase(Phase.READING))
    return {"run": run, "react": loop}


@guarded(ErrorCode.ANSWER_FAILED)
async def finalize_node(
    state: ChatTurnState, *, runtime: Runtime[TurnContext]
) -> NodeUpdate:
    run, deps, loop = state.run, runtime.context.deps, _loop(state)
    stats = _stats(run)
    emit(ProgressEvent.phase(Phase.ANSWERING))
    by_chunk = {e.hit.chunk_version_id: e for e in run.evidence.items}
    shown = sorted(loop.shown.numbers.items(), key=lambda item: item[1])
    # Numbers run 1..n in first-shown order, so the context view numbers them the same.
    context_text, numbered = run.evidence.context_view(
        [by_chunk[chunk_id] for chunk_id, _ in shown]
    )
    if run.actions.last_of(ActionKind.SEARCH) is None:
        stats.answered_without_search = True
        plan = AnswerPlan(mode=AnswerMode.NO_RETRIEVAL)
    elif not numbered:
        plan = AnswerPlan(mode=AnswerMode.ABSTAIN)
    else:
        partial = stats.round_cap_hit or stats.budget_forced or stats.budget_hits > 0
        plan = AnswerPlan(mode=AnswerMode.GROUNDED, partial=partial)
    run.submit_plan(plan, now=deps.clock.now())
    nodes.emit_evidence(numbered)

    sanitizer = CitationSanitizer(index for index, _ in numbered)
    answer = sanitizer.feed(loop.final_text) + sanitizer.flush()
    if answer:
        emit(ProgressEvent.token(answer))
    citations = citations_from(numbered, sanitizer.used)
    nodes.emit_citations(citations)
    run.complete()
    return {
        "run": run,
        "answer_text": answer,
        "citations": citations,
        "context_text": context_text,
    }


def route_after_guard(state: ChatTurnState) -> Literal["agent", "answer", "fallback"]:
    if routing.failed(state):
        return "fallback"
    verdict = state.run.guard_verdict
    return "agent" if verdict is not None and verdict.allows_processing else "answer"


def route_after_agent(
    state: ChatTurnState,
) -> Literal["agent", "tools", "finalize", "fallback"]:
    if routing.failed(state):
        return "fallback"
    loop = _loop(state)
    if loop.pending_calls:
        return "tools"
    return "finalize" if loop.answered else "agent"


def route_after_tools(state: ChatTurnState) -> Literal["agent", "fallback"]:
    return "fallback" if routing.failed(state) else "agent"


def build_react_graph() -> ChatGraph:
    """guard → agent ⇄ tools → finalize, with answer (blocked, redirect) and fallback."""
    builder = StateGraph(ChatTurnState, context_schema=TurnContext)
    builder.add_node("guard", nodes.guard_node)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_node)
    builder.add_node("finalize", finalize_node)
    builder.add_node("answer", nodes.answer_node)
    builder.add_node("fallback", nodes.fallback_node)

    builder.add_edge(START, "guard")
    builder.add_conditional_edges("guard", route_after_guard)
    builder.add_conditional_edges("agent", route_after_agent)
    builder.add_conditional_edges("tools", route_after_tools)
    builder.add_conditional_edges("finalize", routing.route_after_answer)
    builder.add_conditional_edges("answer", routing.route_after_answer)
    builder.add_edge("fallback", END)
    return builder.compile()
