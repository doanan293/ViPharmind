import pytest

from pharma_agent.application.account.messages import (
    Locale,
    code_email,
    code_sms,
    email_changed_notice,
    locale_from_accept_language,
)
from pharma_agent.domain.account.models import OtpPurpose


@pytest.mark.parametrize(
    ("header", "locale"),
    [
        (None, "vi"),
        ("", "vi"),
        ("vi", "vi"),
        ("en", "en"),
        ("en-US,en;q=0.9", "en"),
        ("fr", "vi"),
    ],
)
def test_locale_from_accept_language(header: str | None, locale: str) -> None:
    assert locale_from_accept_language(header) == locale


@pytest.mark.parametrize("purpose", list(OtpPurpose))
@pytest.mark.parametrize("locale", ["vi", "en"])
def test_every_purpose_has_a_message_with_the_code(
    purpose: OtpPurpose, locale: Locale
) -> None:
    email = code_email(purpose, "042137", locale)
    assert "042137" in email.text and "042137" in email.html and email.subject
    sms = code_sms(purpose, "042137", locale)
    assert "042137" in sms and len(sms) <= 160 and sms.isascii()


def test_notice_escapes_the_address() -> None:
    notice = email_changed_notice("<b>x</b>@example.com", "vi")
    assert "<b>x</b>" not in notice.html and "&lt;b&gt;" in notice.html
