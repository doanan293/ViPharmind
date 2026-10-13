"""Daily upkeep that Vercel Cron triggers through the API.

It runs the same code as `pharma-agent cleanup-sessions` and `pharma-agent corpus
purge-deleted`, inside one function call, so the purge gets a time budget well under the
function's maxDuration (300 s); collections it does not reach wait for the next day.
"""

from datetime import timedelta

from pydantic import BaseModel

from pharma_agent.application.corpus.collections import CollectionService
from pharma_agent.infrastructure.auth.session_cleanup import clean_account_tables

PURGE_BUDGET = timedelta(seconds=180)


class MaintenanceReport(BaseModel):
    sessions_deleted: int
    codes_deleted: int
    rate_limit_buckets_deleted: int
    collections_purged: int


class Maintenance:
    def __init__(
        self,
        *,
        conninfo: str,
        session_lifetime_seconds: int,
        collections: CollectionService,
        purge_budget: timedelta = PURGE_BUDGET,
    ) -> None:
        self._conninfo = conninfo
        self._session_lifetime_seconds = session_lifetime_seconds
        self._collections = collections
        self._purge_budget = purge_budget

    async def run(self) -> MaintenanceReport:
        accounts = await clean_account_tables(
            self._conninfo, session_lifetime_seconds=self._session_lifetime_seconds
        )
        purged = await self._collections.purge_deleted(budget=self._purge_budget)
        return MaintenanceReport(
            sessions_deleted=accounts.sessions,
            codes_deleted=accounts.codes,
            rate_limit_buckets_deleted=accounts.rate_limit_buckets,
            collections_purged=purged,
        )
