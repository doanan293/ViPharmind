"""EmailSender adapters: log (local runs), SMTP, Gmail API and Resend."""

import base64
import logging
import time
from email.message import EmailMessage

import aiosmtplib
import httpx

from pharma_agent.domain.account.ports import DeliveryError

logger = logging.getLogger(__name__)
RESEND_URL = "https://api.resend.com/emails"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
# Refresh the access token this long before Google says it expires.
TOKEN_EXPIRY_MARGIN_SECONDS = 60


def _mime_message(
    *, sender: str, to: str, subject: str, text: str, html: str
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    return message


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
        message = _mime_message(
            sender=self._sender, to=to, subject=subject, text=text, html=html
        )
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


class GmailApiEmailSender:
    """Sends as a Gmail account over HTTPS, for hosts that block outbound SMTP.

    The refresh token comes from a one-time consent with the gmail.send scope
    (devops/google/gmail_refresh_token.py); the access token is cached until it expires.
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        sender: str,
        timeout: float,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._sender = sender
        self._timeout = timeout
        self._access_token: str | None = None
        self._expires_at = 0.0

    async def _token(self, client: httpx.AsyncClient) -> str:
        if self._access_token is not None and time.monotonic() < self._expires_at:
            return self._access_token
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
            },
        )
        if response.status_code >= 400:
            # Google names the cause, e.g. invalid_grant for a revoked or expired token.
            raise DeliveryError(
                f"Google token refresh returned HTTP {response.status_code}: {response.text}"
            )
        body = response.json()
        self._access_token = str(body["access_token"])
        self._expires_at = (
            time.monotonic() + float(body["expires_in"]) - TOKEN_EXPIRY_MARGIN_SECONDS
        )
        return self._access_token

    async def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        message = _mime_message(
            sender=self._sender, to=to, subject=subject, text=text, html=html
        )
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                token = await self._token(client)
                response = await client.post(
                    GMAIL_SEND_URL,
                    json={"raw": raw},
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.HTTPError as exc:
            raise DeliveryError(f"Gmail API request failed: {exc}") from exc
        if response.status_code >= 400:
            raise DeliveryError(f"Gmail API returned HTTP {response.status_code}")


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
