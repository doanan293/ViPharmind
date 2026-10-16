import json

from pharma_agent.application.chat.react_graph import build_react_graph
from pharma_agent.application.chat.runner import ChatTurnRunner, TurnOutcome
from pharma_agent.domain.agent.actions import ActionKind
from pharma_agent.domain.agent.budget import BudgetLimits
from pharma_agent.domain.agent.react import (
    BUDGET_NOTE,
    DUPLICATE_NOTE,
    MAX_TOOL_ROUNDS,
    ROUND_CAP_NOTE,
)
from pharma_agent.domain.agent.run import AnswerMode, ReactStats, RunStatus
from pharma_agent.domain.guardrail.models import LlmGuardVerdict
from pharma_agent.domain.llm.models import ChatRole, LlmRole, ToolCall, ToolTurn
from pharma_agent.domain.llm.port import LlmError
from tests.domain.factories import chunk_uuid, make_hit
from tests.fakes import FakeLlm, FakeRetriever, build_deps

QUESTION = "Paracetamol người lớn uống tối đa bao nhiêu?"


def llm_with_guard(attack: bool = False) -> FakeLlm:
    llm = FakeLlm()
    llm.script(
        LlmRole.GUARDRAIL,
        LlmGuardVerdict(is_attack=attack, in_scope=True, reason="ok"),
    )
    return llm


def call(cid: str, query: str) -> ToolCall:
    return ToolCall(
        id=cid, name="search_corpus", arguments=json.dumps({"query": query})
    )


def searching(*calls: ToolCall) -> ToolTurn:
    return ToolTurn(text="", tool_calls=calls, finish_reason="tool_calls")


def answering(text: str) -> ToolTurn:
    return ToolTurn(text=text, tool_calls=(), finish_reason="stop")


async def run_react(
    llm: FakeLlm, retriever: FakeRetriever, limits: BudgetLimits | None = None
):
    runner = ChatTurnRunner(
        build_react_graph(), build_deps(llm, retriever), limits or BudgetLimits()
    )
    execution = runner.start(user_id="u1", message=QUESTION)
    events = [event async for event in execution.events()]
    assert execution.outcome is not None
    return events, execution.outcome


def stats(outcome: TurnOutcome) -> ReactStats:
    assert outcome.run.react is not None
    return outcome.run.react


def tool_messages(llm: FakeLlm, call_index: int):
    return [m for m in llm.tool_calls_seen[call_index][1] if m.role is ChatRole.TOOL]


async def test_one_search_then_answer_with_citation() -> None:
    llm = llm_with_guard()
    llm.script_tool_turns(
        searching(call("c1", "paracetamol liều người lớn")),
        answering("Tối đa 4 g mỗi ngày [1]."),
    )
    _, outcome = await run_react(llm, FakeRetriever([make_hit("c1", fusion=0.9)]))
    assert outcome.run.status is RunStatus.COMPLETED
    assert outcome.answer_text == "Tối đa 4 g mỗi ngày [1]."
    assert [c.index for c in outcome.citations] == [1]
    assert stats(outcome).rounds == 1
    assert stats(outcome).tool_calls == 1
    tools = tool_messages(llm, 1)
    assert tools[0].tool_call_id == "c1"
    assert tools[0].content.startswith("[1] ")
    assert llm.tool_calls_seen[0][2][0].name == "search_corpus"
    assert "[1]" in outcome.context_text


async def test_parallel_calls_count_one_round_and_number_in_call_order() -> None:
    llm = llm_with_guard()
    llm.script_tool_turns(
        searching(
            call("c1", "paracetamol liều"), call("c2", "paracetamol chống chỉ định")
        ),
        answering("Liều [1], chống chỉ định [2]."),
    )
    retriever = FakeRetriever([make_hit("a", fusion=0.9)], [make_hit("b", fusion=0.8)])
    _, outcome = await run_react(llm, retriever)
    assert stats(outcome).rounds == 1
    assert stats(outcome).tool_calls == 2
    first, second = tool_messages(llm, 1)
    assert (first.tool_call_id, second.tool_call_id) == ("c1", "c2")
    assert first.content.startswith("[1] ")
    assert second.content.startswith("[2] ")
    assert [c.index for c in outcome.citations] == [1, 2]


async def test_duplicate_query_reuses_the_first_result() -> None:
    llm = llm_with_guard()
    llm.script_tool_turns(
        searching(call("c1", "paracetamol liều")),
        searching(call("c2", "Paracetamol   LIỀU")),
        answering("Đáp [1]."),
    )
    retriever = FakeRetriever([make_hit("a", fusion=0.9)])
    _, outcome = await run_react(llm, retriever)
    assert len(retriever.calls) == 1
    assert stats(outcome).duplicate_calls == 1
    assert tool_messages(llm, 2)[-1].content.endswith(DUPLICATE_NOTE)


