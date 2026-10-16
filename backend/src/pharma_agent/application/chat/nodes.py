"""Graph nodes: thin wrappers that call the domain and emit public progress events."""

import functools
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any, Protocol

from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime

from pharma_agent.application.chat.context import TurnContext
from pharma_agent.application.chat.state import ChatTurnState
from pharma_agent.application.progress import EventType, Phase, ProgressEvent
from pharma_agent.domain.agent.actions import ActionKind
from pharma_agent.domain.agent.budget import BudgetExhausted
from pharma_agent.domain.agent.citations import (
    SNIPPET_CHARS,
    CitationSanitizer,
    citations_from,
)
from pharma_agent.domain.agent.decisions import (
    asked_intents,
    guard_state,
    intent_questions,
    judge_decision,
    judge_questions,
    judge_state,
    refine_intents,
    template_queries,
)
from pharma_agent.domain.agent.prompts import (
    answer_messages,
    fallback_text,
    judge_messages,
    refine_messages,
    rephrase_messages,
)
from pharma_agent.domain.agent.run import AgentRun, AnswerMode, ErrorCode
from pharma_agent.domain.agent.schemas import (
    JudgeDecision,
    JudgeOutcome,
    RefineResult,
    RephraseResult,
)
from pharma_agent.domain.guardrail.models import Verdict, VerdictSource
from pharma_agent.domain.llm.decision import Decision
from pharma_agent.domain.llm.models import LlmRole, LlmUsage
from pharma_agent.domain.llm.port import LlmError
from pharma_agent.domain.retrieval.models import Query, QueryOrigin
from pharma_agent.domain.shared.text import make_snippet

NodeUpdate = dict[str, Any]


class Node(Protocol):
    def __call__(
        self, state: ChatTurnState, *, runtime: Runtime[TurnContext]
    ) -> Awaitable[NodeUpdate]: ...


def _emit(event: ProgressEvent) -> None:
    get_stream_writer()(event.model_dump(mode="json"))


def guarded(code: ErrorCode) -> Callable[[Node], Node]:
    """Last line of defence: any unexpected exception fails the run so routing sends it to fallback."""

    def decorator(fn: Node) -> Node:
        @functools.wraps(fn)
        async def wrapper(
            state: ChatTurnState, *, runtime: Runtime[TurnContext]
        ) -> NodeUpdate:
            try:
                return await fn(state, runtime=runtime)
            except Exception as exc:
                if not state.run.is_finished:
                    state.run.fail(code, detail=f"{type(exc).__name__}: {exc}")
                return {"run": state.run}

        return wrapper

    return decorator


@guarded(ErrorCode.INTERNAL)
async def guard_node(
    state: ChatTurnState, *, runtime: Runtime[TurnContext]
) -> NodeUpdate:
    run, deps = state.run, runtime.context.deps
    _emit(ProgressEvent.phase(Phase.GUARDING))
    if not runtime.context.pipeline.guard:
        run.record_guard(
            Verdict(
                passed=True,
                in_scope=True,
                source=VerdictSource.SKIPPED,
                reason="guard disabled",
            ),
            now=deps.clock.now(),
        )
        return {"run": run}
    outcome = await deps.guardrail.check(
        run.original_query, runtime.context.conversation
    )
    if outcome.verdict.source in (VerdictSource.LLM, VerdictSource.DECISION):
        with suppress(BudgetExhausted):
            run.charge(outcome.usage)
    run.record_guard(
        outcome.verdict,
        now=deps.clock.now(),
        llm_failed=outcome.llm_failed,
        asked_intents=outcome.asked_intents,
        decision=outcome.decision,
    )
    return {"run": run}


@guarded(ErrorCode.REPHRASE_FAILED)
async def rephrase_node(
    state: ChatTurnState, *, runtime: Runtime[TurnContext]
) -> NodeUpdate:
    run, deps = state.run, runtime.context.deps
    _emit(ProgressEvent.phase(Phase.UNDERSTANDING))
    now = deps.clock.now()
    if not runtime.context.pipeline.rephrase or not run.can_afford_rephrase():
        run.record_rephrase(None, now=now, skipped=True)
        return {"run": run}
    try:
        result, usage = await deps.llm.structured(
            LlmRole.REPHRASE,
            rephrase_messages(run.original_query, runtime.context.conversation),
            RephraseResult,
        )
        run.charge(usage)
    except (LlmError, BudgetExhausted):
        run.record_rephrase(None, now=now, failed=True)
        return {"run": run}
    run.record_rephrase(result, now=now)
    return {"run": run}


