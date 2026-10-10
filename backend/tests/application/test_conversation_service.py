import uuid
from datetime import timedelta

import pytest

from pharma_agent.application.conversation.service import ConversationService
from pharma_agent.application.errors import ConversationNotFound, InvalidInput
from pharma_agent.application.pagination import InvalidCursor
from pharma_agent.domain.agent.run import AgentRun, AnswerMode, AnswerPlan
from pharma_agent.domain.conversation.models import Conversation
from pharma_agent.domain.conversation.turns import build_turn_messages
from pharma_agent.domain.shared.clock import FixedClock
from pharma_agent.domain.shared.ids import new_id
from tests.domain.factories import make_run
from tests.fakes import NOW
from tests.memory_repository import (
    InMemoryCitationReader,
    InMemoryConversationRepository,
    InMemoryFeedbackRepository,
)

OWNER, STRANGER = "a" * 32, "b" * 32


def service_for(
    repo: InMemoryConversationRepository, clock: FixedClock
) -> ConversationService:
    return ConversationService(
        repo,
        clock,
        feedback=InMemoryFeedbackRepository(),
        citations=InMemoryCitationReader(),
    )


def finished_run(query: str) -> AgentRun:
    """Only finished runs are persisted, so history never holds a running status."""
    run = make_run(query)
    run.submit_plan(AnswerPlan(mode=AnswerMode.NO_RETRIEVAL), now=NOW)
    run.complete()
    return run


async def add_turn(
    repo: InMemoryConversationRepository, conversation: Conversation
) -> None:
    """Append a turn stamped NOW, so timestamps tie across turns."""
    user_msg, assistant_msg = build_turn_messages(
        user_message_id=new_id(),
        assistant_message_id=new_id(),
        conversation_id=conversation.conversation_id,
        run=finished_run("q"),
        answer_text="a",
        citations=[],
        now=NOW,
    )
    conversation.record_turn(NOW)
    await repo.append_turn(conversation, user_msg, assistant_msg)


async def test_list_get_messages_rename_delete() -> None:
    repo = InMemoryConversationRepository()
    service = service_for(repo, FixedClock(NOW + timedelta(days=1)))
    older = Conversation.start(user_id=OWNER, first_message="older", now=NOW)
    never_used = Conversation.start(
        user_id=OWNER, first_message="never used", now=NOW + timedelta(minutes=1)
    )
    await repo.create(older)
    await repo.create(never_used)
    user_msg, assistant_msg = build_turn_messages(
        user_message_id=new_id(),
        assistant_message_id=new_id(),
        conversation_id=older.conversation_id,
        run=finished_run("q"),
        answer_text="a",
        citations=[],
        now=NOW,
    )
    older.record_turn(NOW + timedelta(minutes=2))
    await repo.append_turn(older, user_msg, assistant_msg)

    listed = await service.list_conversations(OWNER, limit=10)
    assert [c.title for c in listed.items] == ["older"]
    assert listed.items[0].turn_count == 1 and listed.next_cursor is None

    page = await service.list_messages(OWNER, older.conversation_id, limit=10)
    assert [
        (message.role, message.parts[0].model_dump()) for message in page.items
    ] == [
        ("user", {"type": "text", "text": "q"}),
        ("assistant", {"type": "text", "text": "a"}),
    ]
    assert page.next_cursor is None

    renamed = await service.rename(OWNER, older.conversation_id, "  Thuốc hạ sốt ")
    assert renamed.title == "Thuốc hạ sốt" and renamed.updated_at == NOW + timedelta(
        days=1
    )

    with pytest.raises(InvalidInput):
        await service.rename(OWNER, older.conversation_id, " ")
    for call in (
        service.get_conversation(STRANGER, older.conversation_id),
        service.list_messages(STRANGER, older.conversation_id, limit=10),
        service.rename(STRANGER, older.conversation_id, "x"),
        service.delete(STRANGER, older.conversation_id),
    ):
        with pytest.raises(ConversationNotFound):
            await call

    await service.delete(OWNER, older.conversation_id)
    assert (await service.list_conversations(OWNER, limit=10)).items == []


async def test_pages_have_no_duplicates_or_gaps_when_timestamps_tie() -> None:
    repo = InMemoryConversationRepository()
    service = service_for(repo, FixedClock(NOW))
    created: list[Conversation] = []
    for index in range(5):
        conversation = Conversation.start(
            user_id=OWNER, first_message=f"c{index}", now=NOW
        )
        await repo.create(conversation)
        await add_turn(repo, conversation)
        created.append(conversation)
    for _ in range(3):
        await add_turn(repo, created[0])
    await repo.create(Conversation.start(user_id=OWNER, first_message="empty", now=NOW))

    listed: list[str] = []
    cursor: str | None = None
    while True:
        conversations = await service.list_conversations(OWNER, limit=2, cursor=cursor)
        listed.extend(item.id for item in conversations.items)
        if conversations.next_cursor is None:
            break
        cursor = conversations.next_cursor
    assert listed == sorted((c.conversation_id for c in created), reverse=True)

    conversation_id = created[0].conversation_id
    pages: list[list[str]] = []
    cursor = None
    while True:
        messages = await service.list_messages(
            OWNER, conversation_id, limit=3, cursor=cursor
        )
        pages.append([m.id for m in messages.items])
        if messages.next_cursor is None:
            break
        cursor = messages.next_cursor
    everything = [m.message_id for m in await repo.messages(conversation_id, limit=100)]
    assert len(set(everything)) == 8
    assert [len(ids) for ids in pages] == [3, 3, 2]
    assert [mid for ids in reversed(pages) for mid in ids] == everything

    exact = await service.list_messages(OWNER, conversation_id, limit=8)
    assert len(exact.items) == 8 and exact.next_cursor is None
    first_page = await service.list_conversations(OWNER, limit=2, cursor="")
    assert len(first_page.items) == 2
    with pytest.raises(InvalidCursor):
        await service.list_conversations(OWNER, limit=2, cursor="nope")


async def test_create_starts_an_empty_unlisted_conversation() -> None:
    repo = InMemoryConversationRepository()
    service = service_for(repo, FixedClock(NOW))

    view = await service.create(OWNER)

    assert (view.title, view.turn_count, view.created_at, view.updated_at) == (
        "Cuộc trò chuyện mới",
        0,
        NOW,
        NOW,
    )
    assert repo.rows[view.id].user_id == OWNER
    assert (await service.get_conversation(OWNER, view.id)).id == view.id
    assert (await service.list_conversations(OWNER, limit=10)).items == []


async def test_update_sets_the_sources_and_null_restores_everything() -> None:
    repo = InMemoryConversationRepository()
    service = service_for(repo, FixedClock(NOW))
    created = await service.create(OWNER)
    chosen = [uuid.uuid4(), uuid.uuid4()]

    narrowed = await service.update(OWNER, created.id, collection_ids=chosen)
    assert narrowed.collection_ids == chosen and narrowed.title == created.title
    stored = await repo.get(OWNER, created.id)
    assert stored is not None and stored.collection_ids == tuple(chosen)

    both = await service.update(
        OWNER, created.id, title="Tim mạch", collection_ids=None
    )
    assert both.title == "Tim mạch" and both.collection_ids is None

    with pytest.raises(InvalidInput):
        await service.update(OWNER, created.id, collection_ids=[])
    with pytest.raises(ConversationNotFound):
        await service.update(STRANGER, created.id, collection_ids=chosen)
