from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from pharma_agent.application.chat.react_graph import build_react_graph
from pharma_agent.application.chat.runner import ChatTurnRunner, TurnOutcome
from pharma_agent.application.progress import EventType, ProgressEvent
from pharma_agent.domain.agent.actions import ActionKind
from pharma_agent.domain.agent.budget import BudgetLimits
from pharma_agent.domain.agent.react import (
    BUDGET_NOTE,
    DUPLICATE_NOTE,
    MAX_TOOL_ROUNDS,
    REACT_SYSTEM,
    ROUND_CAP_NOTE,
)
from pharma_agent.domain.agent.run import (
    AnswerMode,
    ErrorCode,
    ReactStats,
    RunStatus,
)
from pharma_agent.domain.guardrail.models import LlmGuardVerdict
from pharma_agent.domain.llm.models import LlmRole
from pharma_agent.domain.retrieval.models import QueryOrigin
from tests.domain.factories import chunk_uuid, make_hit
from tests.fakes import (
    AGENT_USAGE,
    FakeChatModel,
    FakeLlm,
    FakeRetriever,
    RetrievalError,
    answering,
    build_deps,
    searching,
)

QUESTION = "Paracetamol người lớn uống tối đa bao nhiêu?"


def llm_with_guard(attack: bool = False) -> FakeLlm:
    llm = FakeLlm()
    llm.script(
        LlmRole.GUARDRAIL,
        LlmGuardVerdict(is_attack=attack, in_scope=True, reason="ok"),
    )
    return llm


def agent(*responses: AIMessage | Exception) -> FakeChatModel:
    model = FakeChatModel()
    model.script(*responses)
    return model


async def run_react(
    model: FakeChatModel | None,
    retriever: FakeRetriever,
    limits: BudgetLimits | None = None,
    llm: FakeLlm | None = None,
) -> tuple[list[ProgressEvent], TurnOutcome]:
    deps = build_deps(
        llm if llm is not None else llm_with_guard(), retriever, agent_model=model
    )
    runner = ChatTurnRunner(build_react_graph(), deps, limits or BudgetLimits())
    execution = runner.start(user_id="u1", message=QUESTION)
    events = [event async for event in execution.events()]
    assert execution.outcome is not None
    return events, execution.outcome


def stats(outcome: TurnOutcome) -> ReactStats:
    assert outcome.run.react is not None
    return outcome.run.react


def tool_messages(model: FakeChatModel, call_index: int) -> list[ToolMessage]:
    return [m for m in model.seen[call_index] if isinstance(m, ToolMessage)]


def malformed(cid: str, args: object) -> AIMessage:
    message = searching((cid, "x"))
    return message.model_copy(
        update={"tool_calls": [{**message.tool_calls[0], "args": args}]}
    )


async def test_one_search_then_answer_with_citation() -> None:
    model = agent(
        searching(("c1", "paracetamol liều người lớn")),
        answering("Tối đa 4 g mỗi ngày [1]."),
    )
    _, outcome = await run_react(model, FakeRetriever([make_hit("c1", fusion=0.9)]))
    assert outcome.run.status is RunStatus.COMPLETED
    assert outcome.answer_text == "Tối đa 4 g mỗi ngày [1]."
    assert [c.index for c in outcome.citations] == [1]
    assert stats(outcome).rounds == 1
    assert stats(outcome).tool_calls == 1
    tools = tool_messages(model, 1)
    assert tools[0].tool_call_id == "c1"
    assert str(tools[0].content).startswith("[1] ")
    assert model.bound_tools[0] == ["search_corpus"]
    assert model.tool_choices == [None, None]
    first = model.seen[0]
    assert first[0].content == REACT_SYSTEM
    assert isinstance(first[-1], HumanMessage)
    assert first[-1].content == QUESTION
    assert "[1]" in outcome.context_text


async def test_parallel_calls_count_one_round_and_number_in_call_order() -> None:
    model = agent(
        searching(("c1", "paracetamol liều"), ("c2", "paracetamol chống chỉ định")),
        answering("Liều [1], chống chỉ định [2]."),
    )
    retriever = FakeRetriever([make_hit("a", fusion=0.9)], [make_hit("b", fusion=0.8)])
    _, outcome = await run_react(model, retriever)
    assert stats(outcome).rounds == 1
    assert stats(outcome).tool_calls == 2
    first, second = tool_messages(model, 1)
    assert (first.tool_call_id, second.tool_call_id) == ("c1", "c2")
    assert str(first.content).startswith("[1] ")
    assert str(second.content).startswith("[2] ")
    assert [c.index for c in outcome.citations] == [1, 2]


