import math


class ApplicationError(Exception):
    code = "APPLICATION_ERROR"


class AccountNotFound(ApplicationError):
    code = "ACCOUNT_NOT_FOUND"


class RateLimited(ApplicationError):
    code = "RATE_LIMITED"

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"try again in {math.ceil(retry_after)} seconds")
        self.retry_after = retry_after


class ForbiddenRole(ApplicationError):
    """The actor sees the resource but their role does not allow the change."""

    code = "FORBIDDEN_ROLE"


class OrganizationNotFound(ApplicationError):
    code = "ORGANIZATION_NOT_FOUND"


class ConversationNotFound(ApplicationError):
    code = "CONVERSATION_NOT_FOUND"


class CitationNotFound(ApplicationError):
    code = "CITATION_NOT_FOUND"


class InvalidInput(ApplicationError):
    code = "INVALID_INPUT"


class PayloadTooLarge(InvalidInput):
    code = "PAYLOAD_TOO_LARGE"


class ServiceUnavailable(ApplicationError):
    """Something the request needs is not ready or not configured (HTTP 503)."""

    code = "SERVICE_UNAVAILABLE"


class ServiceStarting(ServiceUnavailable):
    code = "SERVICE_STARTING"


class ServiceNotConfigured(ServiceUnavailable):
    code = "SERVICE_NOT_CONFIGURED"


class AgentUnavailable(ServiceUnavailable):
    code = "AGENT_UNAVAILABLE"


class DeliveryFailed(ServiceUnavailable):
    code = "DELIVERY_FAILED"
