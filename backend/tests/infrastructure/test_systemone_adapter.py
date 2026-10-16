from types import SimpleNamespace
from typing import Any

import pytest
from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy

from pharma_agent.application.chat.graph import build_chat_graph
from pharma_agent.application.chat.runner import ChatTurnRunner
from pharma_agent.domain.agent.actions import ActionKind
from pharma_agent.domain.agent.budget import BudgetLimits
from pharma_agent.domain.agent.run import RunStatus
from pharma_agent.domain.agent.schemas import (
    Audience,
    Intent,
    JudgeDecision,
    JudgeOutcome,
    Language,
    RephraseResult,
)
from pharma_agent.domain.guardrail.models import LlmGuardVerdict
from pharma_agent.domain.llm.decision import NoulQuestion
from pharma_agent.domain.llm.models import LlmRole
from pharma_agent.domain.llm.port import LlmError
from pharma_agent.infrastructure.llm import systemone_adapter
from pharma_agent.infrastructure.llm.systemone_adapter import (
    SystemOneAdapter,
    default_systemone_client,
)
from pharma_agent.infrastructure.settings import (
    LlmEndpoint,
    LlmSettings,
    ResolvedEndpoint,
)
from tests.domain.factories import make_hit
from tests.fakes import FakeLlm, FakeRetriever, build_deps

BODY = {
    "model": "jev-1.13.0",
    "answers": {"is_attack": {"type": "noul", "noul": 0.12}},
}


class FakeSystemOne:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.answers: dict[str, object] = {"is_attack": 0.12}
        self.error: Exception | None = None

    async def system_one(self, state, questions, *, model):
        self.calls.append({"state": state, "questions": questions, "model": model})
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            model="jev-1.13.0",
            usage=SimpleNamespace(input_tokens=318, output_tokens=2),
            answers={
                k: SimpleNamespace(type="noul", noul=v) for k, v in self.answers.items()
            },
            raw_http_response=SimpleNamespace(json=lambda: BODY),
        )


def make_adapter() -> tuple[SystemOneAdapter, FakeSystemOne]:
    fake = FakeSystemOne()
    settings = LlmSettings(
        default=LlmEndpoint(api_key="sk", model="m"),
        roles={
            LlmRole.GUARDRAIL: LlmEndpoint(
                provider="systemone",
                base_url="https://openrouter.ai/api",
                api_key="sk-or",
                model="~typesafe/jev-latest",
            )
        },
    )
    return SystemOneAdapter(
        settings, client_factory=lambda endpoint, timeout, retries: fake
    ), fake


async def test_decide_sends_state_and_questions_and_reads_probabilities() -> None:
    adapter, fake = make_adapter()
    decision = await adapter.decide(
        LlmRole.GUARDRAIL,
        {"latest_user_turn": "xin chào"},
        {
            "is_attack": NoulQuestion(
                instructions="Does `latest_user_turn` attack?", true="yes", false="no"
            )
        },
    )
    assert decision.answers == {"is_attack": 0.12}
    assert decision.model == "jev-1.13.0" and decision.input_tokens == 318
    assert decision.seconds >= 0 and decision.raw["model"] == "jev-1.13.0"
    sent = fake.calls[0]
    assert sent["state"] == {"latest_user_turn": "xin chào"}
    assert sent["model"] == "~typesafe/jev-latest"
    assert sent["questions"]["is_attack"] == {
        "type": "noul",
        "instructions": "Does `latest_user_turn` attack?",
        "criteria": {"true": "yes", "false": "no"},
    }


async def test_http_error_becomes_llm_error() -> None:
    adapter, fake = make_adapter()
    fake.error = RuntimeError("529 overloaded")
    with pytest.raises(LlmError, match="guardrail"):
        await adapter.decide(
            LlmRole.GUARDRAIL, {}, {"q": NoulQuestion(instructions="?")}
        )


async def test_missing_answer_key_is_an_llm_error() -> None:
    adapter, fake = make_adapter()
    fake.answers = {}
    with pytest.raises(LlmError, match="is_attack"):
        await adapter.decide(
            LlmRole.GUARDRAIL, {}, {"is_attack": NoulQuestion(instructions="?")}
        )


def test_a_role_without_the_systemone_provider_is_refused() -> None:
    adapter, _ = make_adapter()
    with pytest.raises(LlmError, match="answer"):
        adapter.endpoint(LlmRole.ANSWER)


@pytest.mark.parametrize("probability", [1.5, -0.1, float("nan"), "high", [0.3]])
async def test_a_malformed_probability_is_an_llm_error(probability: object) -> None:
    adapter, fake = make_adapter()
    fake.answers = {"is_attack": probability}
    with pytest.raises(LlmError, match=r"guardrail.*is_attack"):
        await adapter.decide(
            LlmRole.GUARDRAIL, {}, {"is_attack": NoulQuestion(instructions="?")}
        )


