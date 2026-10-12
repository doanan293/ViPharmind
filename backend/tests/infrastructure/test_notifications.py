import base64
import json
from email import message_from_bytes
from email.message import EmailMessage
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr

from pharma_agent.domain.account.ports import DeliveryError
from pharma_agent.infrastructure.notifications import email as email_module
from pharma_agent.infrastructure.notifications.email import (
    GmailApiEmailSender,
    LogEmailSender,
    ResendEmailSender,
    SmtpEmailSender,
)
from pharma_agent.infrastructure.notifications.factory import (
    build_email_sender,
    build_sms_sender,
)
from pharma_agent.infrastructure.notifications.sms import LogSmsSender
from pharma_agent.infrastructure.settings import EmailSettings, SmsSettings


async def test_smtp_sends_a_multipart_message(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, Any] = {}

    async def fake_send(message: EmailMessage, **kwargs: Any) -> None:
        sent["message"], sent["kwargs"] = message, kwargs

    monkeypatch.setattr(email_module.aiosmtplib, "send", fake_send)
    sender = SmtpEmailSender(
        host="smtp.gmail.com",
        port=587,
        username="an@gmail.com",
        password="app-password",
        sender="ViPharMind <an@gmail.com>",
        timeout=5.0,
    )
    await sender.send(
        to="bo@example.com", subject="Mã", text="123456", html="<p>123456</p>"
    )
    message: EmailMessage = sent["message"]
    assert (
        message["To"] == "bo@example.com"
        and message["From"] == "ViPharMind <an@gmail.com>"
    )
    assert [part.get_content_type() for part in message.iter_parts()] == [
        "text/plain",
        "text/html",
    ]
    assert (
        sent["kwargs"]["start_tls"] is True
        and sent["kwargs"]["username"] == "an@gmail.com"
    )


async def test_smtp_failures_become_delivery_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_send(message: EmailMessage, **kwargs: Any) -> None:
        raise email_module.aiosmtplib.SMTPException("refused")

    monkeypatch.setattr(email_module.aiosmtplib, "send", failing_send)
    sender = SmtpEmailSender(
        host="h", port=587, username="u", password="p", sender="s", timeout=5.0
    )
    with pytest.raises(DeliveryError):
        await sender.send(to="a@b.c", subject="s", text="t", html="h")


async def test_resend_posts_the_message_and_maps_errors() -> None:
    async with respx.mock(assert_all_called=True) as resend:
        route = resend.post("https://api.resend.com/emails").mock(
            side_effect=[httpx.Response(200, json={"id": "1"}), httpx.Response(422)]
        )
        sender = ResendEmailSender(
            api_key="re_key", sender="ViPharMind <no-reply@x.dev>", timeout=5.0
        )
        await sender.send(to="an@example.com", subject="S", text="T", html="H")
        request = route.calls[0].request
        assert request.headers["authorization"] == "Bearer re_key"
        assert b'"to":["an@example.com"]' in request.content
        with pytest.raises(DeliveryError):
            await sender.send(to="an@example.com", subject="S", text="T", html="H")


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
    smtp = EmailSettings(
        provider="smtp", smtp_username="u", smtp_password=SecretStr("p")
    )
    assert isinstance(build_email_sender(smtp), SmtpEmailSender)
    resend = EmailSettings(provider="resend", resend_api_key=SecretStr("k"))
    assert isinstance(build_email_sender(resend), ResendEmailSender)
    with pytest.raises(ValueError, match="SMTP_USERNAME"):
        build_email_sender(EmailSettings(provider="smtp"))
    with pytest.raises(ValueError, match="RESEND_API_KEY"):
        build_email_sender(EmailSettings(provider="resend"))
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
