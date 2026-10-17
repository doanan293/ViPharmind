import pytest

from pharma_agent.domain.agent.react import (
    BUDGET_NOTE,
    SEARCH_TOOL,
    Shown,
    normalize_query,
    parse_query,
    react_messages,
    render_result,
)
from pharma_agent.domain.conversation.models import ConversationContext, Turn
from pharma_agent.domain.llm.models import ChatRole, ToolCall
from tests.domain.factories import chunk_uuid, make_hit


def hit(label: str, text: str = "Liều 500 mg."):
    return make_hit(label, text=text)


def test_search_tool_schema_has_one_required_query() -> None:
    assert SEARCH_TOOL.name == "search_corpus"
    assert SEARCH_TOOL.parameters["required"] == ["query"]
    assert SEARCH_TOOL.parameters["additionalProperties"] is False


def test_render_numbers_new_hits_and_refers_to_shown_ones() -> None:
    shown = Shown()
    first, new, budget_hit = render_result(
        [hit("a"), hit("b")], shown, max_chars=60_000
    )
    assert first.startswith("[1] ")
    assert "\n\n[2] " in first
    assert not budget_hit
    assert [h.chunk_version_id for h in new] == [chunk_uuid("a"), chunk_uuid("b")]
    again, new_again, _ = render_result([hit("b"), hit("c")], shown, max_chars=60_000)
    assert "[2] (đã hiển thị ở trên)" in again
    assert "[3] " in again
    assert [h.chunk_version_id for h in new_again] == [chunk_uuid("c")]
    assert shown.chars == 3 * len("Liều 500 mg.")
    assert shown.numbers[chunk_uuid("c")] == 3


def test_render_stops_at_the_evidence_budget() -> None:
    shown = Shown()
    text, new, budget_hit = render_result(
        [hit("a", "x" * 50), hit("b", "y" * 50)], shown, max_chars=80
    )
    assert budget_hit
    assert text.endswith(BUDGET_NOTE)
    assert len(new) == 1
    assert shown.chars == 50


def test_render_says_when_nothing_was_found() -> None:
    text, new, budget_hit = render_result([], Shown(), max_chars=60_000)
    assert text == "Không tìm thấy tài liệu phù hợp."
    assert new == []
    assert not budget_hit


def test_parse_query_rejects_malformed_arguments() -> None:
    call = ToolCall(id="1", name="search_corpus", arguments='{"query": " liều  dùng "}')
    assert parse_query(call) == "liều  dùng"
    for arguments, reason in (
        ("not json", "JSON"),
        ('{"q": "x"}', "query"),
        ('{"query": ""}', "query"),
        ('["x"]', "query"),
    ):
        with pytest.raises(ValueError, match=reason):
            parse_query(ToolCall(id="1", name="search_corpus", arguments=arguments))
    with pytest.raises(ValueError, match="unknown tool"):
        parse_query(ToolCall(id="1", name="read_section", arguments='{"query": "x"}'))


def test_normalize_query_folds_case_and_spaces() -> None:
    assert normalize_query("  Paracetamol   LIỀU ") == "paracetamol liều"


def test_messages_put_history_before_the_question() -> None:
    context = ConversationContext(
        turns=[
            Turn(
                user_text="Paracetamol là gì?",
                assistant_text="Thuốc giảm đau.",
                status="completed",
            )
        ]
    )
    messages = react_messages(context, "Người lớn uống tối đa bao nhiêu?")
    assert [m.role for m in messages] == [
        ChatRole.SYSTEM,
        ChatRole.USER,
        ChatRole.ASSISTANT,
        ChatRole.USER,
    ]
    assert "search_corpus" in messages[0].content
    assert "[n]" in messages[0].content
    assert messages[-1].content == "Người lớn uống tối đa bao nhiêu?"
