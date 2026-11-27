from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class Database:
    """The async engine and session factory for one Postgres DSN."""

    def __init__(self, dsn: str, *, pool_size: int = 10, echo: bool = False) -> None:
        """Create a pre-pinging engine and a session factory that keeps objects after commit."""
        self.engine: AsyncEngine = create_async_engine(
            dsn, pool_size=pool_size, echo=echo, pool_pre_ping=True
        )
        self.sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine, expire_on_commit=False
        )

    async def ping(self) -> bool:
        """Whether a `SELECT 1` succeeds; a database or connection error counts as False."""
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except (SQLAlchemyError, OSError):
            return False
        return True

    async def dispose(self) -> None:
        """Close every pooled connection."""
        await self.engine.dispose()
