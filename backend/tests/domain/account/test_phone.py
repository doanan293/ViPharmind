import pytest

from pharma_agent.domain.account.phone import InvalidPhoneNumber, normalize_phone


@pytest.mark.parametrize(
    "raw",
    ["0912345678", "0912 345 678", "091.234.5678", "+84 91 234 5678", "84912345678"],
)
def test_local_and_international_forms_normalize_to_one_number(raw: str) -> None:
    assert normalize_phone(raw) == ("+84912345678", "VN")


def test_foreign_numbers_keep_their_region() -> None:
    assert normalize_phone("+1 650 253 0000") == ("+16502530000", "US")


@pytest.mark.parametrize("raw", ["", "12345", "not a number", "+84 12"])
def test_invalid_numbers_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidPhoneNumber):
        normalize_phone(raw)
