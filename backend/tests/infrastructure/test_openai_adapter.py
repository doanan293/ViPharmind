from types import SimpleNamespace

import pytest
from openai import OpenAIError
from pydantic import BaseModel, ConfigDict

from pharma_agent.domain.llm.models import (
    ChatMessage,
    ChatRole,
    LlmRole,
    LlmUsage,
    ToolCall,
    ToolSpec,
    system,
    user,
)
from pharma_agent.domain.llm.port import LlmError
from pharma_agent.infrastructure.llm.openai_adapter import OpenAiLlmAdapter
from pharma_agent.infrastructure.settings import LlmEndpoint, LlmSettings


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool


class FakeCompletions:
    def __init__(self) -> None:
        self.parse_kwargs: dict = {}
        self.create_kwargs: dict = {}
        self.parsed: object = Verdict(ok=True)
        self.raise_on_parse: Exception | None = None
        self.usage_details: object | None = None
        self.tool_response: object | None = None

    async def parse(self, **kwargs):
        self.parse_kwargs = kwargs
        if self.raise_on_parse:
            raise self.raise_on_parse
        message = SimpleNamespace(parsed=self.parsed, refusal=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=SimpleNamespace(
                prompt_tokens=12,
                completion_tokens=3,
                completion_tokens_details=self.usage_details,
            ),
        )

    async def create(self, **kwargs):
        self.create_kwargs = kwargs
        if not kwargs.get("stream"):
            return self.tool_response

        async def chunks():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="Xin "))],
                usage=None,
            )
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="chào"))],
                usage=None,
            )
            yield SimpleNamespace(
                choices=[], usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2)
            )

        return chunks()


class FakeClient:
    def __init__(self) -> None:
        self.completions = FakeCompletions()
        self.chat = SimpleNamespace(completions=self.completions)


def make_adapter() -> tuple[OpenAiLlmAdapter, dict[tuple, FakeClient]]:
    created: dict[tuple, FakeClient] = {}

    def factory(endpoint, timeout, max_retries):
        client = FakeClient()
        created[(endpoint.base_url, endpoint.api_key)] = client
        return client

    settings = LlmSettings(
        default=LlmEndpoint(api_key="sk-cloud", model="qwen-small"),
        roles={
            LlmRole.GUARDRAIL: LlmEndpoint(reasoning_effort="minimal"),
            LlmRole.ANSWER: LlmEndpoint(
                base_url="http://local/v1", api_key="local", model="qwen"
            ),
        },
    )
    return OpenAiLlmAdapter(settings, client_factory=factory), created


async def test_structured_uses_parse_with_role_model_and_schema() -> None:
    adapter, created = make_adapter()
    result, usage = await adapter.structured(
        LlmRole.GUARDRAIL, [system("s"), user("u")], Verdict
    )
    assert result == Verdict(ok=True)
    assert usage == LlmUsage(prompt_tokens=12, completion_tokens=3)
    client = created[(None, "sk-cloud")]
    kwargs = client.completions.parse_kwargs
    assert kwargs["model"] == "qwen-small"
    assert kwargs["response_format"] is Verdict
    assert kwargs["reasoning_effort"] == "minimal"
    assert kwargs["messages"] == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
    ]


async def test_stream_yields_text_then_usage_and_uses_role_endpoint() -> None:
    adapter, created = make_adapter()
    deltas = [d async for d in adapter.stream(LlmRole.ANSWER, [user("hi")])]
    assert [d.text for d in deltas if d.text] == ["Xin ", "chào"]
    assert deltas[-1].usage == LlmUsage(prompt_tokens=5, completion_tokens=2)
    client = created[("http://local/v1", "local")]
    assert client.completions.create_kwargs["model"] == "qwen"
    assert client.completions.create_kwargs["stream"] is True
    assert client.completions.create_kwargs["stream_options"] == {"include_usage": True}
    # A role gets no reasoning_effort unless configured, so any server accepts the call.
    assert "reasoning_effort" not in client.completions.create_kwargs


