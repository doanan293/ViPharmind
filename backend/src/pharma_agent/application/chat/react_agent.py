"""The ReAct agent of one turn (spec v2 §2.4) on LangChain's `create_agent`.

The agent loops model ⇄ tools by itself over the one search tool. A middleware holds it
to the domain rules: the round cap, the LLM-call and token budget, malformed calls and
the usage the turn reports. The search calls of one model response form one search
round: each new query is searched once, all at the same time, the results are numbered
in call order and the round is logged as one search.
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Annotated, Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, InjectedToolCallId, StructuredTool
from langgraph.config import get_config
from langgraph.types import Command
from pydantic import ValidationError

from pharma_agent.application.chat.context import TurnDeps
from pharma_agent.application.progress import Phase, ProgressEvent
from pharma_agent.domain.agent.actions import ActionKind
from pharma_agent.domain.agent.budget import BudgetExhausted
from pharma_agent.domain.agent.react import (
    DUPLICATE_NOTE,
    MAX_TOOL_ROUNDS,
    REACT_SYSTEM,
    ROUND_CAP_NOTE,
    SEARCH_TOOL_DESCRIPTION,
    SEARCH_TOOL_NAME,
    SearchArgs,
    Shown,
    normalize_query,
    render_result,
)
from pharma_agent.domain.agent.run import AgentRun, InvalidTransition, ReactStats
from pharma_agent.domain.llm.models import ChatMessage, ChatRole, LlmUsage
from pharma_agent.domain.retrieval.models import Hit, Query, QueryOrigin, ReleaseScope
from pharma_agent.domain.retrieval.service import SearchResult

Notify = Callable[[ProgressEvent], None]


@dataclass(frozen=True)
class _Call:
    """One tool call of a model response, checked: `query` when it is a valid search,
    otherwise `error` says what is wrong."""

    call: ToolCall
    arguments: str
    query: str = ""
    error: str | None = None


class ReactSession:
    """What the tool and the middleware of one turn share: the run, the chunks shown and
    the current search round."""

    def __init__(
        self,
        run: AgentRun,
        deps: TurnDeps,
        *,
        scope: ReleaseScope | None,
        notify: Notify,
    ) -> None:
        self.run = run
        self.deps = deps
        self.scope = scope
        self.notify = notify
        if run.react is None:
            run.react = ReactStats()
        self.stats = run.react
        self.shown = Shown()
        # The next model call answers without tools.
        self.forced = False
        # Call id → the query or the error of the current round's calls.
        self._queries: dict[str, str] = {}
        self._errors: dict[str, str] = {}
        self._round: asyncio.Future[dict[str, str]] | None = None

    async def answer(self, history: Sequence[ChatMessage]) -> AIMessage:
        """Run the agent to its final message. The parent graph's config carries the
        callbacks, so the agent's model and tool calls join the turn's trace."""
        model = self.deps.agent_model
        if model is None:
            raise InvalidTransition("no agent model is configured")
        agent = create_agent(
            model,
            tools=[self.search_tool()],
            system_prompt=REACT_SYSTEM,
            middleware=[ReactBudget(self)],
        )
        config: RunnableConfig = {**get_config(), "run_name": "react_agent"}
        result = await agent.ainvoke(
            {"messages": [_langchain_message(m) for m in history]}, config=config
        )
        final = result["messages"][-1]
        if not isinstance(final, AIMessage):
            raise InvalidTransition(f"the agent ended on a {type(final).__name__}")
        return final

    def search_tool(self) -> BaseTool:
        async def search_corpus(
            query: str, tool_call_id: Annotated[str, InjectedToolCallId]
        ) -> str:
            return await self._search_result(tool_call_id, query)

        return StructuredTool.from_function(
            coroutine=search_corpus,
            name=SEARCH_TOOL_NAME,
            description=SEARCH_TOOL_DESCRIPTION,
            args_schema=SearchArgs,
        )

    def tool_error(self, call_id: str) -> str | None:
        return self._errors.get(call_id)

    def begin_round(self, calls: Sequence[_Call]) -> None:
        """The calls of a model response that asked for tools; searched on first use."""
        self._queries = {c.call["id"] or "": c.query for c in calls if c.error is None}
        self._errors = {c.call["id"] or "": c.error for c in calls if c.error}
        self._round = None
        self.stats.rounds += 1
        self.stats.tool_calls += len(calls)
        self.stats.malformed_calls += len(self._errors)
        self.notify(ProgressEvent.phase(Phase.SEARCHING, round=self.stats.rounds))

    async def _search_result(self, call_id: str, query: str) -> str:
        if self._queries.get(call_id) != query:
            raise InvalidTransition(f"tool call {call_id} is not in the current round")
        # The agent runs a response's tool calls at the same time; the first one starts
        # the round's searches and every call reads its own text from them.
        if self._round is None:
            self._round = asyncio.ensure_future(self._search_round())
        return (await self._round)[call_id]

    async def _search_round(self) -> dict[str, str]:
        run, deps, stats, shown = self.run, self.deps, self.stats, self.shown
        # Each new query is searched once, all of them at the same time.
        fresh: dict[str, Query] = {}
        first = run.actions.last_of(ActionKind.SEARCH) is None
        for query in self._queries.values():
            key = normalize_query(query)
            if key not in shown.results and key not in fresh:
                origin = (
                    QueryOrigin.INITIAL if first and not fresh else QueryOrigin.REFINED
                )
                fresh[key] = Query(text=query, origin=origin)
        results: list[SearchResult] = await asyncio.gather(
            *(
                deps.retrieval.search([q], rerank_query=q.text, scope=self.scope)
                for q in fresh.values()
            )
        )
        searched = dict(zip(fresh, results, strict=True))

        # Rendered in call order, so chunk numbers follow the order the model asked in.
        texts: dict[str, str] = {}
        answered: dict[str, str] = {}
        new_hits: list[Hit] = []
        for call_id, query in self._queries.items():
            key = normalize_query(query)
            if key in shown.results or key in answered:
                earlier = shown.results.get(key) or answered[key]
                text = f"{earlier}\n{DUPLICATE_NOTE}"
                stats.duplicate_calls += 1
            else:
                result = searched[key]
                if result.succeeded:
                    text, new, budget_hit = render_result(
                        result.items, shown, max_chars=run.limits.max_evidence_chars
                    )
                    shown.results[key] = text
                    stats.budget_hits += budget_hit
                    new_hits += new
                else:
                    # Not kept in shown.results: a later round may search it again.
                    text = f"Error: tìm kiếm thất bại ({result.error})"
                answered[key] = text
            texts[call_id] = text
        if fresh:
            run.record_tool_searches(
                list(fresh.values()), results, new_hits, now=deps.clock.now()
            )
        if new_hits:
            self.notify(ProgressEvent.phase(Phase.READING))
        return texts


class ReactBudget(AgentMiddleware):
    """Holds the agent to the domain budget around each model and tool call.

    A model call after MAX_TOOL_ROUNDS rounds, or with fewer than two LLM calls left,
    answers without tools: ROUND_CAP_NOTE is appended and tool_choice is "none" (the tool
    stays declared, since the history holds tool calls). Each response is charged to
    the run and logged as an agent action; malformed calls are answered with an error
    instead of running the tool.
    """

    def __init__(self, session: ReactSession) -> None:
        self._session = session

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        session = self._session
        run, stats = session.run, session.stats
        capped = stats.rounds >= MAX_TOOL_ROUNDS
        final = session.forced or capped or run.calls_left < 2
        if final:
            if capped:
                stats.round_cap_hit = True
            else:
                stats.budget_forced = True
            call = request.override(
                messages=[*request.messages, HumanMessage(content=ROUND_CAP_NOTE)],
                tool_choice="none",
            )
        else:
            call = request.override(
                model_settings={**request.model_settings, "parallel_tool_calls": True}
            )
        started = time.perf_counter()
        response = await handler(call)
        message = _ai_message(response.result)
        usage = _usage(message)
        stats.record_model_call(usage, time.perf_counter() - started)
        calls = [] if final else _checked_calls(message)
        over_budget = False
        try:
            run.charge(usage)
        except BudgetExhausted:
            over_budget = True
        run.record_tool_round(
            [c.call["name"] for c in calls],
            [c.arguments for c in calls],
            now=session.deps.clock.now(),
            malformed=[c.error is not None for c in calls],
            finish_reason=str(message.response_metadata.get("finish_reason") or ""),
        )
        if calls and over_budget:
            # No budget left for the searches it asked for: one last call answers
            # without tools.
            session.forced = True
            return await self.awrap_model_call(request, handler)
        if calls:
            session.begin_round(calls)
        # A final response carries no calls even when the server returned some anyway.
        update = {"tool_calls": [c.call for c in calls], "invalid_tool_calls": []}
        return ModelResponse(result=[message.model_copy(update=update)])

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        call = request.tool_call
        error = self._session.tool_error(call["id"] or "")
        if error is None:
            return await handler(request)
        return ToolMessage(
            content=f"Error: {error}",
            tool_call_id=call["id"] or "",
            name=call["name"],
            status="error",
        )


def _ai_message(messages: Sequence[BaseMessage]) -> AIMessage:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message
    raise InvalidTransition("the agent model returned no AI message")


def _usage(message: AIMessage) -> LlmUsage:
    metadata = message.usage_metadata
    if metadata is None:
        return LlmUsage()
    prompt = metadata.get("input_tokens", 0)
    output = metadata.get("output_tokens", 0)
    total = metadata.get("total_tokens", 0)
    reasoning = (metadata.get("output_token_details") or {}).get("reasoning", 0)
    # As in the LlmPort adapter: some OpenAI-compatible proxies report reasoning tokens
    # only in total_tokens; the larger value bills them either way.
    return LlmUsage(
        prompt_tokens=prompt,
        completion_tokens=max(output, total - prompt),
        reasoning_tokens=reasoning,
    )


def _checked_calls(message: AIMessage) -> list[_Call]:
    """The response's tool calls in order, each with a unique id: arguments that are not
    JSON become a call with no arguments and an error, like any other malformed call."""
    calls: list[_Call] = []
    ids: set[str] = set()

    def unique(call_id: str | None) -> str:
        # Each tool message answers one id, so an empty or repeated id is replaced.
        result = call_id or ""
        if not result or result in ids:
            result = f"call_{len(calls)}"
        ids.add(result)
        return result

    for raw in message.tool_calls:
        call = ToolCall(
            name=raw["name"],
            args=raw["args"],
            id=unique(raw.get("id")),
            type="tool_call",
        )
        arguments = json.dumps(raw["args"], ensure_ascii=False)
        if raw["name"] != SEARCH_TOOL_NAME:
            error = f"unknown tool {raw['name']}; the only tool is {SEARCH_TOOL_NAME}"
            calls.append(_Call(call, arguments, error=error))
            continue
        try:
            query = SearchArgs.model_validate(raw["args"]).query
        except ValidationError:
            error = f"{SEARCH_TOOL_NAME} needs a non-empty string argument query"
            calls.append(_Call(call, arguments, error=error))
            continue
        calls.append(_Call(call, arguments, query=query))
    for invalid in message.invalid_tool_calls:
        name = invalid.get("name") or SEARCH_TOOL_NAME
        call = ToolCall(
            name=name, args={}, id=unique(invalid.get("id")), type="tool_call"
        )
        # LangChain's parse error is long and generic; the model needs only the gist.
        error = "arguments are not valid JSON"
        calls.append(_Call(call, invalid.get("args") or "", error=error))
    return calls


def _langchain_message(message: ChatMessage) -> BaseMessage:
    if message.role is ChatRole.SYSTEM:
        return SystemMessage(content=message.content)
    if message.role is ChatRole.ASSISTANT:
        return AIMessage(content=message.content)
    return HumanMessage(content=message.content)
