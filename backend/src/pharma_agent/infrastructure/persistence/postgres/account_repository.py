"""AccountRepository over the fastapi-users `user` and `oauth_account` tables."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.domain.account.models import AccountConflict, AccountUser
from pharma_agent.infrastructure.persistence.postgres.tables import (
    OAuthAccountTable,
    UserTable,
)

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
    )


class PostgresAccountRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def _one(self, statement: Select[tuple[UserTable]]) -> AccountUser | None:
        async with self._sessions() as session:
            row = (await session.execute(statement)).unique().scalar_one_or_none()
        return None if row is None else _account(row)

    async def get(self, user_id: uuid.UUID) -> AccountUser | None:
        return await self._one(select(UserTable).where(_user.id == user_id))

    async def get_by_email(self, email: str) -> AccountUser | None:
        return await self._one(
            select(UserTable).where(func.lower(_user.email) == email.lower())
        )

    async def get_by_phone(self, phone: str) -> AccountUser | None:
        return await self._one(select(UserTable).where(UserTable.phone_number == phone))

    async def create_phone_user(
        self, *, phone: str, hashed_password: str, now: datetime
    ) -> AccountUser:
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
        await self._update(user_id, {"email_verified_at": now, "is_verified": True})

    async def set_email(self, user_id: uuid.UUID, email: str, now: datetime) -> None:
        await self._update(
            user_id, {"email": email, "email_verified_at": now, "is_verified": True}
        )

    async def set_phone(self, user_id: uuid.UUID, phone: str, now: datetime) -> None:
        await self._update(
            user_id,
            {"phone_number": phone, "phone_verified_at": now, "is_verified": True},
        )

    async def set_password(self, user_id: uuid.UUID, hashed_password: str) -> None:
        await self._update(
            user_id, {"hashed_password": hashed_password, "password_set": True}
        )

    async def hashed_password(self, user_id: uuid.UUID) -> str | None:
        async with self._sessions() as session:
            return (
                await session.execute(
                    select(_user.hashed_password).where(_user.id == user_id)
                )
            ).scalar_one_or_none()

    async def unlink_oauth(self, user_id: uuid.UUID, oauth_name: str) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                delete(OAuthAccountTable).where(
                    _oauth.user_id == user_id,
                    _oauth.oauth_name == oauth_name,
                )
            )

    async def update_display_name(self, user_id: uuid.UUID, display_name: str) -> None:
        await self._update(user_id, {"display_name": display_name})
