"""PasswordHasher backed by fastapi-users' PasswordHelper (the hashes login checks)."""

from fastapi_users.password import PasswordHelper


class FastapiUsersPasswordHasher:
    def __init__(self) -> None:
        self._helper = PasswordHelper()

    def hash(self, password: str) -> str:
        return self._helper.hash(password)

    def verify(self, password: str, hashed: str) -> bool:
        verified, _ = self._helper.verify_and_update(password, hashed)
        return verified
