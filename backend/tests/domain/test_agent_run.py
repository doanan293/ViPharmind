import pytest

from pharma_agent.domain.agent.budget import BudgetExhausted
from pharma_agent.domain.agent.run import (
    AnswerMode,
    AnswerPlan,
    ErrorCode,
    EvidenceRequired,
    InvalidTransition,
    RunStatus,
    Step,
)
from pharma_agent.domain.agent.schemas import (
    Audience,
    Intent,
    JudgeOutcome,
    Language,
    RephraseResult,
)
from pharma_agent.domain.guardrail.models import Verdict, VerdictSource
from pharma_agent.domain.llm.decision import Decision
from pharma_agent.domain.llm.models import LlmUsage
from pharma_agent.domain.retrieval.models import Query, QueryOrigin
from pharma_agent.domain.retrieval.service import SearchResult
from tests.domain.factories import NOW, make_hit, make_run, search_result

PASS = Verdict(passed=True, in_scope=True, source=VerdictSource.LLM)
BLOCK = Verdict(
    passed=False, in_scope=False, source=VerdictSource.REGEX, label="jailbreak"
)
OFF_TOPIC = Verdict(
    passed=True, in_scope=False, source=VerdictSource.LLM, label="out_of_scope"
)
Q1 = [Query(text="paracetamol liều người lớn", origin=QueryOrigin.INITIAL)]


def rephrased(
    intent: Intent = Intent.PHARMA_QUESTION, subjects: list[str] | None = None
) -> RephraseResult:
    return RephraseResult(
        standalone_query="Liều paracetamol cho người lớn",
        audience=Audience.GENERAL_PUBLIC,
        language=Language.VI,
        intent=intent,
        subjects=subjects or [],
    )


def test_happy_path_search_judge_answer() -> None:
    run = make_run()
    run.record_guard(PASS, now=NOW)
    run.record_rephrase(rephrased(), now=NOW)
    assert run.standalone_query == "Liều paracetamol cho người lớn"
    assert run.allowed_steps() == {Step.SEARCH}

    run.record_search(Q1, search_result("c1", "c2"), now=NOW)
    assert run.allowed_steps() == {Step.JUDGE}
    assert run.usage.search_rounds == 1

    run.record_judge(JudgeOutcome.ANSWER, gaps=[], reason="đủ", confidence=0.5, now=NOW)
    assert run.allowed_steps() == {Step.ANSWER}

    plan = run.decide_answer()
    assert plan == AnswerPlan(mode=AnswerMode.GROUNDED, partial=False)
    run.submit_plan(plan, now=NOW)
    run.complete()
    assert run.status is RunStatus.COMPLETED
    assert run.allowed_steps() == frozenset()


def test_search_more_goes_through_refine_and_rejects_duplicate_queries() -> None:
    run = make_run()
    run.record_guard(PASS, now=NOW)
    run.record_rephrase(rephrased(), now=NOW)
    run.record_search(Q1, search_result("c1"), now=NOW)
    run.record_judge(
        JudgeOutcome.SEARCH_MORE,
        gaps=["liều tối đa"],
        reason="thiếu",
        confidence=0.5,
        now=NOW,
    )
    assert run.allowed_steps() == {Step.REFINE}

    fresh = run.record_refine(
        ["Paracetamol LIỀU người lớn", "paracetamol liều tối đa mỗi ngày", ""], now=NOW
    )
    assert [q.text for q in fresh] == ["paracetamol liều tối đa mỗi ngày"]
    assert fresh[0].origin is QueryOrigin.REFINED
    assert run.allowed_steps() == {Step.SEARCH}

    run.record_search(fresh, search_result("c1", "c3"), now=NOW)
    run.record_judge(
        JudgeOutcome.SEARCH_MORE, gaps=["trẻ em"], reason="", confidence=0.5, now=NOW
    )
    only_dupes = run.record_refine(["paracetamol liều tối đa mỗi ngày"], now=NOW)
    assert only_dupes == []
    assert run.allowed_steps() == {Step.ANSWER}
    assert run.decide_answer() == AnswerPlan(mode=AnswerMode.GROUNDED, partial=True)


def test_search_round_limit_forces_partial_answer() -> None:
    run = make_run(max_search_rounds=1)
    run.record_guard(PASS, now=NOW)
    run.record_rephrase(rephrased(), now=NOW)
    run.record_search(Q1, search_result("c1"), now=NOW)
    run.record_judge(
        JudgeOutcome.SEARCH_MORE, gaps=["x"], reason="", confidence=0.5, now=NOW
    )
    assert run.allowed_steps() == {Step.ANSWER}
    assert run.decide_answer().partial is True


def test_no_evidence_leads_to_abstain() -> None:
    run = make_run()
    run.record_guard(PASS, now=NOW)
    run.record_rephrase(rephrased(), now=NOW)
    run.record_search(Q1, search_result(error="qdrant down"), now=NOW)
    run.record_judge(JudgeOutcome.ANSWER, gaps=[], reason="", confidence=0.5, now=NOW)
    assert run.decide_answer() == AnswerPlan(mode=AnswerMode.ABSTAIN)
    with pytest.raises(EvidenceRequired):
        run.submit_plan(AnswerPlan(mode=AnswerMode.GROUNDED), now=NOW)
    run.submit_plan(run.decide_answer(), now=NOW)
    run.complete()
    assert run.status is RunStatus.ABSTAINED


