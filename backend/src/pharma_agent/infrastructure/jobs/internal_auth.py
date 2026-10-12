"""Who may call /internal: the in-process runner or Cloud Tasks, nobody else."""

import hmac
from collections.abc import Mapping

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from pharma_agent.infrastructure.settings import JobsSettings

INTERNAL_TOKEN_HEADER = "x-internal-token"


class InternalAuthError(Exception):
    """The caller did not prove it is the job runner."""


def verify_internal_request(headers: Mapping[str, str], settings: JobsSettings) -> None:
    if settings.dispatcher in ("inprocess", "inline"):
        expected = settings.internal_token
        given = headers.get(INTERNAL_TOKEN_HEADER, "")
        if (
            expected is None
            or not given
            or not hmac.compare_digest(
                given.encode(), expected.get_secret_value().encode()
            )
        ):
            raise InternalAuthError("missing or wrong internal token")
        return
    authorization = headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise InternalAuthError("missing bearer token")
    audience = (settings.backend_url or "").rstrip("/")
    try:
        claims = id_token.verify_oauth2_token(
            token, google_requests.Request(), audience=audience
        )
    except ValueError as exc:
        raise InternalAuthError("invalid Google token") from exc
    if claims.get("email") != settings.service_account_email or not claims.get(
        "email_verified", False
    ):
        raise InternalAuthError("the token is not from the job runner")
