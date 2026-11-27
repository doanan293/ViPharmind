from pydantic import BaseModel, ConfigDict

from pharma_agent.domain.llm.models import LlmUsage
from pharma_agent.domain.shared.errors import DomainError


class BudgetExhausted(DomainError):
    """A turn used more LLM calls or tokens than its limits allow."""

    code = "BUDGET_EXHAUSTED"


class BudgetLimits(BaseModel):
    """Per-turn limits on search rounds, LLM calls, tokens, evidence and time."""

    model_config = ConfigDict(frozen=True)

    max_search_rounds: int = 3
    max_llm_calls: int = 10
    max_tokens: int = 40_000
    max_evidence_chars: int = 60_000
    deadline_seconds: float = 90.0


class BudgetUsage(BaseModel):
    """What a turn has spent so far; immutable, each charge returns a new value."""

    model_config = ConfigDict(frozen=True)

    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    search_rounds: int = 0

    @property
    def total_tokens(self) -> int:
        """Prompt plus completion tokens."""
        return self.prompt_tokens + self.completion_tokens

    def charged(self, usage: LlmUsage) -> "BudgetUsage":
        """A copy with one more LLM call and the call's tokens added."""
        return self.model_copy(
            update={
                "llm_calls": self.llm_calls + 1,
                "prompt_tokens": self.prompt_tokens + usage.prompt_tokens,
                "completion_tokens": self.completion_tokens + usage.completion_tokens,
            }
        )

    def with_search(self) -> "BudgetUsage":
        """A copy with one more search round."""
        return self.model_copy(update={"search_rounds": self.search_rounds + 1})
