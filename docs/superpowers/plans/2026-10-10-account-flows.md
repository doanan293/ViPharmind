# Account Flows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đăng ký và đăng nhập bằng email + mật khẩu, số điện thoại + mã SMS, hoặc Google trên một tài khoản; xác minh bằng mã OTP 6 số; quản lý email, số điện thoại, mật khẩu, Google và phiên đăng nhập trong cài đặt.

**Architecture:** Use case nằm trong `application/account/service.py` (`AccountService`), nói chuyện với Postgres, bộ gửi email/SMS và bộ băm mật khẩu qua các port trong `domain/account/ports.py`. fastapi-users vẫn lo session cookie, đăng ký, đăng nhập bằng mật khẩu và Google; `UserManager` được ghi đè để chặn email chưa xác minh, giới hạn đăng nhập sai và sửa quy tắc liên kết Google. Router mới `api/routers/account.py` phục vụ các luồng OTP, `/users/me` và cài đặt tài khoản. Frontend thêm bước nhập mã, đăng nhập bằng số điện thoại, quên mật khẩu và mục Tài khoản trong cài đặt.

**Tech Stack:** FastAPI, fastapi-users 15.0.5, SQLAlchemy 2 async, Alembic, Postgres, `phonenumbers`, `aiosmtplib`, httpx; React Router 8, TanStack Query, orval, react-hook-form + zod 4, shadcn (`input-otp`, `tabs`), `libphonenumber-js`, Vitest browser, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-10-account-flows-design.md`

## Global Constraints

- Mã OTP: 6 chữ số, hạn 10 phút, dùng một lần; sai quá 5 lần thì mã hết hiệu lực; tạo mã mới làm mã chưa dùng cùng `(purpose, destination)` hết hiệu lực.
- Mã lưu dạng HMAC-SHA256 với khoá `PHARMA_AUTH__OTP_SECRET` (≥ 32 ký tự), gộp `purpose` và `destination`; so sánh bằng `hmac.compare_digest`.
- Giới hạn gửi mã: 5 lần/giờ mỗi địa chỉ, cách nhau tối thiểu 60 giây; 20 lần/giờ mỗi IP. Đăng nhập sai: 10 lần trong 15 phút theo email và theo IP. Vượt giới hạn trả `429` kèm `Retry-After`.
- Mặc định chỉ gửi SMS tới số Việt Nam (`PHARMA_SMS__ALLOWED_COUNTRY_CODES=["VN"]`). Số lưu dạng E.164.
- Mật khẩu: 8 đến 128 ký tự, áp dụng cho mọi đường đặt mật khẩu (đăng ký, đặt lại, đổi).
- Không để lộ tài khoản tồn tại: `forgot`, `verify/request` luôn trả `202`; giới hạn gửi áp dụng trước khi tra tài khoản.
- Gửi email/SMS ngay trong request (Cloud Run giảm CPU sau response). Gửi thất bại: mã bị huỷ, trả `503 DELIVERY_FAILED`.
- Liên kết Google: chỉ tự liên kết khi email trùng một email **đã xác minh**; email chưa xác minh trả `400 OAUTH_USER_ALREADY_EXISTS`.
- Quy tắc kiến trúc: `application` không import fastapi-users, SQLAlchemy, httpx (xem `backend/tests/architecture/test_layering.py`); router không import `infrastructure` (chỉ `api/deps.py`, `api/app.py`); frontend: `settings` không import `auth` (xem `frontend/app/architecture.test.ts`).
- Không thêm dòng `Co-Authored-By` vào commit.

### Điều chỉnh so với spec (đã chốt khi lập plan)

- `UserRead` của fastapi-users không thể có `email` NULL (pyrefly báo `bad-override-mutable-attribute`). `/users/me` (GET, PATCH) chuyển sang router mới và trả `AccountView`; route admin `/users/{id}` của fastapi-users bị bỏ (không ai dùng, mảng 3 làm trang quản trị riêng). Tên route `users:current_user`, `users:patch_current_user` giữ nguyên nên hàm orval phía frontend không đổi tên.
- Ngôn ngữ email/SMS lấy từ header `Accept-Language`; frontend đặt header này bằng ngôn ngữ giao diện cho mọi request.
- Liên kết Google cho tài khoản chưa có email thì nhận luôn email Google (đã được Google xác minh); nếu email đó thuộc tài khoản khác thì từ chối.

## Review Focus

- Số điện thoại gõ kiểu Việt Nam ("0912 345 678", "091.234.5678", "+84 91 234 5678", "84912345678") phải ra cùng `+84912345678` và cùng một tài khoản → test ở Task 2 (`test_local_and_international_forms_normalize_to_one_number`).
- Email khác hoa thường hoặc thừa khoảng trắng ("  An@Example.COM ") ở đăng ký, xác minh, quên mật khẩu phải trỏ cùng tài khoản → test ở Task 4 (`test_get_by_email_ignores_case`) và Task 6 (`test_verify_email_normalizes_the_address`).
- Cùng một mã gửi hai lần (bấm đúp, hai tab) chỉ được dùng một lần, lần sau báo mã sai chứ không lỗi 500 → test ở Task 4 (`test_consume_succeeds_once`) và Task 6 (`test_a_code_cannot_be_used_twice`).
- Bấm "Gửi lại" trong thời gian chờ nhận `429` có `Retry-After`; giao diện đếm ngược theo đúng số giây đó thay vì chỉ báo lỗi → test ở Task 9 (`test_resend_inside_the_cooldown_is_429_with_retry_after`) và Task 11 (`ResendCodeButton` test).
- Thu hồi chính phiên đang dùng trong danh sách phiên: request tiếp theo phải là `401`, không lỗi khác → test ở Task 9 (`test_revoking_the_current_session_logs_out`).

---

## File Structure

Backend (`backend/src/pharma_agent/`):

| File | Trách nhiệm |
| --- | --- |
| `domain/account/__init__.py` | Package |
| `domain/account/models.py` | `OtpPurpose`, `Channel`, `SignInMethod`, `AccountUser`, `OneTimeCode`, `SessionRecord`, `AccountConflict`, `normalize_email`, `session_id_of` |
| `domain/account/phone.py` | `normalize_phone` (thư viện `phonenumbers`) |
| `domain/account/codes.py` | Sinh mã, băm mã, so mã; hằng `CODE_TTL`, `MAX_ATTEMPTS` |
| `domain/account/passwords.py` | Quy tắc độ dài mật khẩu |
| `domain/account/ports.py` | Port: `AccountRepository`, `OneTimeCodeStore`, `RateLimiter`, `EmailSender`, `SmsSender`, `PasswordHasher`, `SessionStore`; `DeliveryError` |
| `application/account/__init__.py` | Package |
| `application/account/errors.py` | Lỗi ứng dụng của feature account |
| `application/account/messages.py` | Nội dung email/SMS tiếng Việt, tiếng Anh; `Locale`, `locale_from_accept_language` |
| `application/account/service.py` | `AccountService`, `AccountPolicy`, `AccountView`, `SessionView` |
| `infrastructure/persistence/postgres/tables.py` | Sửa `UserTable`, `AccessTokenTable`; thêm `OneTimeCodeTable`, `RateLimitBucketTable` |
| `infrastructure/persistence/postgres/migrations/versions/0013_account_flows.py` | Migration |
| `infrastructure/persistence/postgres/account_repository.py` | `PostgresAccountRepository` |
| `infrastructure/persistence/postgres/one_time_codes.py` | `PostgresOneTimeCodeStore` |
| `infrastructure/persistence/postgres/rate_limiter.py` | `PostgresRateLimiter` |
| `infrastructure/persistence/postgres/session_store.py` | `PostgresSessionStore` |
| `infrastructure/notifications/__init__.py` | Package |
| `infrastructure/notifications/email.py` | `LogEmailSender`, `SmtpEmailSender`, `ResendEmailSender` |
| `infrastructure/notifications/sms.py` | `LogSmsSender` |
| `infrastructure/notifications/factory.py` | `build_email_sender`, `build_sms_sender` |
| `infrastructure/auth/passwords.py` | `FastapiUsersPasswordHasher` |
| `infrastructure/auth/users.py` | `UserManager` ghi đè, `TrackedDatabaseStrategy`, `login_session`, router associate |
| `infrastructure/account_factory.py` | `build_account_service` |
| `infrastructure/container.py` | Trường `account`, tham số `email_sender`, `sms_sender` |
| `infrastructure/settings.py` | `EmailSettings`, `SmsSettings`, `AuthSettings.otp_secret` |
| `infrastructure/auth/session_cleanup.py` | Dọn mã và bucket cũ |
| `api/deps.py` | `require_account`, `RequestLocale`, `ClientIp`, `CurrentSessionToken`, `SessionLogin` |
| `api/routers/account.py` | Route OTP, `/users/me`, cài đặt tài khoản |
| `api/errors.py` | Map lỗi mới, header `Retry-After` |
| `api/app.py` | Gắn router mới |
| `cli.py` | `cleanup-sessions` dọn thêm mã và bucket |

Backend tests: `tests/account_fakes.py`, `tests/domain/account/test_*.py`, `tests/application/test_account_service*.py`, `tests/infrastructure/test_account_*.py`, `tests/infrastructure/test_notifications.py`, `tests/api/test_account_api_postgres.py`, cùng các test hiện có cần sửa.

Frontend (`frontend/app/`):

| File | Trách nhiệm |
| --- | --- |
| `api/fetcher.ts` | Header `Accept-Language` |
| `api/problem.ts` | `ApiError.retryAfter` |
| `components/ui/input-otp.tsx`, `components/ui/tabs.tsx` | Sinh bằng shadcn CLI |
| `components/otp-code-field.tsx` | Ô nhập 6 số |
| `components/code-step.tsx` | Bước nhập mã dùng chung (mã, lỗi, gửi lại) |
| `components/resend-code-button.tsx` | Nút gửi lại có đếm ngược |
| `hooks/use-countdown.ts` | Đếm ngược theo giây |
| `lib/phone.ts` | `phoneSchema` (libphonenumber-js) |
| `features/auth/components/VerifyEmailStep.tsx` | Bước xác minh email |
| `features/auth/components/PhoneLoginForm.tsx` | Đăng nhập/đăng ký bằng số điện thoại |
| `features/auth/components/ForgotPasswordForm.tsx` | Quên mật khẩu |
| `features/auth/lib/account-label.ts` | Tên hiển thị của tài khoản |
| `features/settings/components/AccountSection.tsx` | Mục Tài khoản |
| `features/settings/components/ContactChangeFlow.tsx` | Đổi email/số điện thoại bằng mã |
| `features/settings/components/GoogleSetting.tsx` | Liên kết/gỡ Google |
| `features/settings/components/SessionsList.tsx` | Danh sách phiên |
| `features/settings/lib/google-link.ts` | Bắt đầu và hoàn tất liên kết Google |
| `routes/auth/forgot-password.tsx`, `routes/auth/google-link-callback.tsx` | Route mới |

---

### Task 1: Settings và thư viện mới

**Files:**
- Modify: `backend/pyproject.toml`, `uv.lock`
- Modify: `backend/src/pharma_agent/infrastructure/settings.py`
- Modify: `backend/tests/infrastructure/test_settings.py`
- Modify: `backend/tests/api/harness.py:61-64`, `backend/tests/api/postgres_app.py:22-36`, `backend/tests/e2e/server.py` (hàm `e2e_settings`)

**Interfaces:**
- Produces: `EmailSettings(provider: Literal["log","smtp","resend"], sender, smtp_host, smtp_port, smtp_username, smtp_password, resend_api_key, timeout_seconds)`, `SmsSettings(provider: Literal["log"], allowed_country_codes: list[str])`, `Settings.email`, `Settings.sms`, `AuthSettings.otp_secret: SecretStr | None`, `AuthSettings.require_otp_secret() -> str`.

- [ ] **Step 1: Thêm thư viện**

```bash
cd backend && uv add "phonenumbers>=9.0,<10" "aiosmtplib>=4.0,<5" && cd .. && uv lock
```

Expected: `backend/pyproject.toml` có hai dòng mới trong `dependencies`, `uv.lock` cập nhật.

- [ ] **Step 2: Viết test settings (fail)**

Thêm vào `backend/tests/infrastructure/test_settings.py`:

```python
def test_account_settings_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.email.provider == "log"
    assert settings.email.smtp_host == "smtp.gmail.com"
    assert settings.email.smtp_port == 587
    assert settings.sms.provider == "log"
    assert settings.sms.allowed_country_codes == ["VN"]
    assert settings.auth.otp_secret is None
    with pytest.raises(ValueError, match="PHARMA_AUTH__OTP_SECRET"):
        settings.auth.require_otp_secret()


def test_otp_secret_needs_32_characters() -> None:
    with pytest.raises(ValidationError, match="otp_secret"):
        Settings(_env_file=None, auth={"otp_secret": "short"})
    settings = Settings(_env_file=None, auth={"otp_secret": "o" * 32})
    assert settings.auth.require_otp_secret() == "o" * 32


def test_email_and_sms_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHARMA_EMAIL__PROVIDER", "smtp")
    monkeypatch.setenv("PHARMA_EMAIL__SMTP_USERNAME", "an@gmail.com")
    monkeypatch.setenv("PHARMA_SMS__ALLOWED_COUNTRY_CODES", '["VN", "US"]')
    settings = Settings(_env_file=None)
    assert settings.email.provider == "smtp"
    assert settings.email.smtp_username == "an@gmail.com"
    assert settings.sms.allowed_country_codes == ["VN", "US"]
```

Nếu file chưa import `ValidationError`, thêm `from pydantic import ValidationError`.

- [ ] **Step 3: Chạy test, xác nhận fail**

Run: `uv run --directory backend pytest -q tests/infrastructure/test_settings.py`
Expected: FAIL, `Settings` chưa có `email`.

- [ ] **Step 4: Cài đặt settings**

Trong `backend/src/pharma_agent/infrastructure/settings.py`:
1. Thêm `Literal` vào import `typing` nếu chưa có.
2. Trong `AuthSettings`, thêm trường và mở rộng validator:

```python
    otp_secret: SecretStr | None = None
```

```python
    @field_validator("jwt_secret", "csrf_secret", "otp_secret")
```

```python
    def require_otp_secret(self) -> str:
        if self.otp_secret is None:
            raise ValueError("set PHARMA_AUTH__OTP_SECRET (at least 32 characters)")
        return self.otp_secret.get_secret_value()
```

3. Thêm hai model trước `class Settings`:

```python
class EmailSettings(BaseModel):
    """Where account emails go. `log` writes them to the log: local runs and tests only."""

    provider: Literal["log", "smtp", "resend"] = "log"
    sender: str = "ViPharMind <no-reply@vipharmind.local>"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    resend_api_key: SecretStr | None = None
    timeout_seconds: float = Field(default=10.0, gt=0)


class SmsSettings(BaseModel):
    """`log` writes SMS to the log; a real provider is chosen before launch."""

    provider: Literal["log"] = "log"
    # ISO 3166 regions SMS may go to; anything else is rejected before sending.
    allowed_country_codes: list[str] = Field(default_factory=lambda: ["VN"])
```

4. Trong `Settings`, thêm:

```python
    email: EmailSettings = Field(default_factory=EmailSettings)
    sms: SmsSettings = Field(default_factory=SmsSettings)
```

- [ ] **Step 5: Thêm `otp_secret` vào settings của test và server e2e**

`backend/tests/api/harness.py`, hàm `settings()`:

```python
def settings() -> Settings:
    return Settings(
        _env_file=None,
        auth={"jwt_secret": "s" * 40, "csrf_secret": "c" * 40, "otp_secret": "o" * 40},
    )
```

`backend/tests/api/postgres_app.py`: thêm hằng `OTP_SECRET = "o" * 40` và đổi dòng `auth=` thành:

```python
auth = (
    {
        "jwt_secret": JWT_SECRET,
        "csrf_secret": CSRF_SECRET,
        "otp_secret": OTP_SECRET,
        **(auth or {}),
    },
)
```

`backend/tests/e2e/server.py`: thêm hằng `E2E_OTP_SECRET = "e2e-otp-secret-for-tests-only-0123456789"` và trong `e2e_settings` thêm `"otp_secret": E2E_OTP_SECRET,` vào dict `auth`.

- [ ] **Step 6: Chạy test**

Run: `uv run --directory backend pytest -q tests/infrastructure/test_settings.py && uv run --directory backend pytest -q`
Expected: PASS toàn bộ.

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml uv.lock backend/src/pharma_agent/infrastructure/settings.py backend/tests
git commit -m "feat(backend): add email, SMS and OTP settings for account flows"
```

---

### Task 2: Domain `account`

**Files:**
- Create: `backend/src/pharma_agent/domain/account/__init__.py` (rỗng), `models.py`, `phone.py`, `codes.py`, `passwords.py`, `ports.py`
- Test: `backend/tests/domain/account/__init__.py` (rỗng), `test_models.py`, `test_phone.py`, `test_codes.py`, `test_passwords.py`

**Interfaces:**
- Produces (dùng ở mọi task sau):
  - `OtpPurpose` (`VERIFY_EMAIL`, `RESET_PASSWORD`, `CHANGE_EMAIL`, `PHONE_LOGIN`, `CHANGE_PHONE`), `Channel` (`EMAIL`, `SMS`), `CHANNEL_BY_PURPOSE: dict[OtpPurpose, Channel]`, `SignInMethod` (`PASSWORD`, `PHONE`, `GOOGLE`)
  - `AccountUser(id: uuid.UUID, email: str | None, phone_number: str | None, display_name: str, email_verified: bool, phone_verified: bool, password_set: bool, google_linked: bool, is_active: bool, is_superuser: bool)` với `.sign_in_methods() -> set[SignInMethod]`
  - `OneTimeCode(id, purpose, destination, user_id: uuid.UUID | None, digest: str, expires_at: datetime, attempts: int)`
  - `SessionRecord(token: str, created_at: datetime, last_used_at: datetime | None, user_agent: str, ip_address: str)`
  - `AccountConflict(DomainError)`, `normalize_email(str) -> str`, `session_id_of(token: str) -> str`
  - `normalize_phone(raw: str, *, default_region: str = "VN") -> tuple[str, str]` trả `(e164, region)`, ném `InvalidPhoneNumber`
  - `CODE_TTL: timedelta`, `MAX_ATTEMPTS = 5`, `generate_code() -> str`, `code_digest(secret, purpose, destination, code) -> str`, `code_matches(secret, record: OneTimeCode, code: str) -> bool`
  - `PASSWORD_MIN_LENGTH = 8`, `PASSWORD_MAX_LENGTH = 128`, `password_problem(password: str) -> str | None`
  - Port trong `ports.py` (chữ ký ở Step 9)

- [ ] **Step 1: Viết test models (fail)**

`backend/tests/domain/account/test_models.py`:

```python
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
```

- [ ] **Step 2: Viết test phone, codes, passwords (fail)**

`backend/tests/domain/account/test_phone.py`:

```python
import pytest

from pharma_agent.domain.account.phone import InvalidPhoneNumber, normalize_phone


@pytest.mark.parametrize(
    "raw",
    ["0912345678", "0912 345 678", "091.234.5678", "+84 91 234 5678", "84912345678"],
)
def test_local_and_international_forms_normalize_to_one_number(raw: str) -> None:
    assert normalize_phone(raw) == ("+84912345678", "VN")


def test_foreign_numbers_keep_their_region() -> None:
    assert normalize_phone("+1 650 253 0000") == ("+16502530000", "US")


@pytest.mark.parametrize("raw", ["", "12345", "not a number", "+84 12"])
def test_invalid_numbers_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidPhoneNumber):
        normalize_phone(raw)
```

`backend/tests/domain/account/test_codes.py`:

```python
import uuid
from datetime import UTC, datetime

from pharma_agent.domain.account.codes import (
    CODE_TTL,
    MAX_ATTEMPTS,
    code_digest,
    code_matches,
    generate_code,
)
from pharma_agent.domain.account.models import OneTimeCode, OtpPurpose

SECRET = "o" * 40


def test_codes_are_six_digits() -> None:
    codes = {generate_code() for _ in range(200)}
    assert all(len(code) == 6 and code.isdigit() for code in codes)
    assert len(codes) > 150


def test_policy_constants() -> None:
    assert CODE_TTL.total_seconds() == 600
    assert MAX_ATTEMPTS == 5


def test_digest_binds_purpose_and_destination() -> None:
    base = code_digest(SECRET, OtpPurpose.VERIFY_EMAIL, "an@example.com", "123456")
    assert base != code_digest(
        SECRET, OtpPurpose.RESET_PASSWORD, "an@example.com", "123456"
    )
    assert base != code_digest(
        SECRET, OtpPurpose.VERIFY_EMAIL, "bo@example.com", "123456"
    )
    assert base != code_digest(
        "x" * 40, OtpPurpose.VERIFY_EMAIL, "an@example.com", "123456"
    )
    assert "123456" not in base


def test_code_matches_only_the_issued_code() -> None:
    record = OneTimeCode(
        id=uuid.uuid4(),
        purpose=OtpPurpose.PHONE_LOGIN,
        destination="+84912345678",
        user_id=None,
        digest=code_digest(SECRET, OtpPurpose.PHONE_LOGIN, "+84912345678", "000123"),
        expires_at=datetime(2026, 10, 10, tzinfo=UTC),
        attempts=0,
    )
    assert code_matches(SECRET, record, "000123")
    assert not code_matches(SECRET, record, "000124")
```

`backend/tests/domain/account/test_passwords.py`:

```python
from pharma_agent.domain.account.passwords import password_problem


def test_password_length_rule() -> None:
    assert password_problem("a" * 7) == "password must be at least 8 characters"
    assert password_problem("a" * 8) is None
    assert password_problem("a" * 128) is None
    assert password_problem("a" * 129) == "password must be at most 128 characters"
```

- [ ] **Step 3: Chạy, xác nhận fail**

Run: `uv run --directory backend pytest -q tests/domain/account`
Expected: FAIL, `ModuleNotFoundError: pharma_agent.domain.account`.

- [ ] **Step 4: Viết `models.py`**

```python
"""Accounts that sign in with a password, a phone number or Google, and their codes."""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pharma_agent.domain.shared.errors import DomainError


class OtpPurpose(StrEnum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"
    CHANGE_EMAIL = "change_email"
    PHONE_LOGIN = "phone_login"
    CHANGE_PHONE = "change_phone"


class Channel(StrEnum):
    EMAIL = "email"
    SMS = "sms"


CHANNEL_BY_PURPOSE: dict[OtpPurpose, Channel] = {
    OtpPurpose.VERIFY_EMAIL: Channel.EMAIL,
    OtpPurpose.RESET_PASSWORD: Channel.EMAIL,
    OtpPurpose.CHANGE_EMAIL: Channel.EMAIL,
    OtpPurpose.PHONE_LOGIN: Channel.SMS,
    OtpPurpose.CHANGE_PHONE: Channel.SMS,
}


class SignInMethod(StrEnum):
    PASSWORD = "password"
    PHONE = "phone"
    GOOGLE = "google"


class AccountConflict(DomainError):
    """The email or phone number already belongs to another account."""

    code = "ACCOUNT_CONFLICT"


@dataclass(frozen=True)
class AccountUser:
    id: uuid.UUID
    email: str | None
    phone_number: str | None
    display_name: str
    email_verified: bool
    phone_verified: bool
    password_set: bool
    google_linked: bool
    is_active: bool
    is_superuser: bool

    def sign_in_methods(self) -> set[SignInMethod]:
        """Ways this account can sign in now; a password needs a verified email to log in with."""
        methods: set[SignInMethod] = set()
        if self.password_set and self.email is not None and self.email_verified:
            methods.add(SignInMethod.PASSWORD)
        if self.phone_number is not None and self.phone_verified:
            methods.add(SignInMethod.PHONE)
        if self.google_linked:
            methods.add(SignInMethod.GOOGLE)
        return methods


@dataclass(frozen=True)
class OneTimeCode:
    id: uuid.UUID
    purpose: OtpPurpose
    destination: str
    user_id: uuid.UUID | None
    digest: str
    expires_at: datetime
    attempts: int


@dataclass(frozen=True)
class SessionRecord:
    token: str
    created_at: datetime
    last_used_at: datetime | None
    user_agent: str
    ip_address: str


def normalize_email(email: str) -> str:
    return email.strip().lower()


def session_id_of(token: str) -> str:
    """A public id for a session; the token itself is the cookie secret and never leaves."""
    return hashlib.sha256(token.encode()).hexdigest()[:32]
```

- [ ] **Step 5: Viết `phone.py`**

```python
"""Phone numbers in E.164, parsed with Google's libphonenumber rules."""

import phonenumbers

from pharma_agent.domain.shared.errors import DomainError


class InvalidPhoneNumber(DomainError):
    code = "PHONE_NUMBER_INVALID"


def normalize_phone(raw: str, *, default_region: str = "VN") -> tuple[str, str]:
    """`(e164, region)` for a number typed in local or international form."""
    try:
        number = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneNumber(raw) from exc
    if not phonenumbers.is_valid_number(number):
        raise InvalidPhoneNumber(raw)
    region = phonenumbers.region_code_for_number(number) or ""
    e164 = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
    return e164, region
```

Nếu `"84912345678"` (không có `+`) không ra `+84912345678` ở Step 10, thêm nhánh: nếu `raw.strip()` chỉ gồm chữ số, bắt đầu bằng mã quốc gia của `default_region` (`phonenumbers.country_code_for_region`) và parse theo `default_region` không hợp lệ, thì parse lại `"+" + digits`. Viết nhánh này chỉ khi test đó fail.

- [ ] **Step 6: Viết `codes.py`**

```python
"""Six-digit one-time codes, stored only as an HMAC bound to their purpose and destination."""

import hashlib
import hmac
import secrets
from datetime import timedelta

from pharma_agent.domain.account.models import OneTimeCode, OtpPurpose

CODE_LENGTH = 6
CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5


def generate_code() -> str:
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def code_digest(secret: str, purpose: OtpPurpose, destination: str, code: str) -> str:
    message = "\x1f".join((purpose.value, destination, code)).encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def code_matches(secret: str, record: OneTimeCode, code: str) -> bool:
    expected = code_digest(secret, record.purpose, record.destination, code)
    return hmac.compare_digest(record.digest, expected)
```

- [ ] **Step 7: Viết `passwords.py`**

```python
"""Password rule shared by registration, reset and change."""

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


def password_problem(password: str) -> str | None:
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"password must be at least {PASSWORD_MIN_LENGTH} characters"
    if len(password) > PASSWORD_MAX_LENGTH:
        return f"password must be at most {PASSWORD_MAX_LENGTH} characters"
    return None
```

- [ ] **Step 8: Chạy test domain**

Run: `uv run --directory backend pytest -q tests/domain/account`
Expected: PASS.

- [ ] **Step 9: Viết `ports.py`**

```python
"""What the account use cases need from storage, delivery and password hashing."""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from pharma_agent.domain.account.models import (
    AccountUser,
    OneTimeCode,
    OtpPurpose,
    SessionRecord,
)
from pharma_agent.domain.shared.errors import DomainError


class DeliveryError(DomainError):
    """An email or SMS provider refused or failed to take the message."""

    code = "DELIVERY_ERROR"


class AccountRepository(Protocol):
    async def get(self, user_id: uuid.UUID) -> AccountUser | None: ...

    async def get_by_email(self, email: str) -> AccountUser | None:
        """Case-insensitive lookup."""
        ...

    async def get_by_phone(self, phone: str) -> AccountUser | None: ...

    async def create_phone_user(
        self, *, phone: str, hashed_password: str, now: datetime
    ) -> AccountUser:
        """A verified phone-only account; raises AccountConflict if the number is taken."""
        ...

    async def mark_email_verified(self, user_id: uuid.UUID, now: datetime) -> None: ...

    async def set_email(self, user_id: uuid.UUID, email: str, now: datetime) -> None:
        """Set a verified email; raises AccountConflict if another account has it."""
        ...

    async def set_phone(self, user_id: uuid.UUID, phone: str, now: datetime) -> None:
        """Set a verified phone number; raises AccountConflict if another account has it."""
        ...

    async def set_password(self, user_id: uuid.UUID, hashed_password: str) -> None:
        """Store the hash and mark the password as chosen by the user."""
        ...

    async def hashed_password(self, user_id: uuid.UUID) -> str | None: ...

    async def unlink_oauth(self, user_id: uuid.UUID, oauth_name: str) -> None: ...

    async def update_display_name(
        self, user_id: uuid.UUID, display_name: str
    ) -> None: ...


class OneTimeCodeStore(Protocol):
    async def issue(
        self,
        *,
        purpose: OtpPurpose,
        destination: str,
        user_id: uuid.UUID | None,
        digest: str,
        expires_at: datetime,
        now: datetime,
    ) -> uuid.UUID:
        """Store a code and drop every unused code for the same purpose and destination."""
        ...

    async def find_active(
        self, purpose: OtpPurpose, destination: str, now: datetime
    ) -> OneTimeCode | None:
        """The newest unused, unexpired code with fewer than MAX_ATTEMPTS failures."""
        ...

    async def record_failure(self, code_id: uuid.UUID) -> None: ...

    async def consume(self, code_id: uuid.UUID, now: datetime) -> bool:
        """Mark the code used; False if it was already used (exactly one caller wins)."""
        ...

    async def revoke(self, code_id: uuid.UUID, now: datetime) -> None: ...


class RateLimiter(Protocol):
    async def check(self, key: str, *, limit: int, window_seconds: int) -> float | None:
        """Seconds until `key` may act again, or None while it is under `limit`."""
        ...

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> float | None:
        """Count one action; seconds to wait if this action went over `limit`."""
        ...


class EmailSender(Protocol):
    async def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        """Raises DeliveryError when the provider does not take the message."""
        ...


class SmsSender(Protocol):
    async def send(self, *, to: str, text: str) -> None:
        """Raises DeliveryError when the provider does not take the message."""
        ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, hashed: str) -> bool: ...


class SessionStore(Protocol):
    async def for_user(self, user_id: uuid.UUID) -> Sequence[SessionRecord]:
        """Unexpired sessions, newest first."""
        ...

    async def delete(self, user_id: uuid.UUID, token: str) -> bool: ...

    async def delete_all(
        self, user_id: uuid.UUID, *, keep: str | None = None
    ) -> int: ...
```

