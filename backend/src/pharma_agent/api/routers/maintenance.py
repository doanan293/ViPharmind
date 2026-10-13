"""Daily upkeep that Vercel Cron calls (see backend/vercel.json); not in the OpenAPI schema."""

from fastapi import APIRouter

from pharma_agent.api.deps import (
    ContainerDep,
    CronCaller,
    MaintenanceReport,
    require_maintenance,
)


def build_maintenance_router() -> APIRouter:
    router = APIRouter(prefix="/maintenance", include_in_schema=False)

    # Vercel Cron only sends GET requests.
    @router.get("/daily", name="maintenance:daily")
    async def run_daily_maintenance(
        _caller: CronCaller, container: ContainerDep
    ) -> MaintenanceReport:
        return await require_maintenance(container).run()

    return router