async def test_clients_are_shared_per_endpoint() -> None:
    adapter, created = make_adapter()
    await adapter.structured(LlmRole.GUARDRAIL, [user("a")], Verdict)
    await adapter.structured(LlmRole.JUDGE, [user("b")], Verdict)
    assert len(created) == 1


async def test_openai_errors_and_refusals_become_llm_error() -> None:
    adapter, created = make_adapter()
    await adapter.structured(LlmRole.GUARDRAIL, [user("warm up")], Verdict)
    client = created[(None, "sk-cloud")]
    client.completions.raise_on_parse = OpenAIError("rate limited")
    with pytest.raises(LlmError, match="rate limited"):
        await adapter.structured(LlmRole.GUARDRAIL, [user("a")], Verdict)
    client.completions.raise_on_parse = None
    client.completions.parsed = None
    with pytest.raises(LlmError, match="no parsed output"):
        await adapter.structured(LlmRole.GUARDRAIL, [user("a")], Verdict)


def test_message_roles_serialize_to_openai_roles() -> None:
    assert [r.value for r in ChatRole] == ["system", "user", "assistant", "tool"]


async def test_real_sdk_client_against_mocked_http() -> None:
    import json

    import httpx2
    from openai import AsyncOpenAI

    parse_body = {
        "id": "c1",
        "object": "chat.completion",
        "created": 0,
        "model": "qwen-small",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": '{"ok": true}'},
            }
        ],
        "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9},
    }
    chunks = [
        {"choices": [{"index": 0, "delta": {"content": "Xin "}}]},
        {"choices": [{"index": 0, "delta": {"content": "chào"}}]},
        {
            "choices": [],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        },
    ]
    sse = (
        "".join(
            "data: "
            + json.dumps(
                {
                    "id": "s",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": "m",
                    **c,
                }
            )
            + "\n\n"
            for c in chunks
        )
        + "data: [DONE]\n\n"
    )

    calls: list[dict] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        calls.append(body)
        if body.get("stream"):
            return httpx2.Response(
                200, text=sse, headers={"content-type": "text/event-stream"}
            )
        return httpx2.Response(200, json=parse_body)

    def factory(endpoint, timeout, max_retries):
        # The real SDK client; only the transport is replaced.
        return AsyncOpenAI(
            api_key=endpoint.api_key,
            base_url=endpoint.base_url,
            max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        )

    settings = LlmSettings(
        default=LlmEndpoint(
            base_url="http://llm.test/v1", api_key="k", model="qwen-small"
        ),
        roles={LlmRole.ANSWER: LlmEndpoint(model="qwen-large", reasoning_effort="low")},
    )
    adapter = OpenAiLlmAdapter(settings, client_factory=factory)
    result, usage = await adapter.structured(LlmRole.GUARDRAIL, [user("u")], Verdict)
    deltas = [d async for d in adapter.stream(LlmRole.ANSWER, [user("hi")])]

    assert result == Verdict(ok=True) and usage.prompt_tokens == 7
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert calls[0]["response_format"]["json_schema"]["strict"] is True
    assert "".join(d.text for d in deltas) == "Xin chào"
    assert deltas[-1].usage == LlmUsage(prompt_tokens=3, completion_tokens=2)
    assert (calls[0]["model"], calls[1]["model"]) == ("qwen-small", "qwen-large")
    assert "reasoning_effort" not in calls[0]
    assert calls[1]["reasoning_effort"] == "low"


async def test_reasoning_tokens_reported_outside_completion_tokens_are_counted() -> (
    None
):
    adapter, created = make_adapter()
    await adapter.structured(LlmRole.GUARDRAIL, [user("warm up")], Verdict)
    client = created[(None, "sk-cloud")]
    original_parse = client.completions.parse

    async def proxy_style_parse(**kwargs):
        completion = await original_parse(**kwargs)
        # Shape returned by a Gemini proxy: reasoning only in total and completion details.
        completion.usage = SimpleNamespace(
            prompt_tokens=33, completion_tokens=15, total_tokens=392
        )
        return completion

    client.completions.parse = proxy_style_parse
    _, usage = await adapter.structured(LlmRole.GUARDRAIL, [user("a")], Verdict)
    assert usage == LlmUsage(prompt_tokens=33, completion_tokens=359)


