"""Senders chosen by PHARMA_EMAIL__* and PHARMA_SMS__* settings."""

from pharma_agent.domain.account.ports import EmailSender, SmsSender
from pharma_agent.infrastructure.notifications.email import (
    LogEmailSender,
    ResendEmailSender,
)
from pharma_agent.infrastructure.notifications.sms import LogSmsSender
from pharma_agent.infrastructure.settings import EmailSettings, SmsSettings


def build_email_sender(settings: EmailSettings) -> EmailSender:
    if settings.provider == "resend":
        if settings.resend_api_key is None:
            raise ValueError("set PHARMA_EMAIL__RESEND_API_KEY")
        return ResendEmailSender(
            api_key=settings.resend_api_key.get_secret_value(),
            sender=settings.sender,
            timeout=settings.timeout_seconds,
        )
    return LogEmailSender()


def build_sms_sender(settings: SmsSettings) -> SmsSender:
    return LogSmsSender()