- [ ] **Step 10: Chạy test, pyrefly, kiến trúc**

Run: `uv run --directory backend pytest -q tests/domain/account tests/architecture && uv run --directory backend pyrefly check`
Expected: PASS, `0 errors`.

- [ ] **Step 11: Commit**

```bash
git add backend/src/pharma_agent/domain/account backend/tests/domain/account
git commit -m "feat(backend): add the account domain (codes, phone numbers, ports)"
```

---

### Task 3: Bảng và migration 0013

**Files:**
- Modify: `backend/src/pharma_agent/infrastructure/persistence/postgres/tables.py`
- Create: `backend/src/pharma_agent/infrastructure/persistence/postgres/migrations/versions/0013_account_flows.py`
- Modify: `backend/tests/infrastructure/test_migrations.py`, `backend/tests/infrastructure/test_persistence_metadata.py`

**Interfaces:**
- Produces: `UserTable.phone_number`, `.email_verified_at`, `.phone_verified_at`, `.password_set`, property `UserTable.email_verified`, `.phone_verified`, `.google_linked`; `AccessTokenTable.user_agent`, `.ip_address`, `.last_used_at`; `OneTimeCodeTable`, `RateLimitBucketTable`.

- [ ] **Step 1: Viết test migration (fail)**

Trong `backend/tests/infrastructure/test_migrations.py`, thêm `"one_time_codes"` và `"rate_limit_buckets"` vào `EXPECTED_TABLES`, rồi thêm:

```python
def _columns(connection: Connection, table: str) -> dict[str, bool]:
    return {
        column["name"]: bool(column["nullable"])
        for column in inspect(connection).get_columns(table)
    }


async def test_account_columns_exist(migrated_dsn: str) -> None:
    engine = create_async_engine(migrated_dsn)
    async with engine.connect() as connection:
        users = await connection.run_sync(_columns, "user")
        tokens = await connection.run_sync(_columns, "access_tokens")
    await engine.dispose()
    assert users["email"] is True
    assert {"phone_number", "email_verified_at", "phone_verified_at"} <= users.keys()
    assert users["password_set"] is False
    assert {"user_agent", "ip_address", "last_used_at"} <= tokens.keys()


async def test_a_user_needs_an_email_or_a_phone(migrated_dsn: str) -> None:
    engine = create_async_engine(migrated_dsn)
    async with engine.begin() as connection:
        with pytest.raises(IntegrityError, match="ck_user_email_or_phone"):
            await connection.exec_driver_sql(
                'INSERT INTO "user" (id, hashed_password, is_active, is_superuser, '
                "is_verified) VALUES (gen_random_uuid(), 'x', true, false, false)"
            )
    await engine.dispose()
```

Thêm import `from sqlalchemy.exc import IntegrityError`. Trong `backend/tests/infrastructure/test_persistence_metadata.py`, thêm `"one_time_codes"` và `"rate_limit_buckets"` vào tập bảng mong đợi.

- [ ] **Step 2: Chạy, xác nhận fail**

Run: `uv run --directory backend pytest -q -m integration tests/infrastructure/test_migrations.py`
Expected: FAIL (bảng mới chưa có).

- [ ] **Step 3: Sửa `tables.py`**

Thêm `Boolean` và `TYPE_CHECKING` vào import. Thay `UserTable` và `AccessTokenTable`:

```python
class UserTable(SQLAlchemyBaseUserTableUUID, Base):
    """fastapi-users users (table name `user`) plus profile and sign-in columns."""

    __table_args__ = (
        CheckConstraint(
            "email IS NOT NULL OR phone_number IS NOT NULL", name="email_or_phone"
        ),
    )

    # fastapi-users types `email` as str. Phone-only accounts store NULL, so the column is
    # redeclared nullable at runtime while type checkers keep the base declaration;
    # code that reads it for any account converts with `row.email or None`.
    if not TYPE_CHECKING:
        email = mapped_column(String(320), unique=True, index=True, nullable=True)

    phone_number: Mapped[str | None] = mapped_column(
        String(16), unique=True, index=True, nullable=True
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    phone_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_set: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    display_name: Mapped[str] = mapped_column(
        String(120), nullable=False, server_default=""
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    oauth_accounts: Mapped[list[OAuthAccountTable]] = relationship(lazy="joined")

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def phone_verified(self) -> bool:
        return self.phone_verified_at is not None

    @property
    def google_linked(self) -> bool:
        return any(account.oauth_name == "google" for account in self.oauth_accounts)


class AccessTokenTable(SQLAlchemyBaseAccessTokenTableUUID, Base):
    """fastapi-users database sessions behind the `pharma_session` cookie."""

    __tablename__ = "access_tokens"

    user_agent: Mapped[str] = mapped_column(
        String(255), nullable=False, server_default=""
    )
    ip_address: Mapped[str] = mapped_column(
        String(45), nullable=False, server_default=""
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

Giữ nguyên phần còn lại của `AccessTokenTable` nếu có. Thêm hai bảng mới (cuối file):

```python
class OneTimeCodeTable(Base):
    """Hashed one-time codes; see domain/account/codes.py."""

    __tablename__ = "one_time_codes"
    __table_args__ = (
        Index("ix_one_time_codes_lookup", "purpose", "destination", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[str] = mapped_column(String(8), nullable=False)
    destination: Mapped[str] = mapped_column(String(320), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RateLimitBucketTable(Base):
    """Fixed-window counters behind domain/account/ports.RateLimiter."""

    __tablename__ = "rate_limit_buckets"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    count: Mapped[int] = mapped_column(Integer, nullable=False)
```

- [ ] **Step 4: Viết migration 0013**

```python
"""Account flows: nullable email, phone sign-in, one-time codes, rate limits, session details.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-10 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("user", "email", existing_type=sa.String(length=320), nullable=True)
    op.add_column(
        "user", sa.Column("phone_number", sa.String(length=16), nullable=True)
    )
    op.create_index(op.f("ix_user_phone_number"), "user", ["phone_number"], unique=True)
    op.add_column(
        "user",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user",
        sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user",
        sa.Column(
            "password_set", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_user_email_or_phone"),
        "user",
        "email IS NOT NULL OR phone_number IS NOT NULL",
    )
    # Accounts fastapi-users already marked verified keep working without a new code.
    op.execute('UPDATE "user" SET email_verified_at = now() WHERE is_verified')

    op.add_column(
        "access_tokens",
        sa.Column(
            "user_agent", sa.String(length=255), server_default="", nullable=False
        ),
    )
    op.add_column(
        "access_tokens",
        sa.Column(
            "ip_address", sa.String(length=45), server_default="", nullable=False
        ),
    )
    op.add_column(
        "access_tokens",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "one_time_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=8), nullable=False),
        sa.Column("destination", sa.String(length=320), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_one_time_codes_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_one_time_codes")),
    )
    op.create_index(
        "ix_one_time_codes_lookup",
        "one_time_codes",
        ["purpose", "destination", "created_at"],
        unique=False,
    )
    op.create_table(
        "rate_limit_buckets",
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint(
            "key", "window_start", name=op.f("pk_rate_limit_buckets")
        ),
    )


def downgrade() -> None:
    op.drop_table("rate_limit_buckets")
    op.drop_index("ix_one_time_codes_lookup", table_name="one_time_codes")
    op.drop_table("one_time_codes")
    op.drop_column("access_tokens", "last_used_at")
    op.drop_column("access_tokens", "ip_address")
    op.drop_column("access_tokens", "user_agent")
    op.drop_constraint(op.f("ck_user_email_or_phone"), "user", type_="check")
    op.drop_column("user", "password_set")
    op.drop_column("user", "phone_verified_at")
    op.drop_column("user", "email_verified_at")
    op.drop_index(op.f("ix_user_phone_number"), table_name="user")
    op.drop_column("user", "phone_number")
    # Phone-only accounts cannot exist once email is required again.
    op.execute('DELETE FROM "user" WHERE email IS NULL')
    op.alter_column(
        "user", "email", existing_type=sa.String(length=320), nullable=False
    )
```

`server_default` của `created_at` trong model là `func.now()`; Alembic so sánh không phân biệt cách viết `now()`, nên `test_upgrade_head_matches_the_models` vẫn khớp. Nếu test đó báo khác biệt server default, đổi migration sang `server_default=sa.func.now()`.

- [ ] **Step 5: Chạy test migration và toàn bộ**

Run: `uv run --directory backend pytest -q -m integration tests/infrastructure && uv run --directory backend pytest -q && uv run --directory backend pyrefly check`
Expected: PASS, `0 errors`.

- [ ] **Step 6: Commit**

```bash
git add backend/src/pharma_agent/infrastructure/persistence/postgres backend/tests/infrastructure
git commit -m "feat(backend): add account tables and migration 0013"
```

---

### Task 4: Adapter Postgres cho account

**Files:**
- Create: `backend/src/pharma_agent/infrastructure/persistence/postgres/account_repository.py`, `one_time_codes.py`, `rate_limiter.py`, `session_store.py`
- Test: `backend/tests/infrastructure/test_account_postgres.py`

**Interfaces:**
- Consumes: Task 2 ports, Task 3 tables.
- Produces: `PostgresAccountRepository(sessions)`, `PostgresOneTimeCodeStore(sessions)`, `PostgresRateLimiter(sessions, clock)`, `PostgresSessionStore(sessions, *, lifetime_seconds: int, clock: Clock)`.

- [ ] **Step 1: Viết test integration (fail)**

`backend/tests/infrastructure/test_account_postgres.py`:

```python
import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import insert, text

from pharma_agent.domain.account.codes import MAX_ATTEMPTS
from pharma_agent.domain.account.models import AccountConflict, OtpPurpose
from pharma_agent.domain.shared.clock import FixedClock
from pharma_agent.infrastructure.persistence.postgres.account_repository import (
    PostgresAccountRepository,
)
from pharma_agent.infrastructure.persistence.postgres.database import Database
from pharma_agent.infrastructure.persistence.postgres.one_time_codes import (
    PostgresOneTimeCodeStore,
)
from pharma_agent.infrastructure.persistence.postgres.rate_limiter import (
    PostgresRateLimiter,
)
from pharma_agent.infrastructure.persistence.postgres.session_store import (
    PostgresSessionStore,
)
from pharma_agent.infrastructure.persistence.postgres.tables import (
    AccessTokenTable,
    OAuthAccountTable,
    UserTable,
)

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)


@pytest.fixture
async def database(migrated_dsn: str) -> AsyncIterator[Database]:
    db = Database(migrated_dsn, pool_size=2)
    async with db.engine.begin() as connection:
        await connection.execute(
            text('TRUNCATE "user", one_time_codes, rate_limit_buckets CASCADE')
        )
    yield db
    await db.dispose()


async def add_user(db: Database, email: str | None, **values: object) -> uuid.UUID:
    user_id = uuid.uuid4()
    async with db.sessions.begin() as session:
        await session.execute(
            insert(UserTable).values(
                id=user_id,
                email=email,
                hashed_password="hash",
                is_active=True,
                is_superuser=False,
                is_verified=False,
                **values,
            )
        )
    return user_id


async def test_get_by_email_ignores_case(database: Database) -> None:
    repo = PostgresAccountRepository(database.sessions)
    user_id = await add_user(database, "An@Example.com")
    found = await repo.get_by_email("an@example.COM")
    assert found is not None and found.id == user_id
    assert found.email_verified is False and found.password_set is True


async def test_phone_user_round_trip_and_conflicts(database: Database) -> None:
    repo = PostgresAccountRepository(database.sessions)
    user = await repo.create_phone_user(
        phone="+84912345678", hashed_password="h", now=NOW
    )
    assert user.email is None and user.phone_verified and not user.password_set
    with pytest.raises(AccountConflict):
        await repo.create_phone_user(phone="+84912345678", hashed_password="h", now=NOW)
    other = await add_user(database, "bo@example.com")
    with pytest.raises(AccountConflict):
        await repo.set_phone(other, "+84912345678", NOW)


async def test_updates_mark_verified_and_password(database: Database) -> None:
    repo = PostgresAccountRepository(database.sessions)
    user_id = await add_user(database, "an@example.com", password_set=False)
    await repo.mark_email_verified(user_id, NOW)
    await repo.set_password(user_id, "new-hash")
    await repo.update_display_name(user_id, "An")
    user = await repo.get(user_id)
    assert user is not None and user.email_verified and user.password_set
    assert user.display_name == "An"
    assert await repo.hashed_password(user_id) == "new-hash"
    taken = await add_user(database, "bo@example.com")
    with pytest.raises(AccountConflict):
        await repo.set_email(taken, "an@example.com", NOW)


async def test_unlink_oauth_removes_the_google_account(database: Database) -> None:
    repo = PostgresAccountRepository(database.sessions)
    user_id = await add_user(database, "an@example.com")
    async with database.sessions.begin() as session:
        await session.execute(
            insert(OAuthAccountTable).values(
                id=uuid.uuid4(),
                user_id=user_id,
                oauth_name="google",
                access_token="t",
                account_id="g-1",
                account_email="an@example.com",
            )
        )
    linked = await repo.get(user_id)
    assert linked is not None and linked.google_linked
    await repo.unlink_oauth(user_id, "google")
    unlinked = await repo.get(user_id)
    assert unlinked is not None and not unlinked.google_linked


async def test_issue_replaces_unused_codes_and_find_respects_limits(
    database: Database,
) -> None:
    store = PostgresOneTimeCodeStore(database.sessions)
    kwargs = {
        "purpose": OtpPurpose.VERIFY_EMAIL,
        "destination": "an@example.com",
        "user_id": None,
        "expires_at": NOW + timedelta(minutes=10),
        "now": NOW,
    }
    first = await store.issue(digest="a" * 64, **kwargs)
    second = await store.issue(digest="b" * 64, **kwargs)
    active = await store.find_active(OtpPurpose.VERIFY_EMAIL, "an@example.com", NOW)
    assert active is not None and active.id == second and active.id != first
    assert (
        await store.find_active(
            OtpPurpose.VERIFY_EMAIL, "an@example.com", NOW + timedelta(minutes=11)
        )
        is None
    )
    for _ in range(MAX_ATTEMPTS):
        await store.record_failure(second)
    assert (
        await store.find_active(OtpPurpose.VERIFY_EMAIL, "an@example.com", NOW) is None
    )


async def test_consume_succeeds_once(database: Database) -> None:
    store = PostgresOneTimeCodeStore(database.sessions)
    code_id = await store.issue(
        purpose=OtpPurpose.PHONE_LOGIN,
        destination="+84912345678",
        user_id=None,
        digest="c" * 64,
        expires_at=NOW + timedelta(minutes=10),
        now=NOW,
    )
    results = await asyncio.gather(
        store.consume(code_id, NOW), store.consume(code_id, NOW)
    )
    assert sorted(results) == [False, True]


async def test_rate_limiter_counts_per_window(database: Database) -> None:
    clock = FixedClock(NOW + timedelta(seconds=30))
    limiter = PostgresRateLimiter(database.sessions, clock)
    assert await limiter.hit("k", limit=2, window_seconds=60) is None
    assert await limiter.hit("k", limit=2, window_seconds=60) is None
    assert await limiter.check("k", limit=2, window_seconds=60) == pytest.approx(30)
    assert await limiter.hit("k", limit=2, window_seconds=60) == pytest.approx(30)
    assert await limiter.check("other", limit=2, window_seconds=60) is None
    later = PostgresRateLimiter(
        database.sessions, FixedClock(NOW + timedelta(seconds=61))
    )
    assert await later.check("k", limit=2, window_seconds=60) is None


async def test_session_store_lists_and_deletes(database: Database) -> None:
    user_id = await add_user(database, "an@example.com")
    async with database.sessions.begin() as session:
        for token, age in (("t-old", 10), ("t-new", 1), ("t-expired", 9999)):
            await session.execute(
                insert(AccessTokenTable).values(
                    token=token,
                    user_id=user_id,
                    created_at=NOW - timedelta(hours=age),
                    user_agent="Firefox",
                    ip_address="10.0.0.1",
                )
            )
    store = PostgresSessionStore(
        database.sessions, lifetime_seconds=7 * 24 * 3600, clock=FixedClock(NOW)
    )
    assert [record.token for record in await store.for_user(user_id)] == [
        "t-new",
        "t-old",
    ]
    assert await store.delete(user_id, "t-old") is True
    assert await store.delete(user_id, "t-old") is False
    assert await store.delete_all(user_id, keep="t-new") == 1  # only t-expired remained
    assert [record.token for record in await store.for_user(user_id)] == ["t-new"]
```

Kiểm tra dòng `delete_all(..., keep="t-new") == 1`: sau khi xoá `t-old`, còn `t-new` và `t-expired`; xoá tất cả trừ `t-new` là 1 dòng.

- [ ] **Step 2: Chạy, xác nhận fail**

Run: `uv run --directory backend pytest -q -m integration tests/infrastructure/test_account_postgres.py`
Expected: FAIL, module chưa tồn tại.

- [ ] **Step 3: Viết `account_repository.py`**

```python
"""AccountRepository over the fastapi-users `user` and `oauth_account` tables."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.domain.account.models import AccountConflict, AccountUser
from pharma_agent.infrastructure.persistence.postgres.tables import (
    OAuthAccountTable,
    UserTable,
)


def _account(row: UserTable) -> AccountUser:
    return AccountUser(
        id=row.id,
        # Phone-only accounts store NULL (see UserTable).
        email=row.email or None,
        phone_number=row.phone_number,
        display_name=row.display_name,
        email_verified=row.email_verified,
        phone_verified=row.phone_verified,
        password_set=row.password_set,
        google_linked=row.google_linked,
        is_active=row.is_active,
        is_superuser=row.is_superuser,
    )


class PostgresAccountRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def _one(self, statement: Select[tuple[UserTable]]) -> AccountUser | None:
        async with self._sessions() as session:
            row = (await session.execute(statement)).unique().scalar_one_or_none()
        return None if row is None else _account(row)

    async def get(self, user_id: uuid.UUID) -> AccountUser | None:
        return await self._one(select(UserTable).where(UserTable.id == user_id))

    async def get_by_email(self, email: str) -> AccountUser | None:
        return await self._one(
            select(UserTable).where(func.lower(UserTable.email) == email.lower())
        )

    async def get_by_phone(self, phone: str) -> AccountUser | None:
        return await self._one(select(UserTable).where(UserTable.phone_number == phone))

    async def create_phone_user(
        self, *, phone: str, hashed_password: str, now: datetime
    ) -> AccountUser:
        user_id = uuid.uuid4()
        try:
            async with self._sessions.begin() as session:
                await session.execute(
                    insert(UserTable).values(
                        id=user_id,
                        email=None,
                        phone_number=phone,
                        phone_verified_at=now,
                        hashed_password=hashed_password,
                        password_set=False,
                        is_active=True,
                        is_superuser=False,
                        is_verified=True,
                    )
                )
        except IntegrityError as exc:
            raise AccountConflict(phone) from exc
        user = await self.get(user_id)
        if user is None:
            raise AccountConflict(phone)
        return user

    async def _update(self, user_id: uuid.UUID, values: dict[str, Any]) -> None:
        try:
            async with self._sessions.begin() as session:
                await session.execute(
                    update(UserTable).where(UserTable.id == user_id).values(**values)
                )
        except IntegrityError as exc:
            raise AccountConflict(str(user_id)) from exc

    async def mark_email_verified(self, user_id: uuid.UUID, now: datetime) -> None:
        await self._update(user_id, {"email_verified_at": now, "is_verified": True})

    async def set_email(self, user_id: uuid.UUID, email: str, now: datetime) -> None:
        await self._update(
            user_id, {"email": email, "email_verified_at": now, "is_verified": True}
        )

    async def set_phone(self, user_id: uuid.UUID, phone: str, now: datetime) -> None:
        await self._update(
            user_id,
            {"phone_number": phone, "phone_verified_at": now, "is_verified": True},
        )

    async def set_password(self, user_id: uuid.UUID, hashed_password: str) -> None:
        await self._update(
            user_id, {"hashed_password": hashed_password, "password_set": True}
        )

    async def hashed_password(self, user_id: uuid.UUID) -> str | None:
        async with self._sessions() as session:
            return (
                await session.execute(
                    select(UserTable.hashed_password).where(UserTable.id == user_id)
                )
            ).scalar_one_or_none()

    async def unlink_oauth(self, user_id: uuid.UUID, oauth_name: str) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                delete(OAuthAccountTable).where(
                    OAuthAccountTable.user_id == user_id,
                    OAuthAccountTable.oauth_name == oauth_name,
                )
            )

    async def update_display_name(self, user_id: uuid.UUID, display_name: str) -> None:
        await self._update(user_id, {"display_name": display_name})
```

- [ ] **Step 4: Viết `one_time_codes.py`**

```python
"""OneTimeCodeStore over `one_time_codes`."""

import uuid
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.domain.account.codes import MAX_ATTEMPTS
from pharma_agent.domain.account.models import (
    CHANNEL_BY_PURPOSE,
    OneTimeCode,
    OtpPurpose,
)
from pharma_agent.infrastructure.persistence.postgres.tables import OneTimeCodeTable


class PostgresOneTimeCodeStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def issue(
        self,
        *,
        purpose: OtpPurpose,
        destination: str,
        user_id: uuid.UUID | None,
        digest: str,
        expires_at: datetime,
        now: datetime,
    ) -> uuid.UUID:
        code_id = uuid.uuid4()
        async with self._sessions.begin() as session:
            await session.execute(
                delete(OneTimeCodeTable).where(
                    OneTimeCodeTable.purpose == purpose.value,
                    OneTimeCodeTable.destination == destination,
                    OneTimeCodeTable.consumed_at.is_(None),
                )
            )
            session.add(
                OneTimeCodeTable(
                    id=code_id,
                    purpose=purpose.value,
                    channel=CHANNEL_BY_PURPOSE[purpose].value,
                    destination=destination,
                    user_id=user_id,
                    code_hash=digest,
                    expires_at=expires_at,
                    attempts=0,
                    created_at=now,
                )
            )
        return code_id

    async def find_active(
        self, purpose: OtpPurpose, destination: str, now: datetime
    ) -> OneTimeCode | None:
        statement = (
            select(OneTimeCodeTable)
            .where(
                OneTimeCodeTable.purpose == purpose.value,
                OneTimeCodeTable.destination == destination,
                OneTimeCodeTable.consumed_at.is_(None),
                OneTimeCodeTable.expires_at > now,
                OneTimeCodeTable.attempts < MAX_ATTEMPTS,
            )
            .order_by(OneTimeCodeTable.created_at.desc())
            .limit(1)
        )
        async with self._sessions() as session:
            row = (await session.execute(statement)).scalar_one_or_none()
        if row is None:
            return None
        return OneTimeCode(
            id=row.id,
            purpose=OtpPurpose(row.purpose),
            destination=row.destination,
            user_id=row.user_id,
            digest=row.code_hash,
            expires_at=row.expires_at,
            attempts=row.attempts,
        )

    async def record_failure(self, code_id: uuid.UUID) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                update(OneTimeCodeTable)
                .where(OneTimeCodeTable.id == code_id)
                .values(attempts=OneTimeCodeTable.attempts + 1)
            )

    async def consume(self, code_id: uuid.UUID, now: datetime) -> bool:
        async with self._sessions.begin() as session:
            result = await session.execute(
                update(OneTimeCodeTable)
                .where(
                    OneTimeCodeTable.id == code_id,
                    OneTimeCodeTable.consumed_at.is_(None),
                )
                .values(consumed_at=now)
                .returning(OneTimeCodeTable.id)
            )
            return result.first() is not None

    async def revoke(self, code_id: uuid.UUID, now: datetime) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                update(OneTimeCodeTable)
                .where(
                    OneTimeCodeTable.id == code_id,
                    OneTimeCodeTable.consumed_at.is_(None),
                )
                .values(consumed_at=now)
            )
```

- [ ] **Step 5: Viết `rate_limiter.py`**

```python
"""Fixed-window RateLimiter over `rate_limit_buckets`."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.domain.shared.clock import Clock
from pharma_agent.infrastructure.persistence.postgres.tables import RateLimitBucketTable


class PostgresRateLimiter:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], clock: Clock
    ) -> None:
        self._sessions = sessions
        self._clock = clock

    def _window(self, window_seconds: int) -> tuple[datetime, float]:
        """The current window's start and the seconds left in it."""
        epoch = self._clock.now().timestamp()
        start = epoch - epoch % window_seconds
        return datetime.fromtimestamp(start, UTC), start + window_seconds - epoch

    async def check(self, key: str, *, limit: int, window_seconds: int) -> float | None:
        start, remaining = self._window(window_seconds)
        async with self._sessions() as session:
            count = (
                await session.execute(
                    select(RateLimitBucketTable.count).where(
                        RateLimitBucketTable.key == key,
                        RateLimitBucketTable.window_start == start,
                    )
                )
            ).scalar_one_or_none()
        return remaining if (count or 0) >= limit else None

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> float | None:
        start, remaining = self._window(window_seconds)
        statement = (
            insert(RateLimitBucketTable)
            .values(key=key, window_start=start, count=1)
            .on_conflict_do_update(
                index_elements=["key", "window_start"],
                set_={"count": RateLimitBucketTable.count + 1},
            )
            .returning(RateLimitBucketTable.count)
        )
        async with self._sessions.begin() as session:
            count = (await session.execute(statement)).scalar_one()
        return remaining if count > limit else None
```

- [ ] **Step 6: Viết `session_store.py`**

```python
"""SessionStore over the fastapi-users `access_tokens` table."""

import uuid
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.domain.account.models import SessionRecord
from pharma_agent.domain.shared.clock import Clock
from pharma_agent.infrastructure.persistence.postgres.tables import AccessTokenTable


class PostgresSessionStore:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        lifetime_seconds: int,
        clock: Clock,
    ) -> None:
        self._sessions = sessions
        self._lifetime = timedelta(seconds=lifetime_seconds)
        self._clock = clock

    async def for_user(self, user_id: uuid.UUID) -> Sequence[SessionRecord]:
        oldest = self._clock.now() - self._lifetime
        statement = (
            select(AccessTokenTable)
            .where(
                AccessTokenTable.user_id == user_id,
                AccessTokenTable.created_at >= oldest,
            )
            .order_by(AccessTokenTable.created_at.desc())
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).scalars().all()
        return [
            SessionRecord(
                token=row.token,
                created_at=row.created_at,
                last_used_at=row.last_used_at,
                user_agent=row.user_agent,
                ip_address=row.ip_address,
            )
            for row in rows
        ]

    async def delete(self, user_id: uuid.UUID, token: str) -> bool:
        async with self._sessions.begin() as session:
            result = await session.execute(
                delete(AccessTokenTable)
                .where(
                    AccessTokenTable.user_id == user_id, AccessTokenTable.token == token
                )
                .returning(AccessTokenTable.token)
            )
            return result.first() is not None

    async def delete_all(self, user_id: uuid.UUID, *, keep: str | None = None) -> int:
        statement = delete(AccessTokenTable).where(AccessTokenTable.user_id == user_id)
        if keep is not None:
            statement = statement.where(AccessTokenTable.token != keep)
        async with self._sessions.begin() as session:
            result = await session.execute(statement.returning(AccessTokenTable.token))
            return len(result.all())
