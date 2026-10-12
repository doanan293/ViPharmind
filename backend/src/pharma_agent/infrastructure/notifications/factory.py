"""Senders chosen by PHARMA_EMAIL__* and PHARMA_SMS__* settings."""

from pharma_agent.domain.account.ports import EmailSender, SmsSender
from pharma_agent.infrastructure.notifications.email import (
    GmailApiEmailSender,
    LogEmailSender,
)
from pharma_agent.infrastructure.notifications.sms import LogSmsSender
from pharma_agent.infrastructure.settings import EmailSettings, SmsSettings


def build_email_sender(settings: EmailSettings) -> EmailSender:
    if settings.provider == "gmail":
        if (
            settings.gmail_client_id is None
            or settings.gmail_client_secret is None
            or settings.gmail_refresh_token is None
        ):
            raise ValueError(
                "set PHARMA_EMAIL__GMAIL_CLIENT_ID, PHARMA_EMAIL__GMAIL_CLIENT_SECRET"
                " and PHARMA_EMAIL__GMAIL_REFRESH_TOKEN"
            )
        return GmailApiEmailSender(
            client_id=settings.gmail_client_id,
            client_secret=settings.gmail_client_secret.get_secret_value(),
            refresh_token=settings.gmail_refresh_token.get_secret_value(),
            sender=settings.sender,
            timeout=settings.timeout_seconds,
        )
    return LogEmailSender()


def build_sms_sender(settings: SmsSettings) -> SmsSender:
    return LogSmsSender()
