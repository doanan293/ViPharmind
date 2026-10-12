"""Who may call /internal: whoever holds the shared job-runner token, nobody else."""

import hmac
from collections.abc import Mapping

from pharma_agent.infrastructure.settings import JobsSettings

INTERNAL_TOKEN_HEADER = "x-internal-token"


class InternalAuthError(Exception):
    """The caller did not prove it is the job runner."""


def verify_internal_request(headers: Mapping[str, str], settings: JobsSettings) -> None:
    expected = settings.internal_token
    given = headers.get(INTERNAL_TOKEN_HEADER, "")
    if (
        expected is None
        or not given
        or not hmac.compare_digest(given.encode(), expected.get_secret_value().encode())
    ):
        raise InternalAuthError("missing or wrong internal token")
