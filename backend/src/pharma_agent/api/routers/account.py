"""Account flows over one-time codes, the current user's profile, and account settings."""

import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, EmailStr, Field

from pharma_agent.api.deps import (
    ClientIp,
    ContainerDep,
    CurrentSessionToken,
    RequestLocale,
    SessionLogin,
    UserIdDependency,
    require_account,
)
from pharma_agent.api.problems import problem_responses
from pharma_agent.application.account.service import AccountView, SessionView

CODE_PATTERN = r"^\d{6}$"


class EmailBody(BaseModel):
    """An email address that a one-time code is sent to."""

    email: EmailStr


class EmailCodeBody(EmailBody):
    """An email address and the six-digit code sent to it."""

    code: str = Field(pattern=CODE_PATTERN)


class EmailVerifyBody(EmailCodeBody):
    """Email verification code, plus the password when the account has one."""

    # Required whenever the account has a password; see AccountService.verify_email.
    password: str | None = Field(default=None, max_length=1024)


class PasswordResetBody(EmailCodeBody):
    """Email reset code and the new password."""

    password: str = Field(min_length=1, max_length=1024)


class PhoneBody(BaseModel):
    """A phone number that a one-time code is sent to."""

    phone: str = Field(min_length=3, max_length=32)


class PhoneCodeBody(PhoneBody):
    """A phone number and the six-digit code sent to it."""

    code: str = Field(pattern=CODE_PATTERN)


class PasswordChangeBody(BaseModel):
    """New password; `current_password` is needed when the account already has one."""

    current_password: str | None = None
    new_password: str = Field(min_length=1, max_length=1024)


class ProfileUpdate(BaseModel):
    """The current user's new display name."""

    display_name: str = Field(min_length=1, max_length=100)


def accepted() -> Response:
    """An empty 202 Accepted response."""
    return Response(status_code=status.HTTP_202_ACCEPTED)


