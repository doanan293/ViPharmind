"""A decision model answers yes/no questions about a state with probabilities (spec v2 §2.1)."""

from collections.abc import Mapping
from typing import Protocol

from pydantic import BaseModel, ConfigDict, field_validator

from pharma_agent.domain.llm.models import LlmRole


class NoulQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    instructions: str
    true: str | dict[str, object] | None = None
    false: str | dict[str, object] | None = None


class Decision(BaseModel):
    model_config = ConfigDict(frozen=True)

    answers: dict[str, float]
    model: str
    input_tokens: int
    seconds: float
    raw: dict[str, object]

    @field_validator("answers")
    @classmethod
    def _unit_interval(cls, value: dict[str, float]) -> dict[str, float]:
        for key, probability in value.items():
            if not 0.0 <= probability <= 1.0:
                raise ValueError(f"{key}: probability {probability} is outside [0, 1]")
        return value


class DecisionPort(Protocol):
    async def decide(
        self,
        role: LlmRole,
        state: Mapping[str, object],
        questions: Mapping[str, NoulQuestion],
    ) -> Decision:
        """Raises LlmError on any failure."""
        ...
