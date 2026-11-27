"""A decision model answers yes/no questions about a state with probabilities (spec v2 §2.1)."""

from collections.abc import Mapping
from typing import Protocol

from pydantic import BaseModel, ConfigDict, field_validator

from pharma_agent.domain.llm.models import LlmRole


class NoulQuestion(BaseModel):
    """One yes/no question, optionally with what counts as true and as false."""

    model_config = ConfigDict(frozen=True)

    instructions: str
    true: str | dict[str, object] | None = None
    false: str | dict[str, object] | None = None


class Decision(BaseModel):
    """The decision model's probability of yes per question key, with call metadata."""

    model_config = ConfigDict(frozen=True)

    answers: dict[str, float]
    model: str
    input_tokens: int
    seconds: float
    raw: dict[str, object]
    request_id: str | None = None

    @field_validator("answers")
    @classmethod
    def _unit_interval(cls, value: dict[str, float]) -> dict[str, float]:
        for key, probability in value.items():
            if not 0.0 <= probability <= 1.0:
                raise ValueError(f"{key}: probability {probability} is outside [0, 1]")
        return value


class DecisionPort(Protocol):
    """Asks a decision model the questions about a state."""

    async def decide(
        self,
        role: LlmRole,
        state: Mapping[str, object],
        questions: Mapping[str, NoulQuestion],
    ) -> Decision:
        """Raises LlmError on any failure."""
        ...
