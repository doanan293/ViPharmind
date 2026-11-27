"""AI SDK `UIMessage` shapes shared by the chat stream and the history API.

Spec A §3.2, §3.4 and §4.2. Field names are camelCase on the wire through Pydantic's
`to_camel` alias generator; the other REST models keep snake_case.
"""

import uuid
from collections.abc import Collection, Mapping
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from pharma_agent.domain.conversation.models import Citation, Message, MessageRole
from pharma_agent.domain.feedback.models import Feedback, Rating


class CamelModel(BaseModel):
    """Base of the wire models: camelCase aliases, populated by name or alias."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )


class MessageStatus(StrEnum):
    """Final status of a message as shown to the client."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    ABSTAINED = "abstained"
    BLOCKED = "blocked"
    REDIRECTED = "redirected"
    ERROR = "error"
    TIMEOUT = "timeout"


class EvidenceItem(CamelModel):
    """One numbered evidence chunk streamed during a turn."""

    index: int
    source: str
    title: str
    section: str
    start_page: int | None
    end_page: int | None
    snippet: str


class PharmaSourceMetadata(CamelModel):
    """Pharma-specific metadata of a cited source; `is_current` says its release is current."""

    index: int
    source: str
    title: str
    section: str
    start_page: int | None
    end_page: int | None
    snippet: str
    is_current: bool


class SourceProviderMetadata(CamelModel):
    """Provider metadata of a source part, under the `pharma` key."""

    pharma: PharmaSourceMetadata


class TextUIPart(CamelModel):
    """The text of a message."""

    type: Literal["text"]
    text: str


class SourceDocumentUIPart(CamelModel):
    """One cited source of an assistant message."""

    type: Literal["source-document"]
    source_id: str
    media_type: Literal["text/markdown"]
    title: str
    provider_metadata: SourceProviderMetadata


UIMessagePart = Annotated[
    TextUIPart | SourceDocumentUIPart, Field(discriminator="type")
]


class MessageUsage(CamelModel):
    """Token and call usage of an assistant turn."""

    llm_calls: int
    prompt_tokens: int
    completion_tokens: int
    search_rounds: int


class MessageFeedback(CamelModel):
    """The user's rating of an assistant message."""

    rating: Rating
    note: str


class MessageMetadata(CamelModel):
    """Status, timing, usage and feedback of a message."""

    status: MessageStatus
    created_at: datetime
    error_code: str | None = None
    usage: MessageUsage | None = None
    run_id: str | None = None
    persisted: bool | None = None
    feedback: MessageFeedback | None = None


class UIMessage(CamelModel):
    """A chat message in AI SDK `UIMessage` shape."""

    id: str
    role: Literal["user", "assistant"]
    parts: list[UIMessagePart]
    metadata: MessageMetadata


class PhaseData(CamelModel):
    """Payload of a `data-phase` stream part."""

    phase: Literal[
        "guarding",
        "understanding",
        "searching",
        "reading",
        "answering",
    ]
    round: int | None = None


class EvidenceData(CamelModel):
    """Payload of a `data-evidence` stream part."""

    items: list[EvidenceItem]


class ConversationData(CamelModel):
    """Payload of a `data-conversation` stream part."""

    id: str
    title: str


class PharmaDataParts(CamelModel):
    """AI SDK `DataParts` of the chat stream: part `data-<field>` carries the field's payload."""

    phase: PhaseData
    evidence: EvidenceData
    conversation: ConversationData


def source_document_part(
    citation: Citation, *, is_current: bool
) -> SourceDocumentUIPart:
    """Build the source part of a citation."""
    return SourceDocumentUIPart(
        type="source-document",
        source_id=str(citation.chunk_version_id),
        media_type="text/markdown",
        title=f"{citation.title} › {citation.section}",
        provider_metadata=SourceProviderMetadata(
            pharma=PharmaSourceMetadata(
                index=citation.index,
                source=citation.source,
                title=citation.title,
                section=citation.section,
                start_page=citation.start_page,
                end_page=citation.end_page,
                snippet=citation.snippet,
                is_current=is_current,
            )
        ),
    )


def source_document_parts_from_event(
    data: Mapping[str, Any],
) -> list[SourceDocumentUIPart]:
    """Sources of a live turn: the `citations` event carries `Citation` JSON dumps."""
    return [
        source_document_part(Citation.model_validate(item), is_current=True)
        for item in data["items"]
    ]


def evidence_items_from_event(data: Mapping[str, Any]) -> list[EvidenceItem]:
    """Parse the evidence items of an `evidence` progress event."""
    return [EvidenceItem.model_validate(item) for item in data["items"]]


def ui_message_of(
    message: Message,
    *,
    feedback: Feedback | None,
    current_release_ids: Collection[uuid.UUID],
) -> UIMessage:
    """Build the UI message of a stored message, with its sources and feedback."""
    text = TextUIPart(type="text", text=message.content)
    status = MessageStatus(message.status)
    if message.role is MessageRole.USER:
        return UIMessage(
            id=message.message_id,
            role="user",
            parts=[text],
            metadata=MessageMetadata(status=status, created_at=message.created_at),
        )
    parts: list[TextUIPart | SourceDocumentUIPart] = [text]
    parts.extend(
        source_document_part(
            citation, is_current=citation.release_id in current_release_ids
        )
        for citation in message.citations
    )
    return UIMessage(
        id=message.message_id,
        role="assistant",
        parts=parts,
        metadata=MessageMetadata(
            status=status,
            created_at=message.created_at,
            usage=MessageUsage.model_validate(message.usage) if message.usage else None,
            run_id=message.run_id,
            feedback=MessageFeedback(rating=feedback.rating, note=feedback.note)
            if feedback is not None
            else None,
        ),
    )
