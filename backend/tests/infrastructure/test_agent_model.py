from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from pharma_agent.domain.llm.models import LlmRole
from pharma_agent.infrastructure.llm.agent_model import agent_chat_model
from pharma_agent.infrastructure.settings import LlmEndpoint, LlmSettings


def settings(**agent: object) -> LlmSettings:
    return LlmSettings(
        default=LlmEndpoint(
            api_key="sk-cloud", model="gemini-flash", base_url="http://cloud/v1"
        ),
        roles={LlmRole.AGENT: LlmEndpoint.model_validate(agent)},
        timeout_seconds=30.0,
        max_retries=1,
    )


def test_agent_model_uses_the_agent_role_endpoint() -> None:
    model = agent_chat_model(
        settings(
            model="Qwen/Qwen3.5-9B",
            base_url="http://qwen/v1",
            reasoning_effort="low",
            extra_body={"top_k": 20},
            max_output_tokens=2048,
        )
    )
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "Qwen/Qwen3.5-9B"
    assert model.openai_api_base == "http://qwen/v1"
    assert isinstance(model.openai_api_key, SecretStr)
    assert model.openai_api_key.get_secret_value() == "sk-cloud"
    assert model.reasoning_effort == "low"
    assert model.extra_body == {"top_k": 20}
    assert model.max_tokens == 2048
    assert (model.request_timeout, model.max_retries) == (30.0, 1)
    assert model.stream_usage is True
    assert model.use_responses_api is False


def test_max_tokens_param_goes_in_the_body() -> None:
    model = agent_chat_model(
        settings(max_output_tokens=512, max_tokens_param="max_tokens")
    )
    assert isinstance(model, ChatOpenAI)
    assert model.max_tokens is None
    assert model.extra_body == {"max_tokens": 512}


def test_agent_model_without_options_sends_none() -> None:
    model = agent_chat_model(settings())
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "gemini-flash"
    assert model.extra_body is None
    assert model.max_tokens is None
    assert model.reasoning_effort is None