def no_content() -> Response:
    """An empty 204 No Content response."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def uid(user_id: str) -> uuid.UUID:
    """Parse a user id string into a UUID.

    Args:
        user_id: Hex form of the user's UUID.

    Returns:
        The user id as a UUID.
    """
    return uuid.UUID(hex=user_id)


def _add_code_routes(router: APIRouter, Login: Any) -> None:
    """Register the sign-in, verification and reset routes that use one-time codes.

    Args:
        router: Router the routes are added to.
        Login: Annotated dependency that signs the user in and returns the response.
    """

    @router.post(
        "/auth/email/verify/request",
        status_code=202,
        name="auth:email.verify_request",
        tags=["auth"],
        response_class=Response,
        responses=problem_responses(422, 429, 503),
    )
    async def request_email_verification(
        body: EmailBody, container: ContainerDep, locale: RequestLocale, ip: ClientIp
    ) -> Response:
        await require_account(container).request_email_verification(
            body.email, locale=locale, client_ip=ip
        )
        return accepted()

    @router.post(
        "/auth/email/verify",
        status_code=204,
        name="auth:email.verify",
        tags=["auth"],
        response_class=Response,
        responses=problem_responses(400, 403, 422, 429),
    )
    async def verify_email(
        body: EmailVerifyBody, container: ContainerDep, login: Login, ip: ClientIp
    ) -> Response:
        user_id = await require_account(container).verify_email(
            body.email, body.code, body.password, client_ip=ip
        )
        return await login(user_id)

    @router.post(
        "/auth/password/forgot",
        status_code=202,
        name="auth:password.forgot",
        tags=["auth"],
        response_class=Response,
        responses=problem_responses(422, 429, 503),
    )
    async def forgot_password(
        body: EmailBody, container: ContainerDep, locale: RequestLocale, ip: ClientIp
    ) -> Response:
        await require_account(container).request_password_reset(
            body.email, locale=locale, client_ip=ip
        )
        return accepted()

    @router.post(
        "/auth/password/reset",
        status_code=204,
        name="auth:password.reset",
        tags=["auth"],
        response_class=Response,
        responses=problem_responses(400, 422),
    )
    async def reset_password(
        body: PasswordResetBody, container: ContainerDep
    ) -> Response:
        await require_account(container).reset_password(
            body.email, body.code, body.password
        )
        return no_content()

    @router.post(
        "/auth/phone/request",
        status_code=202,
        name="auth:phone.request",
        tags=["auth"],
        response_class=Response,
        responses=problem_responses(422, 429, 503),
    )
    async def request_phone_login(
        body: PhoneBody, container: ContainerDep, locale: RequestLocale, ip: ClientIp
    ) -> Response:
        await require_account(container).request_phone_login(
            body.phone, locale=locale, client_ip=ip
        )
        return accepted()

    @router.post(
        "/auth/phone/login",
        status_code=204,
        name="auth:phone.login",
        tags=["auth"],
        response_class=Response,
        responses=problem_responses(400, 403, 422),
    )
    async def phone_login(
        body: PhoneCodeBody, container: ContainerDep, login: Login
    ) -> Response:
        user_id = await require_account(container).login_with_phone(
            body.phone, body.code
        )
        return await login(user_id)


def _add_profile_routes(router: APIRouter, UserId: Any) -> None:
    """Register the routes that read and update the current user's profile.

    Args:
        router: Router the routes are added to.
        UserId: Annotated dependency resolving the signed-in user's id.
    """

    @router.get(
        "/users/me",
        name="users:current_user",
        tags=["users"],
        responses=problem_responses(401),
    )
    async def current_user(user_id: UserId, container: ContainerDep) -> AccountView:
        return await require_account(container).get_account(uid(user_id))

    @router.patch(
        "/users/me",
        name="users:patch_current_user",
        tags=["users"],
        responses=problem_responses(401, 422),
    )
    async def patch_current_user(
        body: ProfileUpdate, user_id: UserId, container: ContainerDep
    ) -> AccountView:
        return await require_account(container).update_profile(
            uid(user_id), body.display_name
        )


def _add_contact_routes(router: APIRouter, UserId: Any) -> None:
    """Register the routes that change the account's email address and phone number.

    Args:
        router: Router the routes are added to.
        UserId: Annotated dependency resolving the signed-in user's id.
    """

    @router.post(
        "/account/email",
        status_code=202,
        name="account:email.request",
        tags=["account"],
        response_class=Response,
        responses=problem_responses(401, 409, 422, 429, 503),
    )
    async def request_email_change(
        body: EmailBody,
        user_id: UserId,
        container: ContainerDep,
        locale: RequestLocale,
        ip: ClientIp,
    ) -> Response:
        await require_account(container).request_email_change(
            uid(user_id), body.email, locale=locale, client_ip=ip
        )
        return accepted()

    @router.post(
        "/account/email/confirm",
        name="account:email.confirm",
        tags=["account"],
        responses=problem_responses(400, 401, 409, 422),
    )
    async def confirm_email_change(
        body: EmailCodeBody,
        user_id: UserId,
        container: ContainerDep,
        locale: RequestLocale,
    ) -> AccountView:
        return await require_account(container).confirm_email_change(
            uid(user_id), body.email, body.code, locale=locale
        )

    @router.post(
        "/account/phone",
        status_code=202,
        name="account:phone.request",
        tags=["account"],
        response_class=Response,
        responses=problem_responses(401, 409, 422, 429, 503),
    )
    async def request_phone_change(
        body: PhoneBody,
        user_id: UserId,
        container: ContainerDep,
        locale: RequestLocale,
        ip: ClientIp,
    ) -> Response:
        await require_account(container).request_phone_change(
            uid(user_id), body.phone, locale=locale, client_ip=ip
        )
        return accepted()

    @router.post(
        "/account/phone/confirm",
        name="account:phone.confirm",
        tags=["account"],
        responses=problem_responses(400, 401, 409, 422),
    )
    async def confirm_phone_change(
        body: PhoneCodeBody, user_id: UserId, container: ContainerDep
    ) -> AccountView:
        return await require_account(container).confirm_phone_change(
            uid(user_id), body.phone, body.code
        )


def _add_security_routes(router: APIRouter, UserId: Any) -> None:
    """Register the password, linked Google account and session routes.

    Args:
        router: Router the routes are added to.
        UserId: Annotated dependency resolving the signed-in user's id.
    """

    @router.put(
        "/account/password",
        status_code=204,
        name="account:password.change",
        tags=["account"],
        response_class=Response,
        responses=problem_responses(400, 401, 422),
    )
    async def change_password(
        body: PasswordChangeBody, user_id: UserId, container: ContainerDep
    ) -> Response:
        await require_account(container).change_password(
            uid(user_id),
            current_password=body.current_password,
            new_password=body.new_password,
        )
        return no_content()

    @router.delete(
        "/account/oauth/google",
        name="account:google.unlink",
        tags=["account"],
        responses=problem_responses(401, 409),
    )
    async def unlink_google(user_id: UserId, container: ContainerDep) -> AccountView:
        return await require_account(container).unlink_google(uid(user_id))

    @router.get(
        "/account/sessions",
        name="account:sessions.list",
        tags=["account"],
        responses=problem_responses(401),
    )
    async def list_sessions(
        user_id: UserId, container: ContainerDep, token: CurrentSessionToken
    ) -> list[SessionView]:
        return await require_account(container).list_sessions(uid(user_id), token)

    @router.delete(
        "/account/sessions/{session_id}",
        status_code=204,
        name="account:sessions.revoke",
        tags=["account"],
        response_class=Response,
        responses=problem_responses(401, 404),
    )
    async def revoke_session(
        session_id: str, user_id: UserId, container: ContainerDep
    ) -> Response:
        await require_account(container).revoke_session(uid(user_id), session_id)
        return no_content()

    @router.delete(
        "/account/sessions",
        status_code=204,
        name="account:sessions.revoke_others",
        tags=["account"],
        response_class=Response,
        responses=problem_responses(401),
    )
    async def revoke_other_sessions(
        user_id: UserId, container: ContainerDep, token: CurrentSessionToken
    ) -> Response:
        await require_account(container).revoke_other_sessions(uid(user_id), token)
        return no_content()


def build_account_router(
    current_user_id: UserIdDependency, session_login: Callable[..., Any]
) -> APIRouter:
    """Routes for one-time-code flows, the current user's profile, sign-in methods and sessions."""
    router = APIRouter()
    UserId = Annotated[str, Depends(current_user_id)]
    Login = Annotated[SessionLogin, Depends(session_login)]
    _add_code_routes(router, Login)
    _add_profile_routes(router, UserId)
    _add_contact_routes(router, UserId)
    _add_security_routes(router, UserId)
    return router
