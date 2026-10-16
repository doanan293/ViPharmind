import pytest
from pydantic import ValidationError

from pharma_agent.domain.agent.schemas import JudgeDecision, JudgeOutcome


def judge(confidence: float) -> JudgeDecision:
    return JudgeDecision(
        decision=JudgeOutcome.ANSWER, gaps=[], reason="đủ", confidence=confidence
    )


@pytest.mark.parametrize("confidence", [1.5, -0.1, 85.0])
def test_judge_confidence_outside_the_unit_interval_is_rejected(
    confidence: float,
) -> None:
    with pytest.raises(ValidationError):
        judge(confidence)


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
def test_judge_confidence_inside_the_unit_interval_is_accepted(
    confidence: float,
) -> None:
    assert judge(confidence).confidence == confidence


def test_judge_confidence_bounds_stay_out_of_the_json_schema() -> None:
    schema = JudgeDecision.model_json_schema()["properties"]["confidence"]
    assert "minimum" not in schema and "maximum" not in schema
