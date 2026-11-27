import math


class ApplicationError(Exception):
    """Base of every use-case error; `code` is the stable machine-readable error code."""

    code = "APPLICATION_ERROR"


class AccountNotFound(ApplicationError):
    """The user account does not exist."""

    code = "ACCOUNT_NOT_FOUND"


class RateLimited(ApplicationError):
    """Too many requests; the caller should retry after `retry_after` seconds."""

    code = "RATE_LIMITED"

    def __init__(self, retry_after: float) -> None:
        """Store the wait in seconds; the message rounds it up to whole seconds."""
        super().__init__(f"try again in {math.ceil(retry_after)} seconds")
        self.retry_after = retry_after


class ForbiddenRole(ApplicationError):
    """The actor sees the resource but their role does not allow the change."""

    code = "FORBIDDEN_ROLE"


class OrganizationNotFound(ApplicationError):
    """The organization does not exist or is not visible to the actor."""

    code = "ORGANIZATION_NOT_FOUND"


class ConversationNotFound(ApplicationError):
    """The conversation does not exist or does not belong to the user."""

    code = "CONVERSATION_NOT_FOUND"


class CitationNotFound(ApplicationError):
    """The message has no citation with the requested index."""

    code = "CITATION_NOT_FOUND"


class InvalidInput(ApplicationError):
    """The request is well formed but its values are not acceptable (HTTP 422)."""

    code = "INVALID_INPUT"


class PayloadTooLarge(InvalidInput):
    """An uploaded file is larger than allowed (HTTP 413)."""

    code = "PAYLOAD_TOO_LARGE"


class ServiceUnavailable(ApplicationError):
    """Something the request needs is not ready or not configured (HTTP 503)."""

    code = "SERVICE_UNAVAILABLE"


class ServiceStarting(ServiceUnavailable):
    """The application container is not ready yet."""

    code = "SERVICE_STARTING"


class ServiceNotConfigured(ServiceUnavailable):
    """A feature the request needs (database, feedback, authoring...) is not configured."""

    code = "SERVICE_NOT_CONFIGURED"


class AgentUnavailable(ServiceUnavailable):
    """The chat agent is not configured (no LLM API key)."""

    code = "AGENT_UNAVAILABLE"


class DeliveryFailed(ServiceUnavailable):
    """An email or SMS could not be delivered."""

    code = "DELIVERY_FAILED"
