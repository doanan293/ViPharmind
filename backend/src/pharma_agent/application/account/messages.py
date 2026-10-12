"""Account emails and SMS in Vietnamese and English."""

from pharma_agent.application.mail import (
    EmailContent,
    Locale,
    html_message,
    locale_from_accept_language,
)
from pharma_agent.domain.account.codes import CODE_TTL
from pharma_agent.domain.account.models import OtpPurpose

__all__ = [
    "EmailContent",
    "Locale",
    "code_email",
    "code_sms",
    "email_changed_notice",
    "locale_from_accept_language",
]

TTL_MINUTES = int(CODE_TTL.total_seconds() // 60)


_SUBJECTS: dict[OtpPurpose, dict[Locale, str]] = {
    OtpPurpose.VERIFY_EMAIL: {
        "vi": "Mã xác minh email ViPharmind",
        "en": "Your ViPharmind verification code",
    },
    OtpPurpose.RESET_PASSWORD: {
        "vi": "Mã đặt lại mật khẩu ViPharmind",
        "en": "Your ViPharmind password reset code",
    },
    OtpPurpose.CHANGE_EMAIL: {
        "vi": "Xác nhận email mới cho ViPharmind",
        "en": "Confirm your new ViPharmind email",
    },
    OtpPurpose.PHONE_LOGIN: {
        "vi": "Mã đăng nhập ViPharmind",
        "en": "Your ViPharmind sign-in code",
    },
    OtpPurpose.CHANGE_PHONE: {
        "vi": "Xác nhận số điện thoại mới cho ViPharmind",
        "en": "Confirm your new ViPharmind phone number",
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
    "vi": "ViPharmind: ma xac minh cua ban la {code}, het han sau {minutes} phut.",
    "en": "ViPharmind: your code is {code}. It expires in {minutes} minutes.",
}
_CHANGED: dict[Locale, tuple[str, str]] = {
    "vi": (
        "Email ViPharmind của bạn đã được đổi",
        "Email đăng nhập ViPharmind của bạn vừa được đổi sang {email}. "
        "Nếu không phải bạn, hãy đặt lại mật khẩu và liên hệ hỗ trợ.",
    ),
    "en": (
        "Your ViPharmind email was changed",
        "The sign-in email of your ViPharmind account was changed to {email}. "
        "If this was not you, reset your password and contact support.",
    ),
}


def code_email(purpose: OtpPurpose, code: str, locale: Locale) -> EmailContent:
    subject = _SUBJECTS[purpose][locale]
    text = _BODY[locale].format(code=code, minutes=TTL_MINUTES)
    return EmailContent(
        subject=subject, text=text, html=html_message(subject, text, highlight=code)
    )


def code_sms(purpose: OtpPurpose, code: str, locale: Locale) -> str:
    return _SMS[locale].format(code=code, minutes=TTL_MINUTES)


def email_changed_notice(new_email: str, locale: Locale) -> EmailContent:
    subject, body = _CHANGED[locale]
    text = body.format(email=new_email)
    return EmailContent(subject=subject, text=text, html=html_message(subject, text))
