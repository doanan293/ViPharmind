import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langchain_core.language_models import BaseChatModel
from pharma_agent.application.chat.graph import ChatGraph, build_chat_graph
from pharma_agent.application.chat.react_graph import build_react_graph
from pharma_agent.domain.agent.actions import Action, ActionKind
from pharma_agent.domain.agent.budget import BudgetLimits
from pharma_agent.domain.agent.decisions import GuardThresholds
from pharma_agent.domain.agent.schemas import (
    Audience,
    Intent,
    JudgeDecision,
    JudgeOutcome,
    Language,
    RephraseResult,
)
from pharma_agent.domain.guardrail.models import LlmGuardVerdict
from pharma_agent.domain.llm.models import LlmRole, LlmUsage
from pharma_agent.domain.llm.port import LlmError
from pharma_agent.infrastructure.settings import Settings
from tests.e2e.factories import (
    FakeDecision,
    FakeRetriever,
    ScriptedChatModel,
    ScriptedLlm,
    answering,
    make_hit,
    retrieval_service,
    searching,
)

from pharma_lab.e2e.configs import E2EConfig, pipeline_for
from pharma_lab.e2e.executor import (
    BackendTurnExecutor,
    conversation_for,
    degraded_steps,
)
from pharma_lab.e2e.golden import Category, GoldenItem
from pharma_lab.e2e.harness import (
    DecisionVersionGuard,
    release_probe,
    run_items,
    select_items,
    spread,
    with_deadline,
)
from pharma_lab.e2e.recording_llm import RecordingLlm
from pharma_lab.e2e.records import (
    AnswerRecord,
    DecisionRecord,
    JsonlStore,
    RetrievedChunk,
    RoundRecord,
)

SECTION = "drug:paracetamol:lieu-dung"


def item(item_id: str = "e2e-mt-0001") -> GoldenItem:
    return GoldenItem.model_validate(
        {
            "item_id": item_id,
            "category": "multi_turn",
            "turns": [
                {"role": "user", "text": "Paracetamol dùng làm gì?"},
                {"role": "assistant", "text": "Giảm đau, hạ sốt."},
                {"role": "user", "text": "Người lớn uống tối đa bao nhiêu?"},
            ],
            "expected_behavior": "grounded",
            "gold_section_ids": [SECTION],
            "reference": {
                "answer": "4 g/ngày",
                "key_facts": [
                    {"fact": "4 g", "evidence_quote": "4 g", "section_id": SECTION}
                ],
            },
        }
    )


def llm(*, judge: bool, rephrase: bool) -> ScriptedLlm:
    fake = ScriptedLlm(answer="Tối đa 4 g mỗi ngày [1].")
    fake.script(
        LlmRole.GUARDRAIL, LlmGuardVerdict(is_attack=False, in_scope=True, reason="ok")
    )
    if rephrase:
        fake.script(
            LlmRole.REPHRASE,
            RephraseResult(
                standalone_query="Liều tối đa paracetamol người lớn",
                audience=Audience.GENERAL_PUBLIC,
                language=Language.VI,
                intent=Intent.PHARMA_QUESTION,
                subjects=[],
            ),
        )
    if judge:
        fake.script(
            LlmRole.JUDGE,
            JudgeDecision(
                decision=JudgeOutcome.ANSWER, gaps=[], reason="đủ", confidence=1.0
            ),
        )
    return fake


def executor(
    fake: ScriptedLlm,
    retriever: FakeRetriever,
    config: E2EConfig,
    *,
    graph: ChatGraph | None = None,
    agent_model: BaseChatModel | None = None,
):
    return BackendTurnExecutor(
        graph=graph if graph is not None else build_chat_graph(),
        llm=fake,
        retrieval=retrieval_service(retriever),
        limits=BudgetLimits(),
        pipeline=pipeline_for(config),
        config=str(config),
        agent_model=agent_model,
    )