async def test_malformed_tool_call_becomes_a_tool_error() -> None:
    llm = llm_with_guard()
    llm.script_tool_turns(
        searching(ToolCall(id="c1", name="search_corpus", arguments="not json")),
        answering("Tài liệu không đề cập."),
    )
    _, outcome = await run_react(llm, FakeRetriever())
    assert tool_messages(llm, 1)[0].content.startswith("Error:")
    assert stats(outcome).malformed_calls == 1
    assert stats(outcome).rounds == 1
    assert outcome.run.status is RunStatus.COMPLETED


async def test_round_cap_forces_one_final_call_without_tools() -> None:
    llm = llm_with_guard()
    llm.script_tool_turns(
        *(searching(call(f"c{n}", f"truy vấn {n}")) for n in range(MAX_TOOL_ROUNDS)),
        answering("Đáp [1]."),
    )
    retriever = FakeRetriever(
        *([make_hit(f"h{n}", fusion=0.9)] for n in range(MAX_TOOL_ROUNDS))
    )
    _, outcome = await run_react(llm, retriever)
    last_role, last_messages, last_tools = llm.tool_calls_seen[-1]
    assert last_role is LlmRole.AGENT
    assert len(llm.tool_calls_seen) == MAX_TOOL_ROUNDS + 1
    assert last_tools == []
    assert last_messages[-1].role is ChatRole.USER
    assert last_messages[-1].content == ROUND_CAP_NOTE
    assert stats(outcome).round_cap_hit
    assert outcome.run.status is RunStatus.PARTIAL


async def test_evidence_budget_cuts_results_and_marks_partial() -> None:
    llm = llm_with_guard()
    llm.script_tool_turns(searching(call("c1", "x")), answering("Đáp [1]."))
    retriever = FakeRetriever(
        [
            make_hit("a", text="x" * 50, fusion=0.9),
            make_hit("b", text="y" * 50, fusion=0.8),
        ]
    )
    _, outcome = await run_react(llm, retriever, BudgetLimits(max_evidence_chars=60))
    assert tool_messages(llm, 1)[0].content.endswith(BUDGET_NOTE)
    assert stats(outcome).budget_hits == 1
    assert outcome.run.status is RunStatus.PARTIAL


async def test_answer_citations_map_to_shown_chunks() -> None:
    llm = llm_with_guard()
    llm.script_tool_turns(searching(call("c1", "x")), answering("A [2] B [9]."))
    retriever = FakeRetriever([make_hit("a", fusion=0.9), make_hit("b", fusion=0.8)])
    _, outcome = await run_react(llm, retriever)
    assert outcome.answer_text == "A [2] B ."
    assert [c.index for c in outcome.citations] == [2]
    assert outcome.citations[0].chunk_version_id == chunk_uuid("b")


async def test_answer_without_search_is_no_retrieval() -> None:
    llm = llm_with_guard()
    llm.script_tool_turns(answering("Xin chào, tôi tra cứu thông tin thuốc."))
    retriever = FakeRetriever()
    _, outcome = await run_react(llm, retriever)
    assert outcome.run.status is RunStatus.COMPLETED
    assert outcome.run.plan is not None
    assert outcome.run.plan.mode is AnswerMode.NO_RETRIEVAL
    assert stats(outcome).answered_without_search
    assert retriever.calls == []
    assert not any(a.kind is ActionKind.SEARCH for a in outcome.run.actions.entries)


async def test_search_with_no_hit_answers_in_abstain_mode() -> None:
    llm = llm_with_guard()
    llm.script_tool_turns(searching(call("c1", "thuốc lạ")), answering("Không có."))
    _, outcome = await run_react(llm, FakeRetriever([]))
    assert outcome.run.plan is not None
    assert outcome.run.plan.mode is AnswerMode.ABSTAIN
    assert outcome.run.status is RunStatus.ABSTAINED


async def test_blocked_guard_skips_the_agent() -> None:
    llm = llm_with_guard(attack=True)
    _, outcome = await run_react(llm, FakeRetriever())
    assert llm.tool_calls_seen == []
    assert outcome.run.status is RunStatus.BLOCKED


async def test_agent_llm_error_falls_back() -> None:
    llm = llm_with_guard()
    llm.script_tool_turns(LlmError("agent: down"))
    _, outcome = await run_react(llm, FakeRetriever())
    assert outcome.run.status is RunStatus.ERROR
    assert outcome.answer_text


async def test_search_actions_keep_the_pipeline_payload() -> None:
    llm = llm_with_guard()
    llm.script_tool_turns(searching(call("c1", "x")), answering("Đáp [1]."))
    _, outcome = await run_react(llm, FakeRetriever([make_hit("a", fusion=0.9)]))
    search = next(a for a in outcome.run.actions.entries if a.kind is ActionKind.SEARCH)
    for key in (
        "queries",
        "evidence",
        "evidence_chars",
        "retrieval_seconds",
        "rerank_scored",
    ):
        assert key in search.payload
    assert [a.kind for a in outcome.run.actions.entries][:2] == [
        ActionKind.GUARD,
        ActionKind.AGENT,
    ]