def test_guard_and_intent_short_circuit_to_answer() -> None:
    blocked = make_run()
    blocked.record_guard(BLOCK, now=NOW)
    assert blocked.allowed_steps() == {Step.ANSWER}
    assert blocked.decide_answer().mode is AnswerMode.BLOCKED

    off = make_run()
    off.record_guard(OFF_TOPIC, now=NOW)
    assert off.decide_answer().mode is AnswerMode.REDIRECT

    hello = make_run("xin chào")
    hello.record_guard(PASS, now=NOW)
    hello.record_rephrase(rephrased(Intent.SMALLTALK), now=NOW)
    assert hello.allowed_steps() == {Step.ANSWER}
    assert hello.decide_answer().mode is AnswerMode.NO_RETRIEVAL


def test_budget_reservation_and_exhaustion() -> None:
    run = make_run(max_llm_calls=4)
    assert run.can_afford_rephrase() is True
    run.charge(LlmUsage(prompt_tokens=10, completion_tokens=1))
    run.charge(LlmUsage(prompt_tokens=10, completion_tokens=1))
    assert run.usage.llm_calls == 2
    assert run.can_afford_rephrase() is False  # 2 + 3 > 4
    run.charge(LlmUsage())
    run.charge(LlmUsage())
    with pytest.raises(BudgetExhausted):
        run.charge(LlmUsage())
    assert run.usage.llm_calls == 5

    tokens = make_run(max_tokens=100)
    with pytest.raises(BudgetExhausted):
        tokens.charge(LlmUsage(prompt_tokens=90, completion_tokens=20))


def test_judge_failure_marks_partial_and_terminal_transitions_are_guarded() -> None:
    run = make_run()
    run.record_guard(PASS, now=NOW)
    run.record_rephrase(None, failed=True, now=NOW)
    assert run.standalone_query == run.original_query
    run.record_search(Q1, search_result("c1"), now=NOW)
    run.record_judge(
        JudgeOutcome.ANSWER,
        gaps=[],
        reason="judge failed",
        failed=True,
        confidence=0.0,
        now=NOW,
    )
    assert run.decide_answer().partial is True

    run.fail(ErrorCode.ANSWER_FAILED, detail="boom")
    assert run.status is RunStatus.ERROR and run.error_code is ErrorCode.ANSWER_FAILED
    with pytest.raises(InvalidTransition):
        run.timeout()
    trace = run.to_trace()
    assert trace["status"] == "error" and trace["usage"]["search_rounds"] == 1
    assert [a["kind"] for a in trace["actions"]] == [
        "guard",
        "rephrase",
        "search",
        "judge",
    ]


def test_skipped_judge_answers_from_one_search_round() -> None:
    run = make_run()
    run.record_guard(PASS, now=NOW)
    run.record_rephrase(None, now=NOW, skipped=True)
    run.record_search(Q1, search_result("c1"), now=NOW)
    run.skip_judge(now=NOW)
    assert run.allowed_steps() == {Step.ANSWER}
    assert run.actions.entries[-1].outcome == "skipped"
    assert run.decide_answer() == AnswerPlan(mode=AnswerMode.GROUNDED, partial=False)


def test_skipped_judge_without_evidence_abstains() -> None:
    run = make_run()
    run.record_guard(PASS, now=NOW)
    run.record_search(Q1, search_result(), now=NOW)
    run.skip_judge(now=NOW)
    assert run.decide_answer() == AnswerPlan(mode=AnswerMode.ABSTAIN)


def test_each_search_logs_the_evidence_it_leaves_active() -> None:
    run = make_run()
    run.record_guard(PASS, now=NOW)
    run.record_rephrase(rephrased(), now=NOW)
    hits = [
        make_hit("c1", ordinal=2, section_keys=["drug:a:lieu-dung"]),
        make_hit(
            "c2", ordinal=1, section_keys=["drug:a:chi-dinh", "drug:a:thanh-phan"]
        ),
    ]
    run.record_search(Q1, SearchResult(items=hits), now=NOW)
    search = run.actions.entries[-1]
    assert search.payload["evidence"] == [
        {
            "document": "drug:paracetamol",
            "ordinal": 2,
            "sections": ["drug:a:lieu-dung"],
        },
        {
            "document": "drug:paracetamol",
            "ordinal": 1,
            "sections": ["drug:a:chi-dinh", "drug:a:thanh-phan"],
        },
    ]
    assert search.payload["evidence_chars"] == sum(len(h.chunk_text) for h in hits)


def test_search_action_records_retrieval_timing() -> None:
    run = make_run()
    result = SearchResult(items=[], retrieval_seconds=0.5, rerank_seconds=0.25)
    run.record_search([Query(text="q", origin=QueryOrigin.INITIAL)], result, now=NOW)
    payload = run.actions.entries[-1].payload
    assert payload["retrieval_seconds"] == 0.5
    assert payload["rerank_seconds"] == 0.25


def test_record_guard_carries_asked_intents_and_the_raw_decision() -> None:
    run = make_run()
    decision = Decision(
        answers={"asks_dosage": 0.9},
        model="jev-1.13.0",
        input_tokens=300,
        seconds=0.2,
        raw={"answers": {"asks_dosage": 0.9}},
    )
    run.record_guard(PASS, now=NOW, asked_intents=["dosage"], decision=decision)
    assert run.asked_intents == ["dosage"]
    payload = run.actions.entries[-1].payload
    assert payload["asked_intents"] == ["dosage"]
    assert payload["decision"] == {
        "answers": {"asks_dosage": 0.9},
        "model": "jev-1.13.0",
        "input_tokens": 300,
        "seconds": 0.2,
        "raw": {"answers": {"asks_dosage": 0.9}},
    }


def test_record_rephrase_keeps_subjects_and_falls_back_to_the_query() -> None:
    run = make_run()
    run.record_rephrase(rephrased(subjects=[" paracetamol ", ""]), now=NOW)
    assert run.subjects == ["paracetamol"]
    other = make_run()
    other.record_rephrase(rephrased(), now=NOW)
    assert other.subjects == [other.standalone_query]