def test_history_becomes_the_conversation_context() -> None:
    context = conversation_for(item())
    assert [(t.user_text, t.assistant_text) for t in context.turns] == [
        ("Paracetamol dùng làm gì?", "Giảm đau, hạ sốt.")
    ]


async def test_full_agent_record_maps_citations_to_gold_labels() -> None:
    fake = llm(judge=True, rephrase=True)
    retriever = FakeRetriever(
        [
            make_hit("a", SECTION, ordinal=2, score=0.9),
            make_hit("b", "other", score=0.1),
        ]
    )

    record = await executor(fake, retriever, E2EConfig.FULL).execute(item())

    assert record.status == "completed"
    assert record.answer_mode == "grounded"
    assert record.standalone_query == "Liều tối đa paracetamol người lớn"
    assert record.search_queries == [["Liều tối đa paracetamol người lớn"]]
    assert record.judge_outcomes == ["answer"]
    assert [(c.index, c.chunk_id, c.section_ids) for c in record.citations] == [
        (1, "drug:paracetamol:chunk-002", [SECTION])
    ]
    assert record.retrieved[0] == RetrievedChunk(
        chunk_id="drug:paracetamol:chunk-002", section_ids=[SECTION]
    )
    assert record.rounds == [
        RoundRecord(
            sections=sorted([SECTION, "other"]),
            chunks=2,
            evidence_chars=sum(len(h.chunk_text) for h in retriever.hits),
        )
    ]
    assert record.context_text.startswith("[1] Paracetamol > Liều dùng")
    assert record.llm_calls == 4
    assert sorted(record.usage_by_role) == ["answer", "guardrail", "judge", "rephrase"]
    assert record.usage_by_role["answer"].prompt_tokens == 100
    llm_seconds = sum(entry.seconds for entry in record.usage_by_role.values())
    assert 0 <= record.non_llm_seconds <= record.latency_seconds
    assert llm_seconds <= record.latency_seconds + 0.01
    assert not record.retryable
    assert "Người lớn uống tối đa" in fake.calls[1][1][-1].content


async def test_answer_record_keeps_every_raw_decision() -> None:
    fake = llm(judge=False, rephrase=True)
    fake.scripts[LlmRole.GUARDRAIL] = []
    decision = FakeDecision(
        {"is_attack": 0.0, "is_about_medicines": 0.9, "sufficient_overall": 0.9}
    )
    retriever = FakeRetriever([make_hit("a", SECTION, score=0.9)])
    full = BackendTurnExecutor(
        graph=build_chat_graph(),
        llm=fake,
        retrieval=retrieval_service(retriever),
        limits=BudgetLimits(),
        pipeline=pipeline_for(E2EConfig.FULL),
        config="full",
        decisions={LlmRole.GUARDRAIL: decision, LlmRole.JUDGE: decision},
    )

    record = await full.execute(item())

    assert [d.role for d in record.decisions] == ["guardrail", "judge"]
    assert record.decisions[0].model == "jev-1.13.0"
    assert record.decisions[1].answers["sufficient_overall"] == 0.9
    assert record.decisions[1].raw == {"answers": {}}
    assert record.usage_by_role["judge"].prompt_tokens == 300
    assert record.usage_by_role["guardrail"].calls == 1
    assert record.llm_calls == 4
    assert not record.retryable


async def test_the_judges_own_intent_call_is_recorded_as_a_judge_decision() -> None:
    fake = llm(judge=False, rephrase=True)
    decision = FakeDecision({"asks_dosage": 0.9, "sufficient_overall": 0.9})
    retriever = FakeRetriever([make_hit("a", SECTION, score=0.9)])
    full = BackendTurnExecutor(
        graph=build_chat_graph(),
        llm=fake,
        retrieval=retrieval_service(retriever),
        limits=BudgetLimits(),
        pipeline=pipeline_for(E2EConfig.FULL),
        config="full",
        decisions={LlmRole.JUDGE: decision},
    )

    record = await full.execute(item())

    assert [d.role for d in record.decisions] == ["judge", "judge"]
    assert record.decisions[0].answers["asks_dosage"] == 0.9
    assert all(key.startswith("asks_") for key in decision.calls[0][2])
    assert record.usage_by_role["guardrail"].calls == 1
    assert record.usage_by_role["judge"].calls == 2