async def test_parallel_calls_log_one_search_round() -> None:
    model = agent(
        searching(("c1", "liều"), ("c2", "chống chỉ định")),
        answering("Đáp [1] [2]."),
    )
    retriever = FakeRetriever([make_hit("a", fusion=0.9)], [make_hit("b", fusion=0.8)])
    _, outcome = await run_react(model, retriever)
    searches = [a for a in outcome.run.actions.entries if a.kind is ActionKind.SEARCH]
    assert len(searches) == 1
    assert searches[0].payload["queries"] == ["liều", "chống chỉ định"]
    assert len(searches[0].payload["evidence"]) == 2
    assert searches[0].payload["rerank_scored"] == 2
    assert outcome.run.usage.search_rounds == 1


async def test_first_search_is_initial_and_later_ones_refined() -> None:
    model = agent(
        searching(("c1", "liều"), ("c2", "chống chỉ định")),
        searching(("c3", "tương tác")),
        answering("Đáp [1]."),
    )
    retriever = FakeRetriever(
        [make_hit("a", fusion=0.9)], [make_hit("b", fusion=0.8)], []
    )
    await run_react(model, retriever)
    origins = [query.origin for queries in retriever.calls for query in queries]
    assert origins == [QueryOrigin.INITIAL, QueryOrigin.REFINED, QueryOrigin.REFINED]


async def test_duplicate_query_reuses_the_first_result() -> None:
    model = agent(
        searching(("c1", "paracetamol liều")),
        searching(("c2", "Paracetamol   LIỀU")),
        answering("Đáp [1]."),
    )
    retriever = FakeRetriever([make_hit("a", fusion=0.9)])
    _, outcome = await run_react(model, retriever)
    assert len(retriever.calls) == 1
    assert stats(outcome).duplicate_calls == 1
    assert str(tool_messages(model, 2)[-1].content).endswith(DUPLICATE_NOTE)


async def test_identical_queries_in_one_round_search_once() -> None:
    model = agent(
        searching(("c1", "liều"), ("c2", "Liều")),
        answering("Đáp [1]."),
    )
    retriever = FakeRetriever([make_hit("a", fusion=0.9)])
    _, outcome = await run_react(model, retriever)
    assert len(retriever.calls) == 1
    first, second = tool_messages(model, 1)
    assert str(first.content).startswith("[1] ")
    assert str(second.content).endswith(DUPLICATE_NOTE)
    assert stats(outcome).duplicate_calls == 1


async def test_malformed_tool_call_becomes_a_tool_error() -> None:
    model = agent(malformed("c1", {"query": "  "}), answering("Tài liệu không đề cập."))
    retriever = FakeRetriever()
    _, outcome = await run_react(model, retriever)
    (error,) = tool_messages(model, 1)
    assert str(error.content).startswith("Error:")
    assert error.status == "error"
    assert retriever.calls == []
    assert stats(outcome).malformed_calls == 1
    assert stats(outcome).rounds == 1
    assert outcome.run.status is RunStatus.COMPLETED
    agent_action = next(
        a for a in outcome.run.actions.entries if a.kind is ActionKind.AGENT
    )
    assert agent_action.payload["malformed"] == [True]


async def test_arguments_that_are_not_json_become_a_tool_error() -> None:
    bad = AIMessage(
        content="",
        invalid_tool_calls=[
            {
                "name": "search_corpus",
                "args": "not json",
                "id": "c1",
                "error": "Expecting value",
                "type": "invalid_tool_call",
            }
        ],
        usage_metadata=AGENT_USAGE,
    )
    model = agent(bad, answering("Không rõ."))
    _, outcome = await run_react(model, FakeRetriever())
    (error,) = tool_messages(model, 1)
    assert "not valid JSON" in str(error.content)
    assert stats(outcome).malformed_calls == 1
    agent_action = next(
        a for a in outcome.run.actions.entries if a.kind is ActionKind.AGENT
    )
    assert agent_action.payload["arguments"] == ["not json"]


async def test_unknown_tool_becomes_a_tool_error() -> None:
    message = searching(("c1", "x"))
    unknown = message.model_copy(
        update={"tool_calls": [{**message.tool_calls[0], "name": "read_section"}]}
    )
    model = agent(unknown, answering("Không rõ."))
    _, outcome = await run_react(model, FakeRetriever())
    assert "unknown tool read_section" in str(tool_messages(model, 1)[0].content)
    assert stats(outcome).malformed_calls == 1


async def test_a_turn_with_only_malformed_calls_tried_to_search() -> None:
    model = agent(malformed("c1", {}), answering("Không rõ."))
    _, outcome = await run_react(model, FakeRetriever())
    assert not stats(outcome).answered_without_search


