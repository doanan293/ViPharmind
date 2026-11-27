"""Public progress contract emitted during a chat turn. Never expose node names, prompts or reasoning."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Phase(StrEnum):
    """Coarse stage of a chat turn shown to the user."""

    GUARDING = "guarding"
    UNDERSTANDING = "understanding"
    SEARCHING = "searching"
    READING = "reading"
    ANSWERING = "answering"
    DONE = "done"


class EventType(StrEnum):
    """Kind of a progress event streamed to the client."""

    CONVERSATION = "conversation"
    PHASE = "phase"
    EVIDENCE = "evidence"
    TOKEN = "token"
    CITATIONS = "citations"
    DONE = "done"


class ProgressEvent(BaseModel):
    """One progress event; `data` holds the payload of its `type`."""

    type: EventType
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def phase(cls, phase: Phase, **extra: Any) -> "ProgressEvent":
        """Build a phase event; `extra` adds fields to its data."""
        return cls(type=EventType.PHASE, data={"phase": phase.value, **extra})

    @classmethod
    def token(cls, text: str) -> "ProgressEvent":
        """Build an event carrying one chunk of answer text."""
        return cls(type=EventType.TOKEN, data={"text": text})
