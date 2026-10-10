"""Six-digit one-time codes, stored only as an HMAC bound to their purpose and destination."""

import hashlib
import hmac
import secrets
from datetime import timedelta

from pharma_agent.domain.account.models import OneTimeCode, OtpPurpose

CODE_LENGTH = 6
CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5


def generate_code() -> str:
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def code_digest(secret: str, purpose: OtpPurpose, destination: str, code: str) -> str:
    message = "\x1f".join((purpose.value, destination, code)).encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def code_matches(secret: str, record: OneTimeCode, code: str) -> bool:
    expected = code_digest(secret, record.purpose, record.destination, code)
    return hmac.compare_digest(record.digest, expected)