```

- [ ] **Step 7: Chạy test, pyrefly**

Run: `uv run --directory backend pytest -q -m integration tests/infrastructure/test_account_postgres.py && uv run --directory backend pyrefly check`
Expected: PASS, `0 errors`.

- [ ] **Step 8: Commit**

```bash
git add backend/src/pharma_agent/infrastructure/persistence/postgres backend/tests/infrastructure/test_account_postgres.py
git commit -m "feat(backend): add Postgres adapters for accounts, codes, rate limits and sessions"
```

---

### Task 5: Nội dung tin nhắn và bộ gửi email/SMS

**Files:**
- Create: `backend/src/pharma_agent/application/account/__init__.py` (rỗng), `backend/src/pharma_agent/application/account/messages.py`
- Create: `backend/src/pharma_agent/infrastructure/notifications/__init__.py` (rỗng), `email.py`, `sms.py`, `factory.py`
- Test: `backend/tests/application/test_account_messages.py`, `backend/tests/infrastructure/test_notifications.py`

**Interfaces:**
- Consumes: `OtpPurpose`, `CODE_TTL`, `EmailSender`, `SmsSender`, `DeliveryError`, `EmailSettings`, `SmsSettings`.
- Produces: `Locale = Literal["vi", "en"]`, `locale_from_accept_language(header: str | None) -> Locale`, `EmailContent(subject, text, html)`, `code_email(purpose, code, locale) -> EmailContent`, `code_sms(purpose, code, locale) -> str`, `email_changed_notice(new_email, locale) -> EmailContent`; `LogEmailSender()`, `SmtpEmailSender(*, host, port, username, password, sender, timeout)`, `ResendEmailSender(*, api_key, sender, timeout, client=None)`, `LogSmsSender()`, `build_email_sender(EmailSettings) -> EmailSender`, `build_sms_sender(SmsSettings) -> SmsSender`.

- [ ] **Step 1: Viết test messages (fail)**

```python
import pytest

from pharma_agent.application.account.messages import (
    Locale,
    code_email,
    code_sms,
    email_changed_notice,
    locale_from_accept_language,
)
from pharma_agent.domain.account.models import OtpPurpose


@pytest.mark.parametrize(
    ("header", "locale"),
    [
        (None, "vi"),
        ("", "vi"),
        ("vi", "vi"),
        ("en", "en"),
        ("en-US,en;q=0.9", "en"),
        ("fr", "vi"),
    ],
)
def test_locale_from_accept_language(header: str | None, locale: str) -> None:
    assert locale_from_accept_language(header) == locale


@pytest.mark.parametrize("purpose", list(OtpPurpose))
@pytest.mark.parametrize("locale", ["vi", "en"])
def test_every_purpose_has_a_message_with_the_code(
    purpose: OtpPurpose, locale: Locale
) -> None:
    email = code_email(purpose, "042137", locale)
    assert "042137" in email.text and "042137" in email.html and email.subject
    sms = code_sms(purpose, "042137", locale)
    assert "042137" in sms and len(sms) <= 160 and sms.isascii()


def test_notice_escapes_the_address() -> None:
    notice = email_changed_notice("<b>x</b>@example.com", "vi")
    assert "<b>x</b>" not in notice.html and "&lt;b&gt;" in notice.html
```

- [ ] **Step 2: Viết test bộ gửi (fail)**

```python
from email.message import EmailMessage
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr

from pharma_agent.domain.account.ports import DeliveryError
from pharma_agent.infrastructure.notifications import email as email_module
from pharma_agent.infrastructure.notifications.email import (
    LogEmailSender,
    ResendEmailSender,
    SmtpEmailSender,
)
from pharma_agent.infrastructure.notifications.factory import (
    build_email_sender,
    build_sms_sender,
)
from pharma_agent.infrastructure.notifications.sms import LogSmsSender
from pharma_agent.infrastructure.settings import EmailSettings, SmsSettings


async def test_smtp_sends_a_multipart_message(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, Any] = {}

    async def fake_send(message: EmailMessage, **kwargs: Any) -> None:
        sent["message"], sent["kwargs"] = message, kwargs

    monkeypatch.setattr(email_module.aiosmtplib, "send", fake_send)
    sender = SmtpEmailSender(
        host="smtp.gmail.com",
        port=587,
        username="an@gmail.com",
        password="app-password",
        sender="ViPharMind <an@gmail.com>",
        timeout=5.0,
    )
    await sender.send(
        to="bo@example.com", subject="Mã", text="123456", html="<p>123456</p>"
    )
    message: EmailMessage = sent["message"]
    assert (
        message["To"] == "bo@example.com"
        and message["From"] == "ViPharMind <an@gmail.com>"
    )
    assert [part.get_content_type() for part in message.iter_parts()] == [
        "text/plain",
        "text/html",
    ]
    assert (
        sent["kwargs"]["start_tls"] is True
        and sent["kwargs"]["username"] == "an@gmail.com"
    )


async def test_smtp_failures_become_delivery_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_send(message: EmailMessage, **kwargs: Any) -> None:
        raise email_module.aiosmtplib.SMTPException("refused")

    monkeypatch.setattr(email_module.aiosmtplib, "send", failing_send)
    sender = SmtpEmailSender(
        host="h", port=587, username="u", password="p", sender="s", timeout=5.0
    )
    with pytest.raises(DeliveryError):
        await sender.send(to="a@b.c", subject="s", text="t", html="h")


async def test_resend_posts_the_message_and_maps_errors() -> None:
    async with respx.mock(assert_all_called=True) as resend:
        route = resend.post("https://api.resend.com/emails").mock(
            side_effect=[httpx.Response(200, json={"id": "1"}), httpx.Response(422)]
        )
        sender = ResendEmailSender(
            api_key="re_key", sender="ViPharMind <no-reply@x.dev>", timeout=5.0
        )
        await sender.send(to="an@example.com", subject="S", text="T", html="H")
        request = route.calls[0].request
        assert request.headers["authorization"] == "Bearer re_key"
        assert b'"to":["an@example.com"]' in request.content
        with pytest.raises(DeliveryError):
            await sender.send(to="an@example.com", subject="S", text="T", html="H")


async def test_log_senders_accept_messages() -> None:
    await LogEmailSender().send(to="a@b.c", subject="s", text="t", html="h")
    await LogSmsSender().send(to="+84912345678", text="t")


def test_factories_follow_settings() -> None:
    assert isinstance(build_email_sender(EmailSettings()), LogEmailSender)
    smtp = EmailSettings(
        provider="smtp", smtp_username="u", smtp_password=SecretStr("p")
    )
    assert isinstance(build_email_sender(smtp), SmtpEmailSender)
    resend = EmailSettings(provider="resend", resend_api_key=SecretStr("k"))
    assert isinstance(build_email_sender(resend), ResendEmailSender)
    with pytest.raises(ValueError, match="SMTP_USERNAME"):
        build_email_sender(EmailSettings(provider="smtp"))
    with pytest.raises(ValueError, match="RESEND_API_KEY"):
        build_email_sender(EmailSettings(provider="resend"))
    assert isinstance(build_sms_sender(SmsSettings()), LogSmsSender)
```

Lưu `pytest.ini_options.filterwarnings = ["error"]`: log ở mức `warning` không phải `Warning` Python nên không làm fail.

- [ ] **Step 3: Chạy, xác nhận fail**

Run: `uv run --directory backend pytest -q tests/application/test_account_messages.py tests/infrastructure/test_notifications.py`
Expected: FAIL, module chưa tồn tại.

- [ ] **Step 4: Viết `application/account/messages.py`**

```python
"""Account emails and SMS in Vietnamese and English."""

from dataclasses import dataclass
from html import escape
from typing import Literal

from pharma_agent.domain.account.codes import CODE_TTL
from pharma_agent.domain.account.models import OtpPurpose

Locale = Literal["vi", "en"]
TTL_MINUTES = int(CODE_TTL.total_seconds() // 60)


@dataclass(frozen=True)
class EmailContent:
    subject: str
    text: str
    html: str


def locale_from_accept_language(header: str | None) -> Locale:
    first = (header or "").split(",")[0].strip().lower()
    return "en" if first.startswith("en") else "vi"


_SUBJECTS: dict[OtpPurpose, dict[Locale, str]] = {
    OtpPurpose.VERIFY_EMAIL: {
        "vi": "Mã xác minh email ViPharMind",
        "en": "Your ViPharMind verification code",
    },
    OtpPurpose.RESET_PASSWORD: {
        "vi": "Mã đặt lại mật khẩu ViPharMind",
        "en": "Your ViPharMind password reset code",
    },
    OtpPurpose.CHANGE_EMAIL: {
        "vi": "Xác nhận email mới cho ViPharMind",
        "en": "Confirm your new ViPharMind email",
    },
    OtpPurpose.PHONE_LOGIN: {
        "vi": "Mã đăng nhập ViPharMind",
        "en": "Your ViPharMind sign-in code",
    },
    OtpPurpose.CHANGE_PHONE: {
        "vi": "Xác nhận số điện thoại mới cho ViPharMind",
        "en": "Confirm your new ViPharMind phone number",
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
    "vi": "ViPharMind: ma xac minh cua ban la {code}, het han sau {minutes} phut.",
    "en": "ViPharMind: your code is {code}. It expires in {minutes} minutes.",
}
_CHANGED: dict[Locale, tuple[str, str]] = {
    "vi": (
        "Email ViPharMind của bạn đã được đổi",
        "Email đăng nhập ViPharMind của bạn vừa được đổi sang {email}. "
        "Nếu không phải bạn, hãy đặt lại mật khẩu và liên hệ hỗ trợ.",
    ),
    "en": (
        "Your ViPharMind email was changed",
        "The sign-in email of your ViPharMind account was changed to {email}. "
        "If this was not you, reset your password and contact support.",
    ),
}


def _html(subject: str, body: str, code: str | None = None) -> str:
    code_block = (
        ""
        if code is None
        else f'<p style="font-size:32px;font-weight:bold;letter-spacing:4px">{code}</p>'
    )
    return (
        '<div style="font-family:sans-serif;color:#1f2937">'
        f"<h2>{escape(subject)}</h2>{code_block}<p>{escape(body)}</p></div>"
    )


def code_email(purpose: OtpPurpose, code: str, locale: Locale) -> EmailContent:
    subject = _SUBJECTS[purpose][locale]
    text = _BODY[locale].format(code=code, minutes=TTL_MINUTES)
    return EmailContent(subject=subject, text=text, html=_html(subject, text, code))


def code_sms(purpose: OtpPurpose, code: str, locale: Locale) -> str:
    return _SMS[locale].format(code=code, minutes=TTL_MINUTES)


def email_changed_notice(new_email: str, locale: Locale) -> EmailContent:
    subject, body = _CHANGED[locale]
    text = body.format(email=new_email)
    return EmailContent(subject=subject, text=text, html=_html(subject, text))
```

`code_sms` nhận `purpose` để giữ chữ ký giống `code_email`; nội dung SMS hiện giống nhau cho mọi mục đích.

- [ ] **Step 5: Viết `infrastructure/notifications/email.py`**

```python
"""EmailSender adapters: log (local runs), SMTP (Gmail app password) and Resend."""

import logging
from email.message import EmailMessage

import aiosmtplib
import httpx

from pharma_agent.domain.account.ports import DeliveryError

logger = logging.getLogger(__name__)
RESEND_URL = "https://api.resend.com/emails"


class LogEmailSender:
    async def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        logger.warning(
            "email provider is 'log'; not sent to %s: %s | %s", to, subject, text
        )


class SmtpEmailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        timeout: float,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._timeout = timeout

    async def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)
        message.add_alternative(html, subtype="html")
        try:
            await aiosmtplib.send(
                message,
                hostname=self._host,
                port=self._port,
                username=self._username,
                password=self._password,
                start_tls=self._port != 465,
                use_tls=self._port == 465,
                timeout=self._timeout,
            )
        except (aiosmtplib.SMTPException, OSError) as exc:
            raise DeliveryError(f"SMTP delivery failed: {exc}") from exc


class ResendEmailSender:
    def __init__(
        self,
        *,
        api_key: str,
        sender: str,
        timeout: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._sender = sender
        self._timeout = timeout
        self._client = client

    async def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        payload = {
            "from": self._sender,
            "to": [to],
            "subject": subject,
            "text": text,
            "html": html,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            if self._client is not None:
                response = await self._client.post(
                    RESEND_URL, json=payload, headers=headers, timeout=self._timeout
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        RESEND_URL, json=payload, headers=headers
                    )
        except httpx.HTTPError as exc:
            raise DeliveryError(f"Resend request failed: {exc}") from exc
        if response.status_code >= 400:
            raise DeliveryError(f"Resend returned HTTP {response.status_code}")
```

Lưu ý test Resend kiểm tra `b'"to":["an@example.com"]'`: httpx mã hoá JSON gọn không khoảng trắng. Nếu phiên bản httpx thêm khoảng trắng, đổi assertion thành `json.loads(request.content)["to"] == ["an@example.com"]`.

- [ ] **Step 6: Viết `sms.py` và `factory.py`**

`sms.py`:

```python
"""SmsSender adapters. A paid provider is plugged in before launch (sub-project 5)."""

import logging

logger = logging.getLogger(__name__)


class LogSmsSender:
    async def send(self, *, to: str, text: str) -> None:
        logger.warning("SMS provider is 'log'; not sent to %s: %s", to, text)
```

`factory.py`:

```python
"""Senders chosen by PHARMA_EMAIL__* and PHARMA_SMS__* settings."""

from pharma_agent.domain.account.ports import EmailSender, SmsSender
from pharma_agent.infrastructure.notifications.email import (
    LogEmailSender,
    ResendEmailSender,
    SmtpEmailSender,
)
from pharma_agent.infrastructure.notifications.sms import LogSmsSender
from pharma_agent.infrastructure.settings import EmailSettings, SmsSettings


def build_email_sender(settings: EmailSettings) -> EmailSender:
    if settings.provider == "smtp":
        if settings.smtp_username is None or settings.smtp_password is None:
            raise ValueError(
                "set PHARMA_EMAIL__SMTP_USERNAME and PHARMA_EMAIL__SMTP_PASSWORD"
            )
        return SmtpEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password.get_secret_value(),
            sender=settings.sender,
            timeout=settings.timeout_seconds,
        )
    if settings.provider == "resend":
        if settings.resend_api_key is None:
            raise ValueError("set PHARMA_EMAIL__RESEND_API_KEY")
        return ResendEmailSender(
            api_key=settings.resend_api_key.get_secret_value(),
            sender=settings.sender,
            timeout=settings.timeout_seconds,
        )
    return LogEmailSender()


def build_sms_sender(settings: SmsSettings) -> SmsSender:
    return LogSmsSender()
```

`build_sms_sender` nhận `settings` để thêm nhà cung cấp sau mà không đổi chữ ký. Nếu ruff báo tham số không dùng (`ARG001`), thêm `if settings.provider == "log": return LogSmsSender()` và `raise ValueError(f"unknown SMS provider {settings.provider}")` cuối hàm.

- [ ] **Step 7: Chạy test, pyrefly, kiến trúc**

Run: `uv run --directory backend pytest -q tests/application/test_account_messages.py tests/infrastructure/test_notifications.py tests/architecture && uv run --directory backend pyrefly check`
Expected: PASS, `0 errors`.

- [ ] **Step 8: Commit**

```bash
git add backend/src/pharma_agent/application/account backend/src/pharma_agent/infrastructure/notifications backend/tests
git commit -m "feat(backend): add account messages and email/SMS senders"
```

---

### Task 6: `AccountService` phần 1: mã, xác minh email, quên mật khẩu, đăng nhập bằng điện thoại, giới hạn đăng nhập

**Files:**
- Create: `backend/src/pharma_agent/application/account/errors.py`, `backend/src/pharma_agent/application/account/service.py`
- Create: `backend/tests/account_fakes.py`
- Test: `backend/tests/application/test_account_service.py`

**Interfaces:**
- Consumes: Task 2 domain, Task 5 messages.
- Produces:
  - Lỗi (`application/account/errors.py`): `InvalidCode` (`OTP_INVALID`), `RateLimited(retry_after: float)` (`RATE_LIMITED`), `EmailAlreadyUsed`, `PhoneAlreadyUsed`, `LastSignInMethod`, `CurrentPasswordInvalid`, `PasswordInvalid(InvalidInput)`, `PhoneNumberInvalid(InvalidInput)`, `PhoneCountryNotAllowed(InvalidInput)`, `DeliveryFailed(ServiceUnavailable)`, `SessionNotFound`, `AccountNotFound`, `AccountDisabled`.
  - `AccountPolicy(otp_secret: str, allowed_sms_regions: frozenset[str] = frozenset({"VN"}), send_cooldown_seconds=60, sends_per_destination_per_hour=5, sends_per_ip_per_hour=20, login_failures_per_window=10, login_window_seconds=900)`.
  - `AccountService(*, accounts, codes, limiter, email, sms, hasher, sessions, clock, policy)` với các method của phần 1: `request_email_verification(email, *, locale, client_ip) -> None`, `verify_email(email, code) -> uuid.UUID`, `request_password_reset(email, *, locale, client_ip) -> None`, `reset_password(email, code, new_password) -> None`, `request_phone_login(phone, *, locale, client_ip) -> None`, `login_with_phone(phone, code) -> uuid.UUID`, `check_login_allowed(email, client_ip) -> None`, `record_login_failure(email, client_ip) -> None`.
  - `tests/account_fakes.py`: `MutableClock`, `PlainHasher`, `InMemoryAccounts`, `InMemoryCodes`, `InMemoryLimiter`, `RecordingEmailSender`, `RecordingSmsSender`, `InMemorySessions`, `code_in(text: str) -> str`, `AccountFakes`, `build_account_service(clock: MutableClock | None = None, policy: AccountPolicy | None = None) -> tuple[AccountService, AccountFakes]`.

- [ ] **Step 1: Viết `tests/account_fakes.py`**

```python
"""In-memory account ports for AccountService tests and the Postgres/E2E apps' senders."""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from pharma_agent.application.account.service import AccountPolicy, AccountService
from pharma_agent.domain.account.codes import MAX_ATTEMPTS
from pharma_agent.domain.account.models import (
    AccountConflict,
    AccountUser,
    OneTimeCode,
    OtpPurpose,
    SessionRecord,
)
from pharma_agent.domain.account.ports import DeliveryError

START = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
OTP_SECRET = "o" * 40
CODE_PATTERN = re.compile(r"\b(\d{6})\b")


def code_in(text: str) -> str:
    match = CODE_PATTERN.search(text)
    if match is None:
        raise AssertionError(f"no code in {text!r}")
    return match.group(1)


class MutableClock:
    def __init__(self, at: datetime = START) -> None:
        self.at = at

    def now(self) -> datetime:
        return self.at

    def advance(self, **delta: float) -> None:
        self.at += timedelta(**delta)


class PlainHasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, hashed: str) -> bool:
        return hashed == f"hashed:{password}"


class InMemoryAccounts:
    def __init__(self) -> None:
        self.users: dict[uuid.UUID, AccountUser] = {}
        self.passwords: dict[uuid.UUID, str] = {}

    def add(
        self,
        *,
        email: str | None = "an@example.com",
        phone: str | None = None,
        email_verified: bool = False,
        phone_verified: bool = False,
        password: str = "old-password",
        password_set: bool = True,
        google: bool = False,
        active: bool = True,
    ) -> AccountUser:
        user = AccountUser(
            id=uuid.uuid4(),
            email=email,
            phone_number=phone,
            display_name="",
            email_verified=email_verified,
            phone_verified=phone_verified,
            password_set=password_set,
            google_linked=google,
            is_active=active,
            is_superuser=False,
        )
        self.users[user.id] = user
        self.passwords[user.id] = PlainHasher().hash(password)
        return user

    async def get(self, user_id: uuid.UUID) -> AccountUser | None:
        return self.users.get(user_id)

    async def get_by_email(self, email: str) -> AccountUser | None:
        return next(
            (
                u
                for u in self.users.values()
                if u.email is not None and u.email.lower() == email.lower()
            ),
            None,
        )

    async def get_by_phone(self, phone: str) -> AccountUser | None:
        return next((u for u in self.users.values() if u.phone_number == phone), None)

    async def create_phone_user(
        self, *, phone: str, hashed_password: str, now: datetime
    ) -> AccountUser:
        if await self.get_by_phone(phone) is not None:
            raise AccountConflict(phone)
        user = self.add(
            email=None, phone=phone, phone_verified=True, password_set=False
        )
        self.passwords[user.id] = hashed_password
        return user

    async def mark_email_verified(self, user_id: uuid.UUID, now: datetime) -> None:
        self.users[user_id] = replace(self.users[user_id], email_verified=True)

    async def set_email(self, user_id: uuid.UUID, email: str, now: datetime) -> None:
        owner = await self.get_by_email(email)
        if owner is not None and owner.id != user_id:
            raise AccountConflict(email)
        self.users[user_id] = replace(
            self.users[user_id], email=email, email_verified=True
        )

    async def set_phone(self, user_id: uuid.UUID, phone: str, now: datetime) -> None:
        owner = await self.get_by_phone(phone)
        if owner is not None and owner.id != user_id:
            raise AccountConflict(phone)
        self.users[user_id] = replace(
            self.users[user_id], phone_number=phone, phone_verified=True
        )

    async def set_password(self, user_id: uuid.UUID, hashed_password: str) -> None:
        self.passwords[user_id] = hashed_password
        self.users[user_id] = replace(self.users[user_id], password_set=True)

    async def hashed_password(self, user_id: uuid.UUID) -> str | None:
        return self.passwords.get(user_id)

    async def unlink_oauth(self, user_id: uuid.UUID, oauth_name: str) -> None:
        self.users[user_id] = replace(self.users[user_id], google_linked=False)

    async def update_display_name(self, user_id: uuid.UUID, display_name: str) -> None:
        self.users[user_id] = replace(self.users[user_id], display_name=display_name)


@dataclass
class StoredCode:
    id: uuid.UUID
    purpose: OtpPurpose
    destination: str
    user_id: uuid.UUID | None
    digest: str
    expires_at: datetime
    attempts: int = 0
    consumed_at: datetime | None = None


class InMemoryCodes:
    def __init__(self) -> None:
        self.rows: list[StoredCode] = []

    async def issue(
        self,
        *,
        purpose: OtpPurpose,
        destination: str,
        user_id: uuid.UUID | None,
        digest: str,
        expires_at: datetime,
        now: datetime,
    ) -> uuid.UUID:
        self.rows = [
            row
            for row in self.rows
            if not (
                row.purpose is purpose
                and row.destination == destination
                and row.consumed_at is None
            )
        ]
        row = StoredCode(
            uuid.uuid4(), purpose, destination, user_id, digest, expires_at
        )
        self.rows.append(row)
        return row.id

    def _row(self, code_id: uuid.UUID) -> StoredCode:
        return next(row for row in self.rows if row.id == code_id)

    async def find_active(
        self, purpose: OtpPurpose, destination: str, now: datetime
    ) -> OneTimeCode | None:
        for row in reversed(self.rows):
            if (
                row.purpose is purpose
                and row.destination == destination
                and row.consumed_at is None
                and row.expires_at > now
                and row.attempts < MAX_ATTEMPTS
            ):
                return OneTimeCode(
                    row.id,
                    row.purpose,
                    row.destination,
                    row.user_id,
                    row.digest,
                    row.expires_at,
                    row.attempts,
                )
        return None

    async def record_failure(self, code_id: uuid.UUID) -> None:
        self._row(code_id).attempts += 1

    async def consume(self, code_id: uuid.UUID, now: datetime) -> bool:
        row = self._row(code_id)
        if row.consumed_at is not None:
            return False
        row.consumed_at = now
        return True

    async def revoke(self, code_id: uuid.UUID, now: datetime) -> None:
        self._row(code_id).consumed_at = now


class InMemoryLimiter:
    def __init__(self, clock: MutableClock) -> None:
        self._clock = clock
        self.counts: dict[tuple[str, float], int] = {}

    def _slot(self, window_seconds: int) -> tuple[float, float]:
        epoch = self._clock.now().timestamp()
        start = epoch - epoch % window_seconds
        return start, start + window_seconds - epoch

    async def check(self, key: str, *, limit: int, window_seconds: int) -> float | None:
        start, remaining = self._slot(window_seconds)
        return remaining if self.counts.get((key, start), 0) >= limit else None

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> float | None:
        start, remaining = self._slot(window_seconds)
        self.counts[(key, start)] = self.counts.get((key, start), 0) + 1
        return remaining if self.counts[(key, start)] > limit else None


@dataclass(frozen=True)
class SentEmail:
    to: str
    subject: str
    text: str
    html: str


@dataclass(frozen=True)
class SentSms:
    to: str
    text: str


class RecordingEmailSender:
    def __init__(self) -> None:
        self.sent: list[SentEmail] = []
        self.fail = False

    async def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        if self.fail:
            raise DeliveryError("provider down")
        self.sent.append(SentEmail(to, subject, text, html))

    def last_code(self, to: str) -> str:
        return code_in(next(m.text for m in reversed(self.sent) if m.to == to))


class RecordingSmsSender:
    def __init__(self) -> None:
        self.sent: list[SentSms] = []
        self.fail = False

    async def send(self, *, to: str, text: str) -> None:
        if self.fail:
            raise DeliveryError("provider down")
        self.sent.append(SentSms(to, text))

    def last_code(self, to: str) -> str:
        return code_in(next(m.text for m in reversed(self.sent) if m.to == to))


class InMemorySessions:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, list[SessionRecord]] = {}

    def add(self, user_id: uuid.UUID, token: str, at: datetime = START) -> None:
        self.rows.setdefault(user_id, []).append(
            SessionRecord(token, at, None, "Firefox", "10.0.0.1")
        )

    async def for_user(self, user_id: uuid.UUID) -> Sequence[SessionRecord]:
        return sorted(
            self.rows.get(user_id, []), key=lambda r: r.created_at, reverse=True
        )

    async def delete(self, user_id: uuid.UUID, token: str) -> bool:
        before = len(self.rows.get(user_id, []))
        self.rows[user_id] = [r for r in self.rows.get(user_id, []) if r.token != token]
        return len(self.rows[user_id]) < before

    async def delete_all(self, user_id: uuid.UUID, *, keep: str | None = None) -> int:
        before = len(self.rows.get(user_id, []))
        self.rows[user_id] = [r for r in self.rows.get(user_id, []) if r.token == keep]
        return before - len(self.rows[user_id])


@dataclass
class AccountFakes:
    clock: MutableClock
    accounts: InMemoryAccounts = field(default_factory=InMemoryAccounts)
    codes: InMemoryCodes = field(default_factory=InMemoryCodes)
    email: RecordingEmailSender = field(default_factory=RecordingEmailSender)
    sms: RecordingSmsSender = field(default_factory=RecordingSmsSender)
    sessions: InMemorySessions = field(default_factory=InMemorySessions)


def build_account_service(
    clock: MutableClock | None = None, policy: AccountPolicy | None = None
) -> tuple[AccountService, AccountFakes]:
    fakes = AccountFakes(clock=clock or MutableClock())
    service = AccountService(
        accounts=fakes.accounts,
        codes=fakes.codes,
        limiter=InMemoryLimiter(fakes.clock),
        email=fakes.email,
        sms=fakes.sms,
        hasher=PlainHasher(),
        sessions=fakes.sessions,
        clock=fakes.clock,
        policy=policy or AccountPolicy(otp_secret=OTP_SECRET),
    )
    return service, fakes
```

Không dùng `type: ignore` hay `pyrefly: ignore` trong fake; nếu pyrefly báo lỗi, sửa kiểu cho đúng.

- [ ] **Step 2: Viết test service phần 1 (fail)**

`backend/tests/application/test_account_service.py`:

```python
import pytest

from pharma_agent.application.account.errors import (
    DeliveryFailed,
    InvalidCode,
    PasswordInvalid,
    PhoneCountryNotAllowed,
    PhoneNumberInvalid,
    RateLimited,
)
from tests.account_fakes import build_account_service

EMAIL = "an@example.com"
PHONE = "+84912345678"


async def test_verify_email_with_the_sent_code() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email=EMAIL)
    await service.request_email_verification(EMAIL, locale="vi", client_ip="1.1.1.1")
    code = fakes.email.last_code(EMAIL)
    assert await service.verify_email(EMAIL, code) == user.id
    verified = await fakes.accounts.get(user.id)
    assert verified is not None and verified.email_verified


async def test_verify_email_normalizes_the_address() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    await service.request_email_verification(
        "  An@Example.COM ", locale="vi", client_ip=None
    )
    code = fakes.email.last_code(EMAIL)
    assert await service.verify_email(" AN@example.com", code)


async def test_unknown_or_verified_emails_get_no_code_but_the_same_answer() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email="done@example.com", email_verified=True)
    await service.request_email_verification(
        "ghost@example.com", locale="vi", client_ip=None
    )
    await service.request_email_verification(
        "done@example.com", locale="vi", client_ip=None
    )
    assert fakes.email.sent == []


async def test_wrong_codes_count_and_five_failures_burn_the_code() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    code = fakes.email.last_code(EMAIL)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        with pytest.raises(InvalidCode):
            await service.verify_email(EMAIL, wrong)
    with pytest.raises(InvalidCode):
        await service.verify_email(EMAIL, code)


async def test_a_code_cannot_be_used_twice() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    code = fakes.email.last_code(EMAIL)
    await service.verify_email(EMAIL, code)
    with pytest.raises(InvalidCode):
        await service.verify_email(EMAIL, code)


async def test_codes_expire_after_ten_minutes() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    code = fakes.email.last_code(EMAIL)
    fakes.clock.advance(minutes=10, seconds=1)
    with pytest.raises(InvalidCode):
        await service.verify_email(EMAIL, code)


async def test_a_new_code_replaces_the_old_one() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    first = fakes.email.last_code(EMAIL)
    fakes.clock.advance(seconds=61)
    await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    second = fakes.email.last_code(EMAIL)
    if first != second:
        with pytest.raises(InvalidCode):
            await service.verify_email(EMAIL, first)
    assert await service.verify_email(EMAIL, second)


