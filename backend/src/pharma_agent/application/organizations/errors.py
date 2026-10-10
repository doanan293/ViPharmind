"""Errors of the organization use cases; api/errors.py maps them to HTTP statuses.

Anything the actor may not see raises a NotFound error, so an outsider cannot learn that an
organization exists. ForbiddenRole is for what the actor sees but may not change.
"""

from pharma_agent.application.errors import ApplicationError, InvalidInput


class ForbiddenRole(ApplicationError):
    code = "FORBIDDEN_ROLE"


class OrganizationNotFound(ApplicationError):
    code = "ORGANIZATION_NOT_FOUND"


class MemberNotFound(ApplicationError):
    code = "MEMBER_NOT_FOUND"


class LastOwner(ApplicationError):
    code = "LAST_OWNER"


class AlreadyMember(ApplicationError):
    code = "ALREADY_MEMBER"


class InvitationNotFound(ApplicationError):
    code = "INVITATION_NOT_FOUND"


class InvitationExpired(ApplicationError):
    code = "INVITATION_EXPIRED"


class InvitationNotPending(ApplicationError):
    code = "INVITATION_NOT_PENDING"


class InvitationEmailMismatch(ApplicationError):
    code = "INVITATION_EMAIL_MISMATCH"


class InvitationAlreadyOpen(ApplicationError):
    code = "INVITATION_ALREADY_OPEN"


class OrganizationNameInvalid(InvalidInput):
    code = "ORGANIZATION_NAME_INVALID"
