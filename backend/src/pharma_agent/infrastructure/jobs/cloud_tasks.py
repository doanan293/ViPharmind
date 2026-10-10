"""Queue jobs on Google Cloud Tasks, which calls the backend back to run them."""

import uuid
from typing import Any, Protocol

from google.cloud import tasks_v2

from pharma_agent.infrastructure.settings import JobsSettings


class TasksClient(Protocol):
    def queue_path(self, project: str, location: str, queue: str) -> str: ...

    async def create_task(self, *, parent: str, task: dict[str, Any]) -> Any: ...


class _GoogleTasksClient:
    """The real client behind the narrow TasksClient interface the dispatcher uses."""

    def __init__(self) -> None:
        self._client = tasks_v2.CloudTasksAsyncClient()

    def queue_path(self, project: str, location: str, queue: str) -> str:
        return self._client.queue_path(project, location, queue)

    async def create_task(self, *, parent: str, task: dict[str, Any]) -> Any:
        return await self._client.create_task(parent=parent, task=tasks_v2.Task(task))


class CloudTasksDispatcher:
    def __init__(
        self, settings: JobsSettings, *, client: TasksClient | None = None
    ) -> None:
        missing = [
            name
            for name, value in (
                ("PHARMA_JOBS__BACKEND_URL", settings.backend_url),
                ("PHARMA_JOBS__CLOUD_TASKS_PROJECT", settings.cloud_tasks_project),
                ("PHARMA_JOBS__SERVICE_ACCOUNT_EMAIL", settings.service_account_email),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"cloud_tasks jobs need {', '.join(missing)}")
        self._settings = settings
        self._client = client if client is not None else _GoogleTasksClient()
        self._backend_url = (settings.backend_url or "").rstrip("/")

    async def enqueue(self, job_id: uuid.UUID) -> None:
        settings = self._settings
        parent = self._client.queue_path(
            settings.cloud_tasks_project or "",
            settings.cloud_tasks_location,
            settings.cloud_tasks_queue,
        )
        await self._client.create_task(
            parent=parent,
            task={
                "http_request": {
                    "http_method": "POST",
                    "url": f"{self._backend_url}/api/v1/internal/ingest-jobs/{job_id}/run",
                    "oidc_token": {
                        "service_account_email": settings.service_account_email,
                        "audience": self._backend_url,
                    },
                },
                "dispatch_deadline": {"seconds": settings.dispatch_deadline_seconds},
            },
        )
