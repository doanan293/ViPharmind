"""Errors of the collection and content use cases; api/errors.py maps them to statuses."""

from pharma_agent.application.errors import ApplicationError, InvalidInput


class CollectionNotFoundForActor(ApplicationError):
    """Missing, deleted, or not visible to the actor: all look the same from outside."""

    code = "COLLECTION_NOT_FOUND"


class SystemCollectionReadOnly(ApplicationError):
    """Only superadmins may change the system corpus, and it stays public."""

    code = "SYSTEM_COLLECTION_READ_ONLY"


class QuotaExceeded(InvalidInput):
    """A characters, documents or collections quota is used up."""

    code = "QUOTA_EXCEEDED"

    def __init__(self, *, unit: str, used: int, limit: int) -> None:
        """Record which quota (`unit`) is used up and its usage and limit."""
        super().__init__(f"the {unit} quota is used up ({used} of {limit})")
        self.unit = unit
        self.used = used
        self.limit = limit


class PublishInProgress(ApplicationError):
    """The collection is already being published."""

    code = "PUBLISH_IN_PROGRESS"