async def test_round_cap_forces_one_final_call_without_tools() -> None:
    model = agent(
        *(searching((f"c{n}", f"truy vấn {n}")) for n in range(MAX_TOOL_ROUNDS)),
        answering("Đáp [1]."),
    )
    retriever = FakeRetriever(
        *([make_hit(f"h{n}", fusion=0.9)] for n in range(MAX_TOOL_ROUNDS))
    )
    _, outcome = await run_react(model, retriever)
    assert len(model.seen) == MAX_TOOL_ROUNDS + 1
    # The history holds tool calls, so the tool stays declared; the model may not call.
    assert model.bound_tools[-1] == ["search_corpus"]
    assert model.tool_choices[-1] == "none"
    assert model.tool_choices[:-1] == [None] * MAX_TOOL_ROUNDS
    last: BaseMessage = model.seen[-1][-1]
    assert isinstance(last, HumanMessage)
    assert last.content == ROUND_CAP_NOTE
    assert stats(outcome).round_cap_hit
    assert not stats(outcome).budget_forced
    assert outcome.run.status is RunStatus.PARTIAL


async def test_tool_calls_on_the_final_call_are_dropped() -> None:
    model = agent(
        *(searching((f"c{n}", f"truy vấn {n}")) for n in range(MAX_TOOL_ROUNDS)),
        searching(("late", "thêm nữa")).model_copy(update={"content": "Đáp [1]."}),
    )
    retriever = FakeRetriever(
        *([make_hit(f"h{n}", fusion=0.9)] for n in range(MAX_TOOL_ROUNDS))
    )
    _, outcome = await run_react(model, retriever)
    assert len(retriever.calls) == MAX_TOOL_ROUNDS
    assert outcome.answer_text == "Đáp [1]."
    assert outcome.run.status is RunStatus.PARTIAL


async def test_llm_call_budget_forces_the_final_call_without_the_round_cap() -> None:
    model = agent(searching(("c1", "a")), searching(("c2", "b")), answering("Đáp [1]."))
    retriever = FakeRetriever([make_hit("a", fusion=0.9)], [make_hit("b", fusion=0.8)])
    _, outcome = await run_react(model, retriever, BudgetLimits(max_llm_calls=4))
    assert model.tool_choices == [None, None, "none"]
    assert stats(outcome).budget_forced
    assert not stats(outcome).round_cap_hit
    assert outcome.run.status is RunStatus.PARTIAL


async def test_exhausted_token_budget_answers_without_the_asked_searches() -> None:
    model = agent(searching(("c1", "a")), answering("Không đủ tài liệu."))
    retriever = FakeRetriever([make_hit("a", fusion=0.9)])
    limits = BudgetLimits(max_tokens=200)
    _, outcome = await run_react(model, retriever, limits)
    assert retriever.calls == []
    assert model.tool_choices == [None, "none"]
    assert stats(outcome).budget_forced
    assert stats(outcome).rounds == 0
    assert outcome.answer_text == "Không đủ tài liệu."


async def test_evidence_budget_cuts_results_and_marks_partial() -> None:
    model = agent(searching(("c1", "x")), answering("Đáp [1]."))
    retriever = FakeRetriever(
        [
            make_hit("a", text="x" * 50, fusion=0.9),
            make_hit("b", text="y" * 50, fusion=0.8),
        ]
    )
    _, outcome = await run_react(model, retriever, BudgetLimits(max_evidence_chars=60))
    assert str(tool_messages(model, 1)[0].content).endswith(BUDGET_NOTE)
    assert stats(outcome).budget_hits == 1
    assert outcome.run.status is RunStatus.PARTIAL


async def test_answer_citations_map_to_shown_chunks() -> None:
    model = agent(searching(("c1", "x")), answering("A [2] B [9]."))
    retriever = FakeRetriever([make_hit("a", fusion=0.9), make_hit("b", fusion=0.8)])
    _, outcome = await run_react(model, retriever)
    assert outcome.answer_text == "A [2] B ."
    assert [c.index for c in outcome.citations] == [2]
    assert outcome.citations[0].chunk_version_id == chunk_uuid("b")


async def test_answer_without_search_is_no_retrieval() -> None:
    model = agent(answering("Xin chào, tôi tra cứu thông tin thuốc."))
    retriever = FakeRetriever()
    _, outcome = await run_react(model, retriever)
    assert outcome.run.status is RunStatus.COMPLETED
    assert outcome.run.plan is not None
    assert outcome.run.plan.mode is AnswerMode.NO_RETRIEVAL
    assert stats(outcome).answered_without_search
    assert retriever.calls == []
    assert not any(a.kind is ActionKind.SEARCH for a in outcome.run.actions.entries)


async def test_search_with_no_hit_answers_in_abstain_mode() -> None:
    model = agent(searching(("c1", "thuốc lạ")), answering("Không có."))
    _, outcome = await run_react(model, FakeRetriever([]))
    assert outcome.run.plan is not None
    assert outcome.run.plan.mode is AnswerMode.ABSTAIN
    assert outcome.run.status is RunStatus.ABSTAINED