async def test_a_decision_judge_leaves_the_llm_guard_usage_alone() -> None:
    fake = llm(judge=False, rephrase=True)
    decision = FakeDecision({"asks_dosage": 0.9, "sufficient_overall": 0.9})
    retriever = FakeRetriever([make_hit("a", SECTION, score=0.9)])
    full = BackendTurnExecutor(
        graph=build_chat_graph(),
        llm=fake,
        retrieval=retrieval_service(retriever),
        limits=BudgetLimits(),
        pipeline=pipeline_for(E2EConfig.FULL),
        config="full",
        decisions={LlmRole.JUDGE: decision},
    )

    record = await full.execute(item())

    guard = record.usage_by_role["guardrail"]
    assert (guard.calls, guard.prompt_tokens) == (1, 10)
    judge = record.usage_by_role["judge"]
    assert (judge.calls, judge.prompt_tokens) == (2, 600)


@pytest.mark.parametrize(("block", "status"), [(0.5, "blocked"), (0.7, "completed")])
async def test_executor_applies_the_configured_guard_thresholds(
    block: float, status: str
) -> None:
    fake = llm(judge=False, rephrase=False)
    decision = FakeDecision({"is_attack": 0.6, "is_about_medicines": 0.9})
    retriever = FakeRetriever([make_hit("a", SECTION, score=0.9)])
    guarded = BackendTurnExecutor(
        graph=build_chat_graph(),
        llm=fake,
        retrieval=retrieval_service(retriever),
        limits=BudgetLimits(),
        pipeline=pipeline_for(E2EConfig.ONE_STEP),
        config="one_step",
        decisions={LlmRole.GUARDRAIL: decision},
        guard_thresholds=GuardThresholds(block=block),
    )

    record = await guarded.execute(item())

    assert record.status == status


async def test_one_step_searches_the_raw_question_without_a_judge() -> None:
    fake = llm(judge=False, rephrase=False)
    retriever = FakeRetriever([make_hit("a", SECTION, score=0.9)])

    record = await executor(fake, retriever, E2EConfig.ONE_STEP).execute(item())

    assert retriever.queries == [["Người lớn uống tối đa bao nhiêu?"]]
    assert record.judge_outcomes == ["skipped"]
    assert record.llm_calls == 2
    assert record.answer_mode == "grounded"


async def test_a_failed_answer_is_a_retryable_record() -> None:
    fake = llm(judge=False, rephrase=False)
    fake.stream_error = LlmError("endpoint down")
    retriever = FakeRetriever([make_hit("a", SECTION)])

    record = await executor(fake, retriever, E2EConfig.ONE_STEP).execute(item())

    assert record.status == "error"
    assert record.retryable
    assert record.error is not None and record.error.startswith("ANSWER_FAILED")


@pytest.mark.parametrize(
    ("role", "step"),
    [
        (LlmRole.GUARDRAIL, "guard"),
        (LlmRole.REPHRASE, "rephrase"),
        (LlmRole.JUDGE, "judge"),
    ],
)
async def test_a_step_that_fell_back_is_a_retryable_record(role, step) -> None:
    # In production a failed LLM step falls back and the turn goes on. In an
    # evaluation that silently turns the item into another configuration, so the
    # record must be an error that --retry-errors runs again.
    fake = llm(judge=True, rephrase=True)
    fake.scripts[role] = [LlmError("quota exhausted")]
    retriever = FakeRetriever([make_hit("a", SECTION, score=0.9)])

    record = await executor(fake, retriever, E2EConfig.FULL).execute(item())

    assert record.retryable
    assert record.error is not None and f"degraded: {step}" in record.error


