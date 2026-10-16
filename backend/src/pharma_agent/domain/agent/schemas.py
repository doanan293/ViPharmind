"""Structured-output schemas returned by the LLM. No defaults: OpenAI strict mode requires every field."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator


class Audience(StrEnum):
    GENERAL_PUBLIC = "general_public"
    PROFESSIONAL = "professional"
    UNKNOWN = "unknown"


class Language(StrEnum):
    VI = "vi"
    EN = "en"
    OTHER = "other"


class Intent(StrEnum):
    PHARMA_QUESTION = "pharma_question"
    SMALLTALK = "smalltalk"
    META = "meta"


class JudgeOutcome(StrEnum):
    ANSWER = "answer"
    SEARCH_MORE = "search_more"


class RephraseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    standalone_query: str
    audience: Audience
    language: Language
    intent: Intent


class JudgeDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: JudgeOutcome
    gaps: list[str]
    reason: str
    confidence: float

    @field_validator("confidence")
    @classmethod
    def _unit_interval(cls, value: float) -> float:
        # A validator, not Field(ge/le): the bounds would reach the JSON schema,
        # which strict-mode proxies may reject.
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"confidence {value} is outside [0, 1]")
        return value


class RefineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries: list[str]

    @field_validator("queries")
    @classmethod
    def _clean(cls, value: list[str]) -> list[str]:
        cleaned = [q.strip() for q in value if q and q.strip()]
        return cleaned[:3]
