"""fastapi-users wiring: cookie sessions, registration, current user and Google OAuth.

Sessions are backed by the access_tokens table.

Every session is a database row, so logging out or revoking a session takes effect at
once. PHARMA_AUTH__JWT_SECRET only signs the short-lived OAuth state and the user
manager's reset and verification tokens; there is no JWT login.
"""

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, override

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users import (
    BaseUserManager,
    FastAPIUsers,
    UUIDIDMixin,
    exceptions,
    schemas,
)
from fastapi_users.authentication import AuthenticationBackend, CookieTransport
from fastapi_users.authentication.strategy.db import DatabaseStrategy
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from httpx_oauth.clients.google import GoogleOAuth2
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.application.account.errors import DeliveryFailed, RateLimited
from pharma_agent.application.account.messages import locale_from_accept_language
from pharma_agent.application.account.service import AccountService
from pharma_agent.domain.account.passwords import password_problem
from pharma_agent.infrastructure.auth.client_ip import request_client_ip
from pharma_agent.infrastructure.persistence.postgres.tables import (
    AccessTokenTable,
    OAuthAccountTable,
    UserTable,
)
from pharma_agent.infrastructure.settings import AuthSettings

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "pharma_session"
# `last_used_at` is written at most this often, not on every authenticated request.
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)

SessionFactoryResolver = Callable[[Request], async_sessionmaker[AsyncSession]]
UserDatabase = SQLAlchemyUserDatabase[UserTable, uuid.UUID]
AccessTokenDatabase = SQLAlchemyAccessTokenDatabase[AccessTokenTable]
SessionLogin = Callable[[uuid.UUID], Awaitable[Response]]


class UserRead(schemas.BaseUser[uuid.UUID]):
    """Registration and Google association responses; /users/me returns AccountView."""

    display_name: str = ""


class UserCreate(schemas.BaseUserCreate):
    """Registration request body: the fastapi-users fields plus a display name."""

    display_name: str = ""


def _client_ip(request: Request | None) -> str | None:
    return None if request is None else request_client_ip(request)


def _already_exists() -> HTTPException:
    return HTTPException(status_code=400, detail="OAUTH_USER_ALREADY_EXISTS")


