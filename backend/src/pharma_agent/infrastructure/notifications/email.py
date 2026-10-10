"""EmailSender adapters: log (local runs), SMTP (Gmail app password) and Resend."""

import logging
from email.message import EmailMessage

import aiosmtplib
import httpx

from pharma_agent.domain.account.ports import DeliveryError

logger = logging.getLogger(__name__)
RESEND_URL = "https://api.resend.com/emails"


class LogEmailSender:
    async def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        logger.warning(
            "email provider is 'log'; not sent to %s: %s | %s", to, subject, text
        )


class SmtpEmailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        timeout: float,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._timeout = timeout

    async def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)
        message.add_alternative(html, subtype="html")
        try:
            await aiosmtplib.send(
                message,
                hostname=self._host,
                port=self._port,
                username=self._username,
                password=self._password,
                start_tls=self._port != 465,
                use_tls=self._port == 465,
                timeout=self._timeout,
            )
        except (aiosmtplib.SMTPException, OSError) as exc:
            raise DeliveryError(f"SMTP delivery failed: {exc}") from exc


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
