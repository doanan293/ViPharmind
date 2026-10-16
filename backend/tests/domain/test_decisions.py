import pytest

from pharma_agent.domain.agent.decisions import (
    INTENT_PHRASES,
    INTENTS,
    GuardThresholds,
    guard_questions,
    guard_verdict,
    judge_decision,
    judge_questions,
    judge_state,
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
