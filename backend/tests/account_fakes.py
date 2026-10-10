"""In-memory account ports for AccountService tests and the Postgres/E2E apps' senders."""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from pharma_agent.application.account.service import AccountPolicy, AccountService
from pharma_agent.domain.account.codes import MAX_ATTEMPTS
from pharma_agent.domain.account.models import (
    AccountConflict,
    AccountUser,
    OneTimeCode,
    OtpPurpose,
    SessionRecord,
)
from pharma_agent.domain.account.ports import DeliveryError

START = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
OTP_SECRET = "o" * 40
CODE_PATTERN = re.compile(r"\b(\d{6})\b")


def code_in(text: str) -> str:
    match = CODE_PATTERN.search(text)
    if match is None:
        raise AssertionError(f"no code in {text!r}")
    return match.group(1)


class MutableClock:
    def __init__(self, at: datetime = START) -> None:
        self.at = at

    def now(self) -> datetime:
        return self.at

    def advance(self, **delta: float) -> None:
        self.at += timedelta(**delta)


class PlainHasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, hashed: str) -> bool:
        return hashed == f"hashed:{password}"


class InMemoryAccounts:
    def __init__(self) -> None:
        self.users: dict[uuid.UUID, AccountUser] = {}
        self.passwords: dict[uuid.UUID, str] = {}

    def add(
        self,
        *,
        email: str | None = "an@example.com",
        phone: str | None = None,
        email_verified: bool = False,
        phone_verified: bool = False,
        password: str = "old-password",
        password_set: bool = True,
        google: bool = False,
        active: bool = True,
    ) -> AccountUser:
        user = AccountUser(
            id=uuid.uuid4(),
            email=email,
            phone_number=phone,
            display_name="",
            email_verified=email_verified,
            phone_verified=phone_verified,
            password_set=password_set,
            google_linked=google,
            is_active=active,
            is_superuser=False,
        )
        self.users[user.id] = user
        self.passwords[user.id] = PlainHasher().hash(password)
        return user

    async def get(self, user_id: uuid.UUID) -> AccountUser | None:
        return self.users.get(user_id)

    async def get_by_email(self, email: str) -> AccountUser | None:
        return next(
            (
                u
                for u in self.users.values()
                if u.email is not None and u.email.lower() == email.lower()
            ),
            None,
        )

    async def get_by_phone(self, phone: str) -> AccountUser | None:
        return next((u for u in self.users.values() if u.phone_number == phone), None)

    async def create_phone_user(
        self, *, phone: str, hashed_password: str, now: datetime
    ) -> AccountUser:
        if await self.get_by_phone(phone) is not None:
            raise AccountConflict(phone)
        user = self.add(
            email=None, phone=phone, phone_verified=True, password_set=False
        )
        self.passwords[user.id] = hashed_password
        return user

    async def mark_email_verified(self, user_id: uuid.UUID, now: datetime) -> None:
        self.users[user_id] = replace(self.users[user_id], email_verified=True)

    async def set_email(self, user_id: uuid.UUID, email: str, now: datetime) -> None:
        owner = await self.get_by_email(email)
        if owner is not None and owner.id != user_id:
            raise AccountConflict(email)
        self.users[user_id] = replace(
            self.users[user_id], email=email, email_verified=True
        )

    async def set_phone(self, user_id: uuid.UUID, phone: str, now: datetime) -> None:
        owner = await self.get_by_phone(phone)
        if owner is not None and owner.id != user_id:
            raise AccountConflict(phone)
        self.users[user_id] = replace(
            self.users[user_id], phone_number=phone, phone_verified=True
        )

    async def set_password(self, user_id: uuid.UUID, hashed_password: str) -> None:
        self.passwords[user_id] = hashed_password
        self.users[user_id] = replace(self.users[user_id], password_set=True)

    async def hashed_password(self, user_id: uuid.UUID) -> str | None:
        return self.passwords.get(user_id)

    async def unlink_oauth(self, user_id: uuid.UUID, oauth_name: str) -> None:
        self.users[user_id] = replace(self.users[user_id], google_linked=False)

    async def update_display_name(self, user_id: uuid.UUID, display_name: str) -> None:
        self.users[user_id] = replace(self.users[user_id], display_name=display_name)


@dataclass
class StoredCode:
    id: uuid.UUID
    purpose: OtpPurpose
    destination: str
    user_id: uuid.UUID | None
    digest: str
    expires_at: datetime
    attempts: int = 0
    consumed_at: datetime | None = None


