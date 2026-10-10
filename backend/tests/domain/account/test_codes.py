import uuid
from datetime import UTC, datetime

from pharma_agent.domain.account.codes import (
    CODE_TTL,
    MAX_ATTEMPTS,
    code_digest,
    code_matches,
    generate_code,
)
from pharma_agent.domain.account.models import OneTimeCode, OtpPurpose

SECRET = "o" * 40


def test_codes_are_six_digits() -> None:
    codes = {generate_code() for _ in range(200)}
    assert all(len(code) == 6 and code.isdigit() for code in codes)
    assert len(codes) > 150


def test_policy_constants() -> None:
    assert CODE_TTL.total_seconds() == 600
    assert MAX_ATTEMPTS == 5


def test_digest_binds_purpose_and_destination() -> None:
    base = code_digest(SECRET, OtpPurpose.VERIFY_EMAIL, "an@example.com", "123456")
    assert base != code_digest(
        SECRET, OtpPurpose.RESET_PASSWORD, "an@example.com", "123456"
    )
    assert base != code_digest(
        SECRET, OtpPurpose.VERIFY_EMAIL, "bo@example.com", "123456"
    )
    assert base != code_digest(
        "x" * 40, OtpPurpose.VERIFY_EMAIL, "an@example.com", "123456"
    )
    assert "123456" not in base


def test_code_matches_only_the_issued_code() -> None:
    record = OneTimeCode(
        id=uuid.uuid4(),
        purpose=OtpPurpose.PHONE_LOGIN,
        destination="+84912345678",
        user_id=None,
        digest=code_digest(SECRET, OtpPurpose.PHONE_LOGIN, "+84912345678", "000123"),
        expires_at=datetime(2026, 10, 10, tzinfo=UTC),
        attempts=0,
    )
    assert code_matches(SECRET, record, "000123")
    assert not code_matches(SECRET, record, "000124")