async def test_extra_body_is_sent_only_for_roles_that_set_it() -> None:
    created: dict[tuple, FakeClient] = {}

    def factory(endpoint, timeout, max_retries):
        client = FakeClient()
        created[(endpoint.base_url, endpoint.api_key)] = client
        return client

    no_thinking = {"chat_template_kwargs": {"enable_thinking": False}}
    settings = LlmSettings(
        default=LlmEndpoint(api_key="sk-cloud", model="qwen-small"),
        roles={
            LlmRole.ANSWER: LlmEndpoint(
                base_url="http://open/v1",
                api_key="open",
                model="Qwen/Qwen3.5-9B",
                extra_body=no_thinking,
            )
        },
    )
    adapter = OpenAiLlmAdapter(settings, client_factory=factory)
    _ = [d async for d in adapter.stream(LlmRole.ANSWER, [user("hi")])]
    await adapter.structured(LlmRole.GUARDRAIL, [user("a")], Verdict)
    assert (
        created[("http://open/v1", "open")].completions.create_kwargs["extra_body"]
        == no_thinking
    )
    assert "extra_body" not in created[(None, "sk-cloud")].completions.parse_kwargs


async def test_output_of_another_shape_becomes_llm_error() -> None:
    import httpx2
    from openai import AsyncOpenAI

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={
                "id": "c1",
                "object": "chat.completion",
                "created": 0,
                "model": "qwen-small",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": '{"verdict": 1}'},
                    }
                ],
            },
        )

    def factory(endpoint, timeout, max_retries):
        return AsyncOpenAI(
            api_key=endpoint.api_key,
            base_url=endpoint.base_url,
            max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        )

    settings = LlmSettings(
        default=LlmEndpoint(base_url="http://llm.test/v1", api_key="k", model="m")
    )
    adapter = OpenAiLlmAdapter(settings, client_factory=factory)
    with pytest.raises(LlmError, match="does not match Verdict"):
        await adapter.structured(LlmRole.GUARDRAIL, [user("u")], Verdict)


async def test_output_cap_is_sent_only_when_set_under_the_configured_name() -> None:
    created: dict[tuple, FakeClient] = {}

    def factory(endpoint, timeout, max_retries):
        client = FakeClient()
        created[(endpoint.base_url, endpoint.api_key)] = client
        return client

    settings = LlmSettings(
        default=LlmEndpoint(api_key="sk-cloud", model="qwen-small"),
        roles={
            LlmRole.JUDGE: LlmEndpoint(max_output_tokens=512),
            LlmRole.ANSWER: LlmEndpoint(
                base_url="http://open/v1",
                api_key="open",
                max_output_tokens=4096,
                max_tokens_param="max_tokens",
            ),
        },
    )
    adapter = OpenAiLlmAdapter(settings, client_factory=factory)
    await adapter.structured(LlmRole.GUARDRAIL, [user("a")], Verdict)
    guardrail_kwargs = dict(created[(None, "sk-cloud")].completions.parse_kwargs)
    await adapter.structured(LlmRole.JUDGE, [user("b")], Verdict)
    judge_kwargs = created[(None, "sk-cloud")].completions.parse_kwargs
    _ = [d async for d in adapter.stream(LlmRole.ANSWER, [user("hi")])]
    answer_kwargs = created[("http://open/v1", "open")].completions.create_kwargs

    assert "max_completion_tokens" not in guardrail_kwargs
    assert "max_tokens" not in guardrail_kwargs
    assert judge_kwargs["max_completion_tokens"] == 512
    assert answer_kwargs["max_tokens"] == 4096
    assert "max_completion_tokens" not in answer_kwargs


