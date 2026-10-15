import pytest

from pharma_agent.application.conversation.service import ConversationService
from pharma_agent.application.errors import CitationNotFound
from pharma_agent.domain.conversation.models import CitationBlock
from pharma_agent.domain.shared.clock import FixedClock
from tests.citations import SOURCE_TITLE, build_citation
from tests.domain.factories import NOW
from tests.memory_repository import (
    InMemoryCitationReader,
    InMemoryConversationRepository,
    InMemoryFeedbackRepository,
)

OWNER, STRANGER = "a" * 32, "b" * 32
MESSAGE_ID = "d" * 32


async def test_get_citation_returns_the_cited_chunk_text() -> None:
    reader = InMemoryCitationReader()
    reader.blocks[(OWNER, MESSAGE_ID, 1)] = CitationBlock(
        citation=build_citation(1, chunk=2),
        text="## Liều lượng và cách dùng\n\nđoạn 2",
        is_current=False,
    )
    service = ConversationService(
        InMemoryConversationRepository(),
        FixedClock(NOW),
        feedback=InMemoryFeedbackRepository(),
        citations=reader,
    )

    detail = await service.get_citation(OWNER, MESSAGE_ID, 1)

    assert detail.model_dump(mode="json") == {
        "index": 1,
        "source": SOURCE_TITLE,
        "document_title": "Paracetamol",
        "section": "Liều lượng và cách dùng",
        "start_page": 812,
        "end_page": 813,
        "is_current": False,
        "text": "## Liều lượng và cách dùng\n\nđoạn 2",
    }
    for user_id, index in ((STRANGER, 1), (OWNER, 2)):
        with pytest.raises(CitationNotFound):
            await service.get_citation(user_id, MESSAGE_ID, index)
