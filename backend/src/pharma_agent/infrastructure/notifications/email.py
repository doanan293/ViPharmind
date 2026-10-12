"""EmailSender adapters: Resend (production) and log (local runs and tests)."""

import logging

import httpx

from pharma_agent.domain.account.ports import DeliveryError

logger = logging.getLogger(__name__)
RESEND_URL = "https://api.resend.com/emails"


class LogEmailSender:
    async def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        logger.warning(
            "email provider is 'log'; not sent to %s: %s | %s", to, subject, text
        )


class ResendEmailSender:
    def __init__(
        self,
        *,
        api_key: str,
        sender: str,
        timeout: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._sender = sender
        self._timeout = timeout
        self._client = client

    async def send(self, *, to: str, subject: str, text: str, html: str) -> None:
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
