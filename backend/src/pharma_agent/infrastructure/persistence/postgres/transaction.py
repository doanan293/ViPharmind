"""TransactionFactory over SQLAlchemy: the transaction handle is the AsyncSession."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.domain.shared.transaction import Transaction


class PostgresTransactionFactory:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[Transaction]:
        async with self._sessions.begin() as session:
            yield session


def session_of(tx: Transaction) -> AsyncSession:
    """The session behind a handle from PostgresTransactionFactory."""
    if not isinstance(tx, AsyncSession):
        raise TypeError(f"expected a Postgres transaction, got {type(tx).__name__}")
    return tx