class UserManager(UUIDIDMixin, BaseUserManager[UserTable, uuid.UUID]):
    """User manager with the app's password, login-limit and OAuth linking rules.

    Without an AccountService, login is not rate limited and no verification code is
    sent after registration.
    """

    def __init__(
        self,
        user_db: UserDatabase,
        secret: str,
        *,
        account: AccountService | None = None,
        request: Request | None = None,
    ) -> None:
        """Use `secret` for reset and verification tokens.

        `account` adds login limits and verification emails; `request` supplies the
        client IP and locale.
        """
        super().__init__(user_db)
        self.reset_password_token_secret = secret
        self.verification_token_secret = secret
        self._account = account
        self._request = request

    @override
    async def validate_password(
        self, password: str, user: schemas.UC | UserTable
    ) -> None:
        """Reject a password that breaks the domain password rules.

        Raises:
            InvalidPasswordException: With the rule's reason.
        """
        problem = password_problem(password)
        if problem is not None:
            raise exceptions.InvalidPasswordException(reason=problem)

    @override
    async def authenticate(
        self, credentials: OAuth2PasswordRequestForm
    ) -> UserTable | None:
        """Check email and password, counting failures per account and client IP.

        Returns None on wrong credentials.

        Raises:
            HTTPException: 403 EMAIL_NOT_VERIFIED when the email is not verified yet.
            RateLimited: When the AccountService refuses further attempts.
        """
        ip = _client_ip(self._request)
        if self._account is not None:
            await self._account.check_login_allowed(credentials.username, ip)
        user = await super().authenticate(credentials)
        if user is None:
            if self._account is not None:
                await self._account.record_login_failure(credentials.username, ip)
            return None
        if user.email_verified_at is None:
            raise HTTPException(status_code=403, detail="EMAIL_NOT_VERIFIED")
        return user

    @override
    async def on_after_register(
        self, user: UserTable, request: Request | None = None
    ) -> None:
        """Send an email verification code to the new account.

        A rate limit or delivery failure is only logged; the user can ask again later.
        """
        if self._account is None or not user.email:
            return
        locale = locale_from_accept_language(
            None if request is None else request.headers.get("accept-language")
        )
        try:
            await self._account.request_email_verification(
                user.email, locale=locale, client_ip=_client_ip(request)
            )
        except (RateLimited, DeliveryFailed) as exc:
            # The user can ask for the code again from the verification step.
            logger.warning("no verification code after registration: %s", exc)

    @override
    async def oauth_callback(
        self,
        oauth_name: str,
        access_token: str,
        account_id: str,
        account_email: str,
        expires_at: int | None = None,
        refresh_token: str | None = None,
        request: Request | None = None,
        *,
        associate_by_email: bool = False,
        is_verified_by_default: bool = False,
    ) -> UserTable:
        """Sign in with Google, creating or linking the account as fastapi-users does.

        An account created here has its email verified and no password set.

        Raises:
            HTTPException: 400 OAUTH_USER_ALREADY_EXISTS when the email belongs to an
                unverified registration, which linking would hand to the Google user.
        """
        created = False
        try:
            await self.get_by_oauth_account(oauth_name, account_id)
        except exceptions.UserNotExists:
            existing = await self.user_db.get_by_email(account_email)
            if existing is not None and existing.email_verified_at is None:
                # Linking would hand an unverified registration to whoever signs in
                # with Google, so the registration's creator would keep its password.
                raise _already_exists() from None
            created = existing is None
        user = await super().oauth_callback(
            oauth_name,
            access_token,
            account_id,
            account_email,
            expires_at,
            refresh_token,
            request,
            associate_by_email=associate_by_email,
            is_verified_by_default=is_verified_by_default,
        )
        if created:
            user = await self.user_db.update(
                user, {"email_verified_at": datetime.now(UTC), "password_set": False}
            )
        return user

    @override
    async def oauth_associate_callback(
        self,
        user: UserTable,
        oauth_name: str,
        access_token: str,
        account_id: str,
        account_email: str,
        expires_at: int | None = None,
        refresh_token: str | None = None,
        request: Request | None = None,
    ) -> UserTable:
        """Link a Google account to the signed-in `user`.

        An account without an email takes the Google address as its verified email.

        Raises:
            HTTPException: 400 OAUTH_USER_ALREADY_EXISTS when the Google account or its
                email already belongs to another user.
        """
        try:
            owner = await self.get_by_oauth_account(oauth_name, account_id)
        except exceptions.UserNotExists:
            owner = None
        if owner is not None and owner.id != user.id:
            raise _already_exists()
        adopt_email = not user.email
        if adopt_email:
            other = await self.user_db.get_by_email(account_email)
            if other is not None and other.id != user.id:
                raise _already_exists()
        user = await super().oauth_associate_callback(
            user,
            oauth_name,
            access_token,
            account_id,
            account_email,
            expires_at,
            refresh_token,
            request,
        )
        if adopt_email:
            # Google verified this address; a phone-only account takes it as its email.
            user = await self.user_db.update(
                user,
                {
                    "email": account_email.lower(),
                    "email_verified_at": datetime.now(UTC),
                    "is_verified": True,
                },
            )
        return user


class TrackedDatabaseStrategy(DatabaseStrategy[UserTable, uuid.UUID, AccessTokenTable]):
    """DatabaseStrategy that records the device and last use of each session."""

    def __init__(
        self,
        database: AccessTokenDatabase,
        lifetime_seconds: int,
        *,
        user_agent: str,
        ip_address: str,
    ) -> None:
        """Record `user_agent` and `ip_address`, cut to column size, on new sessions."""
        super().__init__(database, lifetime_seconds=lifetime_seconds)
        self._user_agent = user_agent[:255]
        self._ip_address = ip_address[:45]

    @override
    def _create_access_token_dict(self, user: UserTable) -> dict[str, Any]:
        values = super()._create_access_token_dict(user)
        values.update(
            user_agent=self._user_agent,
            ip_address=self._ip_address,
            last_used_at=datetime.now(UTC),
        )
        return values

    @override
    async def read_token(
        self, token: str | None, user_manager: BaseUserManager[UserTable, uuid.UUID]
    ) -> UserTable | None:
        """The user of a live session token; None for a missing, expired or orphan one.

        Updates the session's `last_used_at` when older than SESSION_TOUCH_INTERVAL.
        """
        if token is None:
            return None
        now = datetime.now(UTC)
        max_age = (
            now - timedelta(seconds=self.lifetime_seconds)
            if self.lifetime_seconds
            else None
        )
        access_token = await self.database.get_by_token(token, max_age)
        if access_token is None:
            return None
        try:
            user = await user_manager.get(user_manager.parse_id(access_token.user_id))
        except (exceptions.UserNotExists, exceptions.InvalidID):
            return None
        last_used = access_token.last_used_at
        if last_used is None or now - last_used > SESSION_TOUCH_INTERVAL:
            await self.database.update(access_token, {"last_used_at": now})
        return user