async def test_sending_is_limited_per_destination_and_per_ip() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    await service.request_email_verification(EMAIL, locale="vi", client_ip="1.1.1.1")
    with pytest.raises(RateLimited) as cooldown:
        await service.request_email_verification(
            EMAIL, locale="vi", client_ip="1.1.1.1"
        )
    assert 0 < cooldown.value.retry_after <= 60
    for _ in range(4):
        fakes.clock.advance(seconds=61)
        await service.request_email_verification(
            EMAIL, locale="vi", client_ip="1.1.1.1"
        )
    fakes.clock.advance(seconds=61)
    with pytest.raises(RateLimited):
        await service.request_email_verification(
            EMAIL, locale="vi", client_ip="1.1.1.1"
        )


async def test_limits_apply_even_when_the_account_does_not_exist() -> None:
    service, _ = build_account_service()
    await service.request_password_reset(
        "ghost@example.com", locale="vi", client_ip=None
    )
    with pytest.raises(RateLimited):
        await service.request_password_reset(
            "ghost@example.com", locale="vi", client_ip=None
        )


async def test_delivery_failure_revokes_the_code_and_reports_it() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    fakes.email.fail = True
    with pytest.raises(DeliveryFailed):
        await service.request_email_verification(EMAIL, locale="vi", client_ip=None)
    assert all(row.consumed_at is not None for row in fakes.codes.rows)


async def test_reset_password_sets_the_hash_verifies_email_and_ends_sessions() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email=EMAIL)
    fakes.sessions.add(user.id, "t-1")
    await service.request_password_reset(EMAIL, locale="en", client_ip=None)
    assert fakes.email.sent[-1].subject == "Your ViPharMind password reset code"
    await service.reset_password(EMAIL, fakes.email.last_code(EMAIL), "new-password-1")
    assert fakes.accounts.passwords[user.id] == "hashed:new-password-1"
    updated = await fakes.accounts.get(user.id)
    assert updated is not None and updated.email_verified
    assert await fakes.sessions.for_user(user.id) == []


async def test_reset_password_checks_the_password_before_using_the_code() -> None:
    service, fakes = build_account_service()
    fakes.accounts.add(email=EMAIL)
    await service.request_password_reset(EMAIL, locale="vi", client_ip=None)
    code = fakes.email.last_code(EMAIL)
    with pytest.raises(PasswordInvalid):
        await service.reset_password(EMAIL, code, "short")
    await service.reset_password(EMAIL, code, "long-enough")


async def test_phone_login_creates_the_account_once() -> None:
    service, fakes = build_account_service()
    await service.request_phone_login("0912 345 678", locale="vi", client_ip=None)
    assert fakes.sms.sent[-1].to == PHONE and fakes.sms.sent[-1].text.isascii()
    first = await service.login_with_phone("0912345678", fakes.sms.last_code(PHONE))
    fakes.clock.advance(seconds=61)
    await service.request_phone_login("+84 91 234 5678", locale="vi", client_ip=None)
    second = await service.login_with_phone(PHONE, fakes.sms.last_code(PHONE))
    assert first == second
    created = await fakes.accounts.get(first)
    assert created is not None and created.email is None and not created.password_set


async def test_phone_login_rejects_invalid_and_foreign_numbers() -> None:
    service, fakes = build_account_service()
    with pytest.raises(PhoneNumberInvalid):
        await service.request_phone_login("12345", locale="vi", client_ip=None)
    with pytest.raises(PhoneCountryNotAllowed):
        await service.request_phone_login(
            "+1 650 253 0000", locale="vi", client_ip=None
        )
    assert fakes.sms.sent == []


async def test_login_failures_lock_the_email_for_the_window() -> None:
    service, fakes = build_account_service()
    for _ in range(10):
        await service.check_login_allowed(EMAIL, "1.1.1.1")
        await service.record_login_failure(EMAIL, "1.1.1.1")
    with pytest.raises(RateLimited):
        await service.check_login_allowed(EMAIL, "2.2.2.2")
    with pytest.raises(RateLimited):
        await service.check_login_allowed("other@example.com", "1.1.1.1")
    fakes.clock.advance(minutes=15)
    await service.check_login_allowed(EMAIL, "2.2.2.2")
```

Lưu ý `test_a_new_code_replaces_the_old_one`: hai mã ngẫu nhiên có thể trùng (xác suất 10⁻⁶); test chỉ kiểm tra mã cũ khi khác mã mới.

- [ ] **Step 3: Chạy, xác nhận fail**

Run: `uv run --directory backend pytest -q tests/application/test_account_service.py`
Expected: FAIL, module chưa tồn tại.

- [ ] **Step 4: Viết `application/account/errors.py`**

```python
"""Errors of the account use cases; api/errors.py maps them to HTTP statuses."""

import math

from pharma_agent.application.errors import (
    ApplicationError,
    InvalidInput,
    ServiceUnavailable,
)


class InvalidCode(ApplicationError):
    code = "OTP_INVALID"


class RateLimited(ApplicationError):
    code = "RATE_LIMITED"

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"try again in {math.ceil(retry_after)} seconds")
        self.retry_after = retry_after


class EmailAlreadyUsed(ApplicationError):
    code = "EMAIL_ALREADY_USED"


class PhoneAlreadyUsed(ApplicationError):
    code = "PHONE_ALREADY_USED"


class LastSignInMethod(ApplicationError):
    code = "LAST_SIGN_IN_METHOD"


class CurrentPasswordInvalid(ApplicationError):
    code = "CURRENT_PASSWORD_INVALID"


class AccountNotFound(ApplicationError):
    code = "ACCOUNT_NOT_FOUND"


class AccountDisabled(ApplicationError):
    code = "ACCOUNT_DISABLED"


class SessionNotFound(ApplicationError):
    code = "SESSION_NOT_FOUND"


class PasswordInvalid(InvalidInput):
    code = "PASSWORD_INVALID"


class PhoneNumberInvalid(InvalidInput):
    code = "PHONE_NUMBER_INVALID"


class PhoneCountryNotAllowed(InvalidInput):
    code = "PHONE_COUNTRY_NOT_ALLOWED"


class DeliveryFailed(ServiceUnavailable):
    code = "DELIVERY_FAILED"
```

- [ ] **Step 5: Viết `application/account/service.py` (phần 1)**

```python
"""Account use cases over one-time codes: verification, password reset, phone sign-in."""

import logging
import secrets
import uuid
from dataclasses import dataclass

from pharma_agent.application.account.errors import (
    AccountDisabled,
    DeliveryFailed,
    InvalidCode,
    PasswordInvalid,
    PhoneCountryNotAllowed,
    PhoneNumberInvalid,
    RateLimited,
)
from pharma_agent.application.account.messages import Locale, code_email, code_sms
from pharma_agent.domain.account.codes import (
    CODE_TTL,
    code_digest,
    code_matches,
    generate_code,
)
from pharma_agent.domain.account.models import (
    CHANNEL_BY_PURPOSE,
    AccountConflict,
    Channel,
    OneTimeCode,
    OtpPurpose,
    normalize_email,
)
from pharma_agent.domain.account.passwords import password_problem
from pharma_agent.domain.account.phone import InvalidPhoneNumber, normalize_phone
from pharma_agent.domain.account.ports import (
    AccountRepository,
    DeliveryError,
    EmailSender,
    OneTimeCodeStore,
    PasswordHasher,
    RateLimiter,
    SessionStore,
    SmsSender,
)
from pharma_agent.domain.shared.clock import Clock

logger = logging.getLogger(__name__)
HOUR = 3600


@dataclass(frozen=True)
class AccountPolicy:
    otp_secret: str
    allowed_sms_regions: frozenset[str] = frozenset({"VN"})
    send_cooldown_seconds: int = 60
    sends_per_destination_per_hour: int = 5
    sends_per_ip_per_hour: int = 20
    login_failures_per_window: int = 10
    login_window_seconds: int = 15 * 60


class AccountService:
    def __init__(
        self,
        *,
        accounts: AccountRepository,
        codes: OneTimeCodeStore,
        limiter: RateLimiter,
        email: EmailSender,
        sms: SmsSender,
        hasher: PasswordHasher,
        sessions: SessionStore,
        clock: Clock,
        policy: AccountPolicy,
    ) -> None:
        self._accounts = accounts
        self._codes = codes
        self._limiter = limiter
        self._email = email
        self._sms = sms
        self._hasher = hasher
        self._sessions = sessions
        self._clock = clock
        self._policy = policy

    # Codes -------------------------------------------------------------------------

    async def _limit_send(self, destination: str, client_ip: str | None) -> None:
        """Apply every send limit before looking the account up, so limits leak nothing."""
        policy = self._policy
        limits = [
            (f"otp-cooldown:{destination}", 1, policy.send_cooldown_seconds),
            (f"otp-send:{destination}", policy.sends_per_destination_per_hour, HOUR),
        ]
        if client_ip is not None:
            limits.append(
                (f"otp-send-ip:{client_ip}", policy.sends_per_ip_per_hour, HOUR)
            )
        for key, limit, window in limits:
            retry_after = await self._limiter.check(
                key, limit=limit, window_seconds=window
            )
            if retry_after is not None:
                raise RateLimited(retry_after)
        for key, limit, window in limits:
            await self._limiter.hit(key, limit=limit, window_seconds=window)

    async def _deliver_code(
        self,
        purpose: OtpPurpose,
        destination: str,
        user_id: uuid.UUID | None,
        locale: Locale,
    ) -> None:
        code = generate_code()
        now = self._clock.now()
        code_id = await self._codes.issue(
            purpose=purpose,
            destination=destination,
            user_id=user_id,
            digest=code_digest(self._policy.otp_secret, purpose, destination, code),
            expires_at=now + CODE_TTL,
            now=now,
        )
        try:
            if CHANNEL_BY_PURPOSE[purpose] is Channel.EMAIL:
                content = code_email(purpose, code, locale)
                await self._email.send(
                    to=destination,
                    subject=content.subject,
                    text=content.text,
                    html=content.html,
                )
            else:
                await self._sms.send(
                    to=destination, text=code_sms(purpose, code, locale)
                )
        except DeliveryError as exc:
            await self._codes.revoke(code_id, now)
            logger.warning("could not deliver a %s code: %s", purpose.value, exc)
            raise DeliveryFailed("the code could not be delivered, try again") from exc

    async def _consume(
        self, purpose: OtpPurpose, destination: str, code: str
    ) -> OneTimeCode:
        now = self._clock.now()
        record = await self._codes.find_active(purpose, destination, now)
        if record is None:
            raise InvalidCode("the code is invalid or has expired")
        if not code_matches(self._policy.otp_secret, record, code):
            await self._codes.record_failure(record.id)
            raise InvalidCode("the code is invalid or has expired")
        if not await self._codes.consume(record.id, now):
            raise InvalidCode("the code is invalid or has expired")
        return record

    def _phone(self, raw: str) -> str:
        try:
            number, region = normalize_phone(raw)
        except InvalidPhoneNumber as exc:
            raise PhoneNumberInvalid("the phone number is not valid") from exc
        if region not in self._policy.allowed_sms_regions:
            raise PhoneCountryNotAllowed("SMS cannot be sent to this country")
        return number

    @staticmethod
    def _check_password(password: str) -> None:
        problem = password_problem(password)
        if problem is not None:
            raise PasswordInvalid(problem)

    # Email verification ------------------------------------------------------------

    async def request_email_verification(
        self, email: str, *, locale: Locale, client_ip: str | None
    ) -> None:
        address = normalize_email(email)
        await self._limit_send(address, client_ip)
        user = await self._accounts.get_by_email(address)
        if user is None or user.email_verified:
            return
        await self._deliver_code(OtpPurpose.VERIFY_EMAIL, address, user.id, locale)

    async def verify_email(self, email: str, code: str) -> uuid.UUID:
        address = normalize_email(email)
        record = await self._consume(OtpPurpose.VERIFY_EMAIL, address, code)
        user = await self._accounts.get_by_email(address)
        if user is None or user.id != record.user_id:
            raise InvalidCode("the code is invalid or has expired")
        if not user.is_active:
            raise AccountDisabled("this account is disabled")
        await self._accounts.mark_email_verified(user.id, self._clock.now())
        return user.id

    # Password reset ----------------------------------------------------------------

    async def request_password_reset(
        self, email: str, *, locale: Locale, client_ip: str | None
    ) -> None:
        address = normalize_email(email)
        await self._limit_send(address, client_ip)
        user = await self._accounts.get_by_email(address)
        if user is None or not user.is_active:
            return
        await self._deliver_code(OtpPurpose.RESET_PASSWORD, address, user.id, locale)

    async def reset_password(self, email: str, code: str, new_password: str) -> None:
        self._check_password(new_password)
        address = normalize_email(email)
        record = await self._consume(OtpPurpose.RESET_PASSWORD, address, code)
        user = await self._accounts.get_by_email(address)
        if user is None or user.id != record.user_id:
            raise InvalidCode("the code is invalid or has expired")
        await self._accounts.set_password(user.id, self._hasher.hash(new_password))
        if not user.email_verified:
            # The code reached this inbox, which proves the address.
            await self._accounts.mark_email_verified(user.id, self._clock.now())
        await self._sessions.delete_all(user.id)

    # Phone sign-in -----------------------------------------------------------------

    async def request_phone_login(
        self, phone: str, *, locale: Locale, client_ip: str | None
    ) -> None:
        number = self._phone(phone)
        await self._limit_send(number, client_ip)
        user = await self._accounts.get_by_phone(number)
        await self._deliver_code(
            OtpPurpose.PHONE_LOGIN, number, None if user is None else user.id, locale
        )

    async def login_with_phone(self, phone: str, code: str) -> uuid.UUID:
        number = self._phone(phone)
        await self._consume(OtpPurpose.PHONE_LOGIN, number, code)
        user = await self._accounts.get_by_phone(number)
        if user is None:
            try:
                user = await self._accounts.create_phone_user(
                    phone=number,
                    hashed_password=self._hasher.hash(secrets.token_urlsafe(32)),
                    now=self._clock.now(),
                )
            except AccountConflict:
                # Another request created it first; sign that account in.
                user = await self._accounts.get_by_phone(number)
                if user is None:
                    raise
        if not user.is_active:
            raise AccountDisabled("this account is disabled")
        return user.id

    # Password sign-in throttle (called by the fastapi-users UserManager) ----------

    def _login_keys(self, email: str, client_ip: str | None) -> list[str]:
        keys = [f"login:{normalize_email(email)}"]
        if client_ip is not None:
            keys.append(f"login-ip:{client_ip}")
        return keys

    async def check_login_allowed(self, email: str, client_ip: str | None) -> None:
        for key in self._login_keys(email, client_ip):
            retry_after = await self._limiter.check(
                key,
                limit=self._policy.login_failures_per_window,
                window_seconds=self._policy.login_window_seconds,
            )
            if retry_after is not None:
                raise RateLimited(retry_after)

    async def record_login_failure(self, email: str, client_ip: str | None) -> None:
        for key in self._login_keys(email, client_ip):
            await self._limiter.hit(
                key,
                limit=self._policy.login_failures_per_window,
                window_seconds=self._policy.login_window_seconds,
            )
```

`test_login_failures_lock_the_email_for_the_window` cần cửa sổ 15 phút bắt đầu tại `START` (09:00). `START.timestamp() % 900 == 0` nên `advance(minutes=15)` sang cửa sổ mới. Test giới hạn gửi theo giờ: `START` cũng là đầu giờ, năm lần cách nhau 61 giây vẫn nằm trong cùng giờ.

- [ ] **Step 6: Chạy test, pyrefly, kiến trúc**

Run: `uv run --directory backend pytest -q tests/application/test_account_service.py tests/architecture && uv run --directory backend pyrefly check`
Expected: PASS, `0 errors`.

- [ ] **Step 7: Commit**

```bash
git add backend/src/pharma_agent/application/account backend/tests/account_fakes.py backend/tests/application/test_account_service.py
git commit -m "feat(backend): add account use cases for codes, verification, reset and phone sign-in"
```

---

### Task 7: `AccountService` phần 2: hồ sơ, đổi email/số điện thoại, mật khẩu, Google, phiên

**Files:**
- Modify: `backend/src/pharma_agent/application/account/service.py`
- Test: `backend/tests/application/test_account_settings_service.py`

**Interfaces:**
- Produces:
  - `AccountView` (pydantic): `id: uuid.UUID, email: str | None, phone_number: str | None, display_name: str, is_active: bool, is_superuser: bool, is_verified: bool, email_verified: bool, phone_verified: bool, password_set: bool, google_linked: bool`; `AccountView.of(AccountUser)`.
  - `SessionView` (pydantic): `id: str, created_at: datetime, last_used_at: datetime | None, user_agent: str, ip_address: str, current: bool`.
  - Method: `get_account(user_id) -> AccountView`, `update_profile(user_id, display_name) -> AccountView`, `request_email_change(user_id, email, *, locale, client_ip) -> None`, `confirm_email_change(user_id, email, code, *, locale) -> AccountView`, `request_phone_change(user_id, phone, *, locale, client_ip) -> None`, `confirm_phone_change(user_id, phone, code) -> AccountView`, `change_password(user_id, *, current_password: str | None, new_password: str) -> None`, `unlink_google(user_id) -> AccountView`, `list_sessions(user_id, current_token: str | None) -> list[SessionView]`, `revoke_session(user_id, session_id: str) -> None`, `revoke_other_sessions(user_id, current_token: str | None) -> int`.

- [ ] **Step 1: Viết test (fail)**

`backend/tests/application/test_account_settings_service.py`:

```python
import uuid

import pytest

from pharma_agent.application.account.errors import (
    AccountNotFound,
    CurrentPasswordInvalid,
    EmailAlreadyUsed,
    InvalidCode,
    LastSignInMethod,
    PhoneAlreadyUsed,
    SessionNotFound,
)
from pharma_agent.domain.account.models import session_id_of
from tests.account_fakes import build_account_service

PHONE = "+84912345678"


async def test_account_view_and_profile_update() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email="an@example.com", email_verified=True)
    view = await service.update_profile(user.id, "  Nguyễn An ")
    assert view.display_name == "Nguyễn An"
    assert view.email_verified and view.is_verified and not view.phone_verified


async def test_change_email_sends_to_the_new_address_and_notifies_the_old() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email="an@example.com", email_verified=True)
    await service.request_email_change(
        user.id, "An.New@Example.com", locale="vi", client_ip=None
    )
    code = fakes.email.last_code("an.new@example.com")
    view = await service.confirm_email_change(
        user.id, "an.new@example.com", code, locale="vi"
    )
    assert view.email == "an.new@example.com" and view.email_verified
    assert fakes.email.sent[-1].to == "an@example.com"
    assert "an.new@example.com" in fakes.email.sent[-1].text


async def test_change_email_rejects_an_address_of_another_account() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email="an@example.com", email_verified=True)
    fakes.accounts.add(email="bo@example.com")
    with pytest.raises(EmailAlreadyUsed):
        await service.request_email_change(
            user.id, "bo@example.com", locale="vi", client_ip=None
        )


async def test_a_code_for_someone_else_does_not_change_my_email() -> None:
    service, fakes = build_account_service()
    owner = fakes.accounts.add(email="an@example.com", email_verified=True)
    attacker = fakes.accounts.add(email="eve@example.com", email_verified=True)
    await service.request_email_change(
        owner.id, "new@example.com", locale="vi", client_ip=None
    )
    code = fakes.email.last_code("new@example.com")
    with pytest.raises(InvalidCode):
        await service.confirm_email_change(
            attacker.id, "new@example.com", code, locale="vi"
        )


async def test_change_phone_and_conflicts() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email="an@example.com", email_verified=True)
    fakes.accounts.add(email=None, phone="+84987654321", phone_verified=True)
    with pytest.raises(PhoneAlreadyUsed):
        await service.request_phone_change(
            user.id, "0987654321", locale="vi", client_ip=None
        )
    await service.request_phone_change(
        user.id, "0912 345 678", locale="vi", client_ip=None
    )
    view = await service.confirm_phone_change(
        user.id, "0912345678", fakes.sms.last_code(PHONE)
    )
    assert view.phone_number == PHONE and view.phone_verified


async def test_change_password_needs_the_current_one_when_set() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(
        email="an@example.com", email_verified=True, password="old-password"
    )
    with pytest.raises(CurrentPasswordInvalid):
        await service.change_password(
            user.id, current_password="wrong", new_password="new-password"
        )
    with pytest.raises(CurrentPasswordInvalid):
        await service.change_password(
            user.id, current_password=None, new_password="new-password"
        )
    await service.change_password(
        user.id, current_password="old-password", new_password="new-password"
    )
    assert fakes.accounts.passwords[user.id] == "hashed:new-password"


async def test_phone_accounts_set_a_first_password_without_the_current_one() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(
        email=None, phone=PHONE, phone_verified=True, password_set=False
    )
    await service.change_password(
        user.id, current_password=None, new_password="first-password"
    )
    view = await service.get_account(user.id)
    assert view.password_set


async def test_google_cannot_be_unlinked_when_it_is_the_last_method() -> None:
    service, fakes = build_account_service()
    only_google = fakes.accounts.add(
        email="g@example.com", email_verified=True, password_set=False, google=True
    )
    with pytest.raises(LastSignInMethod):
        await service.unlink_google(only_google.id)
    both = fakes.accounts.add(email="b@example.com", email_verified=True, google=True)
    view = await service.unlink_google(both.id)
    assert not view.google_linked


async def test_sessions_list_marks_the_current_one_and_revokes() -> None:
    service, fakes = build_account_service()
    user = fakes.accounts.add(email="an@example.com", email_verified=True)
    fakes.sessions.add(user.id, "t-current")
    fakes.sessions.add(user.id, "t-other")
    views = await service.list_sessions(user.id, "t-current")
    assert {view.current for view in views} == {True, False}
    assert all("t-" not in view.id for view in views)
    await service.revoke_session(user.id, session_id_of("t-other"))
    with pytest.raises(SessionNotFound):
        await service.revoke_session(user.id, session_id_of("t-other"))
    fakes.sessions.add(user.id, "t-third")
    assert await service.revoke_other_sessions(user.id, "t-current") == 1
    assert [
        view.current for view in await service.list_sessions(user.id, "t-current")
    ] == [True]


async def test_unknown_account_is_reported() -> None:
    service, _ = build_account_service()
    with pytest.raises(AccountNotFound):
        await service.get_account(uuid.uuid4())
```

- [ ] **Step 2: Chạy, xác nhận fail**

Run: `uv run --directory backend pytest -q tests/application/test_account_settings_service.py`
Expected: FAIL (`update_profile` chưa có).

- [ ] **Step 3: Bổ sung `service.py`**

Thêm import: `import hmac`, `from datetime import datetime`, `from pydantic import BaseModel`; từ errors thêm `AccountNotFound, CurrentPasswordInvalid, EmailAlreadyUsed, InvalidInput, LastSignInMethod, PhoneAlreadyUsed, SessionNotFound` (`InvalidInput` lấy từ `pharma_agent.application.errors`); từ messages thêm `email_changed_notice`; từ models thêm `AccountUser, SignInMethod, session_id_of`. Thêm hai model trước `class AccountService`:

```python
class AccountView(BaseModel):
    id: uuid.UUID
    email: str | None
    phone_number: str | None
    display_name: str
    is_active: bool
    is_superuser: bool
    is_verified: bool
    email_verified: bool
    phone_verified: bool
    password_set: bool
    google_linked: bool

    @classmethod
    def of(cls, user: AccountUser) -> "AccountView":
        return cls(
            id=user.id,
            email=user.email,
            phone_number=user.phone_number,
            display_name=user.display_name,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            is_verified=user.email_verified or user.phone_verified,
            email_verified=user.email_verified,
            phone_verified=user.phone_verified,
            password_set=user.password_set,
            google_linked=user.google_linked,
        )


class SessionView(BaseModel):
    id: str
    created_at: datetime
    last_used_at: datetime | None
    user_agent: str
    ip_address: str
    current: bool
```

Thêm các method vào `AccountService` (cuối class):

```python
# Profile and contact changes ----------------------------------------------------


async def _require(self, user_id: uuid.UUID) -> AccountUser:
    user = await self._accounts.get(user_id)
    if user is None:
        raise AccountNotFound(str(user_id))
    return user


async def get_account(self, user_id: uuid.UUID) -> AccountView:
    return AccountView.of(await self._require(user_id))


async def update_profile(self, user_id: uuid.UUID, display_name: str) -> AccountView:
    await self._require(user_id)
    await self._accounts.update_display_name(user_id, display_name.strip())
    return await self.get_account(user_id)


async def request_email_change(
    self, user_id: uuid.UUID, email: str, *, locale: Locale, client_ip: str | None
) -> None:
    user = await self._require(user_id)
    address = normalize_email(email)
    owner = await self._accounts.get_by_email(address)
    if owner is not None and owner.id != user_id:
        raise EmailAlreadyUsed("this email belongs to another account")
    if user.email == address and user.email_verified:
        raise InvalidInput("this is already your email")
    await self._limit_send(address, client_ip)
    await self._deliver_code(OtpPurpose.CHANGE_EMAIL, address, user_id, locale)


async def confirm_email_change(
    self, user_id: uuid.UUID, email: str, code: str, *, locale: Locale
) -> AccountView:
    address = normalize_email(email)
    record = await self._consume(OtpPurpose.CHANGE_EMAIL, address, code)
    if record.user_id != user_id:
        raise InvalidCode("the code is invalid or has expired")
    user = await self._require(user_id)
    try:
        await self._accounts.set_email(user_id, address, self._clock.now())
    except AccountConflict as exc:
        raise EmailAlreadyUsed("this email belongs to another account") from exc
    if user.email is not None and user.email != address:
        notice = email_changed_notice(address, locale)
        try:
            await self._email.send(
                to=user.email,
                subject=notice.subject,
                text=notice.text,
                html=notice.html,
            )
        except DeliveryError as exc:
            logger.warning("could not notify the previous email: %s", exc)
    return await self.get_account(user_id)


async def request_phone_change(
    self, user_id: uuid.UUID, phone: str, *, locale: Locale, client_ip: str | None
) -> None:
    await self._require(user_id)
    number = self._phone(phone)
    owner = await self._accounts.get_by_phone(number)
    if owner is not None and owner.id != user_id:
        raise PhoneAlreadyUsed("this phone number belongs to another account")
    await self._limit_send(number, client_ip)
    await self._deliver_code(OtpPurpose.CHANGE_PHONE, number, user_id, locale)


async def confirm_phone_change(
    self, user_id: uuid.UUID, phone: str, code: str
) -> AccountView:
    number = self._phone(phone)
    record = await self._consume(OtpPurpose.CHANGE_PHONE, number, code)
    if record.user_id != user_id:
        raise InvalidCode("the code is invalid or has expired")
    try:
        await self._accounts.set_phone(user_id, number, self._clock.now())
    except AccountConflict as exc:
        raise PhoneAlreadyUsed("this phone number belongs to another account") from exc
    return await self.get_account(user_id)


async def change_password(
    self, user_id: uuid.UUID, *, current_password: str | None, new_password: str
) -> None:
    self._check_password(new_password)
    user = await self._require(user_id)
    if user.password_set:
        hashed = await self._accounts.hashed_password(user_id)
        if (
            current_password is None
            or hashed is None
            or not self._hasher.verify(current_password, hashed)
        ):
            raise CurrentPasswordInvalid("the current password is wrong")
    await self._accounts.set_password(user_id, self._hasher.hash(new_password))


async def unlink_google(self, user_id: uuid.UUID) -> AccountView:
    user = await self._require(user_id)
    if user.google_linked:
        if not user.sign_in_methods() - {SignInMethod.GOOGLE}:
            raise LastSignInMethod("add another way to sign in before removing Google")
        await self._accounts.unlink_oauth(user_id, SignInMethod.GOOGLE.value)
    return await self.get_account(user_id)


# Sessions -------------------------------------------------------------------------


async def list_sessions(
    self, user_id: uuid.UUID, current_token: str | None
) -> list[SessionView]:
    return [
        SessionView(
            id=session_id_of(record.token),
            created_at=record.created_at,
            last_used_at=record.last_used_at,
            user_agent=record.user_agent,
            ip_address=record.ip_address,
            current=current_token is not None
            and hmac.compare_digest(record.token, current_token),
        )
        for record in await self._sessions.for_user(user_id)
    ]


async def revoke_session(self, user_id: uuid.UUID, session_id: str) -> None:
    for record in await self._sessions.for_user(user_id):
        if hmac.compare_digest(session_id_of(record.token), session_id):
            await self._sessions.delete(user_id, record.token)
            return
    raise SessionNotFound(session_id)


async def revoke_other_sessions(
    self, user_id: uuid.UUID, current_token: str | None
) -> int:
    return await self._sessions.delete_all(user_id, keep=current_token)
```

- [ ] **Step 4: Chạy test, pyrefly**

Run: `uv run --directory backend pytest -q tests/application && uv run --directory backend pyrefly check`
Expected: PASS, `0 errors`.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pharma_agent/application/account/service.py backend/tests/application/test_account_settings_service.py
git commit -m "feat(backend): add account settings use cases (contacts, password, Google, sessions)"
```

