import httpx
import pytest
import respx
from pydantic import SecretStr

from pharma_agent.domain.account.ports import DeliveryError
from pharma_agent.infrastructure.notifications.email import (
    LogEmailSender,
    ResendEmailSender,
)
from pharma_agent.infrastructure.notifications.factory import (
    build_email_sender,
    build_sms_sender,
)
from pharma_agent.infrastructure.notifications.sms import LogSmsSender
from pharma_agent.infrastructure.settings import EmailSettings, SmsSettings


async def test_resend_posts_the_message_and_maps_errors() -> None:
    async with respx.mock(assert_all_called=True) as resend:
        route = resend.post("https://api.resend.com/emails").mock(
            side_effect=[httpx.Response(200, json={"id": "1"}), httpx.Response(422)]
        )
        sender = ResendEmailSender(
            api_key="re_key", sender="ViPharmind <no-reply@x.dev>", timeout=5.0
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
    resend = EmailSettings(provider="resend", resend_api_key=SecretStr("k"))
    assert isinstance(build_email_sender(resend), ResendEmailSender)
    with pytest.raises(ValueError, match="RESEND_API_KEY"):
        build_email_sender(EmailSettings(provider="resend"))
    assert isinstance(build_sms_sender(SmsSettings()), LogSmsSender)
