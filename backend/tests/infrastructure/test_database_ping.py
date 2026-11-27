import asyncio

import pytest

from pharma_agent.infrastructure.persistence.postgres.database import Database


class _Broken:
    """An engine whose connect fails with an error that is neither SQLAlchemy's nor an OSError."""

    def connect(self) -> object:
        raise RuntimeError("driver blew up")


def test_ping_reports_false_for_any_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database("postgresql+psycopg://user:pw@127.0.0.1:1/none")
    monkeypatch.setattr(database, "engine", _Broken())
    assert asyncio.run(database.ping()) is False