---

### Task 8: Nối fastapi-users và container

**Files:**
- Create: `backend/src/pharma_agent/infrastructure/auth/passwords.py`, `backend/src/pharma_agent/infrastructure/account_factory.py`
- Modify: `backend/src/pharma_agent/infrastructure/auth/users.py`, `backend/src/pharma_agent/infrastructure/container.py`
- Modify: `backend/tests/infrastructure/test_auth_wiring.py`, `backend/tests/api/postgres_app.py`
- Test: `backend/tests/api/test_google_oauth_postgres.py` (thêm test)

**Interfaces:**
- Consumes: `AccountService` (Task 6–7), adapter Postgres (Task 4), senders (Task 5).
- Produces:
  - `FastapiUsersPasswordHasher()`.
  - `build_account_service(settings, sessions, *, clock, email=None, sms=None) -> AccountService`.
  - `Container.account: AccountService | None`; `open_container(settings, *, llm=None, embedder=None, email_sender=None, sms_sender=None)`.
  - `Auth.login_session`: FastAPI dependency trả `Callable[[uuid.UUID], Awaitable[Response]]`.
  - Route liên kết Google: `oauth-associate:google.authorize`, `oauth-associate:google.callback` dưới `/auth/google/associate`.
  - `include_auth_routes` **không** còn mount `get_users_router`.
  - `postgres_app(dsn, *, auth=None)` yield thêm `outbox: AppOutbox` (`email: RecordingEmailSender`, `sms: RecordingSmsSender`); helper `verified_register(client, outbox, email)`.

- [ ] **Step 1: Viết test (fail)**

Sửa `backend/tests/infrastructure/test_auth_wiring.py`, `test_routes_without_google`: bỏ dòng `users:current_user`, thêm:

```python
    with pytest.raises(NoMatchFound):
        router.url_path_for("users:current_user")
```

Thêm test:

```python
def test_google_adds_login_and_associate_routes() -> None:
    settings = AuthSettings(
        jwt_secret=SecretStr(SECRET),
        google_client_id="id",
        google_client_secret=SecretStr("secret"),
    )
    router = auth_router(settings)
    assert (
        router.url_path_for("oauth:google.cookie.callback") == "/auth/google/callback"
    )
    assert (
        router.url_path_for("oauth-associate:google.callback")
        == "/auth/google/associate/callback"
    )
```

Thêm vào `backend/tests/api/test_google_oauth_postgres.py` (dùng chung các mock ở đầu file):

```python
async def google_login(
    client: httpx.AsyncClient, google: respx.MockRouter, email: str
) -> httpx.Response:
    google.post(GOOGLE_TOKEN_URL).mock(return_value=TOKEN_RESPONSE)
    google.get(GOOGLE_PROFILE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceName": "people/1234567890",
                "emailAddresses": [{"value": email, "metadata": {"primary": True}}],
            },
        )
    )
    authorize = await client.get("/api/v1/auth/google/authorize")
    state = httpx.URL(authorize.json()["authorization_url"]).params["state"]
    return await client.get(
        "/api/v1/auth/google/callback", params={"code": "auth-code", "state": state}
    )


async def test_google_does_not_take_over_an_unverified_registration(
    migrated_dsn: str,
) -> None:
    email = new_email()
    async with respx.mock() as google:
        async with postgres_app(migrated_dsn, auth=GOOGLE_AUTH) as (client, _, _outbox):
            await register(client, email)
            callback = await google_login(client, google, email)
    assert callback.status_code == 400
    assert callback.json()["code"] == "OAUTH_USER_ALREADY_EXISTS"


async def test_google_links_to_a_verified_registration(migrated_dsn: str) -> None:
    email = new_email()
    async with respx.mock() as google:
        async with postgres_app(migrated_dsn, auth=GOOGLE_AUTH) as (client, _, outbox):
            await verified_register(client, outbox, email)
            client.cookies.clear()
            callback = await google_login(client, google, email)
            assert callback.status_code == 204, callback.text
            me = await client.get("/api/v1/users/me")
    assert me.json()["google_linked"] is True and me.json()["password_set"] is True


async def test_google_sign_up_has_no_password_and_a_verified_email(
    migrated_dsn: str,
) -> None:
    email = new_email()
    async with respx.mock() as google:
        async with postgres_app(migrated_dsn, auth=GOOGLE_AUTH) as (client, _, _outbox):
            assert (await google_login(client, google, email)).status_code == 204
            me = (await client.get("/api/v1/users/me")).json()
    assert me["email_verified"] is True and me["password_set"] is False
```

Sửa mọi chỗ `async with postgres_app(...) as (client, x)` trong `tests/api/*.py` thành ba phần tử `(client, x, outbox)` (hoặc `_outbox`), và mọi luồng "register rồi cookie_login" đổi sang `verified_register` rồi `cookie_login` (bước 6).

- [ ] **Step 2: Chạy, xác nhận fail**

Run: `uv run --directory backend pytest -q tests/infrastructure/test_auth_wiring.py && uv run --directory backend pytest -q -m integration tests/api/test_google_oauth_postgres.py`
Expected: FAIL.

- [ ] **Step 3: Viết `infrastructure/auth/passwords.py`**

```python
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
```

- [ ] **Step 4: Viết `infrastructure/account_factory.py`**

```python
"""AccountService over Postgres and the configured email and SMS senders."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pharma_agent.application.account.service import AccountPolicy, AccountService
from pharma_agent.domain.account.ports import EmailSender, SmsSender
from pharma_agent.domain.shared.clock import Clock
from pharma_agent.infrastructure.auth.passwords import FastapiUsersPasswordHasher
from pharma_agent.infrastructure.notifications.factory import (
    build_email_sender,
    build_sms_sender,
)
from pharma_agent.infrastructure.persistence.postgres.account_repository import (
    PostgresAccountRepository,
)
from pharma_agent.infrastructure.persistence.postgres.one_time_codes import (
    PostgresOneTimeCodeStore,
)
from pharma_agent.infrastructure.persistence.postgres.rate_limiter import (
    PostgresRateLimiter,
)
from pharma_agent.infrastructure.persistence.postgres.session_store import (
    PostgresSessionStore,
)
from pharma_agent.infrastructure.settings import Settings


def build_account_service(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
    *,
    clock: Clock,
    email: EmailSender | None = None,
    sms: SmsSender | None = None,
) -> AccountService:
    return AccountService(
        accounts=PostgresAccountRepository(sessions),
        codes=PostgresOneTimeCodeStore(sessions),
        limiter=PostgresRateLimiter(sessions, clock),
        email=email if email is not None else build_email_sender(settings.email),
        sms=sms if sms is not None else build_sms_sender(settings.sms),
        hasher=FastapiUsersPasswordHasher(),
        sessions=PostgresSessionStore(
            sessions,
            lifetime_seconds=settings.auth.session_lifetime_seconds,
            clock=clock,
        ),
        clock=clock,
        policy=AccountPolicy(
            otp_secret=settings.auth.require_otp_secret(),
            allowed_sms_regions=frozenset(settings.sms.allowed_country_codes),
        ),
    )
```

- [ ] **Step 5: Sửa `container.py`**

1. Import `AccountService` từ `pharma_agent.application.account.service`, `EmailSender, SmsSender` từ `pharma_agent.domain.account.ports`, `build_account_service` từ `pharma_agent.infrastructure.account_factory`.
2. Thêm trường vào `Container` (sau `feedback`): `account: AccountService | None = None`.
3. Thêm tham số vào `open_container`: `email_sender: EmailSender | None = None, sms_sender: SmsSender | None = None`.
4. Ngay sau khi tạo `container = Container(...)`, thêm:

```python
    if settings.auth.otp_secret is None:
        logger.warning("PHARMA_AUTH__OTP_SECRET is not set: account flows are disabled")
    else:
        container.account = build_account_service(
            settings, database.sessions, clock=clock, email=email_sender, sms=sms_sender
        )
```

- [ ] **Step 6: Sửa `infrastructure/auth/users.py`**

Thay toàn bộ phần từ `class UserRead` tới hết `include_auth_routes` bằng nội dung sau (giữ phần import đầu file và thêm import mới):

```python
import logging
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Response
from fastapi_users import exceptions
from fastapi.security import OAuth2PasswordRequestForm

from pharma_agent.application.account.errors import DeliveryFailed, RateLimited
from pharma_agent.application.account.messages import locale_from_accept_language
from pharma_agent.application.account.service import AccountService
from pharma_agent.domain.account.passwords import password_problem

logger = logging.getLogger(__name__)
# `last_used_at` is written at most this often, not on every authenticated request.
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)
SessionLogin = Callable[[uuid.UUID], Awaitable[Response]]


class UserRead(schemas.BaseUser[uuid.UUID]):
    """Registration and Google association responses; /users/me returns AccountView."""

    display_name: str = ""


class UserCreate(schemas.BaseUserCreate):
    display_name: str = ""


def _client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def _already_exists() -> HTTPException:
    return HTTPException(status_code=400, detail="OAUTH_USER_ALREADY_EXISTS")


class UserManager(UUIDIDMixin, BaseUserManager[UserTable, uuid.UUID]):
    def __init__(
        self,
        user_db: UserDatabase,
        secret: str,
        *,
        account: AccountService | None = None,
        request: Request | None = None,
    ) -> None:
        super().__init__(user_db)
        self.reset_password_token_secret = secret
        self.verification_token_secret = secret
        self._account = account
        self._request = request

    async def validate_password(
        self, password: str, user: schemas.UC | UserTable
    ) -> None:
        problem = password_problem(password)
        if problem is not None:
            raise exceptions.InvalidPasswordException(reason=problem)

    async def authenticate(
        self, credentials: OAuth2PasswordRequestForm
    ) -> UserTable | None:
        ip = _client_ip(self._request)
        if self._account is not None:
            await self._account.check_login_allowed(credentials.username, ip)
        user = await super().authenticate(credentials)
        if user is None:
            if self._account is not None:
                await self._account.record_login_failure(credentials.username, ip)
            return None
        if user.email_verified_at is None:
            raise HTTPException(status_code=403, detail="EMAIL_NOT_VERIFIED")
        return user

    async def on_after_register(
        self, user: UserTable, request: Request | None = None
    ) -> None:
        if self._account is None or not user.email:
            return
        locale = locale_from_accept_language(
            None if request is None else request.headers.get("accept-language")
        )
        try:
            await self._account.request_email_verification(
                user.email, locale=locale, client_ip=_client_ip(request)
            )
        except (RateLimited, DeliveryFailed) as exc:
            # The user can ask for the code again from the verification step.
            logger.warning("no verification code after registration: %s", exc)

    async def oauth_callback(
        self,
        oauth_name: str,
        access_token: str,
        account_id: str,
        account_email: str,
        expires_at: int | None = None,
        refresh_token: str | None = None,
        request: Request | None = None,
        *,
        associate_by_email: bool = False,
        is_verified_by_default: bool = False,
    ) -> UserTable:
        created = False
        try:
            await self.get_by_oauth_account(oauth_name, account_id)
        except exceptions.UserNotExists:
            existing = await self.user_db.get_by_email(account_email)
            if existing is not None and existing.email_verified_at is None:
                # Linking would hand an unverified registration's password to its creator.
                raise _already_exists() from None
            created = existing is None
        user = await super().oauth_callback(
            oauth_name,
            access_token,
            account_id,
            account_email,
            expires_at,
            refresh_token,
            request,
            associate_by_email=associate_by_email,
            is_verified_by_default=is_verified_by_default,
        )
        if created:
            user = await self.user_db.update(
                user, {"email_verified_at": datetime.now(UTC), "password_set": False}
            )
        return user

    async def oauth_associate_callback(
        self,
        user: UserTable,
        oauth_name: str,
        access_token: str,
        account_id: str,
        account_email: str,
        expires_at: int | None = None,
        refresh_token: str | None = None,
        request: Request | None = None,
    ) -> UserTable:
        try:
            owner = await self.get_by_oauth_account(oauth_name, account_id)
        except exceptions.UserNotExists:
            owner = None
        if owner is not None and owner.id != user.id:
            raise _already_exists()
        adopt_email = not user.email
        if adopt_email:
            other = await self.user_db.get_by_email(account_email)
            if other is not None and other.id != user.id:
                raise _already_exists()
        user = await super().oauth_associate_callback(
            user,
            oauth_name,
            access_token,
            account_id,
            account_email,
            expires_at,
            refresh_token,
            request,
        )
        if adopt_email:
            # Google verified this address; a phone-only account takes it as its email.
            user = await self.user_db.update(
                user,
                {
                    "email": account_email.lower(),
                    "email_verified_at": datetime.now(UTC),
                    "is_verified": True,
                },
            )
        return user


class TrackedDatabaseStrategy(DatabaseStrategy[UserTable, uuid.UUID, AccessTokenTable]):
    """DatabaseStrategy that records the device and last use of each session."""

    def __init__(
        self,
        database: AccessTokenDatabase,
        lifetime_seconds: int,
        *,
        user_agent: str,
        ip_address: str,
    ) -> None:
        super().__init__(database, lifetime_seconds=lifetime_seconds)
        self._user_agent = user_agent[:255]
        self._ip_address = ip_address[:45]

    def _create_access_token_dict(self, user: UserTable) -> dict[str, Any]:
        values = super()._create_access_token_dict(user)
        values.update(
            user_agent=self._user_agent,
            ip_address=self._ip_address,
            last_used_at=datetime.now(UTC),
        )
        return values

    async def read_token(
        self, token: str | None, user_manager: BaseUserManager[UserTable, uuid.UUID]
    ) -> UserTable | None:
        if token is None:
            return None
        now = datetime.now(UTC)
        max_age = (
            now - timedelta(seconds=self.lifetime_seconds)
            if self.lifetime_seconds
            else None
        )
        access_token = await self.database.get_by_token(token, max_age)
        if access_token is None:
            return None
        try:
            user = await user_manager.get(user_manager.parse_id(access_token.user_id))
        except (exceptions.UserNotExists, exceptions.InvalidID):
            return None
        last_used = access_token.last_used_at
        if last_used is None or now - last_used > SESSION_TOUCH_INTERVAL:
            await self.database.update(access_token, {"last_used_at": now})
        return user
```

Sửa dataclass `Auth`: thêm trường `login_session: Callable[..., Any]`.

Trong `build_auth`:
1. `get_user_manager` lấy thêm `request: Request` và AccountService từ container:

```python
    async def get_user_manager(
        request: Request,
        user_db: Annotated[UserDatabase, Depends(get_user_db)],
    ) -> AsyncIterator[UserManager]:
        container = getattr(request.app.state, "container", None)
        account = getattr(container, "account", None)
        yield UserManager(
            user_db,
            secret,
            account=account if isinstance(account, AccountService) else None,
            request=request,
        )
```

2. `get_session_strategy` dùng `TrackedDatabaseStrategy`:

```python
    def get_session_strategy(
        request: Request,
        access_tokens: Annotated[AccessTokenDatabase, Depends(get_access_token_db)],
    ) -> TrackedDatabaseStrategy:
        return TrackedDatabaseStrategy(
            access_tokens,
            settings.session_lifetime_seconds,
            user_agent=request.headers.get("user-agent", ""),
            ip_address=_client_ip(request) or "",
        )
```

3. Sau khi tạo `cookie_backend`, thêm dependency đăng nhập:

```python
    async def get_session_login(
        user_manager: Annotated[UserManager, Depends(get_user_manager)],
        strategy: Annotated[TrackedDatabaseStrategy, Depends(get_session_strategy)],
    ) -> SessionLogin:
        async def login(user_id: uuid.UUID) -> Response:
            user = await user_manager.get(user_id)
            return await cookie_backend.login(strategy, user)

        return login
```

4. Trả `login_session=get_session_login` trong `Auth(...)`.

Trong `include_auth_routes`: xoá khối `get_users_router`; trong nhánh `auth.google is not None`, sau router OAuth đăng nhập thêm:

```python
        router.include_router(
            auth.users.get_oauth_associate_router(
                auth.google,
                UserRead,
                auth.secret,
                redirect_url=f"{auth.frontend_url.rstrip('/')}/auth/google/link-callback",
                csrf_token_cookie_secure=auth.cookie_secure,
            ),
            prefix="/auth/google/associate",
            tags=["auth"],
        )
```

Xoá `class UserUpdate` (không còn dùng). Nếu pyrefly báo kiểu tham số `credentials` hoặc `user` của các method ghi đè khác base, sao chép đúng chú thích kiểu của base (`fastapi_users/manager.py`) thay vì tắt cảnh báo.

- [ ] **Step 7: Sửa `tests/api/postgres_app.py`**

Factory trong `postgres_app` dựng `AccountService` thật trên Postgres, gửi qua bộ ghi trong bộ nhớ:

```python
from dataclasses import dataclass, field

from pharma_agent.infrastructure.account_factory import build_account_service
from tests.account_fakes import RecordingEmailSender, RecordingSmsSender


@dataclass
class AppOutbox:
    email: RecordingEmailSender = field(default_factory=RecordingEmailSender)
    sms: RecordingSmsSender = field(default_factory=RecordingSmsSender)
```

Trong `postgres_app`: tạo `outbox = AppOutbox()`, trong `factory` thêm vào `Container(...)` đối số
`account=build_account_service(resolved, database.sessions, clock=SystemClock(), email=outbox.email, sms=outbox.sms)`, và đổi kiểu trả thành `AsyncGenerator[tuple[httpx.AsyncClient, Database, AppOutbox]]`, `yield client, database, outbox`.

Thêm helper:

```python
async def verified_register(
    client: httpx.AsyncClient, outbox: AppOutbox, email: str
) -> None:
    await register(client, email)
    code = outbox.email.last_code(email)
    response = await client.post(
        "/api/v1/auth/email/verify", json={"email": email, "code": code}
    )
    assert response.status_code == 204, response.text
```

`verified_register` gọi route của Task 9; test dùng nó chỉ pass sau Task 9. Ở Task 8, chạy test wiring và Google; các test cookie auth chuyển sang `verified_register` ở Task 9.

- [ ] **Step 8: Chạy test**

Run: `uv run --directory backend pytest -q tests/infrastructure/test_auth_wiring.py tests/architecture && uv run --directory backend pyrefly check`
Expected: PASS, `0 errors`. (`test_google_oauth_postgres.py` chạy lại ở cuối Task 9.)

- [ ] **Step 9: Commit**

```bash
git add backend/src/pharma_agent/infrastructure backend/tests
git commit -m "feat(backend): wire account service into fastapi-users and the container"
```

---

### Task 9: Router account, lỗi HTTP và test API trên Postgres

**Files:**
- Create: `backend/src/pharma_agent/api/routers/account.py`
- Modify: `backend/src/pharma_agent/api/deps.py`, `backend/src/pharma_agent/api/errors.py`, `backend/src/pharma_agent/api/app.py`
- Modify: `backend/tests/api/test_openapi.py`, `backend/tests/api/test_cookie_auth_postgres.py`, `backend/tests/api/test_e2e_postgres.py`, `backend/tests/e2e/test_server_smoke.py`
- Test: `backend/tests/api/test_account_api_postgres.py`

**Interfaces:**
- Consumes: `AccountService`, `Auth.login_session`, `SESSION_COOKIE_NAME`.
- Produces: route (tên route → hàm orval phía frontend):

| Method, path | Tên route | Thân / kết quả |
| --- | --- | --- |
| `POST /auth/email/verify/request` | `auth:email.verify_request` | `{email}` → 202 |
| `POST /auth/email/verify` | `auth:email.verify` | `{email, code}` → 204 + cookie |
| `POST /auth/password/forgot` | `auth:password.forgot` | `{email}` → 202 |
| `POST /auth/password/reset` | `auth:password.reset` | `{email, code, password}` → 204 |
| `POST /auth/phone/request` | `auth:phone.request` | `{phone}` → 202 |
| `POST /auth/phone/login` | `auth:phone.login` | `{phone, code}` → 204 + cookie |
| `GET /users/me` | `users:current_user` | `AccountView` |
| `PATCH /users/me` | `users:patch_current_user` | `{display_name}` → `AccountView` |
| `POST /account/email` | `account:email.request` | `{email}` → 202 |
| `POST /account/email/confirm` | `account:email.confirm` | `{email, code}` → `AccountView` |
| `POST /account/phone` | `account:phone.request` | `{phone}` → 202 |
| `POST /account/phone/confirm` | `account:phone.confirm` | `{phone, code}` → `AccountView` |
| `PUT /account/password` | `account:password.change` | `{current_password?, new_password}` → 204 |
| `DELETE /account/oauth/google` | `account:google.unlink` | → `AccountView` |
| `GET /account/sessions` | `account:sessions.list` | `list[SessionView]` |
| `DELETE /account/sessions/{session_id}` | `account:sessions.revoke` | → 204 |
| `DELETE /account/sessions` | `account:sessions.revoke_others` | → 204 |

- [ ] **Step 1: Viết test API (fail)**

`backend/tests/api/test_account_api_postgres.py`:

```python
import pytest

from pharma_agent.domain.account.models import session_id_of
from tests.api.postgres_app import (
    PASSWORD,
    cookie_login,
    csrf_header,
    new_email,
    postgres_app,
    register,
    verified_register,
)

pytestmark = pytest.mark.integration
PHONE = "+84912345678"


async def test_login_before_verification_is_refused_then_allowed(
    migrated_dsn: str,
) -> None:
    email = new_email()
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await register(client, email)
        refused = await client.post(
            "/api/v1/auth/cookie/login", data={"username": email, "password": PASSWORD}
        )
        assert (
            refused.status_code == 403
            and refused.json()["code"] == "EMAIL_NOT_VERIFIED"
        )
        verify = await client.post(
            "/api/v1/auth/email/verify",
            json={"email": email.upper(), "code": outbox.email.last_code(email)},
        )
        assert verify.status_code == 204 and "pharma_session" in client.cookies
        me = (await client.get("/api/v1/users/me")).json()
        assert me["email"] == email and me["email_verified"] and me["password_set"]


async def test_registration_uses_the_ui_language(migrated_dsn: str) -> None:
    email = new_email()
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": PASSWORD},
            headers={"Accept-Language": "en"},
        )
    assert outbox.email.sent[-1].subject == "Your ViPharMind verification code"


async def test_resend_inside_the_cooldown_is_429_with_retry_after(
    migrated_dsn: str,
) -> None:
    email = new_email()
    async with postgres_app(migrated_dsn) as (client, _, _outbox):
        await register(client, email)
        again = await client.post(
            "/api/v1/auth/email/verify/request", json={"email": email}
        )
    assert again.status_code == 429
    assert again.json()["code"] == "RATE_LIMITED"
    assert 1 <= int(again.headers["retry-after"]) <= 60


async def test_wrong_code_is_400_otp_invalid(migrated_dsn: str) -> None:
    email = new_email()
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await register(client, email)
        real = outbox.email.last_code(email)
        wrong = "000000" if real != "000000" else "111111"
        response = await client.post(
            "/api/v1/auth/email/verify", json={"email": email, "code": wrong}
        )
    assert response.status_code == 400 and response.json()["code"] == "OTP_INVALID"


async def test_forgot_password_answers_the_same_and_reset_works(
    migrated_dsn: str,
) -> None:
    email = new_email()
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await verified_register(client, outbox, email)
        ghost = await client.post(
            "/api/v1/auth/password/forgot", json={"email": new_email()}
        )
        real = await client.post("/api/v1/auth/password/forgot", json={"email": email})
        assert ghost.status_code == real.status_code == 202
        reset = await client.post(
            "/api/v1/auth/password/reset",
            json={
                "email": email,
                "code": outbox.email.last_code(email),
                "password": "brand-new-pass",
            },
        )
        assert reset.status_code == 204
        assert (await client.get("/api/v1/users/me")).status_code == 401
        login = await client.post(
            "/api/v1/auth/cookie/login",
            data={"username": email, "password": "brand-new-pass"},
        )
        assert login.status_code == 204


async def test_phone_sign_in_creates_a_phone_only_account(migrated_dsn: str) -> None:
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        sent = await client.post(
            "/api/v1/auth/phone/request", json={"phone": "0912 345 678"}
        )
        assert sent.status_code == 202
        login = await client.post(
            "/api/v1/auth/phone/login",
            json={"phone": "0912345678", "code": outbox.sms.last_code(PHONE)},
        )
        assert login.status_code == 204
        me = (await client.get("/api/v1/users/me")).json()
    assert me["email"] is None and me["phone_number"] == PHONE and me["phone_verified"]


async def test_foreign_numbers_are_422(migrated_dsn: str) -> None:
    async with postgres_app(migrated_dsn) as (client, _, _outbox):
        response = await client.post(
            "/api/v1/auth/phone/request", json={"phone": "+16502530000"}
        )
    assert (
        response.status_code == 422
        and response.json()["code"] == "PHONE_COUNTRY_NOT_ALLOWED"
    )


async def test_settings_change_email_password_and_profile(migrated_dsn: str) -> None:
    email, new = new_email(), new_email()
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await verified_register(client, outbox, email)
        # The first GET makes the CSRF middleware set `csrftoken`.
        await client.get("/api/v1/users/me")
        headers = csrf_header(client)
        assert (
            await client.post(
                "/api/v1/account/email", json={"email": new}, headers=headers
            )
        ).status_code == 202
        confirmed = await client.post(
            "/api/v1/account/email/confirm",
            json={"email": new, "code": outbox.email.last_code(new)},
            headers=headers,
        )
        assert confirmed.status_code == 200 and confirmed.json()["email"] == new
        wrong = await client.put(
            "/api/v1/account/password",
            json={"current_password": "nope", "new_password": "another-pass"},
            headers=headers,
        )
        assert (
            wrong.status_code == 400
            and wrong.json()["code"] == "CURRENT_PASSWORD_INVALID"
        )
        changed = await client.put(
            "/api/v1/account/password",
            json={"current_password": PASSWORD, "new_password": "another-pass"},
            headers=headers,
        )
        assert changed.status_code == 204
        profile = await client.patch(
            "/api/v1/users/me", json={"display_name": "An"}, headers=headers
        )
        assert profile.json()["display_name"] == "An"


async def test_revoking_the_current_session_logs_out(migrated_dsn: str) -> None:
    email = new_email()
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await verified_register(client, outbox, email)
        await client.get("/api/v1/users/me")
        sessions = (await client.get("/api/v1/account/sessions")).json()
        assert len(sessions) == 1 and sessions[0]["current"] is True
        assert sessions[0]["id"] == session_id_of(client.cookies["pharma_session"])
        revoke = await client.delete(
            f"/api/v1/account/sessions/{sessions[0]['id']}", headers=csrf_header(client)
        )
        assert revoke.status_code == 204
        assert (await client.get("/api/v1/users/me")).status_code == 401


async def test_login_is_throttled_after_ten_failures(migrated_dsn: str) -> None:
    email = new_email()
    async with postgres_app(migrated_dsn) as (client, _, outbox):
        await verified_register(client, outbox, email)
        client.cookies.clear()
        for _ in range(10):
            failed = await client.post(
                "/api/v1/auth/cookie/login",
                data={"username": email, "password": "wrong-pass"},
            )
            assert failed.status_code == 400
        locked = await client.post(
            "/api/v1/auth/cookie/login", data={"username": email, "password": PASSWORD}
        )
    assert locked.status_code == 429 and "retry-after" in locked.headers
```

- [ ] **Step 2: Chạy, xác nhận fail**

Run: `uv run --directory backend pytest -q -m integration tests/api/test_account_api_postgres.py`
Expected: FAIL (route chưa có).

- [ ] **Step 3: Sửa `api/deps.py`**

Thêm (giữ nội dung cũ):

```python
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Response

from pharma_agent.application.account.messages import (
    Locale,
    locale_from_accept_language,
)
from pharma_agent.application.account.service import AccountService
from pharma_agent.infrastructure.auth.users import SESSION_COOKIE_NAME

SessionLogin = Callable[[uuid.UUID], Awaitable[Response]]


def require_account(container: Container) -> AccountService:
    if container.account is None:
        raise ServiceNotConfigured(
            "accounts are not configured (set PHARMA_AUTH__OTP_SECRET)"
        )
    return container.account


def request_locale(request: Request) -> Locale:
    return locale_from_accept_language(request.headers.get("accept-language"))


def client_ip(request: Request) -> str | None:
    return None if request.client is None else request.client.host


def current_session_token(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE_NAME)


RequestLocale = Annotated[Locale, Depends(request_locale)]
ClientIp = Annotated[str | None, Depends(client_ip)]
CurrentSessionToken = Annotated[str | None, Depends(current_session_token)]
```

Nếu `deps.py` đã import `UserTable` cho `user_id_dependency` thì giữ nguyên.

- [ ] **Step 4: Viết `api/routers/account.py`**

