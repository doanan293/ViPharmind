# Thiết kế luồng tài khoản chuẩn (mảng 2)

Ngày: 2026-10-10. Trạng thái: đã duyệt qua brainstorming (ba phần), chờ implementation plan.

Mảng 2 trong lộ trình đưa ViPharMind lên production. Mảng 3 (tổ chức, phân quyền, lời mời) dùng lại hạ tầng gửi thư và mã OTP của mảng này.

## 1. Mục tiêu

1. Người dùng đăng ký và đăng nhập bằng **email và mật khẩu**, **số điện thoại và mã SMS**, hoặc **Google**. Cả ba gắn vào **một tài khoản duy nhất**.
2. Mọi bước xác minh dùng **mã OTP 6 số**: xác minh email, đặt lại mật khẩu, đổi email, đổi số điện thoại, đăng nhập bằng số điện thoại.
3. Người dùng tự quản lý cách đăng nhập và phiên đăng nhập trong phần cài đặt.
4. Đạt mức an toàn cho production: không lưu mã gốc, giới hạn số lần thử và số lần gửi, không để lộ tài khoản nào tồn tại.

## 2. Quyết định đã chốt

| Chủ đề | Quyết định |
| --- | --- |
| Nền tảng auth | Mở rộng fastapi-users trong backend Python. Giữ session cookie và CSRF hiện có. Không dùng dịch vụ auth bên ngoài |
| Hình thức xác minh | Mã OTP 6 số, hạn 10 phút, dùng một lần. Không dùng link xác minh của fastapi-users |
| Tài khoản chỉ có số điện thoại | `user.email` cho phép để trống. Mật khẩu ngẫu nhiên không ai biết (như tài khoản Google), `password_set = false` |
| Liên kết Google | Chỉ tự liên kết khi email Google trùng một email **đã xác minh**. Email chưa xác minh thì không liên kết, tránh chiếm tài khoản đăng ký trước. Đây là sửa lỗi: router Google hiện bật `associate_by_email=True`, liên kết cả email chưa xác minh |
| Gửi email | Port `EmailSender`, hai adapter: Resend (production) và ghi log cho local/test. SMTP bị bỏ vì Render Free chặn cổng SMTP |
| Gửi SMS | Port `SmsSender`, adapter ghi log. Nhà cung cấp thật chọn trước khi ra mắt (mảng 5) |
| Cách gửi | Gửi ngay trong request, không chạy nền, vì Cloud Run giảm CPU sau khi trả response |
| Giới hạn | Lưu trong Postgres, không phụ thuộc dịch vụ ngoài |

## 3. Luồng

### 3.1 Không cần đăng nhập

| Luồng | Các bước |
| --- | --- |
| Đăng ký bằng email | Nhập tên, email, mật khẩu → tạo tài khoản chưa xác minh, gửi mã → nhập mã → email được xác minh và người dùng được đăng nhập |
| Đăng nhập bằng email | Email và mật khẩu đúng nhưng email chưa xác minh → lỗi `EMAIL_NOT_VERIFIED`. Frontend tự gửi mã và chuyển sang bước nhập mã |
| Đăng nhập bằng số điện thoại | Nhập số → gửi mã SMS → nhập mã. Số chưa có tài khoản thì tạo mới; có rồi thì đăng nhập |
| Google | Như hiện tại, cộng quy tắc liên kết ở mục 2 |
| Quên mật khẩu | Nhập email → luôn trả cùng một kết quả → nếu email có tài khoản thì gửi mã → nhập mã và mật khẩu mới → mọi phiên cũ bị đăng xuất |

### 3.2 Trong cài đặt (đã đăng nhập)

| Luồng | Quy tắc |
| --- | --- |
| Thêm hoặc đổi email | Gửi mã tới email mới; xác nhận xong mới đổi. Email đã thuộc tài khoản khác thì báo lỗi. Gửi thông báo tới email cũ nếu có |
| Thêm hoặc đổi số điện thoại | Tương tự, mã gửi tới số mới |
| Đặt hoặc đổi mật khẩu | Chưa từng đặt thì không cần mật khẩu cũ; đã đặt thì bắt buộc |
| Liên kết hoặc gỡ Google | Liên kết qua router associate của fastapi-users. Không gỡ được nếu đó là cách đăng nhập cuối cùng |
| Phiên đăng nhập | Xem danh sách (thiết bị, IP, lần dùng gần nhất), đăng xuất một phiên hoặc mọi phiên khác |