class CountingExecutor:
    def __init__(self, failing: set[str]) -> None:
        self.failing = failing
        self.seen: list[str] = []
        self.active = 0
        self.peak = 0

    async def execute(self, item: GoldenItem) -> AnswerRecord:
        golden = item
        self.seen.append(golden.item_id)
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        if golden.item_id in self.failing:
            raise RuntimeError("endpoint down")
        return AnswerRecord(item_id=golden.item_id, config="full", status="completed")


async def test_run_items_resumes_and_retries_only_on_request(tmp_path: Path) -> None:
    items = [item(f"e2e-mt-{n:04d}") for n in range(1, 7)]
    store = JsonlStore(tmp_path / "answers.jsonl", AnswerRecord)
    first = CountingExecutor(failing={"e2e-mt-0002"})

    summary = await run_items(
        items, first, store, config="full", concurrency=2, retry_errors=False
    )

    assert (summary.total, summary.ran, summary.errors) == (6, 6, 1)
    assert first.peak == 2
    again = CountingExecutor(failing=set())
    summary = await run_items(
        items, again, store, config="full", concurrency=2, retry_errors=False
    )
    assert again.seen == []
    assert summary.errors == 1
    summary = await run_items(
        items, again, store, config="full", concurrency=2, retry_errors=True
    )
    assert again.seen == ["e2e-mt-0002"]
    assert summary.errors == 0
    assert store.latest()["e2e-mt-0002"].status == "completed"


class VersionedExecutor:
    """Answers with a decision model whose version follows the given list."""

    def __init__(self, versions: list[str]) -> None:
        self.versions = versions

    async def execute(self, item: GoldenItem) -> AnswerRecord:
        model = self.versions.pop(0)
        return AnswerRecord(
            item_id=item.item_id,
            config="full",
            status="completed",
            decisions=[
                DecisionRecord(
                    role="judge", model=model, input_tokens=1, seconds=0.1, answers={}
                )
            ],
        )


async def test_run_items_stops_when_the_decision_model_version_changes(
    tmp_path: Path,
) -> None:
    items = [item(f"e2e-mt-{n:04d}") for n in range(1, 4)]
    store = JsonlStore(tmp_path / "answers.jsonl", AnswerRecord)

    with pytest.raises(ValueError, match=r"jev-1\.13\.0 to jev-1\.14\.0"):
        await run_items(
            items,
            VersionedExecutor(["jev-1.13.0", "jev-1.14.0", "jev-1.14.0"]),
            store,
            config="full",
            concurrency=1,
            retry_errors=False,
            decision_guard=DecisionVersionGuard(tmp_path),
        )

    assert sorted(store.latest()) == ["e2e-mt-0001"]


def test_select_items_filters_a_category_before_spreading() -> None:
    multi = [item(f"e2e-mt-{n:04d}") for n in range(1, 4)]
    answerable = [
        item(f"e2e-ans-{n:04d}").model_copy(update={"category": Category.ANSWERABLE})
        for n in range(1, 3)
    ]
    golden = [*answerable, *multi]

    assert select_items(golden, limit=None, category=None) == golden
    assert select_items(golden, limit=None, category=Category.MULTI_TURN) == multi
    chosen = select_items(golden, limit=2, category=Category.MULTI_TURN)
    assert len(chosen) == 2
    assert {i.category for i in chosen} == {Category.MULTI_TURN}
    assert select_items(golden, limit=1, category=None) == golden[:1]


def test_release_probe_comes_from_the_whole_golden_set() -> None:
    multi = [item(f"e2e-mt-{n:04d}") for n in range(1, 3)]
    answerable = item("e2e-ans-0001").model_copy(
        update={"category": Category.ANSWERABLE}
    )

    assert release_probe([*multi, answerable]) == answerable.question


