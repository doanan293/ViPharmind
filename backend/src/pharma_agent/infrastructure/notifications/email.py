"""EmailSender adapters: Resend (production) and log (local runs and tests)."""

import logging

import httpx

from pharma_agent.domain.account.ports import DeliveryError

logger = logging.getLogger(__name__)
RESEND_URL = "https://api.resend.com/emails"


class LogEmailSender:
    """EmailSender that only logs the message: local runs and tests."""

    async def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        """Log the recipient, subject and text instead of sending."""
        logger.warning(
            "email provider is 'log'; not sent to %s: %s | %s", to, subject, text
        )


class ResendEmailSender:
    """EmailSender over the Resend HTTP API."""

    def __init__(
        self,
        *,
        api_key: str,
        sender: str,
        timeout: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Send as `sender` with `api_key`.

        `timeout` is in seconds. Without `client`, each send opens and closes its own
        client.
        """
        self._api_key = api_key
        self._sender = sender
        self._timeout = timeout
        self._client = client

    async def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        """Send one email through Resend.

        Raises:
            DeliveryError: When the request fails or Resend answers HTTP 400 or above.
        """
        payload = {
            "from": self._sender,
            "to": [to],
            "subject": subject,
            "text": text,
            "html": html,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            if self._client is not None:
                response = await self._client.post(
                    RESEND_URL, json=payload, headers=headers, timeout=self._timeout
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        RESEND_URL, json=payload, headers=headers
                    )
        except httpx.HTTPError as exc:
            raise DeliveryError(f"Resend request failed: {exc}") from exc
        if response.status_code >= 400:
            raise DeliveryError(f"Resend returned HTTP {response.status_code}")