@guarded(ErrorCode.SEARCH_FAILED)
async def search_node(
    state: ChatTurnState, *, runtime: Runtime[TurnContext]
) -> NodeUpdate:
    run, deps = state.run, runtime.context.deps
    queries = state.pending_queries or [
        Query(text=run.standalone_query, origin=QueryOrigin.INITIAL)
    ]
    _emit(ProgressEvent.phase(Phase.SEARCHING, round=run.usage.search_rounds + 1))
    result = await deps.retrieval.search(
        queries,
        rerank_query=run.standalone_query,
        known_scores=run.evidence.rerank_scores(),
        scope=runtime.context.scope,
    )
    run.record_search(queries, result, now=deps.clock.now())
    if result.items:
        _emit(ProgressEvent.phase(Phase.READING))
    return {"run": run, "pending_queries": []}


@guarded(ErrorCode.JUDGE_FAILED)
async def judge_node(
    state: ChatTurnState, *, runtime: Runtime[TurnContext]
) -> NodeUpdate:
    run, deps = state.run, runtime.context.deps
    now = deps.clock.now()
    if not runtime.context.pipeline.judge_refine:
        run.skip_judge(now=now)
        return {"run": run, "last_gaps": []}
    gaps: list[str] = []
    tau = runtime.context.pipeline.refine_threshold
    decision_port = deps.decisions.get(LlmRole.JUDGE)
    intents: Decision | None = None
    if decision_port is not None and _judge_asks_intents(run):
        # The guard did not ask the intents on the decision model (disabled, failed
        # open, regex or LLM guard), so the judge asks them once per turn itself.
        try:
            intents = await decision_port.decide(
                LlmRole.JUDGE,
                guard_state(runtime.context.conversation, run.original_query),
                intent_questions(),
            )
            run.adopt_asked_intents(
                asked_intents(intents.answers, deps.guardrail.thresholds.asks)
            )
        except LlmError:
            run.adopt_asked_intents([])
    raw: Decision | None = None
    try:
        if intents is not None:
            run.charge(LlmUsage(prompt_tokens=intents.input_tokens))
        if decision_port is not None:
            packed = run.evidence.pack(run.limits.max_evidence_chars)
            raw = await decision_port.decide(
                LlmRole.JUDGE,
                judge_state(
                    run.original_query, run.standalone_query, run.asked_intents, packed
                ),
                judge_questions(run.asked_intents),
            )
            decision = judge_decision(
                raw.answers, run.asked_intents, tau if tau is not None else 0.5
            )
            usage = LlmUsage(prompt_tokens=raw.input_tokens)
        else:
            decision, usage = await deps.llm.structured(
                LlmRole.JUDGE,
                judge_messages(run, run.evidence.summary_view()),
                JudgeDecision,
            )
            if tau is not None:
                decision = decision.model_copy(
                    update={
                        "decision": JudgeOutcome.ANSWER
                        if decision.confidence >= tau
                        else JudgeOutcome.SEARCH_MORE
                    }
                )
        if tau is not None and tau >= 1:
            # tau = 1 means refine until the round limit, whatever the confidence.
            decision = decision.model_copy(
                update={"decision": JudgeOutcome.SEARCH_MORE}
            )
        run.charge(usage)
        run.record_judge(
            decision.decision,
            gaps=decision.gaps,
            reason=decision.reason,
            confidence=decision.confidence,
            now=now,
            decision=raw,
            intents_decision=intents,
        )
        gaps = list(decision.gaps)
    except (LlmError, BudgetExhausted) as exc:
        # A paid decision call stays on record even when charging it ran out of budget.
        run.record_judge(
            JudgeOutcome.ANSWER,
            gaps=[],
            reason=str(exc),
            confidence=0.0,
            now=now,
            failed=True,
            decision=raw,
            intents_decision=intents,
        )
    return {"run": run, "last_gaps": gaps}