```python
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
    email: EmailStr


class EmailCodeBody(EmailBody):
    code: str = Field(pattern=CODE_PATTERN)


class PasswordResetBody(EmailCodeBody):
    password: str = Field(min_length=1, max_length=1024)


class PhoneBody(BaseModel):
    phone: str = Field(min_length=3, max_length=32)


class PhoneCodeBody(PhoneBody):
    code: str = Field(pattern=CODE_PATTERN)


class PasswordChangeBody(BaseModel):
    current_password: str | None = None
    new_password: str = Field(min_length=1, max_length=1024)


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


def accepted() -> Response:
    return Response(status_code=status.HTTP_202_ACCEPTED)


def no_content() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def build_account_router(
    current_user_id: UserIdDependency, session_login: Callable[..., Any]
) -> APIRouter:
    router = APIRouter()
    UserId = Annotated[str, Depends(current_user_id)]
    Login = Annotated[SessionLogin, Depends(session_login)]

    def uid(user_id: str) -> uuid.UUID:
        return uuid.UUID(hex=user_id)

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
        responses=problem_responses(400, 403, 422),
    )
    async def verify_email(
        body: EmailCodeBody, container: ContainerDep, login: Login
    ) -> Response:
        user_id = await require_account(container).verify_email(body.email, body.code)
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

    return router
```

Nếu `test_every_error_response_is_a_problem` báo một status trong `problem_responses` không xuất hiện, thêm hoặc bỏ status cho đúng với lỗi thật mà route có thể trả.

- [ ] **Step 5: Sửa `api/errors.py`**

Import `math` và các lỗi mới từ `pharma_agent.application.account.errors`. Thêm vào đầu `STATUS_BY_ERROR`:

```python
    RateLimited: 429,
    AccountNotFound: 404,
    SessionNotFound: 404,
    AccountDisabled: 403,
    EmailAlreadyUsed: 409,
    PhoneAlreadyUsed: 409,
    LastSignInMethod: 409,
```

Trong `application_error_handler`:

```python
    headers = (
        {"Retry-After": str(math.ceil(exc.retry_after))}
        if isinstance(exc, RateLimited)
        else None
    )
    return problem_response(status, exc.code, detail=str(exc), headers=headers)
```

`InvalidCode`, `CurrentPasswordInvalid` rơi vào mặc định 400; `PasswordInvalid`, `PhoneNumberInvalid`, `PhoneCountryNotAllowed` thừa kế `InvalidInput` (422); `DeliveryFailed` thừa kế `ServiceUnavailable` (503).

- [ ] **Step 6: Sửa `api/app.py`**

Import `build_account_router` và thêm sau `include_auth_routes(api, auth)`/`current_user_id`:

```python
    api.include_router(build_account_router(current_user_id, auth.login_session))
```

- [ ] **Step 7: Sửa test cũ**

- `tests/api/test_openapi.py`: trong `EXPECTED_OPERATION_IDS` bỏ `"users:user"`, `"users:patch_user"`, `"users:delete_user"`; thêm 15 tên route mới của bảng Interfaces (trừ `users:current_user`, `users:patch_current_user` đã có). `oauth-associate:*` không có vì settings xuất OpenAPI không bật Google; nếu `openapi_export_settings` bật Google thì thêm `oauth-associate:google.authorize` và `oauth-associate:google.callback`.
- `tests/api/test_cookie_auth_postgres.py`: mỗi test đang `register` rồi `cookie_login` đổi thành `verified_register(client, outbox, email)` rồi `cookie_login`; unpack `postgres_app` thành ba phần tử. `test_cookie_login_sets_an_httponly_session_that_authorizes`: sau `verified_register` client đã có session từ bước verify, nên trước `cookie_login` thêm `client.cookies.clear()` và giữ assertion `sessions_for(...) == 2` thay cho `== 1` (một phiên từ verify, một từ login), hoặc xoá phiên verify bằng `await client.post("/api/v1/auth/cookie/logout", headers=csrf_header(client))` sau khi gọi `GET /users/me`. Dùng cách logout để giữ `== 1`.
- `tests/api/test_e2e_postgres.py`, `tests/e2e/test_server_smoke.py`: nếu đăng ký rồi đăng nhập, xác minh trước bằng mã. Với `test_server_smoke.py` (app e2e), đọc mã qua endpoint `GET /api/v1/__e2e/outbox/code` của Task 10; chuyển phần sửa file này sang Task 10.

- [ ] **Step 8: Chạy toàn bộ backend**

Run: `uv run --directory backend pytest -q && uv run --directory backend pytest -q -m integration && uv run --directory backend pyrefly check && uv run ruff check backend && uv run ruff format --check backend`
Expected: PASS hết (trừ `tests/e2e/test_server_smoke.py` nếu nó cần endpoint của Task 10; ghi rõ nếu có và sửa ở Task 10).

- [ ] **Step 9: Commit**

```bash
git add backend
git commit -m "feat(backend): add account routes for codes, profile, contacts and sessions"
```

---

### Task 10: Dọn dữ liệu, tài liệu, server e2e

**Files:**
- Modify: `backend/src/pharma_agent/infrastructure/auth/session_cleanup.py`, `backend/src/pharma_agent/cli.py`, `backend/tests/test_cli.py`, `backend/tests/infrastructure/test_session_cleanup.py`
- Modify: `backend/tests/e2e/server.py`, `backend/tests/e2e/test_server_smoke.py`
- Modify: `backend/.env.example`, `backend/README.md`, `backend/.env` (file local của người dùng, không commit)

**Interfaces:**
- Produces: `delete_stale_account_rows(conninfo: str) -> tuple[int, int]` (số mã, số bucket đã xoá); route chỉ có trong server e2e `GET /api/v1/__e2e/outbox/code?to=<địa chỉ>` → `{"code": "123456"}` hoặc 404.

- [ ] **Step 1: Viết test dọn dữ liệu (fail)**

Thêm vào `backend/tests/infrastructure/test_session_cleanup.py`:

```python
async def test_stale_codes_and_buckets_are_deleted(migrated_dsn: str) -> None:
    conninfo = (
        make_url(migrated_dsn)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )
    async with await AsyncConnection.connect(conninfo, autocommit=True) as connection:
        await connection.execute("TRUNCATE one_time_codes, rate_limit_buckets")
        await connection.execute(
            "INSERT INTO one_time_codes (id, purpose, channel, destination, code_hash, expires_at) VALUES "
            "(gen_random_uuid(), 'verify_email', 'email', 'a@b.c', 'x', now() - interval '2 days'),"
            "(gen_random_uuid(), 'verify_email', 'email', 'a@b.c', 'y', now() + interval '5 minutes')"
        )
        await connection.execute(
            "INSERT INTO rate_limit_buckets (key, window_start, count) VALUES "
            "('old', now() - interval '2 days', 1), ('new', now(), 1)"
        )
    assert await delete_stale_account_rows(conninfo) == (1, 1)
```

Import `delete_stale_account_rows`, `AsyncConnection` (psycopg) và `make_url` nếu file chưa có. Trong `backend/tests/test_cli.py`, test `cleanup-sessions` hiện có monkeypatch `delete_expired_access_tokens`; monkeypatch thêm `delete_stale_account_rows` trả `(2, 3)` và assert output có `deleted 2 codes and 3 rate limit buckets`.

- [ ] **Step 2: Cài đặt**

`session_cleanup.py`, thêm:

```python
_DELETE_STALE_CODES = (
    "DELETE FROM one_time_codes WHERE expires_at < now() - interval '1 day'"
)
_DELETE_STALE_BUCKETS = (
    "DELETE FROM rate_limit_buckets WHERE window_start < now() - interval '1 day'"
)


async def delete_stale_account_rows(conninfo: str) -> tuple[int, int]:
    """Delete codes expired over a day ago and rate-limit windows older than a day.

    The longest window is one hour, so a day-old bucket never limits anything.
    """
    async with (
        await AsyncConnection.connect(conninfo) as connection,
        connection.transaction(),
    ):
        codes = await connection.execute(_DELETE_STALE_CODES)
        buckets = await connection.execute(_DELETE_STALE_BUCKETS)
    return codes.rowcount, buckets.rowcount
```

`cli.py`, trong `cleanup_sessions` sau dòng in số phiên:

```python
    codes, buckets = asyncio.run(delete_stale_account_rows(settings.postgres.conninfo))
    typer.echo(f"deleted {codes} codes and {buckets} rate limit buckets")
```

Cập nhật docstring lệnh: `"""Xóa phiên đăng nhập hết hạn, mã OTP và bộ đếm giới hạn cũ."""`.

- [ ] **Step 3: Server e2e đọc được mã**

Trong `backend/tests/e2e/server.py`:

```python
from fastapi import HTTPException

from tests.account_fakes import RecordingEmailSender, RecordingSmsSender, code_in
```

Đổi `e2e_container_factory` nhận hai sender và truyền vào `open_container(..., email_sender=email, sms_sender=sms)`. Đổi `build_e2e_app`:

```python
def build_e2e_app(config: E2EConfig) -> FastAPI:
    email = RecordingEmailSender()
    sms = RecordingSmsSender()
    app = create_app(
        e2e_settings(config), container_factory=e2e_container_factory(email, sms)
    )

    @app.get("/api/v1/__e2e/outbox/code", include_in_schema=False)
    async def latest_code(to: str) -> dict[str, str]:
        """E2E only: the last code sent to `to` (email address or E.164 number)."""
        texts = [m.text for m in email.sent if m.to == to] + [
            m.text for m in sms.sent if m.to == to
        ]
        if not texts:
            raise HTTPException(status_code=404, detail="NO_CODE")
        return {"code": code_in(texts[-1])}

    return app
```

Thứ tự `texts` ưu tiên SMS sau email; một địa chỉ chỉ nhận một kênh nên không lẫn. Sửa `tests/e2e/test_server_smoke.py`: sau khi đăng ký, lấy mã qua `GET /api/v1/__e2e/outbox/code?to=<email>` rồi gọi `POST /api/v1/auth/email/verify` trước khi đăng nhập.

- [ ] **Step 4: Tài liệu và `.env`**

`backend/.env.example`, thêm khối:

```bash
# Account flows: one-time codes are HMAC'd with this secret (at least 32 characters).
PHARMA_AUTH__OTP_SECRET=change-me-to-a-random-string-of-32-characters
# Email: log (local only), smtp (Gmail app password, no domain needed) or resend (needs a verified domain).
# PHARMA_EMAIL__PROVIDER=smtp
# PHARMA_EMAIL__SENDER=ViPharMind <you@gmail.com>
# PHARMA_EMAIL__SMTP_USERNAME=you@gmail.com
# PHARMA_EMAIL__SMTP_PASSWORD=gmail-app-password
# PHARMA_EMAIL__RESEND_API_KEY=re_...
# SMS: only the log provider exists until a provider is chosen; codes go to countries listed here.
# PHARMA_SMS__ALLOWED_COUNTRY_CODES=["VN"]
```

`backend/.env` (local, không commit): thêm `PHARMA_AUTH__OTP_SECRET=` với giá trị sinh bằng `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.

`backend/README.md`, mục `### Xác thực`: thay đoạn mô tả đăng ký/đăng nhập bằng mô tả mới (đăng ký → mã xác minh email → đăng nhập; đăng nhập bằng số điện thoại; quên mật khẩu; các route `/account/*`; biến `PHARMA_AUTH__OTP_SECRET`, `PHARMA_EMAIL__*`, `PHARMA_SMS__*`; provider `log` in mã ra log khi chạy local). Ví dụ curl đăng ký đổi thành ba bước: `POST /auth/register`, đọc mã trong log backend, `POST /auth/email/verify`.

- [ ] **Step 5: Chạy**

Run: `uv run --directory backend pytest -q && uv run --directory backend pytest -q -m integration && uv run pre-commit run --all-files`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src backend/tests backend/.env.example backend/README.md
git commit -m "feat(backend): clean up stale codes, document account settings, expose E2E codes"
```

---

### Task 11: Nền frontend: client API, header ngôn ngữ, thành phần nhập mã

**Files:**
- Modify: `frontend/openapi.json`, `frontend/app/api/gen/**` (sinh lại)
- Modify: `frontend/app/api/fetcher.ts`, `frontend/app/api/fetcher.browser.test.tsx`, `frontend/app/api/problem.ts`, `frontend/app/api/problem.test.ts`
- Create (shadcn CLI): `frontend/app/components/ui/input-otp.tsx`, `frontend/app/components/ui/tabs.tsx`
- Create: `frontend/app/components/otp-code-field.tsx`, `frontend/app/components/resend-code-button.tsx`, `frontend/app/components/code-step.tsx`, `frontend/app/components/code-step.browser.test.tsx`, `frontend/app/hooks/use-countdown.ts`, `frontend/app/lib/phone.ts`, `frontend/app/lib/phone.test.ts`, `frontend/app/features/auth/lib/account-label.ts`, `frontend/app/features/auth/lib/account-label.test.ts`
- Modify: `frontend/app/i18n/resources/{vi,en}/{common,errors,settings}.json`
- Modify (đổi kiểu `UserRead` → `AccountView`): `features/auth/lib/require-user.ts`, `features/shell/components/AppSidebar.tsx`, `features/shell/components/UserMenu.tsx`, `features/settings/components/ProfileForm.tsx`, các test `SettingsPage`, `ProfileForm`, `AppSidebar`
- Modify: `features/settings/components/PasswordForm.tsx`, `PasswordForm.browser.test.tsx`, `features/settings/lib/account-schemas.ts`, `account-schemas.test.ts`, `SettingsPage.tsx`

**Interfaces:**
- Consumes: OpenAPI của Task 9.
- Produces:
  - `ApiError.retryAfter: number | undefined`.
  - `OtpCodeField({ id, value, onChange, invalid?, disabled? })`, `OTP_LENGTH = 6`.
  - `ResendCodeButton({ onResend: () => Promise<void> })`, `RESEND_COOLDOWN_SECONDS = 60`.
  - `CodeStep({ id, description, submitLabel, onSubmit: (code: string) => Promise<void>, onResend: () => Promise<void> })`.
  - `useCountdown(): { secondsLeft: number; start: (seconds: number) => void }`.
  - `phoneSchema(invalidMessage: string)` — zod, output là chuỗi E.164.
  - `accountLabel(user: AccountView): string`.
  - `PasswordForm({ passwordSet }: { passwordSet: boolean })`.

- [ ] **Step 1: Sinh lại client API**

```bash
cd frontend && npm run api:openapi && npm run api:generate
```

Expected: `openapi.json` có các route mới; `app/api/gen/endpoints.ts` có `authEmailVerify`, `useAuthEmailVerifyRequest`, `useAuthPhoneLogin`, `useAccountSessionsList`, `useAccountPasswordChange`, `oauthAssociateGoogleAuthorize` (nếu settings xuất OpenAPI có Google), schema `AccountView`, `SessionView`. Nếu `oauthAssociateGoogle*` không có, chạy `grep -n "google" ../backend/src/pharma_agent/api/openapi.py` để xem `openapi_export_settings`; đặt `google_client_id` và `google_client_secret` giả trong settings xuất OpenAPI (như route Google đăng nhập đang có trong `openapi.json`).

- [ ] **Step 2: Thêm component shadcn và thư viện**

```bash
cd frontend && npx shadcn add input-otp tabs && npm install libphonenumber-js@1
```

Expected: `app/components/ui/input-otp.tsx` export `InputOTP, InputOTPGroup, InputOTPSlot, InputOTPSeparator`; `app/components/ui/tabs.tsx` export `Tabs, TabsList, TabsTrigger, TabsContent, tabsListVariants`; `package.json` có `input-otp` và `libphonenumber-js` với phiên bản cố định (theo quy ước repo, ghi đúng số phiên bản, không dùng `^`). Chạy `npm run lint` để chắc file sinh ra qua oxlint; nếu lint báo lỗi trong file sinh, sửa code chứ không tắt rule.

- [ ] **Step 3: Viết test cho fetcher, problem, phone, account-label (fail)**

`app/api/fetcher.browser.test.tsx`, thêm:

```tsx
test("sends the UI language so emails and SMS match it", async () => {
  let language: string | null = null
  worker.use(
    http.get("/api/v1/probe", ({ request }) => {
      language = request.headers.get("accept-language")
      return HttpResponse.json({})
    })
  )
  document.documentElement.lang = "en"
  await fetcher("/api/v1/probe")
  expect(language).toBe("en")
})
```

`app/api/problem.test.ts`, thêm:

```ts
test("keeps Retry-After in seconds", async () => {
  const response = new Response(
    JSON.stringify({ code: "RATE_LIMITED", title: "Too Many Requests" }),
    { status: 429, headers: { "Retry-After": "42", "Content-Type": "application/problem+json" } }
  )
  const error = await toApiError(response)
  expect(error.retryAfter).toBe(42)
  expect((await toApiError(new Response(null, { status: 500 }))).retryAfter).toBeUndefined()
})
```

`app/lib/phone.test.ts`:

```ts
import { describe, expect, test } from "vitest"

import { phoneSchema } from "./phone"

describe("phoneSchema", () => {
  const schema = phoneSchema("invalid")

  test.each(["0912345678", "0912 345 678", "091.234.5678", "+84 91 234 5678"])(
    "%s becomes E.164",
    (input) => {
      expect(schema.parse(input)).toBe("+84912345678")
    }
  )

  test.each(["", "12345", "abc"])("rejects %j", (input) => {
    const result = schema.safeParse(input)
    expect(result.success).toBe(false)
    expect(result.error?.issues[0]?.message).toBe("invalid")
  })
})
```

`app/features/auth/lib/account-label.test.ts`:

```ts
import { expect, test } from "vitest"

import type { AccountView } from "~/api/gen/schemas"

import { accountLabel } from "./account-label"

const base: AccountView = {
  id: "0b7c3f5e-4a53-4f5e-9a51-7d1e2f3a4b5c",
  email: null,
  phone_number: "+84912345678",
  display_name: "",
  is_active: true,
  is_superuser: false,
  is_verified: true,
  email_verified: false,
  phone_verified: true,
  password_set: false,
  google_linked: false,
}

test("prefers the display name, then email, then phone", () => {
  expect(accountLabel({ ...base, display_name: "An" })).toBe("An")
  expect(accountLabel({ ...base, email: "an@example.com" })).toBe("an@example.com")
  expect(accountLabel(base)).toBe("+84912345678")
})
```

Kiểu field nullable trong `AccountView` do orval sinh là `string | null` hoặc `AccountViewEmail` (alias `string | null`). Nếu orval sinh alias riêng, test vẫn đúng vì gán `null` hợp lệ.

- [ ] **Step 4: Chạy, xác nhận fail**

Run: `cd frontend && npx vitest run app/lib/phone.test.ts app/api/problem.test.ts app/features/auth/lib/account-label.test.ts`
Expected: FAIL (module/field chưa có).

- [ ] **Step 5: Cài đặt fetcher, problem, phone, account-label**

`app/api/fetcher.ts`, thêm trước `fetcher`:

```ts
/** The UI language, so codes and notices arrive in it. Loaders on the server send none. */
function uiLanguage(): string | undefined {
  if (typeof document === "undefined") {
    return undefined
  }
  return document.documentElement.lang || undefined
}
```

và trong `fetcher`, sau khối `Accept`:

```ts
  const language = uiLanguage()
  if (language !== undefined && !headers.has("Accept-Language")) {
    headers.set("Accept-Language", language)
  }
```

`app/api/problem.ts`: thêm `readonly retryAfter: number | undefined` vào `ApiError`, tham số `retryAfter?: number | undefined` trong `init`, gán `this.retryAfter = init.retryAfter`; trong `toApiError` tính một lần:

```ts
  const retryHeader = Number(response.headers.get("Retry-After"))
  const retryAfter =
    Number.isFinite(retryHeader) && retryHeader > 0 ? retryHeader : undefined
```

rồi truyền `retryAfter` vào cả ba `new ApiError({...})`. `Number(null)` là `0` nên header thiếu cho `undefined`.

`app/lib/phone.ts`:

```ts
import { parsePhoneNumberFromString } from "libphonenumber-js/min"
import { z } from "zod"

/** Numbers typed without a country code are Vietnamese. */
export const DEFAULT_PHONE_COUNTRY = "VN"

function parse(value: string) {
  return parsePhoneNumberFromString(value, DEFAULT_PHONE_COUNTRY)
}

/** Accepts local and international input; the parsed value is E.164 ("+84912345678"). */
export function phoneSchema(invalidMessage: string) {
  return z
    .string()
    .trim()
    .refine((value) => parse(value)?.isValid() === true, { error: invalidMessage })
    .transform((value) => parse(value)?.number ?? value)
}
```

`app/features/auth/lib/account-label.ts`:

```ts
import type { AccountView } from "~/api/gen/schemas"

/** How the shell names the signed-in account: phone-only accounts have no email. */
export function accountLabel(user: AccountView): string {
  if (user.display_name !== "") {
    return user.display_name
  }
  return user.email ?? user.phone_number ?? ""
}
```

- [ ] **Step 6: Đổi `UserRead` sang `AccountView`**

```bash
cd frontend && grep -rl "UserRead" app --include=*.ts --include=*.tsx | grep -v "api/gen" | xargs sed -i 's/\bUserRead\b/AccountView/g'
```

Trong các object `USER` của test (`SettingsPage`, `ProfileForm`, `AppSidebar`), thêm các field bắt buộc mới: `phone_number: null, email_verified: true, phone_verified: false, password_set: true, google_linked: false`.

`UserMenu.tsx`: thay khối chọn tên hiển thị (dòng 24–27) bằng `const label = accountLabel(user)` (import từ `~/features/auth/lib/account-label`, được phép vì `shell → auth`), và `<DropdownMenuLabel>{user.email}</DropdownMenuLabel>` bằng `<DropdownMenuLabel>{user.email ?? user.phone_number}</DropdownMenuLabel>`.

- [ ] **Step 7: Chuyển `PasswordForm` sang `PUT /account/password`**

`app/features/settings/lib/account-schemas.ts`, thay `createPasswordSchema`:

```ts
/** `PUT /account/password`; `current_password` is required only once a password is set. */
export function createPasswordSchema(
  messages: PasswordMessages & { currentRequired: string },
  passwordSet: boolean
) {
  return z
    .object({
      current_password: passwordSet
        ? z.string().min(1, { error: messages.currentRequired })
        : z.string(),
      password: z
        .string()
        .min(PASSWORD_MIN_LENGTH, { error: messages.tooShort })
        .max(PASSWORD_MAX_LENGTH, { error: messages.tooLong }),
      confirm: z.string(),
    })
    .refine((values) => values.password === values.confirm, {
      error: messages.mismatch,
      path: ["confirm"],
    })
}
```

Cập nhật `account-schemas.test.ts` cho chữ ký mới (một ca `passwordSet = true` thiếu mật khẩu hiện tại thì lỗi, một ca `false` thì không).

`PasswordForm.tsx`: nhận prop `{ passwordSet }`; dùng `useAccountPasswordChange()`; form có thêm trường `current_password` (label `t("password.current")`, `autoComplete="current-password"`) chỉ hiện khi `passwordSet`; submit gửi `{ data: { current_password: passwordSet ? values.current_password : null, new_password: values.password } }`; lỗi `CURRENT_PASSWORD_INVALID` gắn vào trường `current_password`, lỗi `PASSWORD_INVALID` gắn vào `password`, còn lại dùng `applyApiError` với `PASSWORD_FIELDS = ["password", "current_password"]`. `SettingsPage.tsx` truyền `passwordSet={user.data.password_set}` (render `PasswordForm` khi `user.data` đã có, giống `ProfileForm`).

Cập nhật `PasswordForm.browser.test.tsx`: handler msw đổi sang `http.put("/api/v1/account/password", ...)`, thêm test "asks for the current password when one is set" (render với `passwordSet`, gửi body có `current_password`) và "a phone account sets its first password without the current one" (`passwordSet={false}`, không có ô mật khẩu hiện tại, body `current_password: null`).

- [ ] **Step 8: Viết `use-countdown`, `OtpCodeField`, `ResendCodeButton`, `CodeStep` và test**

`app/hooks/use-countdown.ts`:

```ts
import { useCallback, useEffect, useState } from "react"

/** Whole seconds left until a deadline set with `start`; 0 when idle. */
export function useCountdown(): {
  secondsLeft: number
  start: (seconds: number) => void
} {
  const [deadline, setDeadline] = useState<number | null>(null)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (deadline === null) {
      return
    }
    const timer = window.setInterval(() => {
      const current = Date.now()
      setNow(current)
      if (current >= deadline) {
        setDeadline(null)
      }
    }, 1000)
    return () => {
      window.clearInterval(timer)
    }
  }, [deadline])

  const start = useCallback((seconds: number) => {
    const current = Date.now()
    setNow(current)
    setDeadline(current + seconds * 1000)
  }, [])

  const secondsLeft =
    deadline === null ? 0 : Math.max(0, Math.ceil((deadline - now) / 1000))
  return { secondsLeft, start }
}
```

`app/components/otp-code-field.tsx`:

```tsx
import { REGEXP_ONLY_DIGITS } from "input-otp"

import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
} from "~/components/ui/input-otp"

export const OTP_LENGTH = 6

export function OtpCodeField({
  id,
  value,
  onChange,
  invalid = false,
  disabled = false,
}: {
  id: string
  value: string
  onChange: (value: string) => void
  invalid?: boolean
  disabled?: boolean
}) {
  return (
    <InputOTP
      id={id}
      maxLength={OTP_LENGTH}
      pattern={REGEXP_ONLY_DIGITS}
      inputMode="numeric"
      autoComplete="one-time-code"
      value={value}
      onChange={onChange}
      disabled={disabled}
      aria-invalid={invalid}
    >
      <InputOTPGroup>
        {Array.from({ length: OTP_LENGTH }, (_, index) => (
          <InputOTPSlot key={index} index={index} />
        ))}
      </InputOTPGroup>
    </InputOTP>
  )
}
```

`app/components/resend-code-button.tsx`:

```tsx
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { isApiError } from "~/api/problem"
import { Button } from "~/components/ui/button"
import { useCountdown } from "~/hooks/use-countdown"
import { apiErrorMessage } from "~/i18n/error-message"

/** The backend's minimum gap between two codes to the same address. */
export const RESEND_COOLDOWN_SECONDS = 60