async def test_structured_reads_reasoning_tokens() -> None:
    adapter, created = make_adapter()
    await adapter.structured(LlmRole.GUARDRAIL, [user("q")], Verdict)
    created[(None, "sk-cloud")].completions.usage_details = SimpleNamespace(
        reasoning_tokens=7
    )
    _, usage = await adapter.structured(LlmRole.GUARDRAIL, [user("q")], Verdict)
    assert usage.reasoning_tokens == 7
    assert usage.completion_tokens == 3


SEARCH = ToolSpec(
    name="search_corpus",
    description="Tìm",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)


def tool_response(content, calls, finish_reason):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(content=content, tool_calls=calls),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=30, completion_tokens=5),
    )


async def test_tool_call_sends_tools_and_maps_calls() -> None:
    adapter, created = make_adapter()
    await adapter.structured(LlmRole.GUARDRAIL, [user("warm")], Verdict)
    client = created[(None, "sk-cloud")]
    client.completions.tool_response = tool_response(
        None,
        [
            SimpleNamespace(
                id="c1",
                function=SimpleNamespace(
                    name="search_corpus", arguments='{"query": "liều"}'
                ),
            )
        ],
        "tool_calls",
    )
    turn, usage = await adapter.tool_call(LlmRole.AGENT, [user("liều?")], [SEARCH])
    kwargs = client.completions.create_kwargs
    assert kwargs["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "search_corpus",
                "description": "Tìm",
                "parameters": SEARCH.parameters,
            },
        }
    ]
    assert kwargs["parallel_tool_calls"] is True
    assert turn.text == ""
    assert turn.finish_reason == "tool_calls"
    assert turn.tool_calls == (
        ToolCall(id="c1", name="search_corpus", arguments='{"query": "liều"}'),
    )
    assert usage.prompt_tokens == 30


async def test_tool_call_without_tools_and_tool_messages_serialize() -> None:
    adapter, created = make_adapter()
    await adapter.structured(LlmRole.GUARDRAIL, [user("warm")], Verdict)
    client = created[(None, "sk-cloud")]
    client.completions.tool_response = tool_response("Đáp [1].", None, "stop")
    call = ToolCall(id="c1", name="search_corpus", arguments='{"query": "x"}')
    messages = [
        user("hỏi"),
        ChatMessage(role=ChatRole.ASSISTANT, content="", tool_calls=(call,)),
        ChatMessage(role=ChatRole.TOOL, content="[1] tài liệu", tool_call_id="c1"),
    ]
    turn, _ = await adapter.tool_call(LlmRole.AGENT, messages, [])
    kwargs = client.completions.create_kwargs
    assert "tools" not in kwargs
    assert "parallel_tool_calls" not in kwargs
    assert kwargs["messages"][1] == {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "search_corpus", "arguments": '{"query": "x"}'},
            }
        ],
    }
    assert kwargs["messages"][2] == {
        "role": "tool",
        "content": "[1] tài liệu",
        "tool_call_id": "c1",
    }
    assert turn.text == "Đáp [1]."
    assert turn.tool_calls == ()


async def test_tool_call_errors_become_llm_error() -> None:
    adapter, created = make_adapter()
    await adapter.structured(LlmRole.GUARDRAIL, [user("warm")], Verdict)
    client = created[(None, "sk-cloud")]

    async def boom(**_kwargs):
        raise OpenAIError("down")

    client.completions.create = boom
    with pytest.raises(LlmError, match="agent"):
        await adapter.tool_call(LlmRole.AGENT, [user("x")], [SEARCH])


async def test_tool_choice_none_keeps_the_tools_and_forbids_calls() -> None:
    adapter, created = make_adapter()
    await adapter.structured(LlmRole.GUARDRAIL, [user("warm")], Verdict)
    client = created[(None, "sk-cloud")]
    client.completions.tool_response = tool_response("Đáp.", None, "stop")
    await adapter.tool_call(LlmRole.AGENT, [user("hỏi")], [SEARCH], tool_choice="none")
    kwargs = client.completions.create_kwargs
    assert kwargs["tool_choice"] == "none"
    assert [t["function"]["name"] for t in kwargs["tools"]] == ["search_corpus"]
    assert "parallel_tool_calls" not in kwargs