Cách đăng nhập còn hiệu lực gồm: mật khẩu (khi `password_set` và email đã xác minh), số điện thoại đã xác minh, Google đã liên kết. Không thao tác nào được làm số cách đăng nhập về 0.

## 4. Mô hình dữ liệu

Một migration Alembic mới.

### 4.1 Bảng `user` (mở rộng)

| Cột | Thay đổi |
| --- | --- |
| `email` | Cho phép NULL, unique khi có giá trị |
| `phone_number` | Mới. Chuẩn E.164 (`+84912345678`), NULL được, unique khi có giá trị |
| `email_verified_at`, `phone_verified_at` | Mới, `timestamptz` NULL được |
| `password_set` | Mới, `boolean`. `true` khi đăng ký bằng email; `false` khi tài khoản được tạo qua số điện thoại hoặc Google (mật khẩu ngẫu nhiên) |
| Ràng buộc | `CHECK (email IS NOT NULL OR phone_number IS NOT NULL)` |

`is_verified` của fastapi-users được giữ đồng bộ: đúng khi `email_verified_at` hoặc `phone_verified_at` có giá trị. `UserRead` trả `email` và `phone_number` có thể NULL, kèm `email_verified`, `phone_verified`, `password_set` và danh sách provider đã liên kết.

### 4.2 Bảng `one_time_codes`

| Cột | Ý nghĩa |
| --- | --- |
| `id` | UUID |
| `purpose` | `verify_email`, `reset_password`, `change_email`, `phone_login`, `change_phone` |
| `channel` | `email` hoặc `sms` |
| `destination` | Email đã chuẩn hoá chữ thường, hoặc số E.164 |
| `user_id` | NULL được (đăng nhập bằng số mới chưa có tài khoản) |
| `code_hash` | HMAC-SHA256 của mã, khoá bí mật `PHARMA_AUTH__OTP_SECRET`, gộp cả `purpose` và `destination` |
| `expires_at`, `attempts`, `consumed_at`, `created_at` | Hạn dùng, số lần nhập sai, thời điểm đã dùng |

Index `(purpose, destination, created_at)`. Tạo mã mới làm mọi mã chưa dùng cùng `(purpose, destination)` hết hiệu lực. Mã sai quá 5 lần thì hết hiệu lực. So sánh bằng `hmac.compare_digest`.

### 4.3 Bảng `rate_limit_buckets`

`(key, window_start, count)`, khoá chính `(key, window_start)`, tăng bằng `INSERT ... ON CONFLICT DO UPDATE`. Lệnh `cleanup-sessions` hiện có xoá luôn các bucket cũ.

| Giới hạn | Mức |
| --- | --- |
| Gửi mã tới một địa chỉ | 5 lần mỗi giờ, cách nhau tối thiểu 60 giây |
| Gửi mã từ một IP | 20 lần mỗi giờ |
| Đăng nhập sai | 10 lần trong 15 phút theo tài khoản, và theo IP |

Vượt giới hạn trả `429` kèm `Retry-After`.

### 4.4 Bảng `access_tokens` (mở rộng)

Thêm `user_agent`, `ip_address`, `last_used_at` để hiển thị danh sách phiên.

## 5. Thành phần backend

| Tầng | Nội dung |
| --- | --- |
| `domain/account` | Port `EmailSender`, `SmsSender`, `OneTimeCodes`, `RateLimiter`; kiểu `PhoneNumber` chuẩn hoá bằng thư viện `phonenumbers`; `OtpPurpose`, quy tắc "cách đăng nhập cuối cùng" |
| `application/account/service.py` | `AccountService`, mỗi method là một luồng ở mục 3. Băm và kiểm tra mật khẩu qua `UserManager` của fastapi-users |
| `infrastructure` | `ResendEmailSender` (httpx), `LogEmailSender`, `LogSmsSender`; repository Postgres cho mã và giới hạn; mẫu email tiếng Việt và tiếng Anh theo ngôn ngữ người dùng |
| `api/routers/account.py` | Các route ở mục 6 |

Quy tắc kiến trúc trong `tests/architecture/test_layering.py` áp dụng như với các feature khác.

Settings mới: `auth.otp_secret`; `email.provider` (`log`, `resend`) cùng API key Resend và địa chỉ gửi; `sms.provider` (`log`) và `sms.allowed_country_codes` (mặc định `["VN"]`, chặn gửi SMS tốn tiền ra số nước ngoài).

