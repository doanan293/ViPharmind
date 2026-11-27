from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Source of the current time."""

    def now(self) -> datetime:
        """The current time."""
        ...


class SystemClock:
    """The real clock, in UTC."""

    def now(self) -> datetime:
        """The current time in UTC."""
        return datetime.now(UTC)


class FixedClock:
    """Deterministic clock for tests."""

    def __init__(self, at: datetime) -> None:
        """Always report `at`."""
        self._at = at

    def now(self) -> datetime:
        """The fixed time."""
        return self._at
