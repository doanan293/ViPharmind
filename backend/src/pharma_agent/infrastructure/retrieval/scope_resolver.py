"""What a user may search right now, read from Postgres at every turn (spec §2)."""

import uuid
from collections.abc import Sequence

from pharma_agent.application.access.service import ActorResolver
from pharma_agent.domain.corpus.ports import CollectionRepository
from pharma_agent.domain.retrieval.models import ReleaseScope


class PostgresScopeResolver:
    """Visible collections, narrowed to the conversation's choice, mapped to the
    current release of each. Leaving an organization or a deletion applies at once."""

    def __init__(
        self, actors: ActorResolver, collections: CollectionRepository
    ) -> None:
        self._actors = actors
        self._collections = collections

    async def resolve(
        self, *, user_id: str, requested: Sequence[uuid.UUID] | None
    ) -> ReleaseScope:
        actor = await self._actors.resolve(uuid.UUID(hex=user_id))
        visible = [c.id for c in await self._collections.visible_for(actor)]
        if requested is not None:
            wanted = set(requested)
            visible = [
                collection_id for collection_id in visible if collection_id in wanted
            ]
        return await self._collections.current_releases(visible)
