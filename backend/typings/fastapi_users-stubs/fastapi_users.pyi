"""Type stub for `fastapi_users.fastapi_users`.

The library annotates the user-manager dependency with the generic alias
`UserManagerDependency[UP, ID]`. Python orders an alias's type parameters by first
appearance (UP, ID); pyrefly orders them by TypeVar declaration (ID, UP) and rejects every
correctly typed dependency. This stub states the same types without the alias.
Written for fastapi-users 15.0.5; tests/test_typing_stubs.py fails when the installed
version changes, so the stub is re-checked on every upgrade.
"""

from collections.abc import Callable, Coroutine, Sequence
from typing import Literal

from fastapi import APIRouter
from fastapi_users import models, schemas
from fastapi_users.authentication import AuthenticationBackend, Authenticator
from fastapi_users.jwt import SecretType
from fastapi_users.manager import BaseUserManager
from fastapi_users.types import DependencyCallable
from httpx_oauth.oauth2 import BaseOAuth2

class FastAPIUsers[UP: models.UserProtocol, ID]:
    authenticator: Authenticator[UP, ID]
    get_user_manager: DependencyCallable[BaseUserManager[UP, ID]]
    def current_user(
        self,
        optional: bool = ...,
        active: bool = ...,
        verified: bool = ...,
        superuser: bool = ...,
        get_enabled_backends: DependencyCallable[
            Sequence[AuthenticationBackend[UP, ID]]
        ]
        | None = None,
    ) -> Callable[..., Coroutine[object, object, UP | None]]: ...
    def __init__(
        self,
        get_user_manager: DependencyCallable[BaseUserManager[UP, ID]],
        auth_backends: Sequence[AuthenticationBackend[UP, ID]],
    ) -> None: ...
    def get_register_router(
        self, user_schema: type[schemas.U], user_create_schema: type[schemas.UC]
    ) -> APIRouter: ...
    def get_verify_router(self, user_schema: type[schemas.U]) -> APIRouter: ...
    def get_reset_password_router(self) -> APIRouter: ...
    def get_auth_router(
        self,
        backend: AuthenticationBackend[UP, ID],
        requires_verification: bool = ...,
    ) -> APIRouter: ...
    def get_oauth_router(
        self,
        oauth_client: BaseOAuth2,
        backend: AuthenticationBackend[UP, ID],
        state_secret: SecretType,
        redirect_url: str | None = ...,
        associate_by_email: bool = ...,
        is_verified_by_default: bool = ...,
        *,
        csrf_token_cookie_name: str = ...,
        csrf_token_cookie_path: str = ...,
        csrf_token_cookie_domain: str | None = ...,
        csrf_token_cookie_secure: bool = ...,
        csrf_token_cookie_httponly: bool = ...,
        csrf_token_cookie_samesite: Literal["lax", "strict", "none"] = ...,
    ) -> APIRouter: ...
    def get_oauth_associate_router(
        self,
        oauth_client: BaseOAuth2,
        user_schema: type[schemas.U],
        state_secret: SecretType,
        redirect_url: str | None = ...,
        requires_verification: bool = ...,
        csrf_token_cookie_name: str = ...,
        csrf_token_cookie_path: str = ...,
        csrf_token_cookie_domain: str | None = ...,
        csrf_token_cookie_secure: bool = ...,
        csrf_token_cookie_httponly: bool = ...,
        csrf_token_cookie_samesite: Literal["lax", "strict", "none"] = ...,
    ) -> APIRouter: ...
    def get_users_router(
        self,
        user_schema: type[schemas.U],
        user_update_schema: type[schemas.UU],
        requires_verification: bool = ...,
    ) -> APIRouter: ...
