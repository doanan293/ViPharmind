"""The ReAct agent's tool, prompt and rules for what the model sees (spec v2 §2.4).

One read-only tool, `search_corpus`, returns at most five chunks as the pipeline reads
them; the application builds it as a LangChain tool from SEARCH_TOOL_NAME, its
description and SearchArgs. Chunks are numbered [n] in first-shown order across the
turn, so the answer cites them with the pipeline's rules; a chunk shown before appears
again only as its number, and the evidence budget counts the chunk text placed in the
messages.
"""

from collections.abc import Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pharma_agent.domain.agent.prompts import ASSISTANT_ROLE, CITATION_RULES
from pharma_agent.domain.conversation.models import ConversationContext
from pharma_agent.domain.llm.models import ChatMessage, ChatRole, user
from pharma_agent.domain.retrieval.models import Hit

MAX_TOOL_ROUNDS = 6
ROUND_CAP_NOTE = "Đã hết lượt tra cứu, trả lời từ những gì đã có."
BUDGET_NOTE = "Hết ngân sách bằng chứng, trả lời từ những gì đã có."
DUPLICATE_NOTE = "(Truy vấn này đã tìm ở trên; kết quả như cũ.)"
NO_HIT = "Không tìm thấy tài liệu phù hợp."

SEARCH_TOOL_NAME = "search_corpus"
SEARCH_TOOL_DESCRIPTION = (
    "Tìm trong Dược thư Quốc gia Việt Nam và tờ hướng dẫn sử dụng thuốc. "
    "Trả về tối đa 5 đoạn, mỗi đoạn có số [n] để trích dẫn."
)


class SearchArgs(BaseModel):
    """The arguments of a search_corpus call: one non-empty query."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        description="Câu tìm kiếm tiếng Việt: tên thuốc hoặc hoạt chất và ý cần tìm."
    )

    @field_validator("query")
    @classmethod
    def _not_blank(cls, query: str) -> str:
        query = query.strip()
        if not query:
            raise ValueError("search_corpus needs a non-empty string argument query")
        return query


REACT_SYSTEM = f"""{ASSISTANT_ROLE}
Bạn có một công cụ: search_corpus(query) tìm trong Dược thư Quốc gia và tờ hướng dẫn sử dụng thuốc, trả về tối đa 5 đoạn, mỗi đoạn có số [n].

Cách làm:
- Dùng công cụ để tìm đúng mục trước khi trả lời, không đoán.
- Phần lớn câu chỉ cần một đến hai lần tìm. Đi rộng rồi thu hẹp: tìm theo tên thuốc và ý hỏi, rồi tìm riêng phần còn thiếu.
- Câu chào hỏi hoặc hỏi về chính bạn thì trả lời ngắn, không cần tìm.
- Khi đã đủ, trả lời bằng tiếng Việt, thẳng vào câu hỏi.

{CITATION_RULES}
Ở đây Tài liệu là các đoạn công cụ trả về."""


class Shown(BaseModel):
    """What the model has seen in this turn: chunk numbers, chunk text, results."""

    # chunk_version_id → citation number, in first-shown order.
    numbers: dict[UUID, int] = Field(default_factory=dict)
    # Characters of chunk text placed in the messages so far.
    chars: int = 0
    # Normalized query → the result text it produced.
    results: dict[str, str] = Field(default_factory=dict)


def react_history(context: ConversationContext, question: str) -> list[ChatMessage]:
    """The turn's messages after the system prompt: the summary, the earlier turns and
    the question."""
    messages: list[ChatMessage] = []
    if context.summary:
        messages.append(user(f"Tóm tắt hội thoại trước:\n{context.summary}"))
    for turn in context.turns:
        messages.append(user(turn.user_text))
        messages.append(
            ChatMessage(role=ChatRole.ASSISTANT, content=turn.assistant_text)
        )
    messages.append(user(question))
    return messages


def normalize_query(text: str) -> str:
    return " ".join(text.lower().split())


def render_result(
    hits: Sequence[Hit], shown: Shown, *, max_chars: int
) -> tuple[str, list[Hit], bool]:
    """The text of one search result and the hits it shows for the first time.

    A hit whose text would pass `max_chars` (with what was shown before) is not shown,
    and the result ends with BUDGET_NOTE. Returns (text, newly shown hits, budget hit).
    """
    if not hits:
        return NO_HIT, [], False
    blocks: list[str] = []
    new: list[Hit] = []
    budget_hit = False
    for hit in hits:
        number = shown.numbers.get(hit.chunk_version_id)
        if number is not None:
            blocks.append(f"[{number}] (đã hiển thị ở trên)")
            continue
        if shown.chars + len(hit.chunk_text) > max_chars:
            budget_hit = True
            continue
        number = len(shown.numbers) + 1
        shown.numbers[hit.chunk_version_id] = number
        shown.chars += len(hit.chunk_text)
        new.append(hit)
        page = f" ({hit.page_label})" if hit.page_label else ""
        blocks.append(f"[{number}] {hit.context_header}{page}:\n{hit.chunk_text}")
    if budget_hit:
        blocks.append(BUDGET_NOTE)
    return "\n\n".join(blocks), new, budget_hit