class InMemoryCodes:
    def __init__(self) -> None:
        self.rows: list[StoredCode] = []

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
        self.rows = [
            row
            for row in self.rows
            if not (
                row.purpose is purpose
                and row.destination == destination
                and row.consumed_at is None
            )
        ]
        row = StoredCode(
            uuid.uuid4(), purpose, destination, user_id, digest, expires_at
        )
        self.rows.append(row)
        return row.id

    def _row(self, code_id: uuid.UUID) -> StoredCode:
        return next(row for row in self.rows if row.id == code_id)

    async def find_active(
        self, purpose: OtpPurpose, destination: str, now: datetime
    ) -> OneTimeCode | None:
        for row in reversed(self.rows):
            if (
                row.purpose is purpose
                and row.destination == destination
                and row.consumed_at is None
                and row.expires_at > now
                and row.attempts < MAX_ATTEMPTS
            ):
                return OneTimeCode(
                    row.id,
                    row.purpose,
                    row.destination,
                    row.user_id,
                    row.digest,
                    row.expires_at,
                    row.attempts,
                )
        return None

    async def record_failure(self, code_id: uuid.UUID) -> None:
        self._row(code_id).attempts += 1

    async def consume(self, code_id: uuid.UUID, now: datetime) -> bool:
        row = self._row(code_id)
        if row.consumed_at is not None:
            return False
        row.consumed_at = now
        return True

    async def revoke(self, code_id: uuid.UUID, now: datetime) -> None:
        self._row(code_id).consumed_at = now


class InMemoryLimiter:
    def __init__(self, clock: MutableClock) -> None:
        self._clock = clock
        self.counts: dict[tuple[str, float], int] = {}

    def _slot(self, window_seconds: int) -> tuple[float, float]:
        epoch = self._clock.now().timestamp()
        start = epoch - epoch % window_seconds
        return start, start + window_seconds - epoch

    async def check(self, key: str, *, limit: int, window_seconds: int) -> float | None:
        start, remaining = self._slot(window_seconds)
        return remaining if self.counts.get((key, start), 0) >= limit else None

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> float | None:
        start, remaining = self._slot(window_seconds)
        self.counts[(key, start)] = self.counts.get((key, start), 0) + 1
        return remaining if self.counts[(key, start)] > limit else None


@dataclass(frozen=True)
class SentEmail:
    to: str
    subject: str
    text: str
    html: str


@dataclass(frozen=True)
class SentSms:
    to: str
    text: str


class RecordingEmailSender:
    def __init__(self) -> None:
        self.sent: list[SentEmail] = []
        self.fail = False

    async def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        if self.fail:
            raise DeliveryError("provider down")
        self.sent.append(SentEmail(to, subject, text, html))

    def last_code(self, to: str) -> str:
        return code_in(next(m.text for m in reversed(self.sent) if m.to == to))


class RecordingSmsSender:
    def __init__(self) -> None:
        self.sent: list[SentSms] = []
        self.fail = False

    async def send(self, *, to: str, text: str) -> None:
        if self.fail:
            raise DeliveryError("provider down")
        self.sent.append(SentSms(to, text))

    def last_code(self, to: str) -> str:
        return code_in(next(m.text for m in reversed(self.sent) if m.to == to))


class InMemorySessions:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, list[SessionRecord]] = {}

    def add(self, user_id: uuid.UUID, token: str, at: datetime = START) -> None:
        self.rows.setdefault(user_id, []).append(
            SessionRecord(token, at, None, "Firefox", "10.0.0.1")
        )

    async def for_user(self, user_id: uuid.UUID) -> Sequence[SessionRecord]:
        return sorted(
            self.rows.get(user_id, []), key=lambda r: r.created_at, reverse=True
        )

    async def delete(self, user_id: uuid.UUID, token: str) -> bool:
        before = len(self.rows.get(user_id, []))
        self.rows[user_id] = [r for r in self.rows.get(user_id, []) if r.token != token]
        return len(self.rows[user_id]) < before

    async def delete_all(self, user_id: uuid.UUID, *, keep: str | None = None) -> int:
        before = len(self.rows.get(user_id, []))
        self.rows[user_id] = [r for r in self.rows.get(user_id, []) if r.token == keep]
        return before - len(self.rows[user_id])


@dataclass
class AccountFakes:
    clock: MutableClock
    accounts: InMemoryAccounts = field(default_factory=InMemoryAccounts)
    codes: InMemoryCodes = field(default_factory=InMemoryCodes)
    email: RecordingEmailSender = field(default_factory=RecordingEmailSender)
    sms: RecordingSmsSender = field(default_factory=RecordingSmsSender)
    sessions: InMemorySessions = field(default_factory=InMemorySessions)


def build_account_service(
    clock: MutableClock | None = None, policy: AccountPolicy | None = None
) -> tuple[AccountService, AccountFakes]:
    fakes = AccountFakes(clock=clock or MutableClock())
    service = AccountService(
        accounts=fakes.accounts,
        codes=fakes.codes,
        limiter=InMemoryLimiter(fakes.clock),
        email=fakes.email,
        sms=fakes.sms,
        hasher=PlainHasher(),
        sessions=fakes.sessions,
        clock=fakes.clock,
        policy=policy or AccountPolicy(otp_secret=OTP_SECRET),
    )
    return service, fakes
