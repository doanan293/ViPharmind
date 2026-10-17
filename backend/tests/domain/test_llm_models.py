from pharma_agent.domain.llm.models import (
    ChatMessage,
    ChatRole,
    LlmRole,
    LlmUsage,
    ToolCall,
)


def test_usage_adds_token_counts() -> None:
    total = LlmUsage(prompt_tokens=10, completion_tokens=5) + LlmUsage(
        prompt_tokens=1, completion_tokens=2
    )
    assert total == LlmUsage(prompt_tokens=11, completion_tokens=7)
    assert total.total_tokens == 18


def test_chat_message_is_immutable_value_object() -> None:
    message = ChatMessage(role=ChatRole.USER, content="hi")
    assert ChatMessage.model_config.get("frozen") is True
    assert {message, ChatMessage(role=ChatRole.USER, content="hi")} == {message}


def test_llm_roles_cover_every_pipeline_step() -> None:
    assert {role.value for role in LlmRole} == {
        "guardrail",
        "rephrase",
        "judge",
        "refine",
        "answer",
        "summarizer",
        "agent",
    }


def test_usage_adds_reasoning_tokens() -> None:
    total = LlmUsage(
        prompt_tokens=1, completion_tokens=5, reasoning_tokens=2
    ) + LlmUsage(completion_tokens=3, reasoning_tokens=1)
    assert total.reasoning_tokens == 3
    assert total.completion_tokens == 8


def test_tool_messages_carry_calls_and_answers() -> None:
    call = ToolCall(
        id="c1", name="search_corpus", arguments='{"query": "paracetamol liều"}'
    )
    asked = ChatMessage(role=ChatRole.ASSISTANT, content="", tool_calls=(call,))
    answered = ChatMessage(role=ChatRole.TOOL, content="[1] ...", tool_call_id="c1")
    assert asked.tool_calls[0].name == "search_corpus"
    assert answered.tool_call_id == "c1"
    assert ChatMessage(role=ChatRole.USER, content="x").tool_calls == ()
