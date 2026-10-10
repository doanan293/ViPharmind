"""Account use cases over one-time codes: verification, password reset, phone sign-in."""

import hmac
import logging
import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel

from pharma_agent.application.account.errors import (
    AccountDisabled,
    AccountNotFound,
    CurrentPasswordInvalid,
    DeliveryFailed,
    EmailAlreadyUsed,
    InvalidCode,
    InvalidCredentials,
    LastSignInMethod,
    PasswordInvalid,
    PhoneAlreadyUsed,
    PhoneCountryNotAllowed,
    PhoneNumberInvalid,
    PhoneSignInDisabled,
    RateLimited,
    SessionNotFound,
)
from pharma_agent.application.account.messages import (
    Locale,
    code_email,
    code_sms,
    email_changed_notice,
)
from pharma_agent.application.errors import InvalidInput
from pharma_agent.domain.access.models import Role
from pharma_agent.domain.account.codes import (
    CODE_TTL,
    code_digest,
    code_matches,
    generate_code,
)
from pharma_agent.domain.account.models import (
    CHANNEL_BY_PURPOSE,
    AccountConflict,
    AccountUser,
    Channel,
    OneTimeCode,
    OtpPurpose,
    SignInMethod,
    normalize_email,
    session_id_of,
)
from pharma_agent.domain.account.passwords import password_problem
from pharma_agent.domain.account.phone import InvalidPhoneNumber, normalize_phone
from pharma_agent.domain.account.ports import (
    AccountRepository,
    DeliveryError,
    EmailSender,
    OneTimeCodeStore,
    PasswordHasher,
    RateLimiter,
    SessionStore,
    SmsSender,
)
from pharma_agent.domain.organizations.models import Organization
from pharma_agent.domain.organizations.ports import MembershipLookup
from pharma_agent.domain.shared.clock import Clock

logger = logging.getLogger(__name__)
HOUR = 3600


class MembershipView(BaseModel):
    organization_id: uuid.UUID
    name: str
    role: Role


class AccountView(BaseModel):
    id: uuid.UUID
    email: str | None
    phone_number: str | None
    display_name: str
    is_active: bool
    is_superadmin: bool
    is_verified: bool
    email_verified: bool
    phone_verified: bool
    password_set: bool
    google_linked: bool
    memberships: list[MembershipView] = []
    phone_sign_in_enabled: bool = True

    @classmethod
    def of(
        cls,
        user: AccountUser,
        *,
        memberships: Sequence[tuple[Organization, Role]] = (),
        phone_sign_in_enabled: bool = True,
    ) -> "AccountView":
        return cls(
            id=user.id,
            email=user.email,
            phone_number=user.phone_number,
            display_name=user.display_name,
            is_active=user.is_active,
            is_superadmin=user.is_superuser,
            is_verified=user.email_verified or user.phone_verified,
            email_verified=user.email_verified,
            phone_verified=user.phone_verified,
            password_set=user.password_set,
            google_linked=user.google_linked,
            memberships=[
                MembershipView(
                    organization_id=organization.id, name=organization.name, role=role
                )
                for organization, role in memberships
            ],
            phone_sign_in_enabled=phone_sign_in_enabled,
        )


class SessionView(BaseModel):
    id: str
    created_at: datetime
    last_used_at: datetime | None
    user_agent: str
    ip_address: str
    current: bool


@dataclass(frozen=True)
class AccountPolicy:
    otp_secret: str
    allowed_sms_regions: frozenset[str] = frozenset({"VN"})
    send_cooldown_seconds: int = 60
    sends_per_destination_per_hour: int = 5
    sends_per_ip_per_hour: int = 20
    login_failures_per_window: int = 10
    login_window_seconds: int = 15 * 60
    # False when PHARMA_SMS__PROVIDER=none: phone codes are refused before any send.
    sms_enabled: bool = True


