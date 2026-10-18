"""The ReAct agent's chat model (spec v2 §2.4): LangChain's ChatOpenAI on the agent role's
endpoint, so any OpenAI-compatible server serves it like the other roles."""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from pharma_agent.domain.llm.models import LlmRole
from pharma_agent.infrastructure.settings import LlmSettings


def agent_chat_model(settings: LlmSettings) -> BaseChatModel:
    """ChatOpenAI over Chat Completions with the request fields the LlmPort adapter sends."""
    endpoint = settings.resolve(LlmRole.AGENT)
    extra_body: dict[str, Any] = dict(endpoint.extra_body or {})
    max_completion_tokens: int | None = None
    if endpoint.max_output_tokens is not None:
        if endpoint.max_tokens_param == "max_completion_tokens":
            max_completion_tokens = endpoint.max_output_tokens
        else:
            # ChatOpenAI always sends max_completion_tokens; a server that wants another
            # field name gets it in the body as is.
            extra_body[endpoint.max_tokens_param] = endpoint.max_output_tokens
    return ChatOpenAI(
        model=endpoint.model,
        base_url=endpoint.base_url,
        api_key=SecretStr(endpoint.api_key),
        reasoning_effort=endpoint.reasoning_effort,
        extra_body=extra_body or None,
        max_completion_tokens=max_completion_tokens,
        timeout=settings.timeout_seconds,
        max_retries=settings.max_retries,
        stream_usage=True,
        use_responses_api=False,
    )
