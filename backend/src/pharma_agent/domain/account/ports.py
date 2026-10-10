"""What the account use cases need from storage, delivery and password hashing."""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from pharma_agent.domain.account.models import (
    AccountUser,
    OneTimeCode,
    OtpPurpose,
    SessionRecord,
)
from pharma_agent.domain.shared.errors import DomainError


class DeliveryError(DomainError):
    """An email or SMS provider refused or failed to take the message."""

    code = "DELIVERY_ERROR"


class AccountRepository(Protocol):
    async def get(self, user_id: uuid.UUID) -> AccountUser | None: ...

    async def get_by_email(self, email: str) -> AccountUser | None:
        """Case-insensitive lookup."""
        ...

    async def get_by_phone(self, phone: str) -> AccountUser | None: ...

    async def create_phone_user(
        self, *, phone: str, hashed_password: str, now: datetime
    ) -> AccountUser:
        """A verified phone-only account; raises AccountConflict if the number is taken."""
        ...

    async def mark_email_verified(self, user_id: uuid.UUID, now: datetime) -> None: ...

    async def set_email(self, user_id: uuid.UUID, email: str, now: datetime) -> None:
        """Set a verified email; raises AccountConflict if another account has it."""
        ...

    async def set_phone(self, user_id: uuid.UUID, phone: str, now: datetime) -> None:
        """Set a verified phone number; raises AccountConflict if another account has it."""
        ...

    async def set_password(self, user_id: uuid.UUID, hashed_password: str) -> None:
        """Store the hash and mark the password as chosen by the user."""
        ...

    async def hashed_password(self, user_id: uuid.UUID) -> str | None: ...

    async def unlink_oauth(self, user_id: uuid.UUID, oauth_name: str) -> None: ...

    async def update_display_name(
        self, user_id: uuid.UUID, display_name: str
    ) -> None: ...


class OneTimeCodeStore(Protocol):
    async def issue(
        self,
        *,
        purpose: OtpPurpose,
        destination: str,
        user_id: uuid.UUID | None,
        digest: str,
        expires_at: datetime,
        now: datetime,
    ) -> uuid.UUID:
        """Store a code and drop every unused code for the same purpose and destination."""
        ...

    async def find_active(
        self, purpose: OtpPurpose, destination: str, now: datetime
    ) -> OneTimeCode | None:
        """The newest unused, unexpired code with fewer than MAX_ATTEMPTS failures."""
        ...

    async def claim_attempt(self, code_id: uuid.UUID) -> bool:
        """Count one guess before it is compared; False once MAX_ATTEMPTS were claimed.

        Atomic, so parallel guesses cannot exceed the limit.
        """
        ...

    async def consume(self, code_id: uuid.UUID, now: datetime) -> bool:
        """Mark the code used; False if it was already used (exactly one caller wins)."""
        ...

    async def revoke(self, code_id: uuid.UUID, now: datetime) -> None: ...


class RateLimiter(Protocol):
    """Counters over windows that open at the first counted action of a key.

    A window lasts `window_seconds` from that action, so a burst cannot straddle a clock
    boundary; the next action after it closes opens a new one.
    """

    async def check(self, key: str, *, limit: int, window_seconds: int) -> float | None:
        """Seconds until `key` may act again, or None while it is under `limit`."""
        ...

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> float | None:
        """Count one action; seconds to wait if this action went over `limit`."""
        ...

    async def acquire(
        self, key: str, *, limit: int, window_seconds: int
    ) -> float | None:
        """Count one action only while under `limit`, atomically.

        Returns None when the action was counted, or the seconds to wait when it was
        refused; a refusal counts nothing, so parallel callers can never overshoot.
        """
        ...

    async def release(self, key: str, *, window_seconds: int) -> None:
        """Give back one action counted by `acquire` in the current window."""
        ...


class EmailSender(Protocol):
    async def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        """Raises DeliveryError when the provider does not take the message."""
        ...


class SmsSender(Protocol):
    async def send(self, *, to: str, text: str) -> None:
        """Raises DeliveryError when the provider does not take the message."""
        ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, hashed: str) -> bool: ...


class SessionStore(Protocol):
    async def for_user(self, user_id: uuid.UUID) -> Sequence[SessionRecord]:
        """Unexpired sessions, newest first."""
        ...

    async def delete(self, user_id: uuid.UUID, token: str) -> bool: ...

    async def delete_all(
        self, user_id: uuid.UUID, *, keep: str | None = None
    ) -> int: ...