def _judge_asks_intents(run: AgentRun) -> bool:
    """First judge of the turn, and the guard verdict is not the decision model's."""
    verdict = run.guard_verdict
    first = run.actions.last_of(ActionKind.JUDGE) is None
    return first and (verdict is None or verdict.source is not VerdictSource.DECISION)


@guarded(ErrorCode.REFINE_FAILED)
async def refine_node(
    state: ChatTurnState, *, runtime: Runtime[TurnContext]
) -> NodeUpdate:
    run, deps = state.run, runtime.context.deps
    now = deps.clock.now()
    if runtime.context.pipeline.refine_mode == "template":
        subjects = run.subjects or [run.standalone_query]
        gaps = state.last_gaps or refine_intents(
            run.asked_intents, run.last_judge_answers()
        )
        fresh = run.record_refine(
            template_queries(subjects, gaps), now=now, mode="template"
        )
        return {"run": run, "pending_queries": fresh}
    hints: list[str] = []
    for evidence in run.evidence.active():
        hints.extend(h for h in evidence.hit.term_hints() if h not in hints)
    try:
        result, usage = await deps.llm.structured(
            LlmRole.REFINE,
            refine_messages(run, state.last_gaps, hints[:10]),
            RefineResult,
        )
        run.charge(usage)
        fresh = run.record_refine(result.queries, now=now)
    except (LlmError, BudgetExhausted):
        fresh = run.record_refine([], now=now, failed=True)
    return {"run": run, "pending_queries": fresh}


@guarded(ErrorCode.ANSWER_FAILED)
async def answer_node(
    state: ChatTurnState, *, runtime: Runtime[TurnContext]
) -> NodeUpdate:
    run, deps = state.run, runtime.context.deps
    _emit(ProgressEvent.phase(Phase.ANSWERING))
    plan = run.decide_answer()
    run.submit_plan(plan, now=deps.clock.now())

    packed = (
        run.evidence.pack(run.limits.max_evidence_chars)
        if plan.mode is AnswerMode.GROUNDED
        else []
    )
    context_text, numbered = run.evidence.context_view(packed)
    if numbered:
        _emit(
            ProgressEvent(
                type=EventType.EVIDENCE,
                data={
                    "items": [
                        {
                            "index": index,
                            "source": e.hit.source,
                            "title": e.hit.title,
                            "section": e.hit.section,
                            "start_page": e.hit.start_page,
                            "end_page": e.hit.end_page,
                            "snippet": make_snippet(e.hit.chunk_text, SNIPPET_CHARS),
                        }
                        for index, e in numbered
                    ]
                },
            )
        )

    sanitizer = CitationSanitizer(index for index, _ in numbered)
    parts: list[str] = []
    usage = LlmUsage()
    async for delta in deps.llm.stream(
        LlmRole.ANSWER, answer_messages(run, plan, context_text)
    ):
        if delta.text:
            clean = sanitizer.feed(delta.text)
            if clean:
                parts.append(clean)
                _emit(ProgressEvent.token(clean))
        if delta.usage is not None:
            usage = delta.usage
    tail = sanitizer.flush()
    if tail:
        parts.append(tail)
        _emit(ProgressEvent.token(tail))
    with suppress(BudgetExhausted):
        run.charge(usage)

    citations = citations_from(numbered, sanitizer.used)
    _emit(
        ProgressEvent(
            type=EventType.CITATIONS,
            data={"items": [c.model_dump(mode="json") for c in citations]},
        )
    )
    run.complete()
    return {
        "run": run,
        "answer_text": "".join(parts),
        "citations": citations,
        "context_text": context_text,
    }


async def fallback_node(
    state: ChatTurnState, *, runtime: Runtime[TurnContext]
) -> NodeUpdate:
    run = state.run
    if not run.is_finished:
        run.fail(ErrorCode.INTERNAL, detail="fallback reached without a recorded error")
    text = fallback_text(run.status)
    _emit(ProgressEvent.token(text))
    return {"run": run, "answer_text": text, "citations": []}
