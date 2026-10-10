"""Accounts that sign in with a password, a phone number or Google, and their codes."""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pharma_agent.domain.shared.errors import DomainError


class OtpPurpose(StrEnum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"
    CHANGE_EMAIL = "change_email"
    PHONE_LOGIN = "phone_login"
    CHANGE_PHONE = "change_phone"


class Channel(StrEnum):
    EMAIL = "email"
    SMS = "sms"


CHANNEL_BY_PURPOSE: dict[OtpPurpose, Channel] = {
    OtpPurpose.VERIFY_EMAIL: Channel.EMAIL,
    OtpPurpose.RESET_PASSWORD: Channel.EMAIL,
    OtpPurpose.CHANGE_EMAIL: Channel.EMAIL,
    OtpPurpose.PHONE_LOGIN: Channel.SMS,
    OtpPurpose.CHANGE_PHONE: Channel.SMS,
}


class SignInMethod(StrEnum):
    PASSWORD = "password"
    PHONE = "phone"
    GOOGLE = "google"


class AccountConflict(DomainError):
    """The email or phone number already belongs to another account."""

    code = "ACCOUNT_CONFLICT"


@dataclass(frozen=True)
class AccountUser:
    id: uuid.UUID
    email: str | None
    phone_number: str | None
    display_name: str
    email_verified: bool
    phone_verified: bool
    password_set: bool
    google_linked: bool
    is_active: bool
    is_superuser: bool
    # Overrides of the default quotas; None uses the configured default.
    text_quota_bytes: int | None = None
    collection_quota: int | None = None
    created_at: datetime | None = None

    def sign_in_methods(self) -> set[SignInMethod]:
        """Ways this account can sign in now; a password needs a verified email to log in with."""
        methods: set[SignInMethod] = set()
        if self.password_set and self.email is not None and self.email_verified:
            methods.add(SignInMethod.PASSWORD)
        if self.phone_number is not None and self.phone_verified:
            methods.add(SignInMethod.PHONE)
        if self.google_linked:
            methods.add(SignInMethod.GOOGLE)
        return methods


@dataclass(frozen=True)
class OneTimeCode:
    id: uuid.UUID
    purpose: OtpPurpose
    destination: str
    user_id: uuid.UUID | None
    digest: str
    expires_at: datetime
    attempts: int


@dataclass(frozen=True)
class SessionRecord:
    token: str
    created_at: datetime
    last_used_at: datetime | None
    user_agent: str
    ip_address: str


def normalize_email(email: str) -> str:
    return email.strip().lower()


def session_id_of(token: str) -> str:
    """A public id for a session; the token itself is the cookie secret and never leaves."""
    return hashlib.sha256(token.encode()).hexdigest()[:32]
