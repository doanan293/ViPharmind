"""Run one golden item through the backend chat graph (spec §6)."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence

from pharma_agent.application.chat.context import PipelineOptions, TurnDeps
from pharma_agent.application.chat.graph import ChatGraph
from pharma_agent.application.chat.runner import ChatTurnRunner, TurnOutcome
from pharma_agent.domain.agent.actions import Action, ActionKind
from pharma_agent.domain.agent.budget import BudgetLimits
from pharma_agent.domain.agent.decisions import GuardThresholds
from pharma_agent.domain.agent.run import AgentRun, AnswerMode, RunStatus
from pharma_agent.domain.conversation.models import ConversationContext, Turn
from pharma_agent.domain.guardrail.service import DEFAULT_THRESHOLDS, GuardrailService
from pharma_agent.domain.llm.decision import DecisionPort
from pharma_agent.domain.llm.models import ChatMessage, ChatRole, LlmRole, system, user
from pharma_agent.domain.llm.port import LlmError, LlmPort
from pharma_agent.domain.retrieval.service import RetrievalService
from pharma_agent.domain.shared.clock import Clock, SystemClock

from pharma_lab.bundle.chunks import gold_chunk_label
from pharma_lab.e2e.golden import GoldenItem
from pharma_lab.e2e.recording_llm import RecordingLlm
from pharma_lab.e2e.records import (
    AnswerRecord,
    CitedSection,
    DecisionRecord,
    ReactRecord,
    RetrievedChunk,
    RoundRecord,
    StepRecord,
    TokenUsage,
)

E2E_USER = "e2e-evaluation"

# The closed-book baseline gets the same role and answering rules as the pipeline's
# answer step for an unknown audience, without documents or citation rules.
CLOSED_BOOK_SYSTEM = (
    "Bạn là trợ lý tra cứu thông tin thuốc. Bạn trả lời thẳng vào câu hỏi, chính xác "
    "nhất có thể, bằng ngôn ngữ của người hỏi.\n\n"
    "Chưa rõ người hỏi là ai: trả lời rõ ràng, đủ ý, thuật ngữ kèm giải thích ngắn.\n\n"
    "Trả lời bằng tiếng Việt."
)


def conversation_for(item: GoldenItem) -> ConversationContext:
    return ConversationContext(
        turns=[
            Turn(user_text=user, assistant_text=assistant, status="completed")
            for user, assistant in item.history
        ]
    )


_FALLBACK_KINDS = (ActionKind.REPHRASE, ActionKind.JUDGE, ActionKind.REFINE)


def degraded_steps(entries: Sequence[Action]) -> list[str]:
    """Steps whose LLM call or search failed and fell back.

    Production keeps the turn going after such a failure. In an evaluation the item
    then silently runs another configuration, so the harness treats it as an error.
    """
    steps: list[str] = []
    for action in entries:
        if action.kind is ActionKind.GUARD:
            fell_back = action.payload.get("llm_failed") is True
        elif action.kind is ActionKind.SEARCH:
            # A retrieval outage would otherwise score as an abstention.
            fell_back = action.outcome == "error"
        else:
            fell_back = action.kind in _FALLBACK_KINDS and action.outcome == "failed"
        if fell_back and action.kind.value not in steps:
            steps.append(action.kind.value)
    return steps


def step_records(run: AgentRun, latency: float) -> list[StepRecord]:
    """Seconds between consecutive actions; the answer step runs to the end of the turn
    because its action is logged when the plan is submitted, before streaming."""
    steps: list[StepRecord] = []
    previous = run.started_at
    entries = run.actions.entries
    for index, action in enumerate(entries):
        if index == len(entries) - 1:
            seconds = max(0.0, latency - (previous - run.started_at).total_seconds())
        else:
            seconds = (action.at - previous).total_seconds()
        steps.append(
            StepRecord(
                kind=action.kind.value,
                outcome=action.outcome,
                started_at=previous.isoformat(timespec="milliseconds"),
                seconds=round(seconds, 3),
            )
        )
        previous = action.at
    return steps


def _search_total(entries: Sequence[Action], key: str) -> float:
    return sum(
        float(action.payload.get(key, 0) or 0)
        for action in entries
        if action.kind is ActionKind.SEARCH
    )


def decision_records(entries: Sequence[Action]) -> list[DecisionRecord]:
    """The raw decision-model calls the guard and judge actions carry. A judge action may
    also carry the asks_<intent> call the judge made itself when the guard verdict was
    not the decision model's; it runs on the judge role's port, so it is recorded as "judge"."""
    records: list[DecisionRecord] = []
    for action in entries:
        role = action.kind.value if action.kind is ActionKind.JUDGE else "guardrail"
        for key, key_role in (("intents_decision", "judge"), ("decision", role)):
            raw = action.payload.get(key)
            if raw is not None:
                records.append(
                    DecisionRecord(
                        role=key_role,
                        model=raw["model"],
                        input_tokens=raw["input_tokens"],
                        seconds=raw["seconds"],
                        answers=raw["answers"],
                        raw=raw.get("raw", {}),
                    )
                )
    return records


def with_decision_usage(
    usage: dict[str, TokenUsage], decisions: Sequence[DecisionRecord]
) -> dict[str, TokenUsage]:
    """Decision calls bypass RecordingLlm, so their usage comes from their records."""
    merged = dict(usage)
    for decision in decisions:
        current = merged.get(decision.role, TokenUsage())
        merged[decision.role] = TokenUsage(
            calls=current.calls + 1,
            prompt_tokens=current.prompt_tokens + decision.input_tokens,
            completion_tokens=current.completion_tokens,
            reasoning_tokens=current.reasoning_tokens,
            seconds=round(current.seconds + decision.seconds, 3),
        )
    return merged


def answer_record(
    item: GoldenItem,
    config: str,
    outcome: TurnOutcome,
    usage: dict[str, TokenUsage],
    latency: float,
) -> AnswerRecord:
    run = outcome.run
    hits = {
        evidence.hit.chunk_version_id: evidence.hit
        for evidence in run.evidence.active()
    }
    citations = []
    for citation in outcome.citations:
        hit = hits.get(citation.chunk_version_id)
        citations.append(
            CitedSection(
                index=citation.index,
                chunk_version_id=str(citation.chunk_version_id),
                chunk_id=None
                if hit is None
                else gold_chunk_label(hit.document_key, hit.ordinal),
                section_ids=[] if hit is None else list(hit.section_keys),
            )
        )
    entries = run.actions.entries
    failed = run.status in (RunStatus.ERROR, RunStatus.TIMEOUT)
    degraded = degraded_steps(entries)
    decisions = decision_records(entries)
    usage = with_decision_usage(usage, decisions)
    return AnswerRecord(
        item_id=item.item_id,
        config=config,
        status=run.status.value,
        answer_mode=None if run.plan is None else run.plan.mode.value,
        answer_text=outcome.answer_text,
        context_text=outcome.context_text,
        citations=citations,
        retrieved=[
            RetrievedChunk(
                chunk_id=gold_chunk_label(e.hit.document_key, e.hit.ordinal),
                section_ids=list(e.hit.section_keys),
            )
            for e in run.evidence.active()
        ],
        standalone_query=run.standalone_query,
        search_queries=[
            list(action.payload.get("queries", []))
            for action in entries
            if action.kind is ActionKind.SEARCH
        ],
        rounds=[
            RoundRecord(
                sections=sorted(
                    {s for item in action.payload["evidence"] for s in item["sections"]}
                ),
                chunks=len(action.payload["evidence"]),
                evidence_chars=action.payload["evidence_chars"],
            )
            for action in entries
            if action.kind is ActionKind.SEARCH
        ],
        judge_outcomes=[
            action.outcome for action in entries if action.kind is ActionKind.JUDGE
        ],
        llm_calls=run.usage.llm_calls,
        usage_by_role=usage,
        decisions=decisions,
        latency_seconds=round(latency, 3),
        non_llm_seconds=round(
            max(0.0, latency - sum(entry.seconds for entry in usage.values())), 3
        ),
        steps=step_records(run, latency),
        retrieval_seconds=round(_search_total(entries, "retrieval_seconds"), 3),
        rerank_seconds=round(_search_total(entries, "rerank_seconds"), 3),
        rerank_scored=int(_search_total(entries, "rerank_scored")),
        react=None
        if run.react is None
        else ReactRecord.model_validate(run.react.model_dump()),
        error=(
            f"{run.error_code.value}: {run.error_detail}".strip()
            if run.error_code is not None
            else f"degraded: {', '.join(degraded)}"
            if degraded
            else None
        ),
        retryable=failed or bool(degraded),
    )


class BackendTurnExecutor:
    """Runs a golden item as one chat turn with its scripted history."""

    def __init__(
        self,
        *,
        graph: ChatGraph,
        llm: LlmPort,
        retrieval: RetrievalService,
        limits: BudgetLimits,
        pipeline: PipelineOptions,
        config: str,
        clock: Clock | None = None,
        decisions: Mapping[LlmRole, DecisionPort] | None = None,
        guard_thresholds: GuardThresholds = DEFAULT_THRESHOLDS,
    ) -> None:
        self._guard_thresholds = guard_thresholds
        self._decisions = dict(decisions or {})
        self._graph = graph
        self._llm = llm
        self._retrieval = retrieval
        self._limits = limits
        self._pipeline = pipeline
        self._config = config
        self._clock = clock if clock is not None else SystemClock()

    async def execute(self, item: GoldenItem) -> AnswerRecord:
        recorder = RecordingLlm(self._llm)
        deps = TurnDeps(
            llm=recorder,
            guardrail=GuardrailService(
                recorder,
                decision=self._decisions.get(LlmRole.GUARDRAIL),
                thresholds=self._guard_thresholds,
            ),
            retrieval=self._retrieval,
            clock=self._clock,
            decisions=self._decisions,
        )
        runner = ChatTurnRunner(
            self._graph, deps, self._limits, pipeline=self._pipeline
        )
        execution = runner.start(
            user_id=E2E_USER,
            message=item.question,
            conversation=conversation_for(item),
        )
        started = time.perf_counter()
        async for _ in execution.events():
            pass
        latency = time.perf_counter() - started
        if execution.outcome is None:
            raise RuntimeError(f"{item.item_id}: the chat turn produced no outcome")
        return answer_record(
            item, self._config, execution.outcome, recorder.usage_by_role(), latency
        )


class ClosedBookExecutor:
    """Answers a golden item with the answer model alone, as a plain chat LLM."""

    def __init__(self, *, llm: LlmPort, config: str) -> None:
        self._llm = llm
        self._config = config

    @staticmethod
    def messages(item: GoldenItem) -> list[ChatMessage]:
        history: list[ChatMessage] = []
        for asked, answered in item.history:
            history += [
                user(asked),
                ChatMessage(role=ChatRole.ASSISTANT, content=answered),
            ]
        return [system(CLOSED_BOOK_SYSTEM), *history, user(item.question)]

    async def execute(self, item: GoldenItem) -> AnswerRecord:
        recorder = RecordingLlm(self._llm)
        parts: list[str] = []
        error: str | None = None
        started = time.perf_counter()
        try:
            async for delta in recorder.stream(LlmRole.ANSWER, self.messages(item)):
                parts.append(delta.text)
        except LlmError as exc:
            error = f"closed_book_failed: {exc}"
        latency = time.perf_counter() - started
        usage = recorder.usage_by_role()
        return AnswerRecord(
            item_id=item.item_id,
            config=self._config,
            status=RunStatus.ERROR.value if error else RunStatus.COMPLETED.value,
            # A closed-book answer is an attempted answer, so the judge scores its
            # content; with no context, faithfulness and citations are undefined.
            answer_mode=None if error else AnswerMode.GROUNDED.value,
            answer_text="".join(parts),
            context_text="",
            citations=[],
            retrieved=[],
            standalone_query=item.question,
            search_queries=[],
            rounds=[],
            judge_outcomes=[],
            llm_calls=1,
            usage_by_role=usage,
            latency_seconds=round(latency, 3),
            non_llm_seconds=round(
                max(0.0, latency - sum(entry.seconds for entry in usage.values())), 3
            ),
            error=error,
            retryable=error is not None,
        )