Gửi thất bại: mã vừa tạo bị đánh dấu hết hiệu lực, API trả `503` dạng problem, người dùng bấm gửi lại.

## 6. API

Tiền tố `/api/v1`. Lỗi trả `application/problem+json` như hiện tại.

| Route | Mô tả |
| --- | --- |
| `POST /auth/register` | Như hiện tại, thêm gửi mã xác minh email |
| `POST /auth/email/verify/request` | Gửi lại mã xác minh email, luôn `202` |
| `POST /auth/email/verify` | `{email, code}` → xác minh và tạo session |
| `POST /auth/cookie/login`, `POST /auth/jwt/login` | Như hiện tại; email chưa xác minh → `403 EMAIL_NOT_VERIFIED` |
| `POST /auth/password/forgot` | `{email}` → luôn `202` |
| `POST /auth/password/reset` | `{email, code, password}` → `204`, đăng xuất mọi phiên |
| `POST /auth/phone/request` | `{phone}` → `202` |
| `POST /auth/phone/login` | `{phone, code}` → tạo tài khoản nếu chưa có, tạo session |
| `POST /account/email`, `POST /account/email/confirm` | Đổi email bằng mã |
| `POST /account/phone`, `POST /account/phone/confirm` | Đổi số điện thoại bằng mã |
| `PUT /account/password` | Đặt hoặc đổi mật khẩu |
| `DELETE /account/oauth/google` | Gỡ Google, `409` nếu là cách cuối cùng |
| `GET /account/sessions`, `DELETE /account/sessions/{id}`, `DELETE /account/sessions` | Danh sách và đăng xuất phiên |

Các router xác minh và đặt lại mật khẩu bằng link của fastapi-users không được mount.

## 7. Frontend

| Trang | Nội dung |
| --- | --- |
| `/register` | Hai tab: email (tên, email, mật khẩu → nhập mã) và số điện thoại (số → nhập mã) |
| `/login` | Email và mật khẩu, số điện thoại kèm mã, nút Google. Xử lý `EMAIL_NOT_VERIFIED` bằng cách gửi mã và chuyển sang bước nhập mã |
| `/forgot-password` | Email → mã và mật khẩu mới |
| `/settings`, mục Tài khoản | Email, số điện thoại, mật khẩu, Google, danh sách phiên |

Thành phần dùng chung: ô nhập mã `input-otp` của shadcn (dán cả mã, tự điền mã SMS, nút gửi lại có đếm ngược) và ô số điện thoại kiểm tra bằng `libphonenumber-js`, mặc định `+84`. Code thuộc feature `auth` (luồng không cần đăng nhập) và `settings` (mục tài khoản), theo quy tắc trong `frontend/README.md`. Client API sinh lại bằng orval.

## 8. Kiểm thử

| Lớp | Nội dung |
| --- | --- |
| Unit backend (viết trước) | `AccountService` với bộ gửi giả và đồng hồ giả: mã hết hạn, mã đã dùng, sai 5 lần, mã mới huỷ mã cũ, giới hạn gửi, quên mật khẩu không lộ tài khoản, không gỡ cách đăng nhập cuối cùng, quy tắc liên kết Google |
| Integration backend | Migration lên và xuống, unique có điều kiện, `CHECK` email hoặc số điện thoại, repository mã và giới hạn trên Postgres thật |
| API backend | Mỗi luồng chạy trọn qua HTTP, đọc mã từ hộp thư giả |
| Browser frontend | Từng form với msw |
| E2E | Đăng ký email và xác minh, quên mật khẩu, đăng nhập bằng số điện thoại. Server e2e dùng hộp thư trong bộ nhớ và một endpoint đọc mã chỉ có trong server e2e |
| Hợp đồng API | `npm run api:check` |

## 9. Dữ liệu cũ

Migration đặt `email_verified_at = now()` cho người dùng có `is_verified = true`. Người còn lại xác minh ở lần đăng nhập tới. Production dùng DB mới nên không có dữ liệu cũ.

## 10. Ngoài phạm vi

- Tổ chức, vai trò, lời mời, quyền admin: mảng 3.
- Xác thực hai lớp, đăng nhập GitHub.
- Nhà cung cấp SMS thật, CAPTCHA (ví dụ Cloudflare Turnstile) cho bước gửi SMS nếu bị lạm dụng: quyết định trước khi ra mắt, trong mảng 5.
