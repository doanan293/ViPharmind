import pytest
from pydantic import ValidationError

from pharma_agent.domain.llm.decision import Decision


def test_decision_validates_probabilities() -> None:
    decision = Decision(
        answers={"is_attack": 0.2},
        model="jev-1.13.0",
        input_tokens=5,
        seconds=0.1,
        raw={},
    )
    assert decision.answers["is_attack"] == 0.2
    with pytest.raises(ValidationError):
        Decision(
            answers={"is_attack": 1.5},
            model="jev-1.13.0",
            input_tokens=5,
            seconds=0.1,
            raw={},
        )