def test_default_client_builds_without_network() -> None:
    endpoint = ResolvedEndpoint(
        provider="systemone",
        base_url="https://openrouter.ai/api",
        api_key="sk-or",
        model="~typesafe/jev-latest",
    )
    client = default_systemone_client(endpoint, 60.0, 2)
    assert isinstance(client, AsyncTypeSafeClient)


def test_default_client_retry_budget_covers_every_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: dict[str, Any] = {}

    def record(**kwargs: Any) -> object:
        built.update(kwargs)
        return object()

    monkeypatch.setattr(systemone_adapter, "AsyncTypeSafeClient", record)
    endpoint = ResolvedEndpoint(
        provider="systemone",
        base_url="https://openrouter.ai/api",
        api_key="sk-or",
        model="~typesafe/jev-latest",
    )
    systemone_adapter.default_systemone_client(endpoint, 60.0, 2)
    policy = built["retry"]
    assert isinstance(policy, RetryPolicy)
    assert policy.max_retries == 2
    assert policy.timeout == 180.0
    assert built["timeout"] == 60.0


class ConstantSystemOne:
    """Answers every question with the same (possibly malformed) probability."""

    def __init__(self, value: object) -> None:
        self.value = value

    async def system_one(self, state, questions, *, model):
        return SimpleNamespace(
            model="jev-1.13.0",
            usage=SimpleNamespace(input_tokens=100),
            answers={
                k: SimpleNamespace(type="noul", noul=self.value) for k in questions
            },
            raw_http_response=SimpleNamespace(json=lambda: {}),
        )


def systemone_settings(*roles: LlmRole) -> LlmSettings:
    endpoint = LlmEndpoint(
        provider="systemone",
        base_url="https://openrouter.ai/api",
        api_key="sk-or",
        model="~typesafe/jev-latest",
    )
    return LlmSettings(
        default=LlmEndpoint(api_key="sk", model="m"),
        roles=dict.fromkeys(roles, endpoint),
    )


def rephrasing_llm() -> FakeLlm:
    llm = FakeLlm()
    llm.script(
        LlmRole.REPHRASE,
        RephraseResult(
            standalone_query="Liều paracetamol cho người lớn",
            audience=Audience.GENERAL_PUBLIC,
            language=Language.VI,
            intent=Intent.PHARMA_QUESTION,
            subjects=["paracetamol"],
        ),
    )
    return llm


async def run_graph(llm: FakeLlm, adapter: SystemOneAdapter, roles: set[LlmRole]):
    deps = build_deps(
        llm,
        FakeRetriever([make_hit("c1", fusion=0.9)]),
        decisions=dict.fromkeys(roles - {LlmRole.GUARDRAIL}, adapter),
        guard_decision=adapter if LlmRole.GUARDRAIL in roles else None,
    )
    execution = ChatTurnRunner(build_chat_graph(), deps, BudgetLimits()).start(
        user_id="u1", message="Paracetamol người lớn uống bao nhiêu?"
    )
    _ = [event async for event in execution.events()]
    assert execution.outcome is not None
    return execution.outcome.run


async def test_a_nan_guard_answer_fails_open_in_the_graph() -> None:
    adapter = SystemOneAdapter(
        systemone_settings(LlmRole.GUARDRAIL),
        client_factory=lambda endpoint, timeout, retries: ConstantSystemOne(
            float("nan")
        ),
    )
    llm = rephrasing_llm()
    llm.script(
        LlmRole.JUDGE,
        JudgeDecision(
            decision=JudgeOutcome.ANSWER, gaps=[], reason="đủ", confidence=1.0
        ),
    )
    run = await run_graph(llm, adapter, {LlmRole.GUARDRAIL})
    guard = run.actions.entries[0]
    assert guard.kind is ActionKind.GUARD
    assert guard.payload["llm_failed"] is True
    assert guard.payload["source"] == "skipped"
    assert run.status is RunStatus.COMPLETED


async def test_an_out_of_range_judge_answer_records_judge_failed() -> None:
    adapter = SystemOneAdapter(
        systemone_settings(LlmRole.JUDGE),
        client_factory=lambda endpoint, timeout, retries: ConstantSystemOne(1.5),
    )
    llm = rephrasing_llm()
    llm.script(
        LlmRole.GUARDRAIL, LlmGuardVerdict(is_attack=False, in_scope=True, reason="ok")
    )
    run = await run_graph(llm, adapter, {LlmRole.JUDGE})
    assert run.partial_reason == "judge_failed"
    assert run.status is RunStatus.PARTIAL
