"""Errors of the account use cases; api/errors.py maps them to HTTP statuses.

`AccountNotFound`, `DeliveryFailed` and `RateLimited` live in application/errors.py
because other features raise them too.
"""

from pharma_agent.application.errors import (
    AccountNotFound,
    ApplicationError,
    DeliveryFailed,
    InvalidInput,
    RateLimited,
    ServiceUnavailable,
)

__all__ = ["AccountNotFound", "DeliveryFailed", "RateLimited"]


class InvalidCode(ApplicationError):
    code = "OTP_INVALID"


class InvalidCredentials(ApplicationError):
    """Same code as a failed fastapi-users password sign-in."""

    code = "LOGIN_BAD_CREDENTIALS"


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


class PhoneSignInDisabled(ServiceUnavailable):
    """SMS is switched off (PHARMA_SMS__PROVIDER=none), so no phone codes are sent."""

    code = "PHONE_SIGN_IN_DISABLED"
