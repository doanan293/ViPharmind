"""Errors of the account use cases; api/errors.py maps them to HTTP statuses.

`AccountNotFound` lives in application/errors.py because other features raise it too.
"""

import math

from pharma_agent.application.errors import (
    AccountNotFound,
    ApplicationError,
    InvalidInput,
    ServiceUnavailable,
)

__all__ = ["AccountNotFound"]


class InvalidCode(ApplicationError):
    code = "OTP_INVALID"


class InvalidCredentials(ApplicationError):
    """Same code as a failed fastapi-users password sign-in."""

    code = "LOGIN_BAD_CREDENTIALS"


class RateLimited(ApplicationError):
    code = "RATE_LIMITED"

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"try again in {math.ceil(retry_after)} seconds")
        self.retry_after = retry_after


class EmailAlreadyUsed(ApplicationError):
    code = "EMAIL_ALREADY_USED"


class PhoneAlreadyUsed(ApplicationError):
    code = "PHONE_ALREADY_USED"


class LastSignInMethod(ApplicationError):
    code = "LAST_SIGN_IN_METHOD"


class CurrentPasswordInvalid(ApplicationError):
    code = "CURRENT_PASSWORD_INVALID"


class AccountDisabled(ApplicationError):
    code = "ACCOUNT_DISABLED"


class SessionNotFound(ApplicationError):
    code = "SESSION_NOT_FOUND"


class PasswordInvalid(InvalidInput):
    code = "PASSWORD_INVALID"


class PhoneNumberInvalid(InvalidInput):
    code = "PHONE_NUMBER_INVALID"


class PhoneCountryNotAllowed(InvalidInput):
    code = "PHONE_COUNTRY_NOT_ALLOWED"


class DeliveryFailed(ServiceUnavailable):
    code = "DELIVERY_FAILED"
