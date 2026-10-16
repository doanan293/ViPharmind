from pydantic import BaseModel, ConfigDict, Field

from pharma_agent.domain.agent.decisions import (
    GuardThresholds,
    guard_questions,
    guard_state,
    guard_verdict,
)
from pharma_agent.domain.conversation.models import ConversationContext
from pharma_agent.domain.guardrail.groups import regex_screen
from pharma_agent.domain.guardrail.models import LlmGuardVerdict, Verdict, VerdictSource
from pharma_agent.domain.guardrail.prompts import guardrail_messages
from pharma_agent.domain.llm.decision import Decision, DecisionPort
from pharma_agent.domain.llm.models import LlmRole, LlmUsage
from pharma_agent.domain.llm.port import LlmError, LlmPort

DEFAULT_THRESHOLDS = GuardThresholds()


class GuardrailOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    verdict: Verdict
    usage: LlmUsage = LlmUsage()
    llm_failed: bool = False
    asked_intents: list[str] = Field(default_factory=list)
    decision: Decision | None = None


class GuardrailService:
    """Regex first, then the decision model when the guard role has one, else a small LLM
    classifier. Any model failure fails open."""

    def __init__(
        self,
        llm: LlmPort,
        decision: DecisionPort | None = None,
        thresholds: GuardThresholds = DEFAULT_THRESHOLDS,
    ) -> None:
        self._llm = llm
        self._decision = decision
        self._thresholds = thresholds

    async def check(
        self, query: str, context: ConversationContext | None = None
    ) -> GuardrailOutcome:
        regex_verdict = regex_screen(query)
        if regex_verdict is not None:
            return GuardrailOutcome(verdict=regex_verdict)
        if self._decision is not None:
            return await self._decide(self._decision, query, context)
        try:
            result, usage = await self._llm.structured(
                LlmRole.GUARDRAIL, guardrail_messages(query), LlmGuardVerdict
            )
        except LlmError as exc:
            return GuardrailOutcome(
                verdict=Verdict(
                    passed=True,
                    in_scope=True,
                    source=VerdictSource.SKIPPED,
                    reason=f"guardrail llm failed: {exc}",
                ),
                llm_failed=True,
            )
        if result.is_attack:
            verdict = Verdict(
                passed=False,
                in_scope=False,
                source=VerdictSource.LLM,
                label="llm_attack",
                reason=result.reason,
            )
        else:
            verdict = Verdict(
                passed=True,
                in_scope=result.in_scope,
                source=VerdictSource.LLM,
                label="" if result.in_scope else "out_of_scope",
                reason=result.reason,
            )
        return GuardrailOutcome(verdict=verdict, usage=usage)

    async def _decide(
        self,
        port: DecisionPort,
        query: str,
        context: ConversationContext | None,
    ) -> GuardrailOutcome:
        try:
            decision = await port.decide(
                LlmRole.GUARDRAIL,
                guard_state(context or ConversationContext(), query),
                guard_questions(),
            )
        except LlmError as exc:
            return GuardrailOutcome(
                verdict=Verdict(
                    passed=True,
                    in_scope=True,
                    source=VerdictSource.SKIPPED,
                    reason=f"guardrail decision failed: {exc}",
                ),
                llm_failed=True,
            )
        verdict, asked = guard_verdict(decision.answers, self._thresholds)
        return GuardrailOutcome(
            verdict=verdict,
            usage=LlmUsage(prompt_tokens=decision.input_tokens),
            asked_intents=list(asked),
            decision=decision,
        )
