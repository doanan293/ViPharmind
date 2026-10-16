import pytest

from pharma_agent.domain.agent.decisions import (
    INTENT_PHRASES,
    INTENTS,
    GuardThresholds,
    guard_questions,
    guard_verdict,
    intent_questions,
    judge_decision,
    judge_questions,
    judge_state,
    refine_intents,
    template_queries,
)
from pharma_agent.domain.agent.schemas import JudgeOutcome
from pharma_agent.domain.guardrail.models import VerdictSource
from pharma_agent.domain.retrieval.evidence import Evidence
from tests.domain.factories import make_hit


def test_guard_questions_cover_the_three_flags_and_every_intent() -> None:
    questions = guard_questions()
    assert {"is_attack", "is_about_medicines", "is_smalltalk_or_meta"} <= set(questions)
    assert {f"asks_{intent}" for intent in INTENTS} <= set(questions)
    assert all(
        q.instructions.isascii() for q in questions.values()
    )  # English questions, Vietnamese stays in state


def test_guard_verdict_blocks_above_the_block_threshold() -> None:
    verdict, asked = guard_verdict(
        {
            "is_attack": 0.71,
            "is_about_medicines": 0.9,
            "is_smalltalk_or_meta": 0.0,
            "asks_dosage": 0.8,
        },
        GuardThresholds(),
    )
    assert verdict.passed is False and verdict.label == "decision_attack"
    assert asked == ["dosage"]


def test_guard_verdict_redirects_only_turns_that_are_neither_medicine_nor_smalltalk() -> (
    None
):
    off_topic, _ = guard_verdict(
        {"is_attack": 0.05, "is_about_medicines": 0.1, "is_smalltalk_or_meta": 0.1},
        GuardThresholds(),
    )
    assert (
        off_topic.passed
        and not off_topic.in_scope
        and off_topic.label == "out_of_scope"
    )
    greeting, _ = guard_verdict(
        {"is_attack": 0.1, "is_about_medicines": 0.2, "is_smalltalk_or_meta": 0.9},
        GuardThresholds(),
    )
    assert greeting.allows_processing and greeting.source is VerdictSource.DECISION
    medicine, _ = guard_verdict(
        {"is_attack": 0.1, "is_about_medicines": 0.8, "is_smalltalk_or_meta": 0.1},
        GuardThresholds(),
    )
    assert medicine.allows_processing


def test_judge_state_carries_evidence_with_ids_and_full_text() -> None:
    hit = make_hit("c1", document_key="drug:paracetamol:lieu-dung")
    state = judge_state(
        "Liều?", "liều paracetamol", ["dosage"], [Evidence(ref="E1", hit=hit)]
    )
    assert state["evidence"] == [
        {"id": 1, "source": hit.context_header or hit.title, "text": hit.chunk_text}
    ]
    assert state["asked_intents"] == ["dosage"]


def test_judge_questions_follow_the_asked_intents() -> None:
    assert set(judge_questions(["dosage", "storage"])) == {
        "covers_dosage",
        "covers_storage",
        "sufficient_overall",
        "evidence_conflict",
        "wrong_drug",
    }
    with pytest.raises(ValueError, match="unknown intent"):
        judge_questions(["price"])


def test_judge_decision_answers_when_everything_clears_tau() -> None:
    decision = judge_decision(
        {"sufficient_overall": 0.8, "covers_dosage": 0.9, "covers_storage": 0.3},
        ["dosage", "storage"],
        tau=0.5,
    )
    assert decision.decision is JudgeOutcome.SEARCH_MORE and decision.gaps == [
        "storage"
    ]
    assert decision.confidence == 0.8
    decision = judge_decision(
        {"sufficient_overall": 0.8, "covers_dosage": 0.9, "covers_storage": 0.6},
        ["dosage", "storage"],
        tau=0.5,
    )
    assert decision.decision is JudgeOutcome.ANSWER and decision.gaps == []


def test_threshold_boundary_is_inclusive() -> None:
    decision = judge_decision(
        {"sufficient_overall": 0.5, "covers_dosage": 0.5}, ["dosage"], tau=0.5
    )
    assert decision.decision is JudgeOutcome.ANSWER


def test_intent_phrases_exist_for_every_intent() -> None:
    assert set(INTENT_PHRASES) == set(INTENTS)
    assert INTENT_PHRASES["dosage"] == "liều dùng và cách dùng"


def test_template_queries_combine_subject_and_phrase() -> None:
    assert template_queries(["paracetamol"], ["storage", "dosage"]) == [
        "paracetamol bảo quản",
        "paracetamol liều dùng và cách dùng",
    ]


def test_template_refine_uses_free_text_gaps_verbatim() -> None:
    assert template_queries(["paracetamol"], ["liều paracetamol cho trẻ 2 tuổi"]) == [
        "liều paracetamol cho trẻ 2 tuổi"
    ]


def test_template_queries_cover_every_subject() -> None:
    assert template_queries(["paracetamol", "ibuprofen"], ["dosage"]) == [
        "paracetamol liều dùng và cách dùng",
        "ibuprofen liều dùng và cách dùng",
    ]


def test_template_queries_are_subject_major_and_capped_at_three() -> None:
    assert template_queries(["paracetamol", "ibuprofen"], ["dosage", "storage"]) == [
        "paracetamol liều dùng và cách dùng",
        "paracetamol bảo quản",
        "ibuprofen liều dùng và cách dùng",
    ]


def test_template_free_text_gap_appears_once_with_two_subjects() -> None:
    assert template_queries(["paracetamol", "ibuprofen"], ["tương tác hai thuốc"]) == [
        "tương tác hai thuốc"
    ]


def test_intent_questions_are_the_asks_nouls_only() -> None:
    questions = intent_questions()
    assert set(questions) == {f"asks_{intent}" for intent in INTENTS}
    assert questions["asks_dosage"] == guard_questions()["asks_dosage"]


def test_refine_intents_put_the_least_covered_first_and_default_to_general_info() -> (
    None
):
    asked = ["dosage", "storage", "adr"]
    answers = {"covers_dosage": 0.8, "covers_storage": 0.3, "covers_adr": 0.6}
    assert refine_intents(asked, answers) == ["storage", "adr", "dosage"]
    assert refine_intents(asked, None) == asked
    assert refine_intents([], answers) == ["general_info"]
