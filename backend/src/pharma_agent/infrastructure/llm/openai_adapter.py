"""LlmPort over the OpenAI SDK using Chat Completions, so any OpenAI-compatible server works."""

from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any, TypeVar

from openai import OpenAIError
from pydantic import BaseModel, ValidationError

from pharma_agent.domain.llm.models import (
    ChatMessage,
    ChatRole,
    LlmRole,
    LlmUsage,
    StreamDelta,
    ToolCall,
    ToolChoice,
    ToolSpec,
    ToolTurn,
)
from pharma_agent.domain.llm.port import LlmError
from pharma_agent.infrastructure.openai_client import build_async_openai
from pharma_agent.infrastructure.settings import LlmSettings, ResolvedEndpoint

T = TypeVar("T", bound=BaseModel)
ClientFactory = Callable[[ResolvedEndpoint, float, int], Any]


def default_client_factory(
    endpoint: ResolvedEndpoint, timeout: float, max_retries: int
) -> Any:
    return build_async_openai(
        api_key=endpoint.api_key,
        base_url=endpoint.base_url,
        timeout=timeout,
        max_retries=max_retries,
        traced=False,
    )


def langfuse_client_factory(
    endpoint: ResolvedEndpoint, timeout: float, max_retries: int
) -> Any:
    """Every call becomes a Langfuse generation with tokens and cost."""
    return build_async_openai(
        api_key=endpoint.api_key,
        base_url=endpoint.base_url,
        timeout=timeout,
        max_retries=max_retries,
        traced=True,
    )


class OpenAiLlmAdapter:
    def __init__(
        self,
        settings: LlmSettings,
        client_factory: ClientFactory = default_client_factory,
    ) -> None:
        self._settings = settings
        self._factory = client_factory
        self._endpoints: dict[LlmRole, ResolvedEndpoint] = {
            role: settings.resolve(role) for role in LlmRole
        }
        self._clients: dict[tuple[str | None, str], Any] = {}

    def _client(self, role: LlmRole) -> tuple[Any, ResolvedEndpoint]:
        endpoint = self._endpoints[role]
        key = (endpoint.base_url, endpoint.api_key)
        client = self._clients.get(key)
        if client is None:
            client = self._factory(
                endpoint, self._settings.timeout_seconds, self._settings.max_retries
            )
            self._clients[key] = client
        return client, endpoint

    async def structured(
        self, role: LlmRole, messages: Sequence[ChatMessage], schema: type[T]
    ) -> tuple[T, LlmUsage]:
        client, endpoint = self._client(role)
        try:
            completion = await client.chat.completions.parse(
                model=endpoint.model,
                messages=_to_openai(messages),
                response_format=schema,
                **_options(endpoint),
            )
        except OpenAIError as exc:
            raise LlmError(f"{role.value}: {exc}") from exc
        except ValidationError as exc:
            # A server that does not enforce strict json_schema can return JSON of
            # another shape; the step then degrades like any other LLM failure.
            raise LlmError(
                f"{role.value}: output does not match {schema.__name__}"
            ) from exc
        choice = completion.choices[0]
        parsed = choice.message.parsed
        if parsed is None:
            raise LlmError(
                f"{role.value}: model returned no parsed output (refusal={choice.message.refusal!r})"
            )
        return parsed, _usage(completion.usage)

    async def stream(
        self, role: LlmRole, messages: Sequence[ChatMessage]
    ) -> AsyncIterator[StreamDelta]:
        client, endpoint = self._client(role)
        try:
            stream = await client.chat.completions.create(
                model=endpoint.model,
                messages=_to_openai(messages),
                stream=True,
                stream_options={"include_usage": True},
                **_options(endpoint),
            )
            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta is not None and delta.content:
                        yield StreamDelta(text=delta.content)
                if getattr(chunk, "usage", None) is not None:
                    yield StreamDelta(usage=_usage(chunk.usage))
        except OpenAIError as exc:
            raise LlmError(f"{role.value}: {exc}") from exc

    async def tool_call(
        self,
        role: LlmRole,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec],
        *,
        tool_choice: ToolChoice = "auto",
    ) -> tuple[ToolTurn, LlmUsage]:
        """Native tool calling; with no tools the model can only answer."""
        client, endpoint = self._client(role)
        request: dict[str, Any] = {
            "model": endpoint.model,
            "messages": _to_openai(messages),
            **_options(endpoint),
        }
        if tools:
            request["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ]
            if tool_choice == "none":
                request["tool_choice"] = "none"
            else:
                request["parallel_tool_calls"] = True
        try:
            completion = await client.chat.completions.create(**request)
        except OpenAIError as exc:
            raise LlmError(f"{role.value}: {exc}") from exc
        choice = completion.choices[0]
        calls = tuple(
            ToolCall(
                id=str(call.id),
                name=str(call.function.name),
                arguments=str(call.function.arguments or ""),
            )
            for call in (choice.message.tool_calls or [])
        )
        turn = ToolTurn(
            text=choice.message.content or "",
            tool_calls=calls,
            finish_reason=str(choice.finish_reason or ""),
        )
        return turn, _usage(completion.usage)


def _options(endpoint: ResolvedEndpoint) -> dict[str, Any]:
    """Optional request fields, sent only when set so any OpenAI-compatible server accepts the call."""
    options: dict[str, Any] = {}
    if endpoint.reasoning_effort is not None:
        options["reasoning_effort"] = endpoint.reasoning_effort
    if endpoint.extra_body:
        options["extra_body"] = endpoint.extra_body
    if endpoint.max_output_tokens is not None:
        options[endpoint.max_tokens_param] = endpoint.max_output_tokens
    return options


def _to_openai(messages: Sequence[ChatMessage]) -> list[dict[str, Any]]:
    return [_message(m) for m in messages]


def _message(message: ChatMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": message.role.value, "content": message.content}
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in message.tool_calls
        ]
    if message.role is ChatRole.TOOL and message.tool_call_id is not None:
        payload["tool_call_id"] = message.tool_call_id
    return payload


def _usage(usage: Any) -> LlmUsage:
    if usage is None:
        return LlmUsage()
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    total = int(getattr(usage, "total_tokens", 0) or 0)
    details = getattr(usage, "completion_tokens_details", None)
    reasoning = int(getattr(details, "reasoning_tokens", 0) or 0)
    # OpenAI counts reasoning tokens inside completion_tokens; some OpenAI-compatible
    # proxies report them only in total_tokens. The larger value bills them either way.
    return LlmUsage(
        prompt_tokens=prompt,
        completion_tokens=max(completion, total - prompt),
        reasoning_tokens=reasoning,
    )