def test_spread_takes_items_across_the_set() -> None:
    items = [item(f"e2e-mt-{n:04d}") for n in range(1, 11)]
    assert [i.item_id[-2:] for i in spread(items, 3)] == ["01", "05", "09"]
    assert spread(items, None) == items
    assert spread(items, 50) == items


def test_deadline_override_changes_only_the_budget() -> None:
    base = Settings(_env_file=None)
    assert with_deadline(base, None) is base
    longer = with_deadline(base, 600)
    assert longer.budget.deadline_seconds == 600
    assert base.budget.deadline_seconds == 90
    assert longer.budget.max_llm_calls == base.budget.max_llm_calls
    with pytest.raises(ValueError, match="positive"):
        with_deadline(base, 0)


def test_recording_llm_sums_reasoning_tokens() -> None:
    class ReasoningLlm(ScriptedLlm):
        async def structured(self, role, messages, schema):
            result, _ = await super().structured(role, messages, schema)
            return result, LlmUsage(
                prompt_tokens=10, completion_tokens=6, reasoning_tokens=4
            )

    llm = ReasoningLlm()
    decision = JudgeDecision(
        decision=JudgeOutcome.ANSWER, gaps=[], reason="r", confidence=1.0
    )
    llm.script(LlmRole.JUDGE, decision, decision)
    recorder = RecordingLlm(llm)
    for _ in range(2):
        asyncio.run(recorder.structured(LlmRole.JUDGE, [], JudgeDecision))
    assert recorder.usage_by_role()["judge"].reasoning_tokens == 8


async def test_answer_record_has_one_step_per_action_with_seconds() -> None:
    fake = llm(judge=True, rephrase=True)
    retriever = FakeRetriever([make_hit("a", SECTION, score=0.9)])

    record = await executor(fake, retriever, E2EConfig.FULL).execute(item())

    assert [s.kind for s in record.steps] == [
        "guard",
        "rephrase",
        "search",
        "judge",
        "answer",
    ]
    assert all(s.seconds >= 0 for s in record.steps)
    assert sum(s.seconds for s in record.steps) == pytest.approx(
        record.latency_seconds, abs=0.05
    )
    assert record.rerank_scored == 1
    assert record.retrieval_seconds >= 0.0


def test_old_answer_record_loads() -> None:
    old = {"item_id": "e2e-ans-0001", "config": "full", "status": "completed"}
    record = AnswerRecord.model_validate(old)
    assert record.steps == []
    assert record.retrieval_seconds == 0.0
    assert record.rerank_scored == 0


async def test_react_executor_records_the_react_statistics() -> None:
    fake = llm(judge=False, rephrase=False)
    model = ScriptedChatModel(responses=[searching("x"), answering("Đáp [1].")])
    record = await executor(
        fake,
        FakeRetriever([make_hit("a", SECTION, score=0.9)]),
        E2EConfig.REACT,
        graph=build_react_graph(),
        agent_model=model,
    ).execute(item())
    assert record.status == "completed"
    assert record.react is not None
    assert record.react.rounds == 1
    assert record.react.tool_calls == 1
    agent = record.usage_by_role["agent"]
    assert (agent.calls, agent.prompt_tokens, agent.completion_tokens) == (2, 400, 40)
    assert agent.seconds == record.react.model_seconds
    assert record.react.model_calls == 2
    assert [s.kind for s in record.steps][:2] == ["guard", "agent"]
    assert [(c.index, c.section_ids) for c in record.citations] == [(1, [SECTION])]
    assert record.rounds[-1].sections == [SECTION]
    assert record.search_queries == [["x"]]
    assert record.error is None


def test_a_failed_search_is_a_degraded_step() -> None:
    at = datetime(2026, 10, 16, tzinfo=UTC)
    entries = [
        Action(kind=ActionKind.SEARCH, at=at, outcome="ok"),
        Action(kind=ActionKind.SEARCH, at=at, outcome="error", reason="qdrant down"),
    ]
    assert degraded_steps(entries) == ["search"]
