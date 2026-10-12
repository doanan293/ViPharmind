import base64
import json
from email import message_from_bytes

import httpx
import pytest
import respx
from pydantic import SecretStr

from pharma_agent.domain.account.ports import DeliveryError
from pharma_agent.infrastructure.notifications.email import (
    GmailApiEmailSender,
    LogEmailSender,
)
from pharma_agent.infrastructure.notifications.factory import (
    build_email_sender,
    build_sms_sender,
)
from pharma_agent.infrastructure.notifications.sms import LogSmsSender
from pharma_agent.infrastructure.settings import EmailSettings, SmsSettings

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def _gmail_sender() -> GmailApiEmailSender:
    return GmailApiEmailSender(
        client_id="cid",
        client_secret="csecret",
        refresh_token="rtoken",
        sender="ViPharMind <an@gmail.com>",
        timeout=5.0,
    )


async def test_gmail_api_sends_a_multipart_message_with_one_access_token() -> None:
    async with respx.mock(assert_all_called=True) as google:
        token = google.post(GOOGLE_TOKEN_URL).mock(
            return_value=httpx.Response(
                200, json={"access_token": "at", "expires_in": 3599}
            )
        )
        send = google.post(GMAIL_SEND_URL).mock(
            return_value=httpx.Response(200, json={"id": "m1"})
        )
        sender = _gmail_sender()
        await sender.send(
            to="binh@example.com", subject="Mã", text="T", html="<p>H</p>"
        )
        await sender.send(
            to="binh@example.com", subject="Mã", text="T", html="<p>H</p>"
        )

        assert token.call_count == 1
        form = token.calls[0].request.content.decode()
        assert "grant_type=refresh_token" in form and "refresh_token=rtoken" in form
        request = send.calls[0].request
        assert request.headers["authorization"] == "Bearer at"
        raw = json.loads(request.content)["raw"]
        message = message_from_bytes(base64.urlsafe_b64decode(raw))
        assert message["To"] == "binh@example.com"
        assert message["From"] == "ViPharMind <an@gmail.com>"
        assert message.get_content_type() == "multipart/alternative"


async def test_gmail_api_failures_become_delivery_errors() -> None:
    async with respx.mock() as google:
        google.post(GOOGLE_TOKEN_URL).mock(
            return_value=httpx.Response(400, json={"error": "invalid_grant"})
        )
        with pytest.raises(DeliveryError, match="invalid_grant"):
            await _gmail_sender().send(to="a@b.c", subject="s", text="t", html="h")

    async with respx.mock() as google:
        google.post(GOOGLE_TOKEN_URL).mock(
            return_value=httpx.Response(
                200, json={"access_token": "at", "expires_in": 3599}
            )
        )
        google.post(GMAIL_SEND_URL).mock(return_value=httpx.Response(403))
        with pytest.raises(DeliveryError, match="403"):
            await _gmail_sender().send(to="a@b.c", subject="s", text="t", html="h")


async def test_log_senders_accept_messages() -> None:
    await LogEmailSender().send(to="a@b.c", subject="s", text="t", html="h")
    await LogSmsSender().send(to="+84912345678", text="t")


def test_factories_follow_settings() -> None:
    assert isinstance(build_email_sender(EmailSettings()), LogEmailSender)
    gmail = EmailSettings(
        provider="gmail",
        gmail_client_id="cid",
        gmail_client_secret=SecretStr("cs"),
        gmail_refresh_token=SecretStr("rt"),
    )
    assert isinstance(build_email_sender(gmail), GmailApiEmailSender)
    with pytest.raises(ValueError, match="GMAIL_REFRESH_TOKEN"):
        build_email_sender(EmailSettings(provider="gmail"))
    assert isinstance(build_sms_sender(SmsSettings()), LogSmsSender)