class AccountService:
    def __init__(
        self,
        *,
        accounts: AccountRepository,
        codes: OneTimeCodeStore,
        limiter: RateLimiter,
        email: EmailSender,
        sms: SmsSender,
        hasher: PasswordHasher,
        sessions: SessionStore,
        clock: Clock,
        policy: AccountPolicy,
        memberships: MembershipLookup | None = None,
    ) -> None:
        self._accounts = accounts
        self._codes = codes
        self._limiter = limiter
        self._email = email
        self._sms = sms
        self._hasher = hasher
        self._sessions = sessions
        self._clock = clock
        self._policy = policy
        self._memberships = memberships

    # Codes -------------------------------------------------------------------------

    def _send_limits(
        self, purpose: OtpPurpose, destination: str, client_ip: str | None
    ) -> list[tuple[str, int, int]]:
        policy = self._policy
        limits = [
            (
                f"otp-cooldown:{purpose.value}:{destination}",
                1,
                policy.send_cooldown_seconds,
            ),
            (f"otp-send:{destination}", policy.sends_per_destination_per_hour, HOUR),
        ]
        if client_ip is not None:
            limits.append(
                (f"otp-send-ip:{client_ip}", policy.sends_per_ip_per_hour, HOUR)
            )
        return limits

    async def _limit_send(
        self, purpose: OtpPurpose, destination: str, client_ip: str | None
    ) -> None:
        """Take one send from every limit, or none of them and raise RateLimited.

        Runs before the account is looked up, so the answer never depends on whether the
        address has an account. Each limit is taken atomically, so parallel requests
        cannot all slip under it.
        """
        taken: list[tuple[str, int]] = []
        for key, limit, window in self._send_limits(purpose, destination, client_ip):
            retry_after = await self._limiter.acquire(
                key, limit=limit, window_seconds=window
            )
            if retry_after is not None:
                for taken_key, taken_window in taken:
                    await self._limiter.release(taken_key, window_seconds=taken_window)
                raise RateLimited(retry_after)
            taken.append((key, window))

    async def _refund_send(self, purpose: OtpPurpose, destination: str) -> None:
        """Give the address its send back: a provider failure must not cost a resend.

        The IP keeps the count, so a failing provider cannot be hammered from one place.
        """
        for key, _, window in self._send_limits(purpose, destination, None):
            await self._limiter.release(key, window_seconds=window)

    async def _deliver_code(
        self,
        purpose: OtpPurpose,
        destination: str,
        user_id: uuid.UUID | None,
        locale: Locale,
    ) -> None:
        code = generate_code()
        now = self._clock.now()
        code_id = await self._codes.issue(
            purpose=purpose,
            destination=destination,
            user_id=user_id,
            digest=code_digest(self._policy.otp_secret, purpose, destination, code),
            expires_at=now + CODE_TTL,
            now=now,
        )
        try:
            if CHANNEL_BY_PURPOSE[purpose] is Channel.EMAIL:
                content = code_email(purpose, code, locale)
                await self._email.send(
                    to=destination,
                    subject=content.subject,
                    text=content.text,
                    html=content.html,
                )
            else:
                await self._sms.send(
                    to=destination, text=code_sms(purpose, code, locale)
                )
        except DeliveryError as exc:
            await self._codes.revoke(code_id, now)
            logger.warning("could not deliver a %s code: %s", purpose.value, exc)
            await self._refund_send(purpose, destination)
            raise DeliveryFailed("the code could not be delivered, try again") from exc

    async def _consume(
        self, purpose: OtpPurpose, destination: str, code: str
    ) -> OneTimeCode:
        now = self._clock.now()
        record = await self._codes.find_active(purpose, destination, now)
        if record is None:
            raise InvalidCode("the code is invalid or has expired")
        # Claim the guess first: counting only after a wrong answer lets parallel
        # guesses all pass the attempt check before any failure is recorded.
        if not await self._codes.claim_attempt(record.id):
            raise InvalidCode("the code is invalid or has expired")
        if not code_matches(self._policy.otp_secret, record, code):
            raise InvalidCode("the code is invalid or has expired")
        if not await self._codes.consume(record.id, now):
            raise InvalidCode("the code is invalid or has expired")
        return record

    def _phone(self, raw: str) -> str:
        try:
            number, region = normalize_phone(raw)
        except InvalidPhoneNumber as exc:
            raise PhoneNumberInvalid("the phone number is not valid") from exc
        if region not in self._policy.allowed_sms_regions:
            raise PhoneCountryNotAllowed("SMS cannot be sent to this country")
        return number

    @staticmethod
    def _check_password(password: str) -> None:
        problem = password_problem(password)
        if problem is not None:
            raise PasswordInvalid(problem)

    # Email verification ------------------------------------------------------------

    async def request_email_verification(
        self, email: str, *, locale: Locale, client_ip: str | None
    ) -> None:
        address = normalize_email(email)
        await self._limit_send(OtpPurpose.VERIFY_EMAIL, address, client_ip)
        user = await self._accounts.get_by_email(address)
        if user is None or user.email_verified:
            return
        await self._deliver_code(OtpPurpose.VERIFY_EMAIL, address, user.id, locale)

    async def verify_email(
        self, email: str, code: str, password: str | None, *, client_ip: str | None
    ) -> uuid.UUID:
        """Prove the inbox and sign in, which also needs the account's password.

        A code alone would let the inbox owner sign in to an account someone else
        registered with their address, keeping that person's password. Without the
        password the way in is a password reset, which replaces it.
        """
        address = normalize_email(email)
        await self.check_login_allowed(address, client_ip)
        user = await self._accounts.get_by_email(address)
        if user is not None and user.password_set:
            hashed = await self._accounts.hashed_password(user.id)
            if (
                password is None
                or hashed is None
                or not self._hasher.verify(password, hashed)
            ):
                await self.record_login_failure(address, client_ip)
                raise InvalidCredentials("the email or password is wrong")
        record = await self._consume(OtpPurpose.VERIFY_EMAIL, address, code)
        if user is None or user.id != record.user_id:
            raise InvalidCode("the code is invalid or has expired")
        if not user.is_active:
            raise AccountDisabled("this account is disabled")
        await self._accounts.mark_email_verified(user.id, self._clock.now())
        return user.id

    # Password reset ----------------------------------------------------------------

    async def request_password_reset(
        self, email: str, *, locale: Locale, client_ip: str | None
    ) -> None:
        address = normalize_email(email)
        await self._limit_send(OtpPurpose.RESET_PASSWORD, address, client_ip)
        user = await self._accounts.get_by_email(address)
        if user is None or not user.is_active:
            return
        await self._deliver_code(OtpPurpose.RESET_PASSWORD, address, user.id, locale)

    async def reset_password(self, email: str, code: str, new_password: str) -> None:
        self._check_password(new_password)
        address = normalize_email(email)
        record = await self._consume(OtpPurpose.RESET_PASSWORD, address, code)
        user = await self._accounts.get_by_email(address)
        if user is None or user.id != record.user_id:
            raise InvalidCode("the code is invalid or has expired")
        if not user.is_active:
            raise AccountDisabled("this account is disabled")
        await self._accounts.set_password(user.id, self._hasher.hash(new_password))
        if not user.email_verified:
            # The code reached this inbox, which proves the address.
            await self._accounts.mark_email_verified(user.id, self._clock.now())
        await self._sessions.delete_all(user.id)

    # Phone sign-in -----------------------------------------------------------------

    async def request_phone_login(
        self, phone: str, *, locale: Locale, client_ip: str | None
    ) -> None:
        self._require_sms()
        number = self._phone(phone)
        await self._limit_send(OtpPurpose.PHONE_LOGIN, number, client_ip)
        user = await self._accounts.get_by_phone(number)
        await self._deliver_code(
            OtpPurpose.PHONE_LOGIN, number, None if user is None else user.id, locale
        )

    async def login_with_phone(self, phone: str, code: str) -> uuid.UUID:
        number = self._phone(phone)
        await self._consume(OtpPurpose.PHONE_LOGIN, number, code)
        user = await self._accounts.get_by_phone(number)
        if user is None:
            try:
                user = await self._accounts.create_phone_user(
                    phone=number,
                    hashed_password=self._hasher.hash(secrets.token_urlsafe(32)),
                    now=self._clock.now(),
                )
            except AccountConflict:
                # Another request created it first; sign that account in.
                user = await self._accounts.get_by_phone(number)
                if user is None:
                    raise
        if not user.is_active:
            raise AccountDisabled("this account is disabled")
        return user.id

    # Password sign-in throttle (called by the fastapi-users UserManager) ----------

    def _login_keys(self, email: str, client_ip: str | None) -> list[str]:
        keys = [f"login:{normalize_email(email)}"]
        if client_ip is not None:
            keys.append(f"login-ip:{client_ip}")
        return keys

    async def check_login_allowed(self, email: str, client_ip: str | None) -> None:
        for key in self._login_keys(email, client_ip):
            retry_after = await self._limiter.check(
                key,
                limit=self._policy.login_failures_per_window,
                window_seconds=self._policy.login_window_seconds,
            )
            if retry_after is not None:
                raise RateLimited(retry_after)

    async def record_login_failure(self, email: str, client_ip: str | None) -> None:
        for key in self._login_keys(email, client_ip):
            await self._limiter.hit(
                key,
                limit=self._policy.login_failures_per_window,
                window_seconds=self._policy.login_window_seconds,
            )

    # Profile and contact changes ----------------------------------------------------

    async def _require(self, user_id: uuid.UUID) -> AccountUser:
        user = await self._accounts.get(user_id)
        if user is None:
            raise AccountNotFound(str(user_id))
        return user

    async def get_account(self, user_id: uuid.UUID) -> AccountView:
        user = await self._require(user_id)
        memberships = (
            []
            if self._memberships is None
            else await self._memberships.list_for_user(user_id)
        )
        return AccountView.of(
            user,
            memberships=memberships,
            phone_sign_in_enabled=self._policy.sms_enabled,
        )

    def _require_sms(self) -> None:
        if not self._policy.sms_enabled:
            raise PhoneSignInDisabled("phone sign-in is turned off")

    async def update_profile(
        self, user_id: uuid.UUID, display_name: str
    ) -> AccountView:
        await self._require(user_id)
        await self._accounts.update_display_name(user_id, display_name.strip())
        return await self.get_account(user_id)

    async def request_email_change(
        self, user_id: uuid.UUID, email: str, *, locale: Locale, client_ip: str | None
    ) -> None:
        user = await self._require(user_id)
        address = normalize_email(email)
        # Limit first: the 409 below tells a signed-in user which addresses have accounts.
        await self._limit_send(OtpPurpose.CHANGE_EMAIL, address, client_ip)
        owner = await self._accounts.get_by_email(address)
        if owner is not None and owner.id != user_id:
            raise EmailAlreadyUsed("this email belongs to another account")
        if user.email == address and user.email_verified:
            raise InvalidInput("this is already your email")
        await self._deliver_code(OtpPurpose.CHANGE_EMAIL, address, user_id, locale)

    async def confirm_email_change(
        self, user_id: uuid.UUID, email: str, code: str, *, locale: Locale
    ) -> AccountView:
        address = normalize_email(email)
        # Check before the code is used: a refusal here must leave it for a retry.
        owner = await self._accounts.get_by_email(address)
        if owner is not None and owner.id != user_id:
            raise EmailAlreadyUsed("this email belongs to another account")
        record = await self._consume(OtpPurpose.CHANGE_EMAIL, address, code)
        if record.user_id != user_id:
            raise InvalidCode("the code is invalid or has expired")
        user = await self._require(user_id)
        try:
            await self._accounts.set_email(user_id, address, self._clock.now())
        except AccountConflict as exc:
            raise EmailAlreadyUsed("this email belongs to another account") from exc
        if user.email is not None and user.email != address:
            notice = email_changed_notice(address, locale)
            try:
                await self._email.send(
                    to=user.email,
                    subject=notice.subject,
                    text=notice.text,
                    html=notice.html,
                )
            except DeliveryError as exc:
                logger.warning("could not notify the previous email: %s", exc)
        return await self.get_account(user_id)

    async def request_phone_change(
        self, user_id: uuid.UUID, phone: str, *, locale: Locale, client_ip: str | None
    ) -> None:
        await self._require(user_id)
        self._require_sms()
        number = self._phone(phone)
        await self._limit_send(OtpPurpose.CHANGE_PHONE, number, client_ip)
        owner = await self._accounts.get_by_phone(number)
        if owner is not None and owner.id != user_id:
            raise PhoneAlreadyUsed("this phone number belongs to another account")
        await self._deliver_code(OtpPurpose.CHANGE_PHONE, number, user_id, locale)

    async def confirm_phone_change(
        self, user_id: uuid.UUID, phone: str, code: str
    ) -> AccountView:
        number = self._phone(phone)
        owner = await self._accounts.get_by_phone(number)
        if owner is not None and owner.id != user_id:
            raise PhoneAlreadyUsed("this phone number belongs to another account")
        record = await self._consume(OtpPurpose.CHANGE_PHONE, number, code)
        if record.user_id != user_id:
            raise InvalidCode("the code is invalid or has expired")
        try:
            await self._accounts.set_phone(user_id, number, self._clock.now())
        except AccountConflict as exc:
            raise PhoneAlreadyUsed(
                "this phone number belongs to another account"
            ) from exc
        return await self.get_account(user_id)

    async def change_password(
        self, user_id: uuid.UUID, *, current_password: str | None, new_password: str
    ) -> None:
        self._check_password(new_password)
        user = await self._require(user_id)
        if user.password_set:
            hashed = await self._accounts.hashed_password(user_id)
            if (
                current_password is None
                or hashed is None
                or not self._hasher.verify(current_password, hashed)
            ):
                raise CurrentPasswordInvalid("the current password is wrong")
        await self._accounts.set_password(user_id, self._hasher.hash(new_password))

    async def unlink_google(self, user_id: uuid.UUID) -> AccountView:
        user = await self._require(user_id)
        if user.google_linked:
            if not user.sign_in_methods() - {SignInMethod.GOOGLE}:
                raise LastSignInMethod(
                    "add another way to sign in before removing Google"
                )
            await self._accounts.unlink_oauth(user_id, SignInMethod.GOOGLE.value)
        return await self.get_account(user_id)

    # Sessions -------------------------------------------------------------------------

    async def list_sessions(
        self, user_id: uuid.UUID, current_token: str | None
    ) -> list[SessionView]:
        return [
            SessionView(
                id=session_id_of(record.token),
                created_at=record.created_at,
                last_used_at=record.last_used_at,
                user_agent=record.user_agent,
                ip_address=record.ip_address,
                current=current_token is not None
                and hmac.compare_digest(record.token, current_token),
            )
            for record in await self._sessions.for_user(user_id)
        ]

    async def revoke_session(self, user_id: uuid.UUID, session_id: str) -> None:
        for record in await self._sessions.for_user(user_id):
            if hmac.compare_digest(session_id_of(record.token), session_id):
                await self._sessions.delete(user_id, record.token)
                return
        raise SessionNotFound(session_id)

    async def revoke_other_sessions(
        self, user_id: uuid.UUID, current_token: str | None
    ) -> int:
        return await self._sessions.delete_all(user_id, keep=current_token)
