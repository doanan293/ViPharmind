from pharma_agent.application.organizations.invitations import email_hint
from pharma_agent.application.organizations.messages import invitation_email
from pharma_agent.domain.access.models import Role


def test_invitation_email_carries_the_link_in_both_languages() -> None:
    link = "https://app.example/invitations/abc?x=<1>"
    vi = invitation_email(
        organization="Khoa Dược", inviter="An", role=Role.EDITOR, link=link, locale="vi"
    )
    en = invitation_email(
        organization="Khoa Dược", inviter="An", role=Role.EDITOR, link=link, locale="en"
    )
    assert vi.subject == "Lời mời tham gia Khoa Dược trên ViPharmind"
    assert "biên tập viên" in vi.text and link in vi.text
    assert en.subject == "Join Khoa Dược on ViPharmind" and "editor" in en.text
    assert 'href="https://app.example/invitations/abc?x=&lt;1&gt;"' in en.html
    assert "<1>" not in en.html


def test_email_hint_keeps_only_the_first_letter() -> None:
    assert email_hint("an@example.com") == "a**@example.com"
