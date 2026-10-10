import uuid
from datetime import datetime
from typing import Protocol

from pharma_agent.domain.audit.models import AuditEvent
from pharma_agent.domain.shared.transaction import Transaction

type Cursor = tuple[datetime, str]


class AuditLog(Protocol):
    async def record(self, event: AuditEvent, tx: Transaction) -> None:
        """Append inside `tx`, so the event commits with the change it describes."""
        ...

    async def for_organization(
        self, organization_id: uuid.UUID, *, limit: int, cursor: Cursor | None
    ) -> list[AuditEvent]:
        """Newest first, keyset on (occurred_at, id)."""
        ...

    async def for_user(
        self, user_id: uuid.UUID, *, limit: int, cursor: Cursor | None
    ) -> list[AuditEvent]:
        """Events whose subject is the user."""
        ...

    async def all(self, *, limit: int, cursor: Cursor | None) -> list[AuditEvent]: ...
