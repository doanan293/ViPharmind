from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from pharma_agent.domain.shared.errors import DomainError
from pharma_agent.domain.shared.ids import new_id

MAX_NOTE_CHARS = 2000


class Rating(StrEnum):
    """Thumbs up or down."""

    UP = "up"
    DOWN = "down"


class InvalidNote(DomainError):
    """The feedback note is too long."""

    code = "INVALID_NOTE"


class Feedback(BaseModel):
    """One user's verdict on one assistant message; a second submission replaces the first."""

    model_config = ConfigDict(frozen=True)

    feedback_id: str
    user_id: str
    message_id: str
    rating: Rating
    note: str = ""
    created_at: datetime

    @classmethod
    def create(
        cls, *, user_id: str, message_id: str, rating: Rating, note: str, now: datetime
    ) -> "Feedback":
        """New feedback with a stripped note and a fresh id.

        Raises:
            InvalidNote: the stripped note is longer than MAX_NOTE_CHARS.
        """
        cleaned = note.strip()
        if len(cleaned) > MAX_NOTE_CHARS:
            raise InvalidNote(f"note must be at most {MAX_NOTE_CHARS} characters")
        return cls(
            feedback_id=new_id(),
            user_id=user_id,
            message_id=message_id,
            rating=rating,
            note=cleaned,
            created_at=now,
        )