export function ResendCodeButton({
  onResend,
}: {
  onResend: () => Promise<void>
}) {
  const { t } = useTranslation("common")
  const { t: tErrors } = useTranslation("errors")
  const { secondsLeft, start } = useCountdown()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // A code was sent just before this button appeared.
  useEffect(() => {
    start(RESEND_COOLDOWN_SECONDS)
  }, [start])

  async function resend() {
    setPending(true)
    setError(null)
    try {
      await onResend()
      start(RESEND_COOLDOWN_SECONDS)
    } catch (caught) {
      if (isApiError(caught) && caught.retryAfter !== undefined) {
        start(caught.retryAfter)
      }
      setError(apiErrorMessage(caught, tErrors))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex flex-col items-start gap-1 text-sm">
      <Button
        type="button"
        variant="link"
        className="h-auto p-0"
        disabled={pending || secondsLeft > 0}
        onClick={() => void resend()}
      >
        {secondsLeft > 0 ? t("code.resendIn", { seconds: secondsLeft }) : t("code.resend")}
      </Button>
      {error === null ? null : (
        <p role="alert" className="text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
```

`app/components/code-step.tsx`:

```tsx
import { type FormEvent, useState } from "react"
import { useTranslation } from "react-i18next"

import { OTP_LENGTH, OtpCodeField } from "~/components/otp-code-field"
import { ResendCodeButton } from "~/components/resend-code-button"
import { Button } from "~/components/ui/button"
import { Field, FieldLabel } from "~/components/ui/field"
import { Spinner } from "~/components/ui/spinner"
import { apiErrorMessage } from "~/i18n/error-message"

/** Enter the six-digit code that was just sent, or ask for another one. */
export function CodeStep({
  id,
  description,
  submitLabel,
  onSubmit,
  onResend,
}: {
  id: string
  description: string
  submitLabel: string
  onSubmit: (code: string) => Promise<void>
  onResend: () => Promise<void>
}) {
  const { t } = useTranslation("common")
  const { t: tErrors } = useTranslation("errors")
  const [code, setCode] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (code.length !== OTP_LENGTH) {
      setError(t("code.incomplete"))
      return
    }
    setPending(true)
    setError(null)
    try {
      await onSubmit(code)
    } catch (caught) {
      setError(apiErrorMessage(caught, tErrors))
      setCode("")
    } finally {
      setPending(false)
    }
  }

  return (
    <form noValidate onSubmit={(event) => void submit(event)} className="flex flex-col gap-6">
      <p className="text-sm text-muted-foreground">{description}</p>
      <Field data-invalid={error !== null}>
        <FieldLabel htmlFor={id}>{t("code.label")}</FieldLabel>
        <OtpCodeField id={id} value={code} onChange={setCode} invalid={error !== null} />
      </Field>
      {error === null ? null : (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" disabled={pending}>
        {pending ? <Spinner /> : null}
        {submitLabel}
      </Button>
      <ResendCodeButton onResend={onResend} />
    </form>
  )
}
```

`app/components/code-step.browser.test.tsx`:

```tsx
import { describe, expect, test, vi } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { ApiError } from "~/api/problem"
import { CodeStep } from "~/components/code-step"

import { TestProviders } from "../../tests/utils/providers"

async function renderStep(
  onSubmit: (code: string) => Promise<void>,
  onResend: () => Promise<void> = async () => {}
) {
  await render(
    <TestProviders>
      <CodeStep
        id="code"
        description="Đã gửi mã tới an@example.com"
        submitLabel="Xác minh"
        onSubmit={onSubmit}
        onResend={onResend}
      />
    </TestProviders>
  )
}

describe("CodeStep", () => {
  test("submits the six digits", async () => {
    const codes: string[] = []
    await renderStep(async (code) => {
      codes.push(code)
    })
    await page.getByLabelText("Mã xác minh").fill("042137")
    await page.getByRole("button", { name: "Xác minh" }).click()
    await expect.poll(() => codes).toEqual(["042137"])
  })

  test("asks for all six digits before submitting", async () => {
    await renderStep(async () => {
      throw new Error("must not submit")
    })
    await page.getByLabelText("Mã xác minh").fill("123")
    await page.getByRole("button", { name: "Xác minh" }).click()
    await expect.element(page.getByRole("alert")).toHaveTextContent("Nhập đủ 6 chữ số.")
  })

  test("shows the server error and clears the code", async () => {
    await renderStep(async () => {
      throw new ApiError({ status: 400, code: "OTP_INVALID", title: "Bad Request" })
    })
    await page.getByLabelText("Mã xác minh").fill("000000")
    await page.getByRole("button", { name: "Xác minh" }).click()
    await expect
      .element(page.getByRole("alert"))
      .toHaveTextContent("Mã không đúng hoặc đã hết hạn.")
  })

  test("resend waits for the cooldown, then follows Retry-After", async () => {
    vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] })
    try {
      await renderStep(
        async () => {},
        async () => {
          throw new ApiError({
            status: 429,
            code: "RATE_LIMITED",
            title: "Too Many Requests",
            retryAfter: 42,
          })
        }
      )
      await expect
        .element(page.getByRole("button", { name: "Gửi lại sau 60 giây" }))
        .toBeDisabled()
      await vi.advanceTimersByTimeAsync(61_000)
      await page.getByRole("button", { name: "Gửi lại mã" }).click()
      await expect
        .element(page.getByRole("button", { name: "Gửi lại sau 42 giây" }))
        .toBeDisabled()
      await expect
        .element(page.getByRole("alert"))
        .toHaveTextContent("Bạn thao tác quá nhanh. Vui lòng thử lại sau.")
    } finally {
      vi.useRealTimers()
    }
  })
})
```

Nếu đồng hồ giả làm `expect.element` (vốn thăm dò theo thời gian thật) treo, chỉ giả `Date` và `setInterval`/`clearInterval` như trên, không giả `setTimeout`.

- [ ] **Step 9: Thêm chuỗi i18n**

`app/i18n/resources/vi/common.json`, thêm:

```json
"code": {
  "label": "Mã xác minh",
  "incomplete": "Nhập đủ 6 chữ số.",
  "resend": "Gửi lại mã",
  "resendIn": "Gửi lại sau {{seconds}} giây"
}
```

`en/common.json`:

```json
"code": {
  "label": "Verification code",
  "incomplete": "Enter all 6 digits.",
  "resend": "Resend code",
  "resendIn": "Resend in {{seconds}} seconds"
}
```

`vi/errors.json`, thêm:

```json
"OTP_INVALID": "Mã không đúng hoặc đã hết hạn.",
"RATE_LIMITED": "Bạn thao tác quá nhanh. Vui lòng thử lại sau.",
"EMAIL_NOT_VERIFIED": "Email chưa được xác minh.",
"EMAIL_ALREADY_USED": "Email này đã thuộc tài khoản khác.",
"PHONE_ALREADY_USED": "Số điện thoại này đã thuộc tài khoản khác.",
"LAST_SIGN_IN_METHOD": "Hãy thêm cách đăng nhập khác trước khi gỡ cách này.",
"CURRENT_PASSWORD_INVALID": "Mật khẩu hiện tại không đúng.",
"PASSWORD_INVALID": "Mật khẩu cần từ 8 đến 128 ký tự.",
"PHONE_NUMBER_INVALID": "Số điện thoại không hợp lệ.",
"PHONE_COUNTRY_NOT_ALLOWED": "Hiện chỉ hỗ trợ số điện thoại Việt Nam.",
"DELIVERY_FAILED": "Chưa gửi được mã. Vui lòng thử lại.",
"SESSION_NOT_FOUND": "Phiên đăng nhập không còn tồn tại.",
"ACCOUNT_DISABLED": "Tài khoản này đã bị khoá.",
"ACCOUNT_NOT_FOUND": "Không tìm thấy tài khoản."
```

`en/errors.json`:

```json
"OTP_INVALID": "The code is wrong or has expired.",
"RATE_LIMITED": "Too many attempts. Please try again later.",
"EMAIL_NOT_VERIFIED": "This email is not verified yet.",
"EMAIL_ALREADY_USED": "This email belongs to another account.",
"PHONE_ALREADY_USED": "This phone number belongs to another account.",
"LAST_SIGN_IN_METHOD": "Add another way to sign in before removing this one.",
"CURRENT_PASSWORD_INVALID": "The current password is wrong.",
"PASSWORD_INVALID": "Passwords need 8 to 128 characters.",
"PHONE_NUMBER_INVALID": "This phone number is not valid.",
"PHONE_COUNTRY_NOT_ALLOWED": "Only Vietnamese phone numbers are supported for now.",
"DELIVERY_FAILED": "The code could not be sent. Please try again.",
"SESSION_NOT_FOUND": "This session no longer exists.",
"ACCOUNT_DISABLED": "This account is disabled.",
"ACCOUNT_NOT_FOUND": "Account not found."
```

`settings.json` (vi/en): thêm `password.current` ("Mật khẩu hiện tại" / "Current password") và `password.currentRequired` ("Nhập mật khẩu hiện tại." / "Enter your current password.").

- [ ] **Step 10: Chạy toàn bộ frontend**

Run: `cd frontend && npm run -s typecheck && npm run -s lint && npm run -s format && npm test && npm run -s api:check`
Expected: PASS. `api:check` báo không có khác biệt giữa `openapi.json` và code sinh.

- [ ] **Step 11: Commit**

```bash
git add frontend
git commit -m "feat(frontend): add the code entry step, phone parsing and the account API client"
```

---

### Task 12: Xác minh email khi đăng ký và đăng nhập

**Files:**
- Create: `frontend/app/features/auth/components/VerifyEmailStep.tsx`
- Modify: `frontend/app/features/auth/components/RegisterForm.tsx`, `RegisterForm.browser.test.tsx`, `LoginForm.tsx`, `LoginForm.browser.test.tsx`
- Modify: `frontend/app/i18n/resources/{vi,en}/auth.json`

**Interfaces:**
- Consumes: `CodeStep`, `useAuthEmailVerify`, `useAuthEmailVerifyRequest`.
- Produces: `VerifyEmailStep({ email, nextPath })`.

- [ ] **Step 1: Viết test (fail)**

`RegisterForm.browser.test.tsx`: thay test `"registers, signs in with the same credentials and opens the next path"` bằng:

```tsx
  test("registers, then verifies the email with the code and opens the next path", async () => {
    let registered: unknown = null
    let verifyBody = ""
    worker.use(
      http.post("/api/v1/auth/register", async ({ request }) => {
        registered = await request.json()
        return HttpResponse.json(
          { id: "u1", email: "an@example.com", display_name: "An" },
          { status: 201 }
        )
      }),
      http.post("/api/v1/auth/email/verify", async ({ request }) => {
        verifyBody = await request.text()
        return new HttpResponse(null, { status: 204 })
      }),
      http.get("/api/v1/users/me", () =>
        HttpResponse.json({ id: "u1", email: "an@example.com" })
      )
    )

    await renderAndSubmit()

    await expect
      .element(page.getByText(/Chúng tôi đã gửi mã 6 số tới an@example\.com/))
      .toBeVisible()
    await page.getByLabelText("Mã xác minh").fill("123456")
    await page.getByRole("button", { name: "Xác minh email" }).click()
    await expect.element(page.getByText("chat-page")).toBeVisible()
    expect(registered).toEqual({
      email: "an@example.com",
      password: "correct horse",
      display_name: "An",
    })
    expect(verifyBody).toBe('{"email":"an@example.com","code":"123456"}')
  })
```

Không đăng ký handler cho `cookie/login`: nếu form còn gọi nó, msw (`onUnhandledRequest: "error"`) làm test fail.

`LoginForm.browser.test.tsx`: thêm test:

```tsx
test("an unverified email gets a code and the verification step", async () => {
  const requested: string[] = []
  worker.use(
    http.post("/api/v1/auth/cookie/login", () =>
      HttpResponse.json(
        { code: "EMAIL_NOT_VERIFIED", title: "Forbidden" },
        { status: 403, headers: { "Content-Type": "application/problem+json" } }
      )
    ),
    http.post("/api/v1/auth/email/verify/request", async ({ request }) => {
      requested.push(await request.text())
      return new HttpResponse(null, { status: 202 })
    })
  )
  await renderLogin()
  await submit("an@example.com", "mat-khau-dai")
  await expect
    .element(page.getByText("Chúng tôi đã gửi mã 6 số tới an@example.com"))
    .toBeVisible()
  expect(requested).toEqual(['{"email":"an@example.com"}'])
})
```

- [ ] **Step 2: Chạy, xác nhận fail**

Run: `cd frontend && npx vitest run --project browser app/features/auth/components`
Expected: FAIL.

- [ ] **Step 3: Viết `VerifyEmailStep.tsx`**

```tsx
import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"

import {
  getUsersCurrentUserQueryKey,
  useAuthEmailVerify,
  useAuthEmailVerifyRequest,
} from "~/api/gen/endpoints"
import { CodeStep } from "~/components/code-step"

const SKIP_AUTH_REDIRECT = { mutation: { meta: { skipAuthRedirect: true } } }

/** Verifies the email with the code just sent; a correct code also signs the user in. */
export function VerifyEmailStep({
  email,
  nextPath,
}: {
  email: string
  nextPath: string
}) {
  const { t } = useTranslation("auth")
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const verify = useAuthEmailVerify(SKIP_AUTH_REDIRECT)
  const resend = useAuthEmailVerifyRequest(SKIP_AUTH_REDIRECT)

  return (
    <CodeStep
      id="verify-email-code"
      description={t("verifyEmail.sentTo", { email })}
      submitLabel={t("verifyEmail.submit")}
      onSubmit={async (code) => {
        await verify.mutateAsync({ data: { email, code } })
        await queryClient.invalidateQueries({ queryKey: getUsersCurrentUserQueryKey() })
        await navigate(nextPath, { replace: true })
      }}
      onResend={async () => {
        await resend.mutateAsync({ data: { email } })
      }}
    />
  )
}
```

- [ ] **Step 4: Sửa `RegisterForm` và `LoginForm`**

`RegisterForm.tsx`: bỏ `useAuthCookieLogin`; thêm `const [registered, setRegistered] = useState<string | null>(null)`; trong `onSubmit`, sau khi `register.mutateAsync` thành công thì `setRegistered(values.email)` và `return` (không đăng nhập, không điều hướng); đầu phần render: `if (registered !== null) { return <VerifyEmailStep email={registered} nextPath={nextPath} /> }`.

`LoginForm.tsx`: thêm `const requestCode = useAuthEmailVerifyRequest(SKIP_AUTH_REDIRECT)` và state `unverified`; trong `catch`:

```tsx
      if (isApiError(error) && error.code === "EMAIL_NOT_VERIFIED") {
        // A code may already be on its way; a 429 here changes nothing for the user.
        await requestCode.mutateAsync({ data: { email: values.username } }).catch(() => {})
        setUnverified(values.username)
        return
      }
```

và trước `return (<form ...`: `if (unverified !== null) { return <VerifyEmailStep email={unverified} nextPath={nextPath} /> }`.

`auth.json` (vi):

```json
"verifyEmail": {
  "sentTo": "Chúng tôi đã gửi mã 6 số tới {{email}}. Nhập mã để kích hoạt tài khoản.",
  "submit": "Xác minh email"
}
```

(en):

```json
"verifyEmail": {
  "sentTo": "We sent a 6-digit code to {{email}}. Enter it to activate your account.",
  "submit": "Verify email"
}
```

Test ở Step 1 kiểm tra đoạn "Chúng tôi đã gửi mã 6 số tới an@example.com" bằng `getByText` với chuỗi con; nếu `getByText` cần khớp đủ, dùng `page.getByText(/Chúng tôi đã gửi mã 6 số tới an@example\.com/)`.

- [ ] **Step 5: Chạy**

Run: `cd frontend && npm run -s typecheck && npm run -s lint && npx vitest run --project browser app/features/auth`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat(frontend): verify the email with a code after registering or signing in"
```

---

### Task 13: Đăng nhập và đăng ký bằng số điện thoại

**Files:**
- Create: `frontend/app/features/auth/components/PhoneLoginForm.tsx`, `PhoneLoginForm.browser.test.tsx`
- Modify: `frontend/app/routes/auth/login.tsx`, `frontend/app/routes/auth/register.tsx`, `frontend/app/i18n/resources/{vi,en}/auth.json`

**Interfaces:**
- Consumes: `phoneSchema`, `CodeStep`, `useAuthPhoneRequest`, `useAuthPhoneLogin`, `Tabs`.
- Produces: `PhoneLoginForm({ nextPath })`.

- [ ] **Step 1: Viết test (fail)**

```tsx
import { http, HttpResponse } from "msw"
import { createRoutesStub } from "react-router"
import { beforeEach, describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { PhoneLoginForm } from "~/features/auth/components/PhoneLoginForm"
import { applyZodLocale } from "~/i18n/zod-locale"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

const Stub = createRoutesStub([
  { path: "/login", Component: () => <PhoneLoginForm nextPath="/chat" /> },
  { path: "/chat", Component: () => <p>chat-page</p> },
])

describe("PhoneLoginForm", () => {
  beforeEach(() => {
    applyZodLocale("vi")
  })

  test("sends the E.164 number, then signs in with the code", async () => {
    const bodies: string[] = []
    worker.use(
      http.post("/api/v1/auth/phone/request", async ({ request }) => {
        bodies.push(await request.text())
        return new HttpResponse(null, { status: 202 })
      }),
      http.post("/api/v1/auth/phone/login", async ({ request }) => {
        bodies.push(await request.text())
        return new HttpResponse(null, { status: 204 })
      })
    )
    await render(
      <TestProviders>
        <Stub initialEntries={["/login"]} />
      </TestProviders>
    )
    await page.getByLabelText("Số điện thoại").fill("0912 345 678")
    await page.getByRole("button", { name: "Gửi mã" }).click()
    await page.getByLabelText("Mã xác minh").fill("123456")
    await page.getByRole("button", { name: "Đăng nhập" }).click()
    await expect.element(page.getByText("chat-page")).toBeVisible()
    expect(bodies).toEqual([
      '{"phone":"+84912345678"}',
      '{"phone":"+84912345678","code":"123456"}',
    ])
  })

  test("an invalid number never reaches the server", async () => {
    await render(
      <TestProviders>
        <Stub initialEntries={["/login"]} />
      </TestProviders>
    )
    await page.getByLabelText("Số điện thoại").fill("12345")
    await page.getByRole("button", { name: "Gửi mã" }).click()
    await expect
      .element(page.getByText("Số điện thoại không hợp lệ."))
      .toBeVisible()
  })
})
```

- [ ] **Step 2: Chạy, xác nhận fail**

Run: `cd frontend && npx vitest run --project browser app/features/auth/components/PhoneLoginForm.browser.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Viết `PhoneLoginForm.tsx`**

```tsx
import { zodResolver } from "@hookform/resolvers/zod"
import { useQueryClient } from "@tanstack/react-query"
import { useMemo, useState } from "react"
import { Controller, useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"
import { z } from "zod"

import {
  getUsersCurrentUserQueryKey,
  useAuthPhoneLogin,
  useAuthPhoneRequest,
} from "~/api/gen/endpoints"
import { CodeStep } from "~/components/code-step"
import { Button } from "~/components/ui/button"
import { Field, FieldError, FieldLabel } from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { Spinner } from "~/components/ui/spinner"
import { apiErrorMessage } from "~/i18n/error-message"
import { applyApiError } from "~/lib/form-errors"
import { phoneSchema } from "~/lib/phone"

const SKIP_AUTH_REDIRECT = { mutation: { meta: { skipAuthRedirect: true } } }

/** Phone sign-in; a number without an account gets one, so this also registers. */
export function PhoneLoginForm({ nextPath }: { nextPath: string }) {
  const { t } = useTranslation("auth")
  const { t: tErrors } = useTranslation("errors")
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const requestCode = useAuthPhoneRequest(SKIP_AUTH_REDIRECT)
  const login = useAuthPhoneLogin(SKIP_AUTH_REDIRECT)
  const [phone, setPhone] = useState<string | null>(null)
  const schema = useMemo(
    () => z.object({ phone: phoneSchema(tErrors("PHONE_NUMBER_INVALID")) }),
    [tErrors]
  )
  const form = useForm({ resolver: zodResolver(schema), defaultValues: { phone: "" } })

  async function send(number: string): Promise<void> {
    await requestCode.mutateAsync({ data: { phone: number } })
  }

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await send(values.phone)
      setPhone(values.phone)
    } catch (error) {
      applyApiError(error, form.setError, ["phone"], apiErrorMessage(error, tErrors))
    }
  })

  if (phone !== null) {
    return (
      <CodeStep
        id="phone-login-code"
        description={t("phone.sentTo", { phone })}
        submitLabel={t("login.submit")}
        onSubmit={async (code) => {
          await login.mutateAsync({ data: { phone, code } })
          await queryClient.invalidateQueries({ queryKey: getUsersCurrentUserQueryKey() })
          await navigate(nextPath, { replace: true })
        }}
        onResend={() => send(phone)}
      />
    )
  }

  const serverError = form.formState.errors.root?.server?.message
  return (
    <form noValidate onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-6">
      <Controller
        name="phone"
        control={form.control}
        render={({ field, fieldState }) => (
          <Field data-invalid={fieldState.invalid}>
            <FieldLabel htmlFor="login-phone">{t("phone.label")}</FieldLabel>
            <Input
              {...field}
              id="login-phone"
              type="tel"
              autoComplete="tel"
              inputMode="tel"
              aria-invalid={fieldState.invalid}
            />
            <FieldError errors={[fieldState.error]} />
          </Field>
        )}
      />
      {serverError === undefined ? null : (
        <p role="alert" className="text-sm text-destructive">
          {serverError}
        </p>
      )}
      <Button type="submit" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting ? <Spinner /> : null}
        {t("phone.send")}
      </Button>
    </form>
  )
}
```

Kiểu của `useForm` với schema có `transform`: nếu TypeScript báo `values.phone` là input type, khai báo rõ `useForm<z.input<typeof schema>, unknown, z.output<typeof schema>>`.

- [ ] **Step 4: Gắn tab vào trang đăng nhập và đăng ký**

`routes/auth/login.tsx`: bọc nội dung đăng nhập bằng:

```tsx
      <Tabs defaultValue="email" className="flex flex-col gap-6">
        <TabsList className="w-full">
          <TabsTrigger value="email">{t("tabs.email")}</TabsTrigger>
          <TabsTrigger value="phone">{t("tabs.phone")}</TabsTrigger>
        </TabsList>
        <TabsContent value="email" className="flex flex-col gap-4">
          <LoginForm nextPath={nextPath} />
          <Link to="/forgot-password" className="text-sm underline underline-offset-4">
            {t("login.forgotLink")}
          </Link>
        </TabsContent>
        <TabsContent value="phone">
          <PhoneLoginForm nextPath={nextPath} />
        </TabsContent>
      </Tabs>
```

(giữ `FieldSeparator`, `GoogleButton` và link đăng ký bên dưới). `routes/auth/register.tsx`: tương tự, tab "email" chứa `RegisterForm`, tab "phone" chứa `PhoneLoginForm`.

`auth.json` (vi): thêm

```json
"tabs": { "email": "Email", "phone": "Số điện thoại" },
"phone": {
  "label": "Số điện thoại",
  "send": "Gửi mã",
  "sentTo": "Chúng tôi đã gửi mã 6 số qua SMS tới {{phone}}."
}
```

và `"login.forgotLink": "Quên mật khẩu?"`. (en): `"tabs": { "email": "Email", "phone": "Phone" }`, `"phone": { "label": "Phone number", "send": "Send code", "sentTo": "We sent a 6-digit code by SMS to {{phone}}." }`, `"login.forgotLink": "Forgot your password?"`.

Nếu test cũ của `LoginForm`/e2e tìm nhãn "Email" mà giờ trùng với tên tab "Email", dùng `{ exact: true }` cho `getByLabelText` (label) — tab là nút, không phải label, nên không trùng.

- [ ] **Step 5: Chạy**

Run: `cd frontend && npm run -s typecheck && npm run -s lint && npm test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat(frontend): sign in and register with a phone number and an SMS code"
```

---

### Task 14: Quên mật khẩu

**Files:**
- Create: `frontend/app/features/auth/components/ForgotPasswordForm.tsx`, `ForgotPasswordForm.browser.test.tsx`, `frontend/app/routes/auth/forgot-password.tsx`
- Modify: `frontend/app/routes.ts`, `frontend/app/i18n/resources/{vi,en}/auth.json`

**Interfaces:**
- Consumes: `useAuthPasswordForgot`, `useAuthPasswordReset`, `OtpCodeField`, `ResendCodeButton`, `passwordSchema`.
- Produces: route `/forgot-password`.

- [ ] **Step 1: Viết test (fail)**

```tsx
import { http, HttpResponse } from "msw"
import { createRoutesStub } from "react-router"
import { beforeEach, describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { ForgotPasswordForm } from "~/features/auth/components/ForgotPasswordForm"
import { applyZodLocale } from "~/i18n/zod-locale"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

const Stub = createRoutesStub([
  { path: "/forgot-password", Component: ForgotPasswordForm },
  { path: "/login", Component: () => <p>login-page</p> },
])

describe("ForgotPasswordForm", () => {
  beforeEach(() => {
    applyZodLocale("vi")
  })

  test("requests a code, then resets the password and returns to login", async () => {
    const bodies: string[] = []
    worker.use(
      http.post("/api/v1/auth/password/forgot", async ({ request }) => {
        bodies.push(await request.text())
        return new HttpResponse(null, { status: 202 })
      }),
      http.post("/api/v1/auth/password/reset", async ({ request }) => {
        bodies.push(await request.text())
        return new HttpResponse(null, { status: 204 })
      })
    )
    await render(
      <TestProviders>
        <Stub initialEntries={["/forgot-password"]} />
      </TestProviders>
    )
    await page.getByLabelText("Email").fill("an@example.com")
    await page.getByRole("button", { name: "Gửi mã" }).click()
    await page.getByLabelText("Mã xác minh").fill("123456")
    await page.getByLabelText("Mật khẩu mới", { exact: true }).fill("mat-khau-moi")
    await page.getByLabelText("Nhập lại mật khẩu mới").fill("mat-khau-moi")
    await page.getByRole("button", { name: "Đặt lại mật khẩu" }).click()
    await expect.element(page.getByText("login-page")).toBeVisible()
    expect(bodies).toEqual([
      '{"email":"an@example.com"}',
      '{"email":"an@example.com","code":"123456","password":"mat-khau-moi"}',
    ])
  })

  test("the two passwords must match", async () => {
    worker.use(
      http.post("/api/v1/auth/password/forgot", () => new HttpResponse(null, { status: 202 }))
    )
    await render(
      <TestProviders>
        <Stub initialEntries={["/forgot-password"]} />
      </TestProviders>
    )
    await page.getByLabelText("Email").fill("an@example.com")
    await page.getByRole("button", { name: "Gửi mã" }).click()
    await page.getByLabelText("Mã xác minh").fill("123456")
    await page.getByLabelText("Mật khẩu mới", { exact: true }).fill("mat-khau-moi")
    await page.getByLabelText("Nhập lại mật khẩu mới").fill("khac-hoan-toan")
    await page.getByRole("button", { name: "Đặt lại mật khẩu" }).click()
    await expect.element(page.getByText("Hai mật khẩu không khớp.")).toBeVisible()
  })
})
```

- [ ] **Step 2: Chạy, xác nhận fail**

Run: `cd frontend && npx vitest run --project browser app/features/auth/components/ForgotPasswordForm.browser.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Viết `ForgotPasswordForm.tsx`**

```tsx
import { zodResolver } from "@hookform/resolvers/zod"
import { useMemo, useState } from "react"
import { Controller, useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"
import { z } from "zod"

import { useAuthPasswordForgot, useAuthPasswordReset } from "~/api/gen/endpoints"
import { OTP_LENGTH, OtpCodeField } from "~/components/otp-code-field"
import { ResendCodeButton } from "~/components/resend-code-button"
import { Button } from "~/components/ui/button"
import { Field, FieldError, FieldGroup, FieldLabel } from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { Spinner } from "~/components/ui/spinner"
import { toast } from "~/components/ui/toast"
import { passwordSchema } from "~/features/auth/lib/password"
import { apiErrorMessage } from "~/i18n/error-message"
import { applyApiError } from "~/lib/form-errors"

const SKIP_AUTH_REDIRECT = { mutation: { meta: { skipAuthRedirect: true } } }

export function ForgotPasswordForm() {
  const { t } = useTranslation("auth")
  const { t: tErrors } = useTranslation("errors")
  const navigate = useNavigate()
  const forgot = useAuthPasswordForgot(SKIP_AUTH_REDIRECT)
  const reset = useAuthPasswordReset(SKIP_AUTH_REDIRECT)
  const [email, setEmail] = useState<string | null>(null)

  const emailForm = useForm({
    resolver: zodResolver(z.object({ email: z.email() })),
    defaultValues: { email: "" },
  })
  const resetSchema = useMemo(
    () =>
      z
        .object({
          code: z.string().length(OTP_LENGTH, { error: t("forgot.codeIncomplete") }),
          password: passwordSchema(t("passwordTooShort")),
          confirm: z.string(),
        })
        .refine((values) => values.password === values.confirm, {
          error: t("forgot.mismatch"),
          path: ["confirm"],
        }),
    [t]
  )
  const resetForm = useForm({
    resolver: zodResolver(resetSchema),
    defaultValues: { code: "", password: "", confirm: "" },
  })

  const sendCode = emailForm.handleSubmit(async (values) => {
    try {
      await forgot.mutateAsync({ data: { email: values.email } })
      setEmail(values.email)
    } catch (error) {
      applyApiError(error, emailForm.setError, ["email"], apiErrorMessage(error, tErrors))
    }
  })

  const submitReset = resetForm.handleSubmit(async (values) => {
    if (email === null) {
      return
    }
    try {
      await reset.mutateAsync({ data: { email, code: values.code, password: values.password } })
    } catch (error) {
      applyApiError(error, resetForm.setError, ["password"], apiErrorMessage(error, tErrors))
      return
    }
    toast.add({ type: "success", title: t("forgot.done") })
    await navigate("/login", { replace: true })
  })

  if (email === null) {
    const serverError = emailForm.formState.errors.root?.server?.message
    return (
      <form noValidate onSubmit={(event) => void sendCode(event)} className="flex flex-col gap-6">
        <Controller
          name="email"
          control={emailForm.control}
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldLabel htmlFor="forgot-email">{t("email")}</FieldLabel>
              <Input {...field} id="forgot-email" type="email" autoComplete="email" aria-invalid={fieldState.invalid} />
              <FieldError errors={[fieldState.error]} />
            </Field>
          )}
        />
        {serverError === undefined ? null : (
          <p role="alert" className="text-sm text-destructive">{serverError}</p>
        )}
        <Button type="submit" disabled={emailForm.formState.isSubmitting}>
          {emailForm.formState.isSubmitting ? <Spinner /> : null}
          {t("phone.send")}
        </Button>
      </form>
    )
  }

  const serverError = resetForm.formState.errors.root?.server?.message
  return (
    <form noValidate onSubmit={(event) => void submitReset(event)} className="flex flex-col gap-6">
      <p className="text-sm text-muted-foreground">{t("forgot.sentTo", { email })}</p>
      <FieldGroup>
        <Controller
          name="code"
          control={resetForm.control}
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.invalid}>
              <FieldLabel htmlFor="forgot-code">{t("forgot.code")}</FieldLabel>
              <OtpCodeField id="forgot-code" value={field.value} onChange={field.onChange} invalid={fieldState.invalid} />
              <FieldError errors={[fieldState.error]} />
            </Field>
          )}
        />
        {(["password", "confirm"] as const).map((name) => (
          <Controller
            key={name}
            name={name}
            control={resetForm.control}
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.invalid}>
                <FieldLabel htmlFor={`forgot-${name}`}>{t(`forgot.${name}`)}</FieldLabel>
                <Input {...field} id={`forgot-${name}`} type="password" autoComplete="new-password" aria-invalid={fieldState.invalid} />
                <FieldError errors={[fieldState.error]} />
              </Field>
            )}
          />
        ))}
      </FieldGroup>
      {serverError === undefined ? null : (
        <p role="alert" className="text-sm text-destructive">{serverError}</p>
      )}
      <Button type="submit" disabled={resetForm.formState.isSubmitting}>
        {resetForm.formState.isSubmitting ? <Spinner /> : null}
        {t("forgot.submit")}
      </Button>
      <ResendCodeButton onResend={async () => { await forgot.mutateAsync({ data: { email } }) }} />
    </form>
  )
}
```

Chạy `npm run format:write` để prettier xuống dòng các JSX dài. `t(\`forgot.${name}\`)` cần khoá `forgot.password` và `forgot.confirm` có trong `auth.json`; nếu typecheck của i18next báo khoá động, viết hai `Controller` riêng thay cho `.map`.

- [ ] **Step 4: Route và chuỗi**

`routes/auth/forgot-password.tsx`:

```tsx
import { useTranslation } from "react-i18next"
import { Link } from "react-router"

import { AuthCard } from "~/features/auth/components/AuthCard"
import { ForgotPasswordForm } from "~/features/auth/components/ForgotPasswordForm"

export default function ForgotPasswordPage() {
  const { t } = useTranslation("auth")
  return (
    <AuthCard title={t("forgot.title")} description={t("forgot.description")}>
      <title>{t("forgot.title")}</title>
      <ForgotPasswordForm />
      <p className="text-center text-sm text-muted-foreground">
        <Link to="/login" className="underline underline-offset-4">
          {t("register.loginLink")}
        </Link>
      </p>
    </AuthCard>
  )
}
```

`routes.ts`: thêm `route("forgot-password", "routes/auth/forgot-password.tsx"),` sau dòng `register`.

`auth.json` (vi):

```json
"forgot": {
  "title": "Quên mật khẩu",
  "description": "Nhập email để nhận mã đặt lại mật khẩu.",
  "sentTo": "Nếu {{email}} có tài khoản, chúng tôi đã gửi mã 6 số tới email đó.",
  "code": "Mã xác minh",
  "codeIncomplete": "Nhập đủ 6 chữ số.",
  "password": "Mật khẩu mới",
  "confirm": "Nhập lại mật khẩu mới",
  "mismatch": "Hai mật khẩu không khớp.",
  "submit": "Đặt lại mật khẩu",
  "done": "Đã đặt lại mật khẩu. Hãy đăng nhập lại."
}
```

(en): `"title": "Forgot password"`, `"description": "Enter your email to get a reset code."`, `"sentTo": "If {{email}} has an account, we sent a 6-digit code to it."`, `"code": "Verification code"`, `"codeIncomplete": "Enter all 6 digits."`, `"password": "New password"`, `"confirm": "Repeat the new password"`, `"mismatch": "The passwords do not match."`, `"submit": "Reset password"`, `"done": "Your password was reset. Please sign in again."`.

- [ ] **Step 5: Chạy**

Run: `cd frontend && npm run -s typecheck && npm run -s lint && npm run -s format && npm test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat(frontend): add the forgot password page with an emailed code"
```

---

### Task 15: Mục Tài khoản trong cài đặt

**Files:**
- Create: `frontend/app/features/settings/components/AccountSection.tsx`, `ContactChangeFlow.tsx`, `ContactChangeFlow.browser.test.tsx`, `GoogleSetting.tsx`, `SessionsList.tsx`, `SessionsList.browser.test.tsx`
- Create: `frontend/app/features/settings/lib/google-link.ts`, `frontend/app/routes/auth/google-link-callback.tsx`
- Modify: `frontend/app/features/settings/components/SettingsPage.tsx`, `SettingsPage.browser.test.tsx`, `frontend/app/routes.ts`, `frontend/app/i18n/resources/{vi,en}/settings.json`

**Interfaces:**
- Consumes: `useAccountEmailRequest`, `useAccountEmailConfirm`, `useAccountPhoneRequest`, `useAccountPhoneConfirm`, `useAccountGoogleUnlink`, `useAccountSessionsList`, `useAccountSessionsRevoke`, `useAccountSessionsRevokeOthers`, `oauthAssociateGoogleAuthorize`, `oauthAssociateGoogleCallback`, `CodeStep`, `phoneSchema`.
- Produces: `AccountSection({ user })`, `ContactChangeFlow({ kind, current, verified })`, route `/auth/google/link-callback`.

- [ ] **Step 1: Viết test (fail)**

`ContactChangeFlow.browser.test.tsx`:

```tsx
import { QueryClient } from "@tanstack/react-query"
import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { ContactChangeFlow } from "~/features/settings/components/ContactChangeFlow"
import { applyZodLocale } from "~/i18n/zod-locale"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

const ACCOUNT = {
  id: "0b7c3f5e-4a53-4f5e-9a51-7d1e2f3a4b5c",
  email: "an.moi@example.com",
  phone_number: null,
  display_name: "An",
  is_active: true,
  is_superuser: false,
  is_verified: true,
  email_verified: true,
  phone_verified: false,
  password_set: true,
  google_linked: false,
}

describe("ContactChangeFlow", () => {
  beforeEach(() => {
    applyZodLocale("vi")
  })

  test("changes the email with a code sent to the new address", async () => {
    const bodies: string[] = []
    worker.use(
      http.post("/api/v1/account/email", async ({ request }) => {
        bodies.push(await request.text())
        return new HttpResponse(null, { status: 202 })
      }),
      http.post("/api/v1/account/email/confirm", async ({ request }) => {
        bodies.push(await request.text())
        return HttpResponse.json(ACCOUNT)
      })
    )
    const client = new QueryClient()
    await render(
      <TestProviders client={client}>
        <ContactChangeFlow kind="email" current="an@example.com" verified />
      </TestProviders>
    )
    await page.getByRole("button", { name: "Đổi email" }).click()
    await page.getByLabelText("Email mới").fill("an.moi@example.com")
    await page.getByRole("button", { name: "Gửi mã" }).click()
    await page.getByLabelText("Mã xác minh").fill("123456")
    await page.getByRole("button", { name: "Xác nhận" }).click()
    await expect.element(page.getByText("Đã cập nhật email.")).toBeVisible()
    expect(bodies).toEqual([
      '{"email":"an.moi@example.com"}',
      '{"email":"an.moi@example.com","code":"123456"}',
    ])
    expect(client.getQueryData(["/api/v1/users/me"])).toEqual(ACCOUNT)
  })

  test("adds a phone number, sending E.164", async () => {
    const bodies: string[] = []
    worker.use(
      http.post("/api/v1/account/phone", async ({ request }) => {
        bodies.push(await request.text())
        return new HttpResponse(null, { status: 202 })
      })
    )
    await render(
      <TestProviders>
        <ContactChangeFlow kind="phone" current={null} verified={false} />
      </TestProviders>
    )
    await page.getByRole("button", { name: "Thêm số điện thoại" }).click()
    await page.getByLabelText("Số điện thoại mới").fill("0912 345 678")
    await page.getByRole("button", { name: "Gửi mã" }).click()
    await expect.element(page.getByLabelText("Mã xác minh")).toBeVisible()
    expect(bodies).toEqual(['{"phone":"+84912345678"}'])
  })
})
```

`SessionsList.browser.test.tsx`:

```tsx
import { http, HttpResponse } from "msw"
import { describe, expect, test } from "vitest"
import { page } from "vitest/browser"
import { render } from "vitest-browser-react"

import { SessionsList } from "~/features/settings/components/SessionsList"

import { worker } from "../../../../tests/msw/browser"
import { TestProviders } from "../../../../tests/utils/providers"

const SESSIONS = [
  { id: "a".repeat(32), created_at: "2026-10-10T09:00:00Z", last_used_at: "2026-10-10T10:00:00Z", user_agent: "Mozilla/5.0 (Windows NT 10.0) Firefox/140.0", ip_address: "10.0.0.1", current: true },
  { id: "b".repeat(32), created_at: "2026-10-09T09:00:00Z", last_used_at: null, user_agent: "Mozilla/5.0 (iPhone) Safari/17.0", ip_address: "10.0.0.2", current: false },
]

describe("SessionsList", () => {
  test("marks this device and signs out another one", async () => {
    const deleted: string[] = []
    worker.use(
      http.get("/api/v1/account/sessions", () => HttpResponse.json(SESSIONS)),
      http.delete("/api/v1/account/sessions/:id", ({ params }) => {
        deleted.push(String(params.id))
        return new HttpResponse(null, { status: 204 })
      })
    )
    await render(
      <TestProviders>
        <SessionsList />
      </TestProviders>
    )
    await expect.element(page.getByText("Thiết bị này")).toBeVisible()
    await page.getByRole("button", { name: "Đăng xuất phiên trên Safari" }).click()
    await expect.poll(() => deleted).toEqual(["b".repeat(32)])
  })
})
```

- [ ] **Step 2: Chạy, xác nhận fail**

Run: `cd frontend && npx vitest run --project browser app/features/settings`
Expected: FAIL.

- [ ] **Step 3: Viết `ContactChangeFlow.tsx`**

```tsx
import { zodResolver } from "@hookform/resolvers/zod"
import { useQueryClient } from "@tanstack/react-query"
import { useMemo, useState } from "react"
import { Controller, useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { z } from "zod"

import {
  getUsersCurrentUserQueryKey,
  useAccountEmailConfirm,
  useAccountEmailRequest,
  useAccountPhoneConfirm,
  useAccountPhoneRequest,
} from "~/api/gen/endpoints"
import type { AccountView } from "~/api/gen/schemas"
import { CodeStep } from "~/components/code-step"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Field, FieldError, FieldLabel } from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { Spinner } from "~/components/ui/spinner"
import { toast } from "~/components/ui/toast"
import { apiErrorMessage } from "~/i18n/error-message"
import { applyApiError } from "~/lib/form-errors"
import { phoneSchema } from "~/lib/phone"

type Kind = "email" | "phone"
type Step = { name: "idle" } | { name: "editing" } | { name: "code"; value: string }

/** Adds or changes the email or phone number; the change applies once the code is confirmed. */
export function ContactChangeFlow({
  kind,
  current,
  verified,
}: {
  kind: Kind
  current: string | null
  verified: boolean
}) {
  const { t } = useTranslation("settings")
  const { t: tErrors } = useTranslation("errors")
  const queryClient = useQueryClient()
  const requestEmail = useAccountEmailRequest()
  const confirmEmail = useAccountEmailConfirm()
  const requestPhone = useAccountPhoneRequest()
  const confirmPhone = useAccountPhoneConfirm()
  const [step, setStep] = useState<Step>({ name: "idle" })
  const schema = useMemo(
    () =>
      z.object({
        value: kind === "email" ? z.email() : phoneSchema(tErrors("PHONE_NUMBER_INVALID")),
      }),
    [kind, tErrors]
  )
  const form = useForm({ resolver: zodResolver(schema), defaultValues: { value: "" } })

  async function request(value: string): Promise<void> {
    if (kind === "email") {
      await requestEmail.mutateAsync({ data: { email: value } })
    } else {
      await requestPhone.mutateAsync({ data: { phone: value } })
    }
  }

  async function confirm(value: string, code: string): Promise<AccountView> {
    return kind === "email"
      ? await confirmEmail.mutateAsync({ data: { email: value, code } })
      : await confirmPhone.mutateAsync({ data: { phone: value, code } })
  }

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await request(values.value)
      setStep({ name: "code", value: values.value })
    } catch (error) {
      applyApiError(error, form.setError, ["value"], apiErrorMessage(error, tErrors))
    }
  })

  if (step.name === "code") {
    return (
      <CodeStep
        id={`${kind}-change-code`}
        description={t(`account.${kind}.sentTo`, { value: step.value })}
        submitLabel={t("account.confirm")}
        onSubmit={async (code) => {
          const updated = await confirm(step.value, code)
          queryClient.setQueryData(getUsersCurrentUserQueryKey(), updated)
          toast.add({ type: "success", title: t(`account.${kind}.saved`) })
          setStep({ name: "idle" })
          form.reset({ value: "" })
        }}
        onResend={() => request(step.value)}
      />
    )
  }

  if (step.name === "idle") {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm">
          <span>{current ?? t(`account.${kind}.none`)}</span>
          {current === null ? null : (
            <Badge variant={verified ? "secondary" : "outline"}>
              {verified ? t("account.verified") : t("account.unverified")}
            </Badge>
          )}
        </div>
        <Button type="button" variant="outline" onClick={() => setStep({ name: "editing" })}>
          {current === null ? t(`account.${kind}.add`) : t(`account.${kind}.change`)}
        </Button>
      </div>
    )
  }

  const serverError = form.formState.errors.root?.server?.message
  return (
    <form noValidate onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-4">
      <Controller
        name="value"
        control={form.control}
        render={({ field, fieldState }) => (
          <Field data-invalid={fieldState.invalid}>
            <FieldLabel htmlFor={`${kind}-new`}>{t(`account.${kind}.newLabel`)}</FieldLabel>
            <Input
              {...field}
              id={`${kind}-new`}
              type={kind === "email" ? "email" : "tel"}
              autoComplete={kind === "email" ? "email" : "tel"}
              aria-invalid={fieldState.invalid}
            />
            <FieldError errors={[fieldState.error]} />
          </Field>
        )}
      />
      {serverError === undefined ? null : (
        <p role="alert" className="text-sm text-destructive">{serverError}</p>
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? <Spinner /> : null}
          {t("account.sendCode")}
        </Button>
        <Button type="button" variant="ghost" onClick={() => setStep({ name: "idle" })}>
          {t("account.cancel")}
        </Button>
      </div>
    </form>
  )
}
```

Kiểm tra `Badge` có `variant` `"secondary"` và `"outline"` trong `components/ui/badge.tsx`; nếu tên khác, dùng tên có sẵn.

- [ ] **Step 4: Viết `google-link.ts`, `GoogleSetting.tsx`, route callback**

`features/settings/lib/google-link.ts`:

```ts
import {
  oauthAssociateGoogleAuthorize,
  oauthAssociateGoogleCallback,
} from "~/api/gen/endpoints"

export async function startGoogleLink(
  assign: (url: string) => void = (url) => window.location.assign(url)
): Promise<void> {
  const { authorization_url: authorizationUrl } = await oauthAssociateGoogleAuthorize()
  assign(authorizationUrl)
}

export async function completeGoogleLink(callbackUrl: URL): Promise<void> {
  const { searchParams } = callbackUrl
  await oauthAssociateGoogleCallback({
    code: searchParams.get("code") ?? undefined,
    state: searchParams.get("state") ?? undefined,
  })
}
```

Tham số của `oauthAssociateGoogleAuthorize` do orval sinh có thể là `params` tuỳ chọn (`scopes`); gọi không tham số nếu được, như `oauthGoogleCookieAuthorize()` đang làm.

`GoogleSetting.tsx`:

```tsx
import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { getUsersCurrentUserQueryKey, useAccountGoogleUnlink } from "~/api/gen/endpoints"
import { Button } from "~/components/ui/button"
import { apiErrorMessage } from "~/i18n/error-message"

import { startGoogleLink } from "../lib/google-link"

export function GoogleSetting({ linked }: { linked: boolean }) {
  const { t } = useTranslation("settings")
  const { t: tErrors } = useTranslation("errors")
  const queryClient = useQueryClient()
  const unlink = useAccountGoogleUnlink()
  const [error, setError] = useState<string | null>(null)

  async function toggle() {
    setError(null)
    try {
      if (linked) {
        const updated = await unlink.mutateAsync()
        queryClient.setQueryData(getUsersCurrentUserQueryKey(), updated)
      } else {
        await startGoogleLink()
      }
    } catch (caught) {
      setError(apiErrorMessage(caught, tErrors))
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span>{linked ? t("account.google.linked") : t("account.google.notLinked")}</span>
        <Button type="button" variant="outline" onClick={() => void toggle()}>
          {linked ? t("account.google.unlink") : t("account.google.link")}
        </Button>
      </div>
      {error === null ? null : (
        <p role="alert" className="text-sm text-destructive">{error}</p>
      )}
    </div>
  )
}
```

`routes/auth/google-link-callback.tsx`:

```tsx
import { useTranslation } from "react-i18next"
import { redirect } from "react-router"

import { getUsersCurrentUserQueryKey } from "~/api/gen/endpoints"
import { UNKNOWN_ERROR_CODE, isApiError } from "~/api/problem"
import { queryClient } from "~/api/query-client"
import { Spinner } from "~/components/ui/spinner"
import { completeGoogleLink } from "~/features/settings/lib/google-link"

import type { Route } from "./+types/google-link-callback"

export async function clientLoader({ request }: Route.ClientLoaderArgs) {
  try {
    await completeGoogleLink(new URL(request.url))
  } catch (error) {
    const code = isApiError(error) ? error.code : UNKNOWN_ERROR_CODE
    throw redirect(`/settings?error=${encodeURIComponent(code)}`)
  }
  await queryClient.invalidateQueries({ queryKey: getUsersCurrentUserQueryKey() })
  throw redirect("/settings")
}

export function HydrateFallback() {
  const { t } = useTranslation("auth")
  return (
    <main className="flex min-h-svh items-center justify-center gap-2 text-sm text-muted-foreground">
      <Spinner />
      <span>{t("googleCompleting")}</span>
    </main>
  )
}

export default function GoogleLinkCallback() {
  return <HydrateFallback />
}
```

`routes.ts`: thêm `route("auth/google/link-callback", "routes/auth/google-link-callback.tsx"),` sau route callback Google hiện có.

- [ ] **Step 5: Viết `SessionsList.tsx` và `AccountSection.tsx`**

`SessionsList.tsx`:

```tsx
import { useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"

import {
  getAccountSessionsListQueryKey,
  useAccountSessionsList,
  useAccountSessionsRevoke,
  useAccountSessionsRevokeOthers,
} from "~/api/gen/endpoints"
import type { SessionView } from "~/api/gen/schemas"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Spinner } from "~/components/ui/spinner"

const BROWSERS = ["Edg", "Chrome", "Firefox", "Safari"] as const

/** A short device name from the user agent, enough to tell sessions apart. */
function browserOf(session: SessionView): string {
  const name = BROWSERS.find((browser) => session.user_agent.includes(`${browser}/`))
  return name === "Edg" ? "Edge" : (name ?? session.user_agent.slice(0, 40))
}

export function SessionsList() {
  const { t, i18n } = useTranslation("settings")
  const queryClient = useQueryClient()
  const sessions = useAccountSessionsList()
  const revoke = useAccountSessionsRevoke()
  const revokeOthers = useAccountSessionsRevokeOthers()
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: getAccountSessionsListQueryKey() })
  const format = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeStyle: "short" })

  if (sessions.data === undefined) {
    return <Spinner />
  }
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-2">
        {sessions.data.map((session) => (
          <li key={session.id} className="flex items-center justify-between gap-2 text-sm">
            <div className="flex flex-col">
              <span className="flex items-center gap-2">
                {browserOf(session)}
                {session.current ? <Badge variant="secondary">{t("sessions.current")}</Badge> : null}
              </span>
              <span className="text-muted-foreground">
                {session.ip_address} · {format.format(new Date(session.last_used_at ?? session.created_at))}
              </span>
            </div>
            {session.current ? null : (
              <Button
                type="button"
                variant="outline"
                aria-label={t("sessions.revokeOne", { device: browserOf(session) })}
                onClick={() => void revoke.mutateAsync({ sessionId: session.id }).then(refresh)}
              >
                {t("sessions.revoke")}
              </Button>
            )}
          </li>
        ))}
      </ul>
      {sessions.data.some((session) => !session.current) ? (
        <Button
          type="button"
          variant="outline"
          className="self-start"
          onClick={() => void revokeOthers.mutateAsync().then(refresh)}
        >
          {t("sessions.revokeOthers")}
        </Button>
      ) : null}
    </div>
  )
}
```

`AccountSection.tsx`:

```tsx
import { useTranslation } from "react-i18next"

import type { AccountView } from "~/api/gen/schemas"
import { Separator } from "~/components/ui/separator"

import { ContactChangeFlow } from "./ContactChangeFlow"
import { GoogleSetting } from "./GoogleSetting"
import { SessionsList } from "./SessionsList"

export function AccountSection({ user }: { user: AccountView }) {
  const { t } = useTranslation("settings")
  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">{t("account.email.heading")}</h3>
        <ContactChangeFlow kind="email" current={user.email ?? null} verified={user.email_verified} />
      </section>
      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">{t("account.phone.heading")}</h3>
        <ContactChangeFlow kind="phone" current={user.phone_number ?? null} verified={user.phone_verified} />
      </section>
      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">{t("account.google.heading")}</h3>
        <GoogleSetting linked={user.google_linked} />
      </section>
      <Separator />
      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">{t("sessions.heading")}</h3>
        <SessionsList />
      </section>
    </div>
  )
}
```

`SettingsPage.tsx`: thêm một `Card` "Tài khoản" (`t("account.heading")`) giữa thẻ hồ sơ và thẻ mật khẩu, nội dung `user.data === undefined ? <Spinner /> : <AccountSection user={user.data} />`; đọc `?error=` từ `useSearchParams` và hiện `<p role="alert">` với `tErrors(isErrorCode(code) ? code : "UNKNOWN")` ở đầu trang (giống `routes/auth/login.tsx`). `SettingsPage.browser.test.tsx`: thêm handler `GET /api/v1/account/sessions` trả `[]` để thẻ mới không gọi mạng thật.

Thứ tự tham số mutation `revoke.mutateAsync({ sessionId })` theo tên orval sinh cho path param `session_id`; nếu orval đặt `{ sessionId: string }` khác, theo đúng kiểu sinh ra.

- [ ] **Step 6: Chuỗi `settings.json`**

(vi), thêm:

```json
"account": {
  "heading": "Tài khoản",
  "verified": "Đã xác minh",
  "unverified": "Chưa xác minh",
  "sendCode": "Gửi mã",
  "confirm": "Xác nhận",
  "cancel": "Huỷ",
  "email": {
    "heading": "Email",
    "none": "Chưa có email",
    "add": "Thêm email",
    "change": "Đổi email",
    "newLabel": "Email mới",
    "sentTo": "Chúng tôi đã gửi mã 6 số tới {{value}}.",
    "saved": "Đã cập nhật email."
  },
  "phone": {
    "heading": "Số điện thoại",
    "none": "Chưa có số điện thoại",
    "add": "Thêm số điện thoại",
    "change": "Đổi số điện thoại",
    "newLabel": "Số điện thoại mới",
    "sentTo": "Chúng tôi đã gửi mã 6 số qua SMS tới {{value}}.",
    "saved": "Đã cập nhật số điện thoại."
  },
  "google": {
    "heading": "Google",
    "linked": "Đã liên kết tài khoản Google",
    "notLinked": "Chưa liên kết Google",
    "link": "Liên kết Google",
    "unlink": "Gỡ liên kết"
  }
},
"sessions": {
  "heading": "Phiên đăng nhập",
  "current": "Thiết bị này",
  "revoke": "Đăng xuất",
  "revokeOne": "Đăng xuất phiên trên {{device}}",
  "revokeOthers": "Đăng xuất mọi thiết bị khác"
}
```

(en): cùng khoá với nội dung: "Account", "Verified", "Not verified", "Send code", "Confirm", "Cancel"; email: "Email", "No email yet", "Add email", "Change email", "New email", "We sent a 6-digit code to {{value}}.", "Email updated."; phone: "Phone number", "No phone number yet", "Add phone number", "Change phone number", "New phone number", "We sent a 6-digit code by SMS to {{value}}.", "Phone number updated."; google: "Google", "Google account linked", "Google not linked", "Link Google", "Unlink"; sessions: "Signed-in sessions", "This device", "Sign out", "Sign out the session on {{device}}", "Sign out all other devices".

- [ ] **Step 7: Chạy**

Run: `cd frontend && npm run -s typecheck && npm run -s lint && npm run -s format && npm test`
Expected: PASS, gồm `app/architecture.test.ts` (settings không import auth).

- [ ] **Step 8: Commit**

```bash
git add frontend
git commit -m "feat(frontend): manage email, phone, Google and sessions in settings"
```

---

### Task 16: E2E

**Files:**
- Modify: `frontend/tests/e2e/support/api.ts`, `frontend/tests/e2e/support/fixtures.ts` (nếu fixture đăng ký người dùng), `frontend/tests/e2e/auth.e2e.ts`
- Create: `frontend/tests/e2e/account.e2e.ts`

**Interfaces:**
- Consumes: route `GET /api/v1/__e2e/outbox/code?to=` (Task 10).
- Produces: `latestCode(request: APIRequestContext, to: string): Promise<string>`; `registerUser` xác minh email trước khi trả.

- [ ] **Step 1: Sửa `support/api.ts`**

```ts
const CodeResponse = z.object({ code: z.string().regex(/^\d{6}$/) })

/** The last code the E2E backend sent to an email address or E.164 number. */
export async function latestCode(
  request: APIRequestContext,
  to: string
): Promise<string> {
  const response = await request.get(`${API}/__e2e/outbox/code`, { params: { to } })
  await assertStatus(response, 200)
  return CodeResponse.parse(await response.json()).code
}
```

Trong `registerUser`, sau `assertStatus(response, 201)`:

```ts
  const verify = await request.post(`${API}/auth/email/verify`, {
    data: { email: user.email, code: await latestCode(request, user.email) },
  })
  await assertStatus(verify, 204)
```

- [ ] **Step 2: Sửa `auth.e2e.ts`**

Test đầu tiên: sau khi bấm "Tạo tài khoản", thay `await expect(page).toHaveURL(/\/chat$/)` bằng:

```ts
  await expect(page.getByText(/Chúng tôi đã gửi mã 6 số tới/)).toBeVisible()
  const code = await latestCode(request, user.email)
  await page.getByLabel("Mã xác minh").fill(code)
  await page.getByRole("button", { name: "Xác minh email" }).click()
  await expect(page).toHaveURL(/\/chat$/)
```

Lấy `request` từ fixture của test (`async ({ page, request }) =>`) và import `latestCode`. Hàm `logIn` điền "Email" — trang đăng nhập giờ có tab "Email" mặc định nên không đổi.

- [ ] **Step 3: Viết `account.e2e.ts`**

```ts
import { latestCode, newUser, registerUser } from "./support/api"
import { expect, test } from "./support/fixtures"

test("forgot password resets with an emailed code", async ({ page, request }) => {
  const user = newUser()
  await registerUser(request, user)

  await page.goto("/login")
  await page.getByRole("link", { name: "Quên mật khẩu?" }).click()
  await page.getByLabel("Email", { exact: true }).fill(user.email)
  await page.getByRole("button", { name: "Gửi mã" }).click()
  await page.getByLabel("Mã xác minh").fill(await latestCode(request, user.email))
  await page.getByLabel("Mật khẩu mới", { exact: true }).fill("e2e-mat-khau-moi")
  await page.getByLabel("Nhập lại mật khẩu mới").fill("e2e-mat-khau-moi")
  await page.getByRole("button", { name: "Đặt lại mật khẩu" }).click()
  await expect(page).toHaveURL(/\/login$/)

  await page.getByLabel("Email", { exact: true }).fill(user.email)
  await page.getByLabel("Mật khẩu", { exact: true }).fill("e2e-mat-khau-moi")
  await page.getByRole("button", { name: "Đăng nhập" }).click()
  await expect(page).toHaveURL(/\/chat$/)
})

test("phone sign-in creates an account and opens the chat", async ({ page, request }) => {
  const local = `09${String(Date.now()).slice(-8)}`
  const e164 = `+84${local.slice(1)}`

  await page.goto("/login")
  await page.getByRole("tab", { name: "Số điện thoại" }).click()
  await page.getByLabel("Số điện thoại").fill(local)
  await page.getByRole("button", { name: "Gửi mã" }).click()
  await page.getByLabel("Mã xác minh").fill(await latestCode(request, e164))
  await page.getByRole("button", { name: "Đăng nhập" }).click()
  await expect(page).toHaveURL(/\/chat$/)
})
```

Số `09xxxxxxxx` có 10 chữ số, đầu `09` là đầu số di động Việt Nam hợp lệ theo libphonenumber; nếu một số sinh ra bị từ chối, đổi tiền tố sang `091`.

- [ ] **Step 4: Chạy e2e**

Run: `docker compose up -d --wait postgres qdrant && cd frontend && npm run -s e2e`
Expected: mọi spec pass, kể cả hai test mới.

- [ ] **Step 5: Commit**

```bash
git add frontend/tests/e2e
git commit -m "test(e2e): cover email verification, password reset and phone sign-in"
```

---

### Task 17: Kiểm tra cuối

**Files:** không thêm file mới (sửa nếu kiểm tra phát hiện lỗi).

- [ ] **Step 1: Chạy toàn bộ**

```bash
uv run --directory backend pytest -q
uv run --directory backend pytest -q -m integration
uv run --directory pharma-lab pytest -q
cd frontend && npm test && npm run -s e2e && cd ..
uv run pre-commit run --all-files
```

Expected: tất cả pass.

- [ ] **Step 2: Chạy thử trên stack local**

```bash
docker compose up -d --build --wait
```

Mở `http://localhost:8080/register`, đăng ký bằng một email; xem mã trong `docker compose logs backend | grep "email provider is 'log'"`; nhập mã, vào `/chat`. Vào `/settings`, kiểm tra mục Tài khoản và danh sách phiên.

- [ ] **Step 3: Cập nhật lộ trình**

Không cần commit nếu không có thay đổi. Báo lại kết quả kiểm tra (số test, e2e) cho người dùng.
