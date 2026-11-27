from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ActionKind(StrEnum):
    """The kind of step an action records."""

    GUARD = "guard"
    REPHRASE = "rephrase"
    SEARCH = "search"
    JUDGE = "judge"
    REFINE = "refine"
    ANSWER = "answer"
    AGENT = "agent"


class Action(BaseModel):
    """One recorded step of a turn: its kind, time, outcome, reason and payload."""

    model_config = ConfigDict(frozen=True)

    kind: ActionKind
    at: datetime
    outcome: str = ""
    reason: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class ActionLog(BaseModel):
    """The ordered actions of a turn."""

    entries: list[Action] = Field(default_factory=list)

    def append(self, action: Action) -> None:
        """Add `action` at the end."""
        self.entries.append(action)

    def last_of(self, *kinds: ActionKind) -> Action | None:
        """The latest action of any of `kinds`, or None."""
        for action in reversed(self.entries):
            if action.kind in kinds:
                return action
        return None

    def count(self, kind: ActionKind) -> int:
        """Number of actions of `kind`."""
        return sum(1 for a in self.entries if a.kind is kind)
