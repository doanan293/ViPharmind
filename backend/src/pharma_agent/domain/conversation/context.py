from collections.abc import Sequence

from pharma_agent.domain.conversation.models import ConversationContext, Turn

EXCLUDED_STATUSES = frozenset({"blocked", "error", "timeout"})


def context_for_rephrase(
    summary: str, turns: Sequence[Turn], *, max_turns: int = 4, max_chars: int = 4000
) -> ConversationContext:
    """Summary + the last usable turns, trimmed from the oldest turn until it fits max_chars."""
    summary = summary.strip()[:max_chars]
    usable = [t for t in turns if t.status not in EXCLUDED_STATUSES][-max_turns:]
    budget = max_chars - len(summary)
    while usable and sum(t.char_count() for t in usable) > budget:
        usable.pop(0)
    return ConversationContext(summary=summary, turns=usable)


def query_with_history(question: str, context: ConversationContext) -> str:
    """The earlier user questions followed by this one: a conversational query with no rewrite."""
    return " ".join([*(t.user_text.strip() for t in context.turns), question.strip()])
