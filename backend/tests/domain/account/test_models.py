import uuid

from pharma_agent.domain.account.models import (
    AccountUser,
    SignInMethod,
    normalize_email,
    session_id_of,
)


def account(
    *,
    email: str | None = "an@example.com",
    phone_number: str | None = None,
    email_verified: bool = True,
    phone_verified: bool = False,
    password_set: bool = True,
    google_linked: bool = False,
) -> AccountUser:
    return AccountUser(
        id=uuid.uuid4(),
        email=email,
        phone_number=phone_number,
        display_name="",
        email_verified=email_verified,
        phone_verified=phone_verified,
        password_set=password_set,
        google_linked=google_linked,
        is_active=True,
        is_superuser=False,
    )


def test_password_counts_only_with_a_verified_email() -> None:
    assert account().sign_in_methods() == {SignInMethod.PASSWORD}
    assert account(email_verified=False).sign_in_methods() == set()
    assert account(email=None, email_verified=False).sign_in_methods() == set()
    assert account(password_set=False).sign_in_methods() == set()


def test_phone_and_google_are_methods_of_their_own() -> None:
    user = account(
        email=None,
        email_verified=False,
        password_set=False,
        phone_number="+84912345678",
        phone_verified=True,
        google_linked=True,
    )
    assert user.sign_in_methods() == {SignInMethod.PHONE, SignInMethod.GOOGLE}


def test_normalize_email_trims_and_lowercases() -> None:
    assert normalize_email("  An@Example.COM ") == "an@example.com"


def test_session_id_is_stable_and_hides_the_token() -> None:
    token = "secret-session-token"
    assert session_id_of(token) == session_id_of(token)
    assert token not in session_id_of(token)
    assert len(session_id_of(token)) == 32
