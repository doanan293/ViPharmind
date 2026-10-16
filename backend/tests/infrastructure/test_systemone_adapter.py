from types import SimpleNamespace

import pytest

from pharma_agent.domain.llm.decision import NoulQuestion
from pharma_agent.domain.llm.models import LlmRole
from pharma_agent.domain.llm.port import LlmError
from pharma_agent.infrastructure.llm.systemone_adapter import SystemOneAdapter
from pharma_agent.infrastructure.settings import LlmEndpoint, LlmSettings

BODY = {
    "model": "jev-1.13.0",
    "answers": {"is_attack": {"type": "noul", "noul": 0.12}},
}


class FakeSystemOne:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.answers = {"is_attack": 0.12}
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
