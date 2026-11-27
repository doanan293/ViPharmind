"""PasswordHasher backed by fastapi-users' PasswordHelper (the hashes login checks)."""

from fastapi_users.password import PasswordHelper


class FastapiUsersPasswordHasher:
    """Hashes and verifies passwords the same way fastapi-users does at login."""

    def __init__(self) -> None:
        """Use fastapi-users' default PasswordHelper."""
        self._helper = PasswordHelper()

    def hash(self, password: str) -> str:
        """Hash `password` for storage."""
        return self._helper.hash(password)

    def verify(self, password: str, hashed: str) -> bool:
        """Whether `password` matches `hashed`."""
        verified, _ = self._helper.verify_and_update(password, hashed)
        return verified
