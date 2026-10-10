"""Account emails and SMS in Vietnamese and English."""

from dataclasses import dataclass
from html import escape
from typing import Literal

from pharma_agent.domain.account.codes import CODE_TTL
from pharma_agent.domain.account.models import OtpPurpose

Locale = Literal["vi", "en"]
TTL_MINUTES = int(CODE_TTL.total_seconds() // 60)


@dataclass(frozen=True)
class EmailContent:
    subject: str
    text: str
    html: str


def locale_from_accept_language(header: str | None) -> Locale:
    first = (header or "").split(",")[0].strip().lower()
    return "en" if first.startswith("en") else "vi"


_SUBJECTS: dict[OtpPurpose, dict[Locale, str]] = {
    OtpPurpose.VERIFY_EMAIL: {
        "vi": "Mã xác minh email ViPharMind",
        "en": "Your ViPharMind verification code",
    },
    OtpPurpose.RESET_PASSWORD: {
        "vi": "Mã đặt lại mật khẩu ViPharMind",
        "en": "Your ViPharMind password reset code",
    },
    OtpPurpose.CHANGE_EMAIL: {
        "vi": "Xác nhận email mới cho ViPharMind",
        "en": "Confirm your new ViPharMind email",
    },
    OtpPurpose.PHONE_LOGIN: {
        "vi": "Mã đăng nhập ViPharMind",
        "en": "Your ViPharMind sign-in code",
    },
    OtpPurpose.CHANGE_PHONE: {
        "vi": "Xác nhận số điện thoại mới cho ViPharMind",
        "en": "Confirm your new ViPharMind phone number",
    },
}
_BODY: dict[Locale, str] = {
    "vi": "Mã của bạn là {code}. Mã hết hạn sau {minutes} phút. "
    "Nếu bạn không yêu cầu mã này, hãy bỏ qua thư.",
    "en": "Your code is {code}. It expires in {minutes} minutes. "
    "If you did not ask for it, ignore this message.",
}
# GSM-7 text without Vietnamese diacritics: one SMS segment instead of three.
_SMS: dict[Locale, str] = {
    "vi": "ViPharMind: ma xac minh cua ban la {code}, het han sau {minutes} phut.",
    "en": "ViPharMind: your code is {code}. It expires in {minutes} minutes.",
}
_CHANGED: dict[Locale, tuple[str, str]] = {
    "vi": (
        "Email ViPharMind của bạn đã được đổi",
        "Email đăng nhập ViPharMind của bạn vừa được đổi sang {email}. "
        "Nếu không phải bạn, hãy đặt lại mật khẩu và liên hệ hỗ trợ.",
    ),
    "en": (
        "Your ViPharMind email was changed",
        "The sign-in email of your ViPharMind account was changed to {email}. "
        "If this was not you, reset your password and contact support.",
    ),
}


def _html(subject: str, body: str, code: str | None = None) -> str:
    code_block = (
        ""
        if code is None
        else f'<p style="font-size:32px;font-weight:bold;letter-spacing:4px">{code}</p>'
    )
    return (
        '<div style="font-family:sans-serif;color:#1f2937">'
        f"<h2>{escape(subject)}</h2>{code_block}<p>{escape(body)}</p></div>"
    )


def code_email(purpose: OtpPurpose, code: str, locale: Locale) -> EmailContent:
    subject = _SUBJECTS[purpose][locale]
    text = _BODY[locale].format(code=code, minutes=TTL_MINUTES)
    return EmailContent(subject=subject, text=text, html=_html(subject, text, code))


def code_sms(purpose: OtpPurpose, code: str, locale: Locale) -> str:
    return _SMS[locale].format(code=code, minutes=TTL_MINUTES)


def email_changed_notice(new_email: str, locale: Locale) -> EmailContent:
    subject, body = _CHANGED[locale]
    text = body.format(email=new_email)
    return EmailContent(subject=subject, text=text, html=_html(subject, text))
