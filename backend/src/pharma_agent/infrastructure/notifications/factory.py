"""The email sender PHARMA_EMAIL__PROVIDER selects."""

from pharma_agent.domain.account.ports import EmailSender
from pharma_agent.infrastructure.notifications.email import (
    LogEmailSender,
    ResendEmailSender,
)
from pharma_agent.infrastructure.settings import EmailSettings


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