async def test_blocked_guard_skips_the_agent() -> None:
    model = agent()
    _, outcome = await run_react(
        model, FakeRetriever(), llm=llm_with_guard(attack=True)
    )
    assert model.seen == []
    assert outcome.run.status is RunStatus.BLOCKED


async def test_agent_model_error_falls_back() -> None:
    _, outcome = await run_react(agent(RuntimeError("agent: down")), FakeRetriever())
    assert outcome.run.status is RunStatus.ERROR
    assert outcome.run.error_code is ErrorCode.ANSWER_FAILED
    assert "agent: down" in outcome.run.error_detail
    assert outcome.answer_text


async def test_missing_agent_model_falls_back() -> None:
    _, outcome = await run_react(None, FakeRetriever())
    assert outcome.run.status is RunStatus.ERROR
    assert outcome.run.error_code is ErrorCode.ANSWER_FAILED
    assert outcome.answer_text


async def test_empty_final_answer_fails_the_turn() -> None:
    model = agent(searching(("c1", "x")), answering("  ", finish_reason="length"))
    _, outcome = await run_react(model, FakeRetriever([make_hit("a", fusion=0.9)]))
    assert outcome.run.status is RunStatus.ERROR
    assert outcome.run.error_code is ErrorCode.ANSWER_FAILED
    assert "finish_reason=length" in outcome.run.error_detail
    agent_actions = [
        a for a in outcome.run.actions.entries if a.kind is ActionKind.AGENT
    ]
    assert agent_actions[-1].payload["finish_reason"] == "length"


async def test_search_actions_keep_the_pipeline_payload() -> None:
    model = agent(searching(("c1", "x")), answering("Đáp [1]."))
    _, outcome = await run_react(model, FakeRetriever([make_hit("a", fusion=0.9)]))
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


async def test_search_evidence_accumulates_across_rounds() -> None:
    model = agent(
        searching(("c1", "liều")),
        searching(("c2", "chống chỉ định")),
        answering("Đáp [1] [2]."),
    )
    retriever = FakeRetriever([make_hit("a", fusion=0.9)], [make_hit("b", fusion=0.8)])
    _, outcome = await run_react(model, retriever)
    searches = [a for a in outcome.run.actions.entries if a.kind is ActionKind.SEARCH]
    assert [len(a.payload["evidence"]) for a in searches] == [1, 2]
    assert [a.payload["new_evidence"] for a in searches] == [1, 1]


async def test_failed_search_repeated_in_one_round_searches_once() -> None:
    model = agent(searching(("c1", "liều"), ("c2", "Liều")), answering("Không rõ."))
    retriever = FakeRetriever(RetrievalError("qdrant down"))
    _, outcome = await run_react(model, retriever)
    assert len(retriever.calls) == 1
    assert stats(outcome).duplicate_calls == 1
    assert all(str(m.content).startswith("Error:") for m in tool_messages(model, 1))
    (search,) = [a for a in outcome.run.actions.entries if a.kind is ActionKind.SEARCH]
    assert search.outcome == "error"


async def test_failed_search_is_searched_again_in_a_later_round() -> None:
    model = agent(
        searching(("c1", "liều")), searching(("c2", "liều")), answering("Đáp [1].")
    )
    retriever = FakeRetriever(RetrievalError("qdrant down"), [make_hit("a")])
    _, outcome = await run_react(model, retriever)
    assert len(retriever.calls) == 2
    assert str(tool_messages(model, 2)[-1].content).startswith("[1] ")
    assert stats(outcome).duplicate_calls == 0


async def test_model_usage_is_charged_and_recorded() -> None:
    model = agent(searching(("c1", "x")), answering("Đáp [1]."))
    _, outcome = await run_react(model, FakeRetriever([make_hit("a", fusion=0.9)]))
    react = stats(outcome)
    assert react.model_calls == 2
    assert (react.prompt_tokens, react.completion_tokens) == (400, 40)
    assert react.model_seconds >= 0.0
    # The guard's structured call plus the agent's two calls.
    assert outcome.run.usage.llm_calls == 3


async def test_progress_events_reach_the_turn_stream() -> None:
    model = agent(searching(("c1", "x")), answering("Đáp [1]."))
    events, _ = await run_react(model, FakeRetriever([make_hit("a", fusion=0.9)]))
    phases = [e.data["phase"] for e in events if e.type is EventType.PHASE]
    assert phases[-4:] == ["understanding", "searching", "reading", "answering"]


async def test_empty_or_repeated_call_ids_are_renumbered() -> None:
    model = agent(
        searching(("", "liều"), ("dup", "chống chỉ định"), ("dup", "tương tác")),
        answering("Đáp."),
    )
    retriever = FakeRetriever([], [], [])
    await run_react(model, retriever)
    ids = [m.tool_call_id for m in tool_messages(model, 1)]
    assert ids == ["call_0", "dup", "call_2"]
