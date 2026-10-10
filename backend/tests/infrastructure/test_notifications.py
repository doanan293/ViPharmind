from email.message import EmailMessage
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr

from pharma_agent.domain.account.ports import DeliveryError
from pharma_agent.infrastructure.notifications import email as email_module
from pharma_agent.infrastructure.notifications.email import (
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
    assert isinstance(build_sms_sender(SmsSettings()), LogSmsSender)
