"""Invitation emails in Vietnamese and English."""

from pharma_agent.application.mail import EmailContent, Locale, html_message
from pharma_agent.domain.access.models import Role

_ROLES: dict[Locale, dict[Role, str]] = {
    "vi": {
        Role.OWNER: "chủ sở hữu",
        Role.EDITOR: "biên tập viên",
        Role.MEMBER: "thành viên",
    },
    "en": {Role.OWNER: "owner", Role.EDITOR: "editor", Role.MEMBER: "member"},
}
_TEXT: dict[Locale, tuple[str, str, str]] = {
    "vi": (
        "Lời mời tham gia {organization} trên ViPharmind",
        "{inviter} mời bạn tham gia tổ chức {organization} với vai trò {role}. "
        "Lời mời có hạn 7 ngày. Mở liên kết để nhận lời mời: {link}",
        "Xem lời mời",
    ),
    "en": (
        "Join {organization} on ViPharmind",
        "{inviter} invited you to the organization {organization} as {role}. "
        "The invitation is valid for 7 days. Open the link to accept it: {link}",
        "View the invitation",
    ),
}


def invitation_email(
    *, organization: str, inviter: str, role: Role, link: str, locale: Locale
) -> EmailContent:
    subject_template, body_template, button = _TEXT[locale]
    values = {
        "organization": organization,
        "inviter": inviter,
        "role": _ROLES[locale][role],
        "link": link,
    }
    subject = subject_template.format(**values)
    text = body_template.format(**values)
    return EmailContent(
        subject=subject,
        text=text,
        html=html_message(subject, text, link=(button, link)),
    )
