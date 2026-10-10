"""Phone numbers in E.164, parsed with Google's libphonenumber rules."""

import phonenumbers

from pharma_agent.domain.shared.errors import DomainError


class InvalidPhoneNumber(DomainError):
    code = "PHONE_NUMBER_INVALID"


def normalize_phone(raw: str, *, default_region: str = "VN") -> tuple[str, str]:
    """`(e164, region)` for a number typed in local or international form."""
    try:
        number = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneNumber(raw) from exc
    if not phonenumbers.is_valid_number(number):
        raise InvalidPhoneNumber(raw)
    region = phonenumbers.region_code_for_number(number) or ""
    e164 = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
    return e164, region
