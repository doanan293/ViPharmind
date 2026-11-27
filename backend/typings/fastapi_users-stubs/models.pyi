"""Type stub for `fastapi_users.models` (fastapi-users 15.0.5).

Identical to the library except one line: `UserOAuthProtocol` lists `Protocol` among its
bases. Without it, PEP 544 makes the class nominal (a subclass of a protocol is a protocol
only when it names `Protocol` again), so no ORM model can satisfy it structurally and every
`oauth_callback` / `oauth_associate_callback` call is rejected by the type checker.
"""

from typing import Protocol, TypeVar

ID = TypeVar("ID")

class UserProtocol(Protocol[ID]):
    id: ID
    email: str
    hashed_password: str
    is_active: bool
    is_superuser: bool
    is_verified: bool

class OAuthAccountProtocol(Protocol[ID]):
    id: ID
    oauth_name: str
    access_token: str
    expires_at: int | None
    refresh_token: str | None
    account_id: str
    account_email: str

UP = TypeVar("UP", bound=UserProtocol)
OAP = TypeVar("OAP", bound=OAuthAccountProtocol)

class UserOAuthProtocol(UserProtocol[ID], Protocol[ID, OAP]):
    id: ID
    email: str
    hashed_password: str
    is_active: bool
    is_superuser: bool
    is_verified: bool
    oauth_accounts: list[OAP]

UOAP = TypeVar("UOAP", bound=UserOAuthProtocol)