@dataclass(frozen=True)
class Auth:
    """The fastapi-users objects and settings the API routers need."""

    users: FastAPIUsers[UserTable, uuid.UUID]
    cookie_backend: AuthenticationBackend[UserTable, uuid.UUID]
    current_active_user: Callable[..., Any]
    login_session: Callable[..., Any]
    google: GoogleOAuth2 | None
    secret: str
    frontend_url: str
    cookie_secure: bool


def build_auth(
    settings: AuthSettings, resolve_sessions: SessionFactoryResolver
) -> Auth:
    """Wire fastapi-users: cookie sessions, the user manager and optional Google OAuth.

    `resolve_sessions` gives the session factory of the app serving a request.

    Raises:
        ValueError: When PHARMA_AUTH__JWT_SECRET is not set.
    """
    secret = settings.require_jwt_secret()

    async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
        async with resolve_sessions(request)() as session:
            yield session

    async def get_user_db(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> AsyncIterator[UserDatabase]:
        yield SQLAlchemyUserDatabase(session, UserTable, OAuthAccountTable)

    async def get_access_token_db(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> AsyncIterator[AccessTokenDatabase]:
        yield SQLAlchemyAccessTokenDatabase(session, AccessTokenTable)

    async def get_user_manager(
        request: Request,
        user_db: Annotated[UserDatabase, Depends(get_user_db)],
    ) -> AsyncIterator[UserManager]:
        container = getattr(request.app.state, "container", None)
        account = getattr(container, "account", None)
        yield UserManager(
            user_db,
            secret,
            account=account if isinstance(account, AccountService) else None,
            request=request,
        )

    def get_session_strategy(
        request: Request,
        access_tokens: Annotated[AccessTokenDatabase, Depends(get_access_token_db)],
    ) -> TrackedDatabaseStrategy:
        return TrackedDatabaseStrategy(
            access_tokens,
            settings.session_lifetime_seconds,
            user_agent=request.headers.get("user-agent", ""),
            ip_address=_client_ip(request) or "",
        )

    cookie_backend = AuthenticationBackend(
        name="cookie",
        transport=CookieTransport(
            cookie_name=SESSION_COOKIE_NAME,
            cookie_max_age=settings.session_lifetime_seconds,
            cookie_secure=settings.cookie_secure,
            cookie_httponly=True,
            cookie_samesite="lax",
        ),
        get_strategy=get_session_strategy,
    )

    async def get_session_login(
        user_manager: Annotated[UserManager, Depends(get_user_manager)],
        strategy: Annotated[TrackedDatabaseStrategy, Depends(get_session_strategy)],
    ) -> SessionLogin:
        async def login(user_id: uuid.UUID) -> Response:
            user = await user_manager.get(user_id)
            return await cookie_backend.login(strategy, user)

        return login

    # The types of FastAPIUsers come from typings/fastapi_users-stubs (see its docstring).
    users = FastAPIUsers[UserTable, uuid.UUID](
        get_user_manager,
        [cookie_backend],
    )
    google = None
    if (
        settings.google_enabled
        and settings.google_client_id
        and settings.google_client_secret
    ):
        google = GoogleOAuth2(
            settings.google_client_id, settings.google_client_secret.get_secret_value()
        )
    return Auth(
        users=users,
        cookie_backend=cookie_backend,
        current_active_user=users.current_user(active=True),
        login_session=get_session_login,
        google=google,
        secret=secret,
        frontend_url=settings.frontend_url,
        cookie_secure=settings.cookie_secure,
    )


def include_auth_routes(router: APIRouter, auth: Auth) -> None:
    """Mount cookie login, registration and, when enabled, the Google OAuth routes."""
    router.include_router(
        auth.users.get_auth_router(auth.cookie_backend),
        prefix="/auth/cookie",
        tags=["auth"],
    )
    router.include_router(
        auth.users.get_register_router(UserRead, UserCreate),
        prefix="/auth",
        tags=["auth"],
    )
    if auth.google is not None:
        router.include_router(
            auth.users.get_oauth_router(
                auth.google,
                auth.cookie_backend,
                auth.secret,
                redirect_url=f"{auth.frontend_url.rstrip('/')}/auth/google/callback",
                associate_by_email=True,
                is_verified_by_default=True,
                csrf_token_cookie_secure=auth.cookie_secure,
            ),
            prefix="/auth/google",
            tags=["auth"],
        )
        router.include_router(
            auth.users.get_oauth_associate_router(
                auth.google,
                UserRead,
                auth.secret,
                redirect_url=f"{auth.frontend_url.rstrip('/')}/auth/google/link-callback",
                csrf_token_cookie_secure=auth.cookie_secure,
            ),
            prefix="/auth/google/associate",
            tags=["auth"],
        )
