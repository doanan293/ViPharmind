"""AccountRepository over the fastapi-users `user` and `oauth_account` tables."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Select,
    Uuid,
    delete,
    func,
    insert,
    literal,
    or_,
    select,
    tuple_,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.domain.account.models import AccountConflict, AccountUser
from pharma_agent.domain.shared.transaction import Transaction
from pharma_agent.infrastructure.persistence.postgres.tables import (
    OAuthAccountTable,
    UserTable,
)
from pharma_agent.infrastructure.persistence.postgres.transaction import session_of

# fastapi-users declares these columns with plain Python types for type checkers, so the
# SQL expressions below use the table's own columns.
_user = UserTable.__table__.c
_oauth = OAuthAccountTable.__table__.c


def _account(row: UserTable) -> AccountUser:
    return AccountUser(
        id=row.id,
        # Phone-only accounts store NULL (see UserTable).
        email=row.email or None,
        phone_number=row.phone_number,
        display_name=row.display_name,
        email_verified=row.email_verified,
        phone_verified=row.phone_verified,
        password_set=row.password_set,
        google_linked=row.google_linked,
        is_active=row.is_active,
        is_superuser=row.is_superuser,
        text_quota_bytes=row.text_quota_bytes,
        collection_quota=row.collection_quota,
        created_at=row.created_at,
    )


class PostgresAccountRepository:
    """AccountRepository over `user` and `oauth_account`; each write commits on its own."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Read and write through sessions from `sessions`."""
        self._sessions = sessions

    async def _one(self, statement: Select[tuple[UserTable]]) -> AccountUser | None:
        async with self._sessions() as session:
            row = (await session.execute(statement)).unique().scalar_one_or_none()
        return None if row is None else _account(row)

    async def get(self, user_id: uuid.UUID) -> AccountUser | None:
        """The account, or None if there is no such id."""
        return await self._one(select(UserTable).where(_user.id == user_id))

    async def get_by_email(self, email: str) -> AccountUser | None:
        """The account with this email, ignoring case."""
        return await self._one(
            select(UserTable).where(func.lower(_user.email) == email.lower())
        )

    async def get_by_phone(self, phone: str) -> AccountUser | None:
        """The account with exactly this phone number."""
        return await self._one(select(UserTable).where(UserTable.phone_number == phone))

    async def create_phone_user(
        self, *, phone: str, hashed_password: str, now: datetime
    ) -> AccountUser:
        """Create a verified phone-only account whose password is not yet user-chosen.

        Raises:
            AccountConflict: The phone number is taken.
        """
        user_id = uuid.uuid4()
        try:
            async with self._sessions.begin() as session:
                await session.execute(
                    insert(UserTable).values(
                        id=user_id,
                        email=None,
                        phone_number=phone,
                        phone_verified_at=now,
                        hashed_password=hashed_password,
                        password_set=False,
                        is_active=True,
                        is_superuser=False,
                        is_verified=True,
                    )
                )
        except IntegrityError as exc:
            raise AccountConflict(phone) from exc
        user = await self.get(user_id)
        if user is None:
            raise AccountConflict(phone)
        return user

    async def _update(self, user_id: uuid.UUID, values: dict[str, Any]) -> None:
        try:
            async with self._sessions.begin() as session:
                await session.execute(
                    update(UserTable).where(_user.id == user_id).values(**values)
                )
        except IntegrityError as exc:
            raise AccountConflict(str(user_id)) from exc

    async def mark_email_verified(self, user_id: uuid.UUID, now: datetime) -> None:
        """Mark the account's email, and so the account, verified at `now`."""
        await self._update(user_id, {"email_verified_at": now, "is_verified": True})

    async def set_email(self, user_id: uuid.UUID, email: str, now: datetime) -> None:
        """Set a verified email.

        Raises:
            AccountConflict: Another account has the email.
        """
        await self._update(
            user_id, {"email": email, "email_verified_at": now, "is_verified": True}
        )

    async def set_phone(self, user_id: uuid.UUID, phone: str, now: datetime) -> None:
        """Set a verified phone number.

        Raises:
            AccountConflict: Another account has the number.
        """
        await self._update(
            user_id,
            {"phone_number": phone, "phone_verified_at": now, "is_verified": True},
        )

    async def set_password(self, user_id: uuid.UUID, hashed_password: str) -> None:
        """Store the hash and mark the password as chosen by the user."""
        await self._update(
            user_id, {"hashed_password": hashed_password, "password_set": True}
        )

    async def hashed_password(self, user_id: uuid.UUID) -> str | None:
        """The stored password hash, or None if the account does not exist."""
        async with self._sessions() as session:
            return (
                await session.execute(
                    select(_user.hashed_password).where(_user.id == user_id)
                )
            ).scalar_one_or_none()

    async def unlink_oauth(self, user_id: uuid.UUID, oauth_name: str) -> None:
        """Delete the account's link to the `oauth_name` provider, if any."""
        async with self._sessions.begin() as session:
            await session.execute(
                delete(OAuthAccountTable).where(
                    _oauth.user_id == user_id,
                    _oauth.oauth_name == oauth_name,
                )
            )

    async def update_display_name(self, user_id: uuid.UUID, display_name: str) -> None:
        """Replace the account's display name."""
        await self._update(user_id, {"display_name": display_name})


class PostgresAccountAdmin:
    """AccountAdmin: account changes the superadmin console makes in a transaction."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Read through sessions from `sessions`; writes use the caller's transaction."""
        self._sessions = sessions

    async def get(self, user_id: uuid.UUID) -> AccountUser | None:
        """The account, or None if there is no such id."""
        async with self._sessions() as session:
            row = (
                (await session.execute(select(UserTable).where(_user.id == user_id)))
                .unique()
                .scalar_one_or_none()
            )
        return None if row is None else _account(row)

    async def search(
        self,
        query: str | None,
        *,
        limit: int,
        cursor: tuple[datetime, str] | None,
    ) -> list[AccountUser]:
        """Accounts newest first, keyset on (created_at, id).

        A non-empty `query` matches a substring of the email, phone number or display name,
        ignoring case.
        """
        statement = select(UserTable)
        if query:
            pattern = f"%{query}%"
            statement = statement.where(
                or_(
                    _user.email.ilike(pattern),
                    _user.phone_number.ilike(pattern),
                    _user.display_name.ilike(pattern),
                )
            )
        if cursor is not None:
            at, key = cursor
            statement = statement.where(
                tuple_(_user.created_at, _user.id)
                < tuple_(
                    literal(at, DateTime(timezone=True)),
                    literal(uuid.UUID(hex=key), Uuid()),
                )
            )
        statement = statement.order_by(_user.created_at.desc(), _user.id.desc()).limit(
            limit
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).unique().scalars().all()
        return [_account(row) for row in rows]

    async def set_active(
        self, user_id: uuid.UUID, active: bool, tx: Transaction
    ) -> None:
        """Activate or deactivate the account inside `tx`."""
        await session_of(tx).execute(
            update(UserTable)
            .where(_user.id == user_id)
            .values({_user.is_active: active})
        )

    async def set_quotas(
        self,
        user_id: uuid.UUID,
        *,
        text_quota_bytes: int | None,
        collection_quota: int | None,
        tx: Transaction,
    ) -> None:
        """Overwrite both quota overrides inside `tx`; None clears an override."""
        await session_of(tx).execute(
            update(UserTable)
            .where(_user.id == user_id)
            .values(
                text_quota_bytes=text_quota_bytes, collection_quota=collection_quota
            )
        )
