"""Password rule shared by registration, reset and change."""

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


def password_problem(password: str) -> str | None:
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"password must be at least {PASSWORD_MIN_LENGTH} characters"
    if len(password) > PASSWORD_MAX_LENGTH:
        return f"password must be at most {PASSWORD_MAX_LENGTH} characters"
    return None
