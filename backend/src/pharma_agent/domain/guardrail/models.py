from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class VerdictSource(StrEnum):
    """Which check produced a verdict; SKIPPED means the model failed (fail open)."""

    REGEX = "regex"
    LLM = "llm"
    SKIPPED = "skipped"
    DECISION = "decision"


class Verdict(BaseModel):
    """Guard ruling: `passed` is False for an attack, `in_scope` for medicine topics."""

    model_config = ConfigDict(frozen=True)

    passed: bool
    in_scope: bool
    source: VerdictSource
    label: str = ""
    reason: str = ""

    @property
    def allows_processing(self) -> bool:
        """Whether the turn passed and is in scope."""
        return self.passed and self.in_scope


class LlmGuardVerdict(BaseModel):
    """LLM guard classifier output."""

    model_config = ConfigDict(extra="forbid")

    is_attack: bool
    in_scope: bool
    reason: str
