# Danh mục tính năng ViPharmind (để chọn nhiệm vụ thí nghiệm)

Ngày lập: 2026-11-26, trên nhánh `clean` (mã giống `v2.0.0`). Mục đích: mỗi mục là một tính năng có thể **gỡ khỏi
một bản sao của `clean`** (backend + frontend + test), rồi giao cho agent dựng lại từ một câu yêu cầu ngắn. Phần mã
bị gỡ là lời giải tham chiếu.

## Quy ước

- Viết tắt đường dẫn: `B/` = `backend/src/pharma_agent/`, `BT/` = `backend/tests/`, `F/` = `frontend/app/`,
  `FF/` = `frontend/app/features/`, `M/` = `B/infrastructure/persistence/postgres/migrations/versions/`,
  `PG/` = `B/infrastructure/persistence/postgres/`. Mọi route API có tiền tố `/api/v1`.
- **Cỡ** tính trên số dòng mã sẽ bị gỡ **không kể test và mã sinh** (`F/api/gen/**`, `frontend/openapi.json`), giả
  định gỡ riêng một mục và giữ nguyên mọi mục khác (hạ tầng dùng chung ở lại). Test ghi riêng. nhỏ < 150,
  vừa 150–600, lớn > 600. Con số là ước lượng tay từ `wc -l` cả file cộng phần ước lượng trong file dùng chung,
  sai số khoảng ±30%.
- **Nặng quy tắc**: có = tính năng mã hóa quy tắc nghiệp vụ mà người dùng phải nói ra (quyền, vai trò, hiển thị,
  mời, hạn mức, giới hạn tần suất, quy tắc kiểm tra dữ liệu).
- **Commit**: lịch sử `v2-new` đã gộp (squash) mạnh. Phần lớn commit `feat(...)` gom nhiều tính năng một lúc, nên
  cột commit chỉ là các commit đầu tiên chạm vào file chính, không phải một commit sạch cho từng tính năng.

## Rủi ro rò rỉ chung (áp dụng cho mọi mục)

Khi gỡ bất kỳ mục nào, các chỗ sau phải được sửa theo, nếu không agent đọc được lời giải:

1. **Client sinh**: `frontend/openapi.json`, `F/api/gen/endpoints.ts`, `endpoints.msw.ts`, `zod.ts`, `schemas/*`. Phải
   chạy lại `npm --prefix frontend run api:openapi` rồi orval sau khi gỡ route; nếu không, tên hook, kiểu và đường dẫn
   API của tính năng còn nguyên.
2. **i18n**: `F/i18n/resources/{vi,en}/*.json` (mỗi namespace có khóa theo tính năng) và `errors.json` (mã lỗi như
   `LAST_OWNER`, `QUOTA_EXCEEDED`, `INVITATION_EXPIRED`, `RATE_LIMITED`...). Khóa mã lỗi còn sót gần như đọc ra quy tắc.
3. **Tài liệu thiết kế**: `docs/superpowers/specs/2026-11-15-product-accounts-orgs-design.md` (bảng quyền §3.2, hạn
   mức §4.4, API §5, frontend §6), `2026-11-15-frontend-design.md` §7, `2026-11-15-backend-agent-api-design.md` §6–7,
   `backend/README.md` (mục "Xác thực", "Tổ chức, collection và xuất bản"), `docs/cleanup/*`,
   `docs/launch-checklist.md`, `docs/research/paper-v2/06-repo-map.md`. Nên xóa cả thư mục `docs/` trừ phần cần thiết,
   hoặc ít nhất các file này.
4. **Nội dung công khai**: `F/i18n/resources/*/landing.json` (giới thiệu "trích dẫn từng ý", "bộ tài liệu riêng, có
   phân quyền"...), `FF/legal/lib/content.ts` (chính sách quyền riêng tư nói admin đọc được hội thoại, nói về mã OTP,
   phiên đăng nhập...).
5. **Bảng kiến trúc**: `F/architecture.test.ts` và `frontend/.oxlintrc.json` liệt kê tên thư mục feature;
   `backend/pyproject.toml` (`[tool.importlinter]`) liệt kê package `application.*`. Gỡ cả một thư mục feature thì phải
   sửa các bảng này.
6. **Migration dùng chung**: các tính năng chia nhau migration: `0013_account_flows` (OTP, phone, rate limit, chi tiết
   phiên), `0017_organizations_and_audit` (tổ chức, thành viên, lời mời, audit, cột hạn mức), `0018` (chủ sở hữu
   collection + `conversations.collection_ids`), `0020` (tài liệu soạn, glossary, tên thông dụng, ingest job). Gỡ một
   tính năng nghĩa là sửa migration cũ trong bản sao (để DB không còn bảng/cột) và để agent tự thêm migration mới; test
   `BT/infrastructure/test_migrations.py` và `test_persistence_metadata.py` liệt kê tên bảng/cột, phải sửa theo.
7. **Test hạ tầng dùng chung**: `BT/api/harness.py`, `BT/api/postgres_app.py`, `BT/fakes.py`, `BT/account_fakes.py`,
   `BT/organization_fakes.py`, `BT/collection_fakes.py`, `BT/memory_repository.py`, `BT/api/test_openapi.py`,
   `BT/api/test_problem_details.py`, `BT/infrastructure/test_container.py`, `BT/e2e/server.py`; frontend
   `frontend/tests/e2e/*.e2e.ts`, `frontend/tests/e2e/support/api.ts`, `frontend/tests/demo/chapters/*.ts`,
   `frontend/tests/utils/account.ts`. Các file này chứa fake/fixture của nhiều tính năng.
8. **Enum audit**: `B/domain/audit/models.py` `AuditAction` có tên hành động của mọi tính năng (`glossary.updated`,
   `quota.changed`, `invitation.approved`...). Gỡ tính năng nào thì gỡ hành động đó.
9. **Lịch sử git**: bản sao giao cho agent phải không có `.git` của repo (hoặc một repo mới một commit), vì `v2-new` và
   `clean` chứa toàn bộ lời giải.

## Nguồn lộ đáp án chung

- **Chỉ dựng nhiệm vụ từ `git archive`** của file được theo dõi trong `clean` (sau khi gỡ), không chép thư mục làm
  việc. Thư mục làm việc hiện có file bị ignore hoặc chưa theo dõi chứa lời giải: `frontend/build/`,
  `frontend/.react-router/`, `frontend/demo-videos/`, `frontend/playwright-report/`, `frontend/test-results/`,
  `.vitest/`, `**/__pycache__`, `.import_linter_cache`, `.superpowers/`, `.claude/skills`, `.agents/`,
  `frontend/node_modules/.vite`.
- **README**: `frontend/README.md` dòng ~15 (bảng hướng import giữa feature), ~29 (danh sách composition như
  `feedback-dialog`, `code-step`, `tags-input`), ~70 (danh sách luồng e2e: hết hạn phiên, 👎 feedback, tải tin cũ, đổi
  ngôn ngữ/giao diện); `backend/README.md` mục "Bố cục" (liệt kê package `application/*`) cùng các mục đã nêu ở trên.
- **Endpoint chỉ cho test**: `BT/e2e/server.py` có `/api/v1/__e2e/outbox/code` và `/__e2e/outbox/invitation` (đọc mã
  OTP, link mời); phải gỡ theo tính năng tương ứng.
- **Điểm chạm dùng chung** (đã kể ở "Rủi ro rò rỉ chung"): migration `0013`/`0017`/`0018`/`0020`, client OpenAPI sinh,
  i18n + `errors.json`, enum `AuditAction`, bảng import-linter/oxlint/`architecture.test.ts`, fake và harness test.
- **Cách làm**: việc gỡ phải là **một script cho từng nhiệm vụ** (xóa file, sửa file dùng chung, sửa migration, sinh
  lại client), kèm một bước **grep rò rỉ** (mã lỗi, đường dẫn route, tên test, khóa i18n, tên `AuditAction` của tính
  năng) phải ra rỗng, và **chạy xanh toàn bộ test** trên mỗi bản sao gốc trước khi giao cho agent.

## Nền tảng không gỡ (mọi mục dưới đây cần)

- **Chat cốt lõi**: `POST /chat`, `POST /chat/stream` (SSE theo UI message stream của AI SDK), pipeline LangGraph
  (guard → rephrase → search → judge → answer), trích dẫn `[n]` trong câu trả lời, danh sách nguồn, trạng thái agent.
  `B/application/chat/*`, `B/api/routers/chat.py`, `B/api/ui_stream.py`, `FF/chat/*` (trừ phần các mục 9, 10, 12).
- **Hội thoại tối thiểu**: tạo hội thoại, đọc một hội thoại, đọc trang tin nhắn (`POST /conversations`,
  `GET /conversations/{id}`, `GET /conversations/{id}/messages`).
- **Đăng ký/đăng nhập email + mật khẩu bằng cookie** (fastapi-users: `POST /auth/register`,
  `POST /auth/cookie/login`, `POST /auth/cookie/logout`, `GET /users/me`), CSRF, `B/infrastructure/auth/users.py`,
  `FF/auth/components/LoginForm.tsx`, `RegisterForm.tsx`.
- **Khung app, i18n, health**: `FF/shell/*`, `F/i18n/config.ts` + middleware, `GET /health`, xử lý lỗi RFC 9457.
- **Hạ tầng mã một lần (OTP)**: `PG/one_time_codes.py`, `B/domain/account/codes.py`, `B/application/account/messages.py`,
  `B/infrastructure/notifications/*`, `F/components/{code-step,otp-code-field,resend-code-button}.tsx`. Dùng chung cho
  mục 1, 2, 3, 6; chỉ gỡ được khi gỡ cả bốn.
- **Collection hệ thống `formulary`** (nạp bằng CLI `pharma-agent corpus import`): chat cần nó để có dữ liệu.

Ngoài phạm vi danh mục: pipeline RAG/retrieval (embedding, rerank, guardrail, tóm tắt bộ nhớ, ReAct agent dùng cho
đánh giá), `pharma-lab/`, cấu hình triển khai (Vercel, Cloud Run, Render, compose), primitive UI (`F/components/ui/*`),
`GET /maintenance/daily` (dọn phiên hết hạn, purge collection đã xóa, job kẹt), CLI corpus.

---

## A. Tài khoản và xác thực

### 1. `email-verification`: Xác minh email khi đăng ký

- Người dùng: đăng ký xong nhận mã 6 số qua email, nhập mã để kích hoạt; chưa xác minh thì không đăng nhập được.
- Yêu cầu: "Làm chức năng xác minh email bằng mã OTP khi đăng ký giúp tôi."
- Backend: `B/application/account/service.py` (`request_email_verification`, `verify_email`), `B/api/routers/account.py`
  (2 route), `B/infrastructure/auth/users.py` (`on_after_register` gửi mã, `authenticate` chặn tài khoản chưa xác
  minh), `B/application/account/errors.py` (`EmailNotVerified`).
- Frontend: `FF/auth/components/VerifyEmailStep.tsx`, phần bước 2 trong `FF/auth/components/RegisterForm.tsx` và
  `LoginForm.tsx` (lỗi `LOGIN_USER_NOT_VERIFIED`).
- API: `POST /auth/email/verify/request`, `POST /auth/email/verify`.
- Migration: không riêng (cột `email_verified_at` trong `0013`).
- Test: `BT/application/test_account_service.py` (các test `verify_email_*`, `codes_*`), `BT/api/test_account_api_postgres.py`
  (`test_login_before_verification_*`, `test_wrong_code_*`), `FF/auth/components/RegisterForm.browser.test.tsx`,
  `frontend/tests/e2e/auth.e2e.ts`.
- Phụ thuộc: nền đăng ký. Bị phụ thuộc: không (mục 2, 3, 6 chỉ dùng chung hạ tầng OTP).
- Cỡ: vừa, ~250 dòng mã; test ~350.
- Nặng quy tắc: có (mã 10 phút, sai 5 lần hủy mã, tài khoản có mật khẩu phải nhập lại mật khẩu, trả lời giống nhau cho
  email không tồn tại).
- Rò rỉ: `messages.py` (mẫu email "verify"), `OtpPurpose.VERIFY_EMAIL` trong `B/domain/account/models.py`, khóa i18n
  `auth.json`, `errors.json` `EMAIL_NOT_VERIFIED`. Gỡ làm vỡ nhiều test đăng ký/đăng nhập vì chúng giả định phải xác minh.
- **Không chọn**: helper đăng ký dùng chung của test gọi thẳng route xác minh (`verified_register` trong
  `BT/api/postgres_app.py` ~dòng 182, `frontend/tests/e2e/support/api.ts:66`), nên gỡ mục này sửa hạ tầng test của mọi
  tính năng khác; và `reset_password` (mục 2) cũng gọi `mark_email_verified`, nên quy tắc "đã xác minh" không nằm gọn
  trong mục này.
- Commit: `a6740bba feat(backend): add email, SMS and OTP settings for account flows`,
  `a90d12ea feat(frontend): add the code entry step, phone parsing and the account API client`,
  `94e1a289 feat(e2e): cover email verification, password reset and phone sign-in`.

### 2. `password-reset`: Quên mật khẩu

- Người dùng: nhập email, nhận mã, đặt mật khẩu mới; mọi phiên cũ bị đăng xuất.
- Yêu cầu: "Làm chức năng quên mật khẩu giúp tôi."
- Backend: `service.py` (`request_password_reset`, `reset_password`), `routers/account.py` (2 route), mẫu email trong
  `messages.py`.
- Frontend: `FF/auth/components/ForgotPasswordForm.tsx`, `F/routes/auth/forgot-password.tsx`, dòng route trong
  `F/routes.ts`, liên kết trong `LoginForm.tsx`.
- API: `POST /auth/password/forgot`, `POST /auth/password/reset`.
- Migration: không.
- Test: `FF/auth/components/ForgotPasswordForm.browser.test.tsx`, `test_account_service.py` (`test_reset_password_*`),
  `test_account_api_postgres.py` (`test_forgot_password_answers_the_same_and_reset_works`),
  `frontend/tests/e2e/account.e2e.ts` (`forgot password resets with an emailed code`).
- Phụ thuộc: hạ tầng OTP; `SessionStore.delete_all` của mục 7 (reset đăng xuất mọi phiên) và `mark_email_verified`.
  Bị phụ thuộc: không.
- Cỡ: vừa, ~300; test ~250.
- Nặng quy tắc: có, vừa phải (trả lời giống nhau dù email không tồn tại, kiểm tra mật khẩu trước khi tiêu mã, tài
  khoản bị khóa không reset được, hủy mọi phiên).
- Rò rỉ: `OtpPurpose.RESET_PASSWORD`, mẫu email, i18n `auth.json`. Không vỡ test khác.
- Commit: như mục 1.

### 3. `phone-sign-in`: Đăng nhập bằng số điện thoại (SMS OTP)

- Người dùng: nhập số Việt Nam, nhận mã SMS, đăng nhập; lần đầu tự tạo tài khoản chỉ có số điện thoại. Ẩn khi server
  không cấu hình SMS.
- Yêu cầu: "Làm chức năng đăng nhập bằng số điện thoại giúp tôi."
- Backend: `service.py` (`request_phone_login`, `login_with_phone`, `_require_sms`), `routers/account.py` (2 route),
  `B/infrastructure/notifications/sms.py`, `SmsSettings` trong `B/infrastructure/settings.py`, cờ
  `phone_sign_in_enabled` trong `B/api/app.py`, `routers/health.py`, `AccountView`; tạo user theo số trong
  `PG/account_repository.py`.
- Frontend: `FF/auth/components/PhoneLoginForm.tsx`, `SignInMethods.tsx`, `FF/auth/hooks/use-sign-in-options.ts`,
  `F/lib/phone.ts`.
- API: `POST /auth/phone/request`, `POST /auth/phone/login`.
- Migration: cột `phone_number`, `phone_verified_at` trong `0013` (dùng chung với mục 6, để lại).
- Test: `PhoneLoginForm.browser.test.tsx`, `SignInMethods.browser.test.tsx`, `F/lib/phone.test.ts`,
  `test_account_service.py` (`test_phone_login_*`), `test_account_api_postgres.py` (`test_phone_sign_in_*`,
  `test_foreign_numbers_are_422`), `BT/domain/account/test_phone.py`, `frontend/tests/e2e/account.e2e.ts`
  (`phone sign-in creates an account and opens the chat`).
- Phụ thuộc: hạ tầng OTP. Bị phụ thuộc: phần đổi số điện thoại của mục 6 dùng `normalize_phone` (để lại).
- Cỡ: vừa, ~350; test ~300.
- Nặng quy tắc: có (chỉ vùng `VN`, tắt khi `PHARMA_SMS__PROVIDER=none`, tự tạo tài khoản).
- Rò rỉ: cột phone ở DB và `AccountView.phone_number`, `F/lib/phone.ts` nếu để lại, i18n, `errors.json`
  (`PHONE_COUNTRY_NOT_ALLOWED`, `PHONE_SIGN_IN_DISABLED`), `scripts/demo-stack.sh` nói SMS ghi ra log.
- Commit: như mục 1, thêm `4ef11c6d feat(frontend): ... hide phone sign-in when SMS is off`,
  `5e62e89a feat(api): report whether phone sign-in is on in /health`.

### 4. `google-oauth`: Đăng nhập Google và liên kết/hủy liên kết Google

- Người dùng: nút "Đăng nhập với Google"; trong Cài đặt, liên kết hoặc gỡ liên kết tài khoản Google (không gỡ được nếu
  là cách đăng nhập duy nhất). Chỉ hiện khi server có Google client.
- Yêu cầu: "Làm chức năng đăng nhập bằng Google giúp tôi."
- Backend: `B/infrastructure/auth/users.py` (`oauth_callback`, `oauth_associate_callback`, phần Google trong
  `include_auth_routes`), `AuthSettings.google_*` trong `settings.py`, `service.py` (`unlink_google`),
  `routers/account.py` (route unlink), `PG/account_repository.py` (unlink).
- Frontend: `FF/auth/components/GoogleButton.tsx`, `FF/auth/lib/google.ts`, `F/routes/auth/google-callback.tsx`,
  `F/routes/auth/google-link-callback.tsx`, `FF/settings/components/GoogleSetting.tsx`, `FF/settings/lib/google-link.ts`,
  2 dòng trong `F/routes.ts`.
- API: `GET /auth/google/authorize`, `GET /auth/google/callback`, `GET /auth/google/associate/authorize`,
  `GET /auth/google/associate/callback`, `DELETE /account/oauth/google`.
- Migration: bảng `oauth_account` có từ `0001` (nền fastapi-users, để lại).
- Test: `BT/api/test_google_oauth_postgres.py`, `FF/auth/components/GoogleButton.browser.test.tsx`,
  `FF/auth/lib/google.browser.test.tsx`, `FF/settings/components/GoogleSetting.browser.test.tsx`,
  `test_account_settings_service.py` (`test_google_*`).
- Phụ thuộc: nền đăng nhập. Bị phụ thuộc: không.
- Cỡ: vừa, ~480; test ~400. Có thể tách đôi: đăng nhập Google (~300) và liên kết trong Cài đặt (~180).
- Nặng quy tắc: một phần (không gỡ cách đăng nhập cuối cùng `LAST_SIGN_IN_METHOD`; email Google trùng thì liên kết).
- Rò rỉ: bảng `oauth_account`, `OAuthAccountTable`, `AccountView.google_linked/google_sign_in_enabled`,
  `backend/.env.example` (biến `PHARMA_AUTH__GOOGLE_*`), `errors.json` `OAUTH_*`.
- Commit: `a496bcd8 feat(auth): show Google sign-in only when a Google client is configured`.
- **Không chọn**: phải có Google OAuth client thật (hoặc giả lập redirect) mới chạy và chấm được; phần lớn là nối
  thư viện fastapi-users chứ không phải quy tắc; bảng `oauth_account` và `OAuthAccountTable` ở lại lộ hướng làm.

### 5. `profile-and-password`: Đổi tên hiển thị và đổi mật khẩu

- Người dùng: trong Cài đặt sửa tên hiển thị; đổi mật khẩu (phải nhập mật khẩu hiện tại nếu đã có; tài khoản chỉ có
  số điện thoại được đặt mật khẩu đầu tiên).
- Yêu cầu: "Làm chức năng đổi tên và đổi mật khẩu trong trang cài đặt giúp tôi."
- Backend: `service.py` (`update_profile`, `change_password`), `routers/account.py` (`PATCH /users/me`,
  `PUT /account/password`).
- Frontend: `FF/settings/components/ProfileForm.tsx`, `PasswordForm.tsx`, phần schema trong
  `FF/settings/lib/account-schemas.ts`, 2 thẻ trong `SettingsPage.tsx`.
- API: `PATCH /users/me`, `PUT /account/password`.
- Migration: không.
- Test: `ProfileForm.browser.test.tsx`, `PasswordForm.browser.test.tsx`, `account-schemas.test.ts` (một phần),
  `test_account_settings_service.py` (`test_account_view_and_profile_update`, `test_change_password_*`,
  `test_phone_accounts_set_a_first_password_*`), `test_account_api_postgres.py` (`test_settings_change_email_password_and_profile`).
  Không có e2e (`settings.e2e.ts` chỉ phủ ngôn ngữ và giao diện).
- Phụ thuộc: nền; nhánh "đặt mật khẩu đầu tiên" dựa vào `password_set` của tài khoản chỉ có số điện thoại (mục 3).
  Bị phụ thuộc: không.
- Cỡ: vừa, ~370 (tên hiển thị riêng ~130 là nhỏ); test ~330.
- Nặng quy tắc: có, nhẹ (độ dài tên 1–100, quy tắc mật khẩu hiện tại).
- Rò rỉ: i18n `settings.json` (`profile`, `password`), `errors.json` `CURRENT_PASSWORD_INVALID`.
- Commit: `a90d12ea`, `4ef11c6d` (gộp).

### 6. `contact-change`: Đổi email / số điện thoại có xác minh

- Người dùng: đổi email hoặc số điện thoại; mã gửi tới địa chỉ mới, email cũ nhận thông báo; địa chỉ đã thuộc tài
  khoản khác bị từ chối.
- Yêu cầu: "Làm chức năng đổi email và số điện thoại giúp tôi."
- Backend: `service.py` (`request_email_change`, `confirm_email_change`, `request_phone_change`,
  `confirm_phone_change`), `routers/account.py` (4 route), `email_changed_notice` trong `messages.py`.
- Frontend: `FF/settings/components/ContactChangeFlow.tsx`, `AccountSection.tsx` (2 section).
- API: `POST /account/email`, `POST /account/email/confirm`, `POST /account/phone`, `POST /account/phone/confirm`.
- Migration: không.
- Test: `ContactChangeFlow.browser.test.tsx`, `AccountSection.browser.test.tsx`, `test_account_settings_service.py`
  (`test_change_email_*`, `test_change_phone_*`, `test_*_taken_meanwhile_*`, `test_probing_taken_addresses_*`).
- Phụ thuộc: hạ tầng OTP; phần số điện thoại cần mục 3 bật SMS. Bị phụ thuộc: không.
- Cỡ: vừa, ~360; test ~250.
- Nặng quy tắc: có (xung đột địa chỉ, thông báo địa chỉ cũ, mã chỉ có hiệu lực cho đúng tài khoản).
- Rò rỉ: `OtpPurpose.CHANGE_EMAIL/CHANGE_PHONE`, i18n `settings.json.account`, `errors.json` `EMAIL_ALREADY_USED`,
  `PHONE_ALREADY_USED`.
- Commit: `a90d12ea`, `4ef11c6d` (gộp).

### 7. `active-sessions`: Quản lý phiên đăng nhập

- Người dùng: xem các phiên đang mở (thiết bị, IP, lần dùng cuối, phiên hiện tại), đăng xuất một phiên hoặc mọi phiên
  khác.
- Yêu cầu: "Làm chức năng xem và đăng xuất các phiên đăng nhập trên thiết bị khác giúp tôi."
- Backend: `service.py` (`list_sessions`, `revoke_session`, `revoke_other_sessions`), `routers/account.py` (3 route),
  `PG/session_store.py`, phần ghi user-agent/IP/last-used trong `users.py` (`get_session_strategy`, `read_token`).
- Frontend: `FF/settings/components/SessionsList.tsx`, section trong `AccountSection.tsx`.
- API: `GET /account/sessions`, `DELETE /account/sessions/{session_id}`, `DELETE /account/sessions`.
- Migration: cột `user_agent`, `ip_address`, `last_used_at` của `access_tokens` trong `0013`.
- Test: `SessionsList.browser.test.tsx`, `test_account_settings_service.py` (`test_sessions_*`),
  `test_account_api_postgres.py` (`test_revoking_the_current_session_logs_out`, `test_sessions_and_limits_use_the_forwarded_client_ip`),
  `BT/infrastructure/test_account_postgres.py` (`test_session_store_*`), `frontend/tests/demo/chapters/account.ts`.
- Phụ thuộc: nền phiên cookie. Bị phụ thuộc: `SessionStore.delete_all` được `reset_password` (mục 2) và khóa tài
  khoản (mục 26) dùng, nên **chỉ gỡ được phần liệt kê và thu hồi** (`list_sessions`, `revoke_*`, 3 route, UI);
  `session_store.py` và `delete_all` ở lại.
- Cỡ: vừa, ~250 (sau khi giữ `delete_all`); test ~220.
- Nặng quy tắc: không (ít quy tắc, chủ yếu CRUD).
- Rò rỉ: `SessionView` còn trong client sinh, `B/infrastructure/auth/client_ip.py` (dùng chung với mục 8), i18n
  `settings.json.sessions`.
- Commit: `36224121 feat(auth): add Postgres cookie sessions next to bearer JWT` (nền), `a90d12ea` (UI).

### 8. `rate-limiting`: Giới hạn tần suất gửi mã và đăng nhập sai

- Người dùng: gửi lại mã phải chờ 60 giây (nút đếm ngược), tối đa 5 mã/địa chỉ/giờ và 20 mã/IP/giờ; đăng nhập sai 10
  lần trong 15 phút thì bị khóa tạm; lời mời bị giới hạn mỗi người mời/mỗi email; trả 429 kèm `Retry-After`.
- Yêu cầu: "Làm chức năng giới hạn số lần gửi mã và đăng nhập sai giúp tôi."
- Backend: `PG/rate_limiter.py`, `RateLimiter` trong `B/domain/account/ports.py`, `service.py` (`_send_limits`,
  `_limit_send`, `_refund_send`, `check_login_allowed`, `record_login_failure`, các trường trong `AccountPolicy`),
  `users.py` (`authenticate` gọi kiểm tra/ghi lỗi), `B/application/organizations/invitations.py` (`_limit`,
  `InvitationPolicy`), lỗi `RateLimited` + header `Retry-After` trong `B/api/errors.py`, wiring trong
  `B/infrastructure/account_factory.py`, `organizations_factory.py`.
- Frontend: đếm ngược trong `F/components/resend-code-button.tsx`, `F/hooks/use-countdown.ts`, đọc `retry_after` trong
  `F/api/problem.ts`.
- API: không route riêng; thêm 429 vào các route gửi mã, đăng nhập, mời.
- Migration: bảng `rate_limit_buckets` (`0013`, sửa ở `0015`).
- Test: `test_account_service.py` (`test_sending_is_limited_*`, `test_login_failures_lock_*`,
  `test_the_send_cooldown_*`, `test_a_refused_send_*`, `test_a_failed_delivery_*`), `test_account_postgres.py`
  (`test_rate_limiter_*`), `test_account_api_postgres.py` (`test_resend_inside_the_cooldown_is_429_*`,
  `test_login_is_throttled_*`), `test_invitation_service.py` (phần giới hạn), `test_account_settings_service.py`
  (`test_probing_taken_addresses_is_rate_limited_per_ip`).
- Phụ thuộc: mục 1/2/3/6 (để có chỗ gửi mã), mục 15. Bị phụ thuộc: không.
- Cỡ: vừa, ~420; test ~300.
- Nặng quy tắc: có (rất rõ: con số giới hạn, cửa sổ, hoàn lượt khi gửi lỗi).
- Rò rỉ: `errors.json` `RATE_LIMITED`, `problem_responses(429)` trong các router (phải gỡ để không lộ), `CODE_TTL`
  và docstring trong `codes.py`. Ranh giới **lẫn**: logic giới hạn nằm xen trong `AccountService`; gỡ đòi sửa nhiều
  hàm và nhiều test của mục 1–3.
- Commit: `a6740bba` (gộp).

## B. Chat và hội thoại

### 9. `message-feedback`: Đánh giá câu trả lời

- Người dùng: bấm thích/không thích dưới câu trả lời; khi không thích, chọn lý do (sai, thiếu, sai nguồn, khó hiểu)
  và ghi chú; đánh giá hiển thị lại khi mở lịch sử.
- Yêu cầu: "Làm chức năng đánh giá câu trả lời (like/dislike) giúp tôi."
- Backend: `B/domain/feedback/*`, `B/application/feedback/service.py`, `PG/feedback_repository.py`,
  `B/api/routers/feedback.py`, `FeedbackRequest` trong `B/api/schemas.py`, `FeedbackTable` trong `PG/tables.py`, phần
  feedback trong `B/application/conversation/service.py` và `ui_message.py` (`MessageFeedback`), `record_feedback`
  trong `B/application/tracing.py` và `B/infrastructure/observability/langfuse_tracing.py`, wiring `container.py`,
  `deps.py`, `app.py`.
- Frontend: `FF/chat/components/elements/feedback-dialog.tsx`, `FF/chat/lib/feedback-note.ts`, nút thích/không thích
  trong `FF/chat/components/MessageActions.tsx`, `setMessageFeedbackInCache` trong
  `FF/conversations/lib/conversation-cache.ts`.
- API: `POST /messages/{message_id}/feedback`.
- Migration: `0003_feedback.py` (riêng).
- Test: `BT/domain/test_feedback.py`, `BT/application/test_feedback_service.py`, `BT/api/test_feedback_api.py`,
  `BT/infrastructure/test_feedback_repository.py`, phần trong `test_conversation_service.py`, `test_ui_message.py`,
  `test_tracing.py`, `test_langfuse_tracing.py`; `MessageActions.browser.test.tsx`, `feedback-note.test.ts`,
  `conversation-cache.test.ts` (một phần), `frontend/tests/e2e/chat.e2e.ts` (`👎 with a reason and a note is stored for the answer`).
- Phụ thuộc: chat. Bị phụ thuộc: không.
- Cỡ: lớn, ~720 sau khi đếm lại (xem mục "Danh sách ứng viên"); test ~680.
- Nặng quy tắc: không (một đánh giá mỗi người mỗi tin nhắn, ghi đè).
- Rò rỉ: `exclude={"feedback"}` ở `B/api/ui_stream.py:113`; `feedback` trong `messageMetadata` của stream fixture (`BT/contract/*`, `frontend/tests/chat/*`), `test_persistence_metadata.py`,
  i18n `chat.json.feedback`. Gỡ làm vỡ vài test hội thoại/tracing nếu không sửa kèm.
- Commit: `9f7ebfbc feat(feedback): add feedback domain, repository and service with score sink`,
  `946dcfe8 feat(api): add skill upload and message feedback endpoints` (phần feedback).

### 10. `citation-detail`: Xem nguyên văn đoạn trích dẫn

- Người dùng: bấm vào `[1]` trong câu trả lời để mở sheet (desktop) / drawer (mobile) chứa toàn bộ khối văn bản gốc,
  tên tài liệu, mục.
- Yêu cầu: "Làm chức năng bấm vào trích dẫn để xem đoạn tài liệu gốc giúp tôi."
- Backend: `B/api/routers/citations.py`, `B/application/conversation/citations.py`, `PG/citation_reader.py`, lỗi
  `CITATION_NOT_FOUND` trong `B/api/errors.py`, phần tài liệu OpenAPI trong `B/api/openapi.py`.
- Frontend: `FF/chat/components/CitationSheet.tsx`, phần mở sheet trong `CitationMarker.tsx` và `citation-context.tsx`,
  namespace `citations.json`.
- API: `GET /messages/{message_id}/citations/{index}`.
- Migration: không (bảng `message_citations` là nền chat).
- Test: `BT/api/test_citations_api.py`, `BT/application/test_conversation_citations.py`,
  `BT/infrastructure/test_citation_reader.py`, `test_openapi.py::test_citation_detail_is_documented`,
  `CitationSheet.browser.test.tsx`, `frontend/tests/e2e/chat.e2e.ts` (một phần).
- Phụ thuộc: chat. Bị phụ thuộc: không.
- Cỡ: vừa, ~360; test ~280.
- Nặng quy tắc: không.
- Rò rỉ: landing.json nói "Bấm vào [1], [2] để xem đúng đoạn tài liệu", i18n `citations.json`.
- Commit: `a59548e8 feat(api): add citation detail endpoint with the full cited block`,
  `b7f4b23a feat(citations): show the full citation block in a sheet or drawer`.

### 11. `conversation-history`: Danh sách, đổi tên, xóa hội thoại

- Người dùng: thanh bên liệt kê các hội thoại cũ (cuộn để tải thêm), mở lại, đổi tên, xóa có xác nhận.
- Yêu cầu: "Làm chức năng lịch sử hội thoại ở thanh bên (xem lại, đổi tên, xóa) giúp tôi."
- Backend: `B/application/conversation/service.py` (`list_conversations`, `rename`, nhánh title của `update`, `delete`),
  `B/api/routers/conversations.py` (`GET` list, nhánh title của `PATCH`, `DELETE`), `PG/conversation_repository.py`
  (`list_for_user`, `delete`), `UpdateConversationRequest.title` trong `B/api/schemas.py`. `update_title` của
  repository **ở lại**: `B/application/chat/service.py:195` dùng nó để tự đặt tiêu đề; route `PATCH` cũng ở lại vì
  mục 12 dùng `collection_ids`. Cache `updateConversationTitle`/`invalidateConversations` ở lại (ChatSession dùng).
- Frontend: `FF/conversations/components/ConversationSidebar.tsx`, `RenameConversationDialog.tsx`,
  `DeleteConversationDialog.tsx`, phần danh sách trong `FF/conversations/lib/conversation-cache.ts`, chỗ gắn vào
  `FF/shell/components/AppSidebar.tsx`.
- API: `GET /conversations`, `PATCH /conversations/{id}` (title), `DELETE /conversations/{id}`.
- Migration: không (index keyset trong `0007` là nền).
- Test: `ConversationSidebar.browser.test.tsx`, `conversation-cache.test.ts`, `AppSidebar.browser.test.tsx` (một
  phần), `BT/api/test_conversations_api.py` (phần list/patch/delete), `BT/application/test_conversation_service.py`,
  `BT/infrastructure/test_conversation_repository.py` (một phần), `frontend/tests/demo/chapters/history.ts`.
- Phụ thuộc: chat. Bị phụ thuộc: mục 27 (admin xem hội thoại dùng `list_conversations`), mục 12 dùng chung
  `PATCH /conversations/{id}` và cache.
- Cỡ: vừa, ~500 sau khi đếm lại (frontend ~430, backend ~50–100); test ~330.
- Nặng quy tắc: không.
- Rò rỉ: `conversation-cache.ts` dùng chung với mục 9, 12; `F/architecture.test.ts` (chat, shell import conversations);
  i18n `chat.json.conversations`.
- Commit: `a74c4382 feat(conversations): list, rename and delete conversations in the app sidebar`.

### 12. `conversation-source-scope`: Chọn nguồn tài liệu cho từng hội thoại

- Người dùng: trong khung chat chọn các collection để tìm (mặc định tất cả những gì mình được xem); lựa chọn lưu theo
  hội thoại và áp dụng lại mỗi lượt hỏi.
- Yêu cầu: "Làm chức năng chọn bộ tài liệu để hỏi trong từng cuộc trò chuyện giúp tôi."
- Backend: `B/infrastructure/retrieval/scope_resolver.py` (phần `requested`), `B/application/chat/service.py`
  (`collection_ids` cho hội thoại mới), `B/application/conversation/service.py` (`update` phần `collection_ids`),
  `PG/conversation_repository.py` (`update_scope`), `B/domain/conversation/models.py` / `ports.py`,
  `ChatRequest.collection_ids`, `UpdateConversationRequest.collection_ids` trong `B/api/schemas.py`.
- Frontend: `FF/chat/components/SourcesPopover.tsx`, phần scope trong `NewChat.tsx`, `ChatSession.tsx`,
  `replaceConversationInCache`.
- API: trường `collection_ids` của `POST /chat`, `POST /chat/stream`, `PATCH /conversations/{id}`.
- Migration: cột `conversations.collection_ids` trong `0018`.
- Test: `SourcesPopover.browser.test.tsx`, `NewChat.browser.test.tsx` (một phần), `BT/infrastructure/test_scope_resolver.py`,
  `test_scope_retrieval_integration.py` (một phần), `test_chat_service.py`, `test_conversations_api.py` (một phần).
- Phụ thuộc: mục 18 (collection để chọn), chat. Bị phụ thuộc: không.
- Cỡ: vừa, ~330; test ~300.
- Nặng quy tắc: có, vừa (chỉ chọn trong collection được xem; quyền đọc lại mỗi lượt; `null` = mọi nguồn; danh sách
  rỗng bị từ chối).
- Rò rỉ: phần lọc "collection được xem" của `PostgresScopeResolver` phải giữ (đó là quyền, không phải scope), nên
  resolver còn lại gợi ý cấu trúc; landing.json nhắc "scope guard"; i18n `chat.json.scope`.
- Commit: `984a9585 feat(chat): search only the collections the user may see, narrowed per conversation`,
  `998f5933 feat(api): collection management and per-conversation source scope`.

## C. Tổ chức và phân quyền

### 13. `organizations-core`: Tạo, xem, đổi tên, xóa tổ chức

- Người dùng: tạo tổ chức (người tạo là owner), xem danh sách tổ chức của mình, trang tổ chức có tab thành viên; owner
  đổi tên, xóa (phải gõ lại tên để xác nhận).
- Yêu cầu: "Làm chức năng tổ chức (tạo, đổi tên, xóa) giúp tôi."
- Backend: `B/application/organizations/service.py` (`list_mine`, `get`, `create`, `rename`, `delete`, `members`),
  `B/application/organizations/errors.py`, `B/domain/organizations/models.py` + `ports.py` (phần Organization,
  Membership), `B/api/routers/organizations.py` (5 route + list members), `PG/organization_repository.py`,
  `B/infrastructure/organizations_factory.py`, `OrganizationTable`, `OrganizationMemberTable`, `memberships` trong
  `AccountView`.
- Frontend: `FF/organizations/components/OrganizationsPage.tsx`, `OrganizationPage.tsx`, phần danh sách của
  `MembersTab.tsx`, `F/routes/app/organization(s).tsx`, mục điều hướng trong `AppSidebar.tsx`, `F/components/name-form.tsx`.
- API: `GET/POST /organizations`, `GET/PATCH/DELETE /organizations/{id}`, `GET /organizations/{id}/members`.
- Migration: bảng `organizations`, `organization_members` trong `0017`.
- Test: `BT/application/test_organization_service.py`, `BT/api/test_organizations_api_postgres.py`,
  `BT/infrastructure/test_organizations_postgres.py`, `BT/domain/organizations/test_models.py`, `BT/organization_fakes.py`,
  `OrganizationPage.browser.test.tsx`, `frontend/tests/e2e/organizations.e2e.ts`.
- Phụ thuộc: nền. Bị phụ thuộc: 14, 15, 17 (log tổ chức), 18 (collection của tổ chức), 19, 20 (hạn mức tổ chức), 26
  (admin tổ chức). Phải gỡ sau các mục đó hoặc gỡ cùng.
- Cỡ: lớn, ~1100; test ~750.
- Nặng quy tắc: có (chỉ owner đổi tên/xóa, xác nhận bằng tên, xóa không kéo theo collection).
- Rò rỉ: `Role`/`Actor.memberships` ở `B/domain/access` (nền phân quyền, xem mục 16), `can_*_organization` trong
  `policy.py`, cột `owner_organization_id` của collection. Gỡ làm vỡ rất nhiều test (collection, audit, admin).
- **Không chọn**: gần như mọi mục C, D, E dựa vào nó; gỡ là gỡ nửa ứng dụng và vỡ phần lớn test.
- Commit: `8e66c1a1 feat(domain): add the access policy for organizations and collections`,
  `4c1a8b86 feat(db): add organizations, members, invitations, audit events and quota columns`,
  `a03e7295 feat(infra): persist organizations, invitations and audit events in one transaction`,
  `f9227d33 feat(organizations): create, rename, delete organizations and manage members`,
  `98547946 feat(api): organizations, invitations and audit endpoints`.

### 14. `member-management`: Đổi vai trò, xóa thành viên, rời tổ chức

- Người dùng: owner đổi vai trò thành viên (owner/editor/member) và xóa thành viên (có xác nhận); thành viên tự rời
  tổ chức; tổ chức luôn còn ít nhất một owner.
- Yêu cầu: "Làm chức năng quản lý vai trò thành viên trong tổ chức giúp tôi."
- Backend: `service.py` (`set_role`, `remove_member`, `leave`, `_keep_an_owner`, `_remove`), 3 route trong
  `routers/organizations.py`, phương thức tương ứng trong `PG/organization_repository.py`, `can_manage_members`,
  `can_leave` trong `B/domain/access/policy.py`, lỗi `LastOwner`, `MemberNotFound`.
- Frontend: chọn vai trò và nút xóa trong `FF/organizations/components/MembersTab.tsx`, `FF/organizations/lib/roles.ts`,
  nút rời trong `OrganizationPage.tsx`.
- API: `PATCH /organizations/{id}/members/{user_id}`, `DELETE /organizations/{id}/members/{user_id}`,
  `POST /organizations/{id}/leave`.
- Migration: không.
- Test: `test_organization_service.py` (phần role/remove/leave), `BT/domain/access/test_policy.py` (một phần),
  `FF/organizations/lib/roles.test.ts`, `OrganizationPage.browser.test.tsx` (một phần). `organizations.e2e.ts` không có
  test nào cho mục này.
- Phụ thuộc: 13. Bị phụ thuộc: không.
- Cỡ: vừa, ~370; test ~250.
- Nặng quy tắc: có (rất rõ: ai đổi vai trò, owner cuối không rời/không bị hạ, thay đổi có hiệu lực ngay ở request sau).
- Rò rỉ: enum `Role` và `ROLE_RANK` phải ở lại (cả hệ thống dùng); `errors.json` `LAST_OWNER`, `MEMBER_NOT_FOUND`;
  `AuditAction.MEMBER_*`. Đây là bản "phân quyền" gỡ được sạch nhất.
- Commit: `f9227d33`, `874a38e0 feat(frontend): ... confirm member removal`.

### 15. `invitations`: Mời thành viên qua email

- Người dùng: mời theo email kèm vai trò; người nhận mở link, xem trước (tên tổ chức, người mời, email che bớt), chấp
  nhận hoặc từ chối; lời mời hết hạn; người mời có thể thu hồi/gửi lại. Lời mời do member tạo phải chờ owner/editor
  duyệt trước khi gửi email.
- Yêu cầu: "Làm chức năng mời người khác vào tổ chức qua email giúp tôi."
- Backend: `B/application/organizations/invitations.py`, `B/application/organizations/messages.py`,
  `B/api/routers/invitations.py`, 6 route trong `routers/organizations.py`, `PG/invitation_repository.py`, `Invitation`,
  `InvitationStatus`, token trong `B/domain/organizations/models.py`, `invitable_roles`, `invite_needs_approval`,
  `can_decide_invitation`, `can_cancel_invitation` trong `policy.py`, `OrganizationInvitationTable`.
- Frontend: `FF/organizations/components/InvitationsTab.tsx`, `InvitationLanding.tsx`,
  `F/routes/public/invitation.tsx`, dòng route trong `F/routes.ts`, tab trong `OrganizationPage.tsx`.
- API: `GET/POST /organizations/{id}/invitations`, `POST .../invitations/{invitation_id}/{approve,reject,revoke,resend}`,
  `GET /invitations/{token}`, `POST /invitations/{token}/accept`, `POST /invitations/{token}/decline`.
- Migration: bảng `organization_invitations` + 2 index trong `0017`.
- Test: `BT/application/test_invitation_service.py`, `test_invitation_messages.py`, `test_organizations_api_postgres.py`
  (phần mời), `test_migrations.py::test_one_open_invitation_per_email_and_organization`,
  `InvitationLanding.browser.test.tsx`, `organizations.e2e.ts`, `frontend/tests/demo/chapters/orgs.ts`.
- Phụ thuộc: 13, hạ tầng email. Bị phụ thuộc: phần giới hạn mời của mục 8.
- Cỡ: lớn, ~1400; test ~600. Có thể tách phần **duyệt lời mời** (approve/reject, trạng thái chờ duyệt, ~200 dòng) thành
  một nhiệm vụ vừa riêng, nhưng nó xen trong `invite()`.
- Nặng quy tắc: có (rất rõ: ai mời được vai trò nào, member mời phải được duyệt, một lời mời mở cho mỗi email/tổ chức,
  hết hạn, email người chấp nhận phải khớp).
- Rò rỉ: `errors.json` `INVITATION_*`, `ALREADY_MEMBER`; `AuditAction.INVITATION_*`; i18n `organizations.json.invitations`,
  `.landing`; `InvitationPolicy.frontend_url` trong settings.
- Commit: `4c1a8b86`, `a03e7295`, `98547946` (gộp).

### 16. `access-policy`: Phân quyền theo vai trò (bảng quyền)

- Người dùng: ai xem/sửa được tổ chức, collection, nhật ký; superadmin vượt mọi quyền dữ liệu.
- Yêu cầu: "Làm chức năng phân quyền giúp tôi."
- Backend: `B/domain/access/policy.py`, `B/domain/access/models.py`, `B/application/access/service.py`
  (`ActorResolver`), `actor_dependency`, `superadmin_dependency` trong `B/api/deps.py`; lời gọi `can_*` trong mọi
  service của organizations, corpus, audit, admin.
- Frontend: ẩn/hiện nút theo vai trò rải trong `FF/organizations`, `FF/collections`, `FF/admin`.
- API: không route riêng.
- Migration: không riêng.
- Test: `BT/domain/access/test_policy.py`, `BT/application/test_actor_resolver.py`, và gián tiếp gần như mọi test của
  mục 13–27.
- Phụ thuộc: 13. Bị phụ thuộc: 14, 15, 17, 18, 19, 21–27.
- Cỡ: lớn nếu tính lời gọi (~150 dòng policy/actor + ~300 dòng kiểm tra rải rác).
- Nặng quy tắc: có (đây chính là bảng quyền).
- Rò rỉ: rất cao. **Không gỡ sạch được**: gỡ thì mọi service phải viết lại kiểm tra, vỡ hầu hết test của tổ chức và
  collection. Đề xuất dùng mục 14, 19 hoặc 15 làm nhiệm vụ "phân quyền" thay cho mục này.
- **Không chọn**: lý do như trên.
- Commit: `8e66c1a1 feat(domain): add the access policy for organizations and collections`.

### 17. `audit-log`: Nhật ký hoạt động

- Người dùng: trang "Hoạt động" xem việc mình đã làm; tab "Nhật ký" của tổ chức (editor trở lên); superadmin xem nhật ký
  toàn hệ thống. Ghi lại tạo/đổi tên/xóa tổ chức, thay đổi thành viên, lời mời, collection, tài liệu, xuất bản, khóa
  tài khoản, đổi hạn mức.
- Yêu cầu: "Làm chức năng nhật ký hoạt động (audit log) giúp tôi."
- Backend: `B/domain/audit/models.py` + `ports.py`, `B/application/audit/service.py`, `PG/audit_log.py`,
  `B/api/routers/audit.py`, route `/organizations/{id}/audit` và `/admin/audit`, `can_view_audit` trong `policy.py`,
  `AuditEventTable`; **lời gọi `_audit.record(...)`** trong `organizations/service.py`, `invitations.py`,
  `corpus/collections.py`, `corpus/content.py`, `corpus/jobs.py`, `admin/service.py`.
- Frontend: `FF/audit/components/AuditList.tsx`, `MyActivity.tsx`, `FF/audit/lib/describe-event.ts`,
  `F/routes/app/activity.tsx`, tab audit trong `OrganizationPage.tsx`, `AuditSection` trong `FF/admin/components/AdminPage.tsx`,
  mục "Hoạt động" trong `AppSidebar.tsx`.
- API: `GET /account/audit`, `GET /organizations/{id}/audit`, `GET /admin/audit`.
- Migration: bảng `audit_events` + 3 index trong `0017`.
- Test: `BT/application/test_audit_service.py`, assert về sự kiện audit trong `test_organization_service.py`,
  `test_invitation_service.py`, `test_collection_service.py`, `test_content_service.py`, `test_publish_service.py`,
  `test_admin_service.py`; `AuditList.browser.test.tsx`, `describe-event.test.ts`.
- Phụ thuộc: 13 (log tổ chức). Bị phụ thuộc: không.
- Cỡ: lớn, ~800 (chỉ phần đọc + UI: ~450, vừa); test ~400.
- Nặng quy tắc: có (ai xem nhật ký nào; ghi trong cùng giao dịch với thay đổi).
- Rò rỉ: nếu chỉ gỡ phần đọc thì bảng, `AuditAction` và các lời gọi ghi còn nguyên = lộ gần hết lời giải. Gỡ đầy đủ
  phải sửa 6 service và test của chúng (ranh giới **cắt ngang**). i18n `audit.json` liệt kê mô tả từng hành động.
- Commit: `95515d19 feat(audit): read organization, personal and global audit logs`, `a03e7295`, `98547946`.

## D. Collection và nội dung soạn trong app

### 18. `collections-core`: Bộ tài liệu cá nhân và của tổ chức

- Người dùng: tạo collection cho mình hoặc cho tổ chức (editor trở lên), xem danh sách nhóm theo chủ sở hữu, đổi tên,
  xóa (xóa mềm, dọn sau); tab "Collection" trong trang tổ chức.
- Yêu cầu: "Làm chức năng quản lý bộ tài liệu riêng (collection) cho người dùng và tổ chức giúp tôi."
- Backend: `B/application/corpus/collections.py` (trừ phần hạn mức và hiển thị), `B/api/routers/collections.py`,
  `PG/collection_repository.py`, `B/infrastructure/collections_factory.py`, chủ sở hữu trong
  `B/domain/corpus/models.py`, `purge_deleted` + `B/infrastructure/maintenance.py`, CLI `corpus purge-deleted`.
- Frontend: `FF/collections/components/CollectionsPage.tsx`, `CollectionPage.tsx` (khung + tab),
  `FF/organizations/components/OrgCollectionsTab.tsx`, `F/routes/app/collection(s).tsx`, mục điều hướng.
- API: `GET/POST /collections`, `GET/PATCH/DELETE /collections/{id}`.
- Migration: `0018` (chủ sở hữu), `0019` (xóa mềm).
- Test: `BT/application/test_collection_service.py`, `BT/api/test_collections_api_postgres.py`,
  `BT/infrastructure/test_collection_repository.py`, `BT/collection_fakes.py`, `CollectionPage.browser.test.tsx`,
  `frontend/tests/e2e/collections.e2e.ts`.
- Phụ thuộc: 13 (collection tổ chức). Bị phụ thuộc: 12, 19, 20, 21–25, 26 (admin collections).
- Cỡ: lớn, ~1000; test ~750.
- Nặng quy tắc: có (ai tạo cho ai, collection hệ thống chỉ đọc).
- Rò rỉ: bảng `corpus.collections` phải ở lại cho collection hệ thống `formulary`, nên cột chủ sở hữu/`deleted_at`
  khó gỡ mà không đụng pipeline corpus; `SYSTEM_COLLECTION_READ_ONLY`.
- **Không chọn**: bảng collection là nền của corpus hệ thống, và 12, 19–25 đều dựa vào nó.
- Commit: `29706c46 feat(corpus): collections owned by users or organizations with visibility rules`,
  `998f5933 feat(api): collection management and per-conversation source scope`.

### 19. `collection-visibility`: Mức "trong tổ chức" và quyền đặt công khai

- Phạm vi đã thu hẹp: cột `visibility` (`private`/`public`) có từ `0005_corpus_schema`, collection hệ thống `formulary`
  luôn `public`; `0018` chỉ thêm giá trị `organization` cùng ràng buộc chủ sở hữu. Mục này chỉ gỡ phần đó.
- Người dùng: collection của tổ chức có thêm mức "trong tổ chức" (mọi thành viên thấy); collection riêng tư của tổ
  chức là bản nháp chỉ owner/editor thấy; chỉ superadmin đặt được "công khai".
- Yêu cầu: "Làm chức năng chia sẻ bộ tài liệu cho cả tổ chức, và chỉ admin mới được công khai giúp tôi."
- Backend: nhánh `ORGANIZATION` trong `can_view_collection`, `can_set_visibility` trong `policy.py`; `set_visibility`
  trong `collections.py`; trường `visibility` của `UpdateCollection`; giá trị `Visibility.ORGANIZATION` trong
  `B/domain/corpus/models.py`; nhánh tổ chức trong `visible_for` của `PG/collection_repository.py`.
- Frontend: ô chọn visibility trong `FF/collections/components/CollectionPage.tsx` (`visibilityChoices`).
- API: trường `visibility` của `PATCH /collections/{id}`.
- Migration: phần `ck_collections_visibility` (thêm `organization`) và `visibility <> 'organization' OR
  owner_organization_id IS NOT NULL` trong `0018`; ràng buộc `ck_collections_system_is_public` ở lại.
- Test: `test_policy.py` (phần collection), `test_collection_service.py` (phần visibility),
  `test_scope_retrieval_integration.py`, `CollectionPage.browser.test.tsx` (một phần).
- Phụ thuộc: 18, 13. Bị phụ thuộc: 12 (scope lọc theo collection được xem).
- Cỡ: nhỏ–vừa, ~150; test ~200.
- Nặng quy tắc: có (rất rõ, quy tắc ngắn và kiểm chứng được).
- Rò rỉ: sau khi gỡ, collection tổ chức mặc định `private` = chỉ editor trở lên thấy (quy tắc nháp phải giữ hoặc bỏ có
  chủ ý, ghi vào bản sao); `AuditAction.COLLECTION_VISIBILITY_CHANGED`; i18n `collections.json.visibility`; giá trị
  `organization` trong client sinh.
- Commit: `29706c46`.

### 20. `content-quotas`: Hạn mức nội dung

- Người dùng: mỗi người tối đa 5 collection và 1 MB văn bản, mỗi tổ chức 20 collection và 5 MB, tối đa 100 tài liệu
  mỗi collection và 200.000 ký tự mỗi tài liệu; thanh hiển thị mức đã dùng; superadmin đổi hạn mức riêng cho người
  dùng/tổ chức.
- Yêu cầu: "Làm chức năng giới hạn dung lượng và số bộ tài liệu cho mỗi người dùng và tổ chức giúp tôi."
- Backend: `QuotaPolicy`, `owner_limits`, `quota()`, kiểm tra trong `create` của `collections.py`; `_check_text`,
  đếm tài liệu trong `content.py`; `QuotaSettings` trong `settings.py`; `set_user_quotas`, `set_organization_quotas`
  trong `B/application/admin/service.py` + trường quota trong 2 route `PATCH /admin/...`; cột quota trong
  `PG/account_repository.py`, `organization_repository.py`, `tables.py`; lỗi `QuotaExceeded`.
- Frontend: `QuotaBar` trong `FF/collections/components/CollectionsPage.tsx`, `FF/admin/components/QuotaDialog.tsx`,
  `QuotaValue.tsx`, cột quota trong `UsersSection.tsx`, `OrganizationsSection.tsx`.
- API: `GET /collections/quota`; trường quota của `PATCH /admin/users/{id}`, `PATCH /admin/organizations/{id}`.
- Migration: cột `text_quota_bytes`, `collection_quota` của `user` và `organizations` trong `0017`.
- Test: `test_collection_service.py`, `test_content_service.py` (phần quota), `test_admin_service.py` (phần quota),
  `test_migrations.py::test_quota_columns_exist`, `AdminPage.browser.test.tsx` (một phần).
- Phụ thuộc: 18, 21, 26. Bị phụ thuộc: không.
- Cỡ: vừa, ~500; test ~200.
- Nặng quy tắc: có (rất rõ: con số hạn mức, ghi đè theo chủ sở hữu).
- Rò rỉ: `errors.json` `QUOTA_EXCEEDED`, `AuditAction.QUOTA_CHANGED`, i18n `admin.json.quota`, `collections.json.list.quota`,
  `backend/.env.example` (các dòng `PHARMA_QUOTAS__*` ghi sẵn con số hạn mức). Giới hạn kích thước glossary/colloquial (`_check_sizes`) không
  thuộc mục này.
- Commit: `4c1a8b86` (cột), `505033b6 feat(admin): superadmin reads and manages users, organizations, collections and jobs`,
  `b6ee6a7c feat(backend): ... bound and purge authored content ...`.

### 21. `authored-documents`: Soạn tài liệu Markdown trong app

- Người dùng: trong collection, tạo/sửa/xóa tài liệu bằng trình soạn Markdown có thanh công cụ (tiêu đề, loại tài
  liệu, nội dung), xem danh sách tài liệu.
- Yêu cầu: "Làm chức năng soạn tài liệu Markdown trong bộ tài liệu giúp tôi."
- Backend: `B/application/corpus/content.py` (phần document: `list_documents`, `get_document`, `create_document`,
  `update_document`, `delete_document`, `DocumentInput/View/Detail`), 5 route đầu của `B/api/routers/documents.py`,
  phần document của `PG/source_repository.py`, `B/domain/corpus/source.py` (SourceDocument, DocumentKind).
- Frontend: `FF/collections/components/DocumentsTab.tsx`, `DocumentEditorPage.tsx`, `MarkdownEditor.tsx`,
  `EditorToolbar.tsx`, `F/routes/app/document.tsx`, route trong `F/routes.ts`.
- API: `GET/POST /collections/{id}/documents`, `GET/PUT/DELETE /collections/{id}/documents/{document_id}`.
- Migration: bảng `corpus.source_documents` trong `0020`.
- Test: `BT/application/test_content_service.py` (phần document), `BT/api/test_documents_api_postgres.py`,
  `BT/infrastructure/test_source_repository.py`, `DocumentEditorPage.browser.test.tsx`,
  `MarkdownEditor.browser.test.tsx`, `frontend/tests/demo/chapters/collections.ts`.
- Phụ thuộc: 18. Bị phụ thuộc: 22, 24 (chọn mục trong tài liệu), 25 (`jobs.py:151` đếm và `jobs.py:263`
  `list_documents` khi xuất bản), 20 (đọc `text_usage` từ `source_documents`).
- **Không chọn riêng**: chỉ gỡ được khi gộp với 22 và 25, xem mục 31 `authoring-and-publishing`.
- Cỡ: lớn, ~1300; test ~450.
- Nặng quy tắc: có, vừa (chỉ editor sửa, giới hạn ký tự, loại tài liệu).
- Rò rỉ: `B/domain/corpus/authoring.py` (tách Markdown, dựng bundle) ở lại cho mục 25 và lộ cấu trúc tài liệu;
  `AuditAction.DOCUMENT_*`; i18n `collections.json.documents`, `.editor`.
- Commit: `95cf02d6 feat(db): authored documents, glossary, colloquial names and ingest jobs`,
  `57a4e0e2 feat(api): author, upload and publish collection content`,
  `44d33347 feat(collections): shadcn combobox chips, toggle toolbar and typography in the editors`.

### 22. `document-upload`: Tải tệp .md/.txt lên làm tài liệu

- Người dùng: chọn tệp `.md`, `.markdown`, `.txt` (UTF-8, tối đa 1 MB); app đọc tiêu đề từ dòng `# ` đầu tiên và mở
  sẵn trong trình soạn để lưu.
- Yêu cầu: "Làm chức năng tải file Markdown lên thành tài liệu giúp tôi."
- Backend: `read_upload`, `UploadResult`, `MAX_UPLOAD_BYTES`, `UPLOAD_SUFFIXES` trong `content.py`; route upload trong
  `routers/documents.py`; `PayloadTooLarge`.
- Frontend: `FF/collections/components/UploadButton.tsx`, chỗ gắn trong `DocumentsTab.tsx`.
- API: `POST /collections/{id}/documents/upload` (multipart).
- Migration: không.
- Test: phần upload trong `test_content_service.py` và `test_documents_api_postgres.py`.
- Phụ thuộc: 21. Bị phụ thuộc: không.
- Cỡ: vừa (cận nhỏ), ~160; test ~60.
- Nặng quy tắc: có, nhẹ (đuôi tệp, kích thước, mã hóa, cách lấy tiêu đề).
- Rò rỉ: `bodyDocumentsUpload.ts` trong client sinh, `errors.json` `PAYLOAD_TOO_LARGE` (dùng chung), i18n. Ranh giới sạch.
- **Không chọn riêng**: quá mỏng nếu tách và thuộc về mục 31 khi gộp; dùng được như nhiệm vụ nhỏ phụ nếu cần.
- Commit: `57a4e0e2`.

### 23. `glossary`: Bảng thuật ngữ của collection

- Người dùng: tab "Thuật ngữ" để thêm/sửa/xóa thuật ngữ, từ đồng nghĩa và định nghĩa; được dùng khi xuất bản để làm
  giàu đoạn văn bản.
- Yêu cầu: "Làm chức năng bảng thuật ngữ cho bộ tài liệu giúp tôi."
- Backend: `glossary`, `replace_glossary` trong `content.py`, 2 route trong `routers/documents.py`, phần glossary của
  `PG/source_repository.py`; `jobs.py:264` đọc glossary khi dựng bundle, khi gỡ thay bằng `[]`.
- Frontend: `FF/collections/components/GlossaryTab.tsx`, tab trong `CollectionPage.tsx`, `F/components/tags-input.tsx`
  (dùng chung với mục 24).
- API: `GET /collections/{id}/glossary`, `PUT /collections/{id}/glossary`.
- Migration: bảng `corpus.glossary_entries` trong `0020`.
- Test: phần glossary trong `test_content_service.py`, `test_documents_api_postgres.py`, `test_source_repository.py`,
  `test_publish_service.py`.
- Phụ thuộc: 18; 25 để có tác dụng. Bị phụ thuộc: không.
- Cỡ: vừa, ~320; test ~120.
- Nặng quy tắc: có, nhẹ (giới hạn 2000 mục, độ dài trường).
- Rò rỉ: `GlossaryEntry` trong `B/domain/corpus/models.py` và `bundle.py`/`enrichment.py` (pipeline dùng glossary của
  bundle, phải ở lại), `AuditAction.GLOSSARY_UPDATED`, i18n `collections.json.glossary`.
- Commit: `95cf02d6`, `57a4e0e2`.

### 24. `colloquial-names`: Tên thông dụng của thuốc

- Người dùng: tab "Tên thông dụng" để khai báo tên dân gian/nhận dạng (ví dụ "viên sủi hạ sốt") trỏ tới hoạt chất và
  các mục cụ thể trong tài liệu (chọn bằng SectionPicker).
- Yêu cầu: "Làm chức năng khai báo tên gọi thông dụng của thuốc giúp tôi."
- Backend: `colloquial`, `replace_colloquial`, `sections` trong `content.py`, 3 route trong `routers/documents.py`,
  phần colloquial của `PG/source_repository.py`, `section_choices` trong `authoring.py`; `jobs.py:265` đọc tên thông dụng, khi gỡ thay
  bằng `[]`.
- Frontend: `FF/collections/components/ColloquialTab.tsx`, `SectionPicker.tsx`, tab trong `CollectionPage.tsx`.
- API: `GET/PUT /collections/{id}/colloquial`, `GET /collections/{id}/sections`.
- Migration: bảng `corpus.colloquial_mappings` trong `0020`.
- Test: phần colloquial/sections trong `test_content_service.py`, `test_documents_api_postgres.py`,
  `test_source_repository.py`, `BT/domain/corpus/test_authoring.py` (section choices).
- Phụ thuộc: 18, 21 (mục để trỏ tới), 25 để có tác dụng. Bị phụ thuộc: không.
- Cỡ: vừa, ~450; test ~150.
- Nặng quy tắc: có, nhẹ (giới hạn kích thước, section key phải thuộc collection).
- Rò rỉ: `ColloquialMappingRecord` trong domain, retrieval (`B/domain/retrieval/models.py`,
  `B/infrastructure/retrieval/postgres_corpus.py`) dùng tên thông dụng; `AuditAction.COLLOQUIAL_UPDATED`; i18n.
- Commit: `95cf02d6`, `57a4e0e2`.

### 25. `publish-and-releases`: Xuất bản collection, lịch sử phiên bản, quay lui

- Người dùng: bấm "Xuất bản" để dựng bản mới từ tài liệu đã soạn (job chạy nền, thanh tiến độ theo bước), xem danh sách
  bản phát hành, quay lui về bản trước; superadmin xem danh sách job.
- Yêu cầu: "Làm chức năng xuất bản bộ tài liệu để chatbot tìm kiếm được giúp tôi."
- Backend: `B/application/corpus/jobs.py` (`PublishService`), `B/api/routers/jobs.py`, `PG/ingest_job_repository.py`,
  `B/infrastructure/publishing_factory.py`, `B/infrastructure/jobs/{inline,inprocess}.py`, `build_bundle` trong
  `B/domain/corpus/authoring.py`, `JobsSettings`, phục hồi job kẹt trong `maintenance.py`, route `GET /admin/ingest-jobs`.
- Frontend: `FF/collections/components/PublishButton.tsx`, `ReleasesTab.tsx`, `FF/admin/components/JobsSection.tsx`.
- API: `POST /collections/{id}/publish`, `POST /collections/{id}/rollback`, `GET /collections/{id}/releases`,
  `GET /ingest-jobs/{job_id}`, `GET /admin/ingest-jobs`.
- Migration: bảng `corpus.ingest_jobs` + index trong `0020`.
- Test: `BT/application/test_publish_service.py`, `BT/infrastructure/test_inline_dispatcher.py`,
  `test_inprocess_dispatcher.py`, `test_jobs.py`, `BT/domain/corpus/test_authoring.py` (build_bundle),
  `frontend/tests/e2e/collections.e2e.ts`, `organizations.e2e.ts` (luồng xuất bản).
- Phụ thuộc: 18, 21; dùng `ImportKnowledgeBundle` của pipeline corpus (để lại). Bị phụ thuộc: 23, 24 (chỉ có tác dụng
  khi xuất bản), 26 (tab job).
- Cỡ: lớn, ~1100; test ~500.
- Nặng quy tắc: có, vừa (một job mỗi collection, job quá hạn bị thay, chỉ editor xuất bản/quay lui).
- Rò rỉ: CLI `corpus publish/rollback` và `CorpusService.publish/rollback` (nền, cho collection hệ thống) gần giống lời
  giải; `PUBLISH_IN_PROGRESS`; `JobStep` trong `B/domain/corpus/source.py`; `backend/README.md` mô tả cách chạy job.
- Commit: `4a5e6132 feat(corpus): build a knowledge bundle from authored Markdown documents`, `57a4e0e2`,
  `b6ee6a7c feat(backend): recover stuck publish jobs ...`.

## E. Quản trị

### 26. `admin-console`: Bảng điều khiển superadmin

- Người dùng: superadmin vào `/admin`: tổng quan (thẻ số liệu), danh sách người dùng (tìm kiếm, phân trang, khóa/mở
  khóa tài khoản, khóa thì đăng xuất mọi phiên, không tự khóa mình), tổ chức, collection; người khác nhận 404. Cấp
  quyền superadmin bằng CLI.
- Yêu cầu: "Làm trang quản trị cho superadmin giúp tôi."
- Backend: `B/application/admin/service.py` (trừ quota), `B/api/routers/admin.py` (users, organizations, collections),
  `superadmin_dependency` trong `B/api/deps.py`, `B/infrastructure/auth/superadmin.py`, lệnh `superadmin grant/revoke/list`
  trong `B/cli.py`, phương thức liệt kê trong `account_repository.py`, `organization_repository.py`, `overview` của
  `collections.py`.
- Frontend: `FF/admin/components/{AdminPage,AdminOverview,UsersSection,OrganizationsSection,CollectionsSection,columns}.tsx`,
  `FF/admin/lib/require-superadmin.ts`, `F/components/data-table.tsx`, `F/components/section-cards.tsx`,
  `F/routes/app/admin.tsx`, mục điều hướng có điều kiện trong `AppSidebar.tsx`.
- API: `GET /admin/users`, `PATCH /admin/users/{id}` (is_active), `GET /admin/organizations`,
  `PATCH /admin/organizations/{id}`, `GET /admin/collections`.
- Migration: không (cờ `is_superuser` là của fastapi-users).
- Test: `BT/application/test_admin_service.py`, `BT/api/test_admin_api_postgres.py`,
  `BT/infrastructure/test_superadmin_cli.py`, `AdminPage.browser.test.tsx`, `AppSidebar.browser.test.tsx` (một phần),
  `frontend/tests/e2e/admin.e2e.ts`, `frontend/tests/demo/chapters/admin.ts`.
- Phụ thuộc: 13, 18, 7 (thu hồi phiên). Bị phụ thuộc: 20 (dialog hạn mức), 25 (tab job), 27, 17 (tab nhật ký toàn cục).
- Cỡ: lớn, ~1000; test ~350.
- Nặng quy tắc: có (chỉ superadmin, trả 404 để giấu, không tự khóa, khóa thì hủy phiên).
- Rò rỉ: `AccountView.is_superadmin`, `is_superadmin` trong `Actor` (nền phân quyền), `AuditAction.USER_*`, i18n `admin.json`,
  `F/architecture.test.ts` (admin import auth/chat/audit). Nên gỡ cùng 20, 27 và phần tab job/nhật ký, hoặc giữ chúng
  và chỉ gỡ phần người dùng/tổ chức/collection.
- Commit: `505033b6 feat(admin): superadmin reads and manages users, organizations, collections and jobs`,
  `10a74ee5 feat(frontend): superadmin console`, `31d57116 feat(frontend): admin dashboard and app shell from the shadcn dashboard-01 block`,
  `63085d07 feat(account): ... grant superadmin from the CLI`.

### 27. `admin-user-conversations`: Superadmin xem hội thoại của người dùng

- Người dùng: trong danh sách người dùng, superadmin mở sheet xem các hội thoại của một người và đọc từng hội thoại ở
  chế độ chỉ đọc (không ghi nhật ký, chính sách quyền riêng tư có nói).
- Yêu cầu: "Làm chức năng cho admin xem lại các cuộc trò chuyện của người dùng giúp tôi."
- Backend: 2 route cuối trong `B/api/routers/admin.py` (gọi lại `ConversationService`).
- Frontend: `FF/admin/components/UserConversationsSheet.tsx`, `ReadOnlyThread.tsx`, nút mở trong `UsersSection.tsx`.
- API: `GET /admin/users/{user_id}/conversations`, `GET /admin/users/{user_id}/conversations/{conversation_id}/messages`.
- Migration: không.
- Test: `ReadOnlyThread.browser.test.tsx`, phần trong `test_admin_api_postgres.py`, `AdminPage.browser.test.tsx`.
- Phụ thuộc: 26, 11 (`list_conversations`). Bị phụ thuộc: không.
- Cỡ: vừa, ~280; test ~90.
- Nặng quy tắc: có, nhẹ (chỉ superadmin, chỉ đọc, không ghi nhật ký).
- Rò rỉ: `FF/legal/lib/content.ts` (chính sách quyền riêng tư nói rõ admin đọc được hội thoại), i18n `admin.json.conversations`,
  `F/architecture.test.ts` (admin import chat). Ranh giới sạch.
- Commit: `505033b6`, `10a74ee5`.

## F. Giao diện, cài đặt, trang công khai

### 28. `theme-switch`: Chọn giao diện sáng/tối/theo hệ thống

- Người dùng: trong Cài đặt chọn sáng, tối hoặc theo hệ thống; lưu qua cookie, render đúng ngay từ SSR (không nháy).
- Yêu cầu: "Làm chức năng chuyển giao diện sáng tối giúp tôi."
- Backend: không.
- Frontend: `FF/settings/components/ThemeRadioGroup.tsx`, `F/lib/theme.server.ts`, `F/routes/actions/theme.ts`, dòng
  route trong `F/routes.ts`, `ThemeProvider`/`PreventFlashOnWrongTheme` trong `F/root.tsx`, biến dark trong `F/app.css`
  (để lại).
- API: action frontend `POST /actions/theme`.
- Migration: không.
- Test: `F/lib/theme.server.test.ts`, `SettingsPage.browser.test.tsx` (một phần), `frontend/tests/e2e/settings.e2e.ts`,
  `frontend/tests/demo/chapters/account.ts`.
- Phụ thuộc: không. Bị phụ thuộc: không.
- Cỡ: nhỏ, ~110; test ~60.
- Nặng quy tắc: không.
- Rò rỉ: gói `remix-themes` trong `frontend/package.json`, biến `THEME_COOKIE_SECRET`, CSS `.dark` trong `app.css`, i18n
  `settings.json.theme`.
- Commit: không có commit riêng (`3a3396b2 feat(frontend): add skills page ...` là commit tạo file).

### 29. `language-switch`: Chuyển ngôn ngữ Việt/Anh

- Người dùng: trong Cài đặt chọn Tiếng Việt hoặc English; lưu cookie, áp dụng cho cả email/SMS gửi đi.
- Yêu cầu: "Làm chức năng chuyển đổi ngôn ngữ tiếng Việt / tiếng Anh giúp tôi."
- Backend: không (đọc `Accept-Language`/cookie qua `RequestLocale` là nền).
- Frontend: `FF/settings/components/LanguageSelect.tsx`, `F/routes/actions/locale.ts`, `setLocale` trong
  `F/i18n/locale.server.ts`, dòng route trong `F/routes.ts`.
- API: action frontend `POST /actions/locale`.
- Migration: không.
- Test: `F/i18n/locale.server.test.ts` (một phần), `SettingsPage.browser.test.tsx`, `settings.e2e.ts`.
- Phụ thuộc: hạ tầng i18n (nền). Bị phụ thuộc: không.
- Cỡ: nhỏ, ~110; test ~50.
- Nặng quy tắc: không.
- Rò rỉ: cả bộ `F/i18n/resources/en/*` ở lại nên agent chỉ cần nối; i18n `settings.json.language`. Nhiệm vụ dễ.
- Commit: không có commit riêng.

### 30. `public-pages`: Trang giới thiệu và trang pháp lý

- Người dùng: trang chủ công khai (giới thiệu, tính năng, nút đăng nhập/đăng ký, meta SEO, bản `/en`), trang Chính sách
  quyền riêng tư và Điều khoản (vi/en), chân trang có liên kết.
- Yêu cầu: "Làm trang giới thiệu và trang chính sách, điều khoản giúp tôi."
- Backend: không.
- Frontend: `FF/landing/components/LandingPage.tsx`, `FF/landing/lib/meta.ts`, `FF/legal/components/{LegalPage,LegalLinks,SiteFooter}.tsx`,
  `FF/legal/lib/{content,meta}.ts`, `F/routes/public/{landing,privacy,terms}.tsx`, 6 dòng route trong `F/routes.ts`,
  namespace `landing.json`, `F/i18n/public-page-locale.test.ts`.
- API: không.
- Migration: không.
- Test: `LandingPage.test.tsx`, `FF/landing/lib/meta.test.ts`, `LegalPage.browser.test.tsx`,
  `F/i18n/public-page-locale.test.ts`, `frontend/tests/e2e/public.e2e.ts`, `frontend/tests/demo/chapters/public.ts`.
- Phụ thuộc: không. Bị phụ thuộc: liên kết pháp lý trong `RegisterForm.tsx` (sửa kèm).
- Cỡ: lớn, ~700 (phần lớn là văn bản; mã thực ~300); test ~260.
- Nặng quy tắc: không.
- Rò rỉ: `frontend/public/` (favicon, ảnh), `F/root.tsx` (meta), docs. Văn bản pháp lý không thể "dựng lại" khách
  quan, nên chấm khó; có thể chỉ dùng phần landing (~250, vừa).
- **Không chọn**: phần lớn là văn bản, không có tiêu chí đúng/sai để chấm theo hành vi.
- Commit: `f9842e6b feat(ui): ViPharmind brand: logo, green theme, favicon, touch-size controls` (gộp),
  `badd47c9 fix(landing): present private collections and the scope guard too`.

### 31. `authoring-and-publishing`: Soạn, tải lên và xuất bản tài liệu (gộp 21 + 22 + 25)

- Người dùng: trong collection, soạn tài liệu Markdown hoặc tải tệp `.md`/`.txt` lên, rồi bấm "Xuất bản" để chatbot tìm
  được; xem tiến độ job, lịch sử bản phát hành, quay lui.
- Yêu cầu: "Làm chức năng soạn và xuất bản tài liệu vào bộ tài liệu để chatbot tìm được giúp tôi."
- Backend/Frontend/API/Test: hợp của mục 21, 22, 25.
- Migration: `corpus.source_documents` và `corpus.ingest_jobs` trong `0020` (glossary/colloquial ở lại cho 23, 24).
- Phụ thuộc: 18. Bị phụ thuộc: 20 (`text_usage` đọc `source_documents`: gỡ kèm phần hạn mức văn bản hoặc trả 0),
  23, 24 (chỉ có tác dụng khi xuất bản; `section_choices` của 24 cần tài liệu: gỡ 24 cùng hoặc để `sections` trả rỗng),
  26 (tab job).
- Cỡ: lớn, ~2.500 (21 ~1.300 + 22 ~160 + 25 ~1.100); test ~1.000.
- Nặng quy tắc: có, vừa (chỉ editor soạn/xuất bản, giới hạn ký tự và số tài liệu, một job mỗi collection, job quá hạn
  bị thay).
- Rò rỉ: như 21 và 25 (CLI `corpus publish/rollback`, `CorpusService`, `ImportKnowledgeBundle` ở lại; `authoring.py`
  nếu không gỡ cùng), `AuditAction.DOCUMENT_*`, `COLLECTION_PUBLISHED`, `COLLECTION_ROLLED_BACK`, i18n
  `collections.json.documents/.editor/.publish/.releases`, `backend/README.md` mục xuất bản.
- Commit: `95cf02d6`, `4a5e6132`, `57a4e0e2`, `b6ee6a7c`.

---

## Bảng tóm tắt

| # | id | cỡ (mã, ~dòng) | nặng quy tắc | phụ thuộc | chọn |
|---|---|---|---|---|---|
| 1 | email-verification | vừa (~250) | có | nền đăng ký, OTP | không chọn |
| 2 | password-reset | vừa (~300) | có | OTP, 7 (`delete_all`) | ứng viên |
| 3 | phone-sign-in | vừa (~350) | có | OTP | ứng viên |
| 4 | google-oauth | vừa (~480) | một phần | nền đăng nhập | không chọn |
| 5 | profile-and-password | vừa (~370) | có (nhẹ) | nền, 3 (`password_set`) | ứng viên |
| 6 | contact-change | vừa (~360) | có | OTP, 3 (phần SĐT) | ứng viên |
| 7 | active-sessions | vừa (~250) | không | nền phiên cookie | ứng viên (chỉ liệt kê/thu hồi) |
| 8 | rate-limiting | vừa (~420) | có | 1/2/3/6, 15 | ứng viên |
| 9 | message-feedback | lớn (~720, đếm lại) | không | chat | ứng viên |
| 10 | citation-detail | vừa (~360) | không | chat | ứng viên |
| 11 | conversation-history | vừa (~500, đếm lại) | không | chat | ứng viên |
| 12 | conversation-source-scope | vừa (~330) | có | 18, chat | ứng viên |
| 13 | organizations-core | lớn (~1100) | có | nền | không chọn |
| 14 | member-management | vừa (~370) | có | 13 | ứng viên |
| 15 | invitations | lớn (~1400) | có | 13, email | ứng viên |
| 16 | access-policy | lớn (~450, rải rác) | có | 13 | không chọn |
| 17 | audit-log | lớn (~800, gỡ cả lời gọi ghi) | có | 13 | ứng viên |
| 18 | collections-core | lớn (~1000) | có | 13 | không chọn |
| 19 | collection-visibility | nhỏ–vừa (~150) | có | 18, 13 | ứng viên |
| 20 | content-quotas | vừa (~500) | có | 18, 21, 26 | ứng viên |
| 21 | authored-documents | lớn (~1300) | có | 18 | chỉ trong 31 |
| 22 | document-upload | vừa (~160) | có (nhẹ) | 21 | chỉ trong 31 |
| 23 | glossary | vừa (~320) | có (nhẹ) | 18, (25) | ứng viên |
| 24 | colloquial-names | vừa (~450) | có (nhẹ) | 18, 21, (25) | ứng viên |
| 25 | publish-and-releases | lớn (~1100) | có | 18, 21 | ứng viên |
| 26 | admin-console | lớn (~1000) | có | 13, 18, 7 | ứng viên (gộp được với 27) |
| 27 | admin-user-conversations | vừa (~280) | có (nhẹ) | 26, 11 | ứng viên |
| 28 | theme-switch | nhỏ (~110) | không | không | ứng viên |
| 29 | language-switch | nhỏ (~110) | không | i18n (nền) | ứng viên |
| 30 | public-pages | lớn (~700, mã ~300) | không | không | không chọn |
| 31 | authoring-and-publishing | lớn (~2.500) | có | 18 | ứng viên (gộp 21+22+25) |

Tổng 31 mục: nhỏ 2, nhỏ–vừa 1, vừa 17, lớn 11. Nặng quy tắc: có 23 (5 ở mức nhẹ: 5, 22, 23, 24, 27), một phần 1 (4),
không 7 (7, 9, 10, 11, 28, 29, 30). Không chọn: 1, 4, 13, 16, 18, 30; chỉ dùng trong mục gộp: 21, 22.

Thứ tự gỡ khi gỡ nhiều mục một lúc: gỡ lá trước (8, 22, 23, 24, 27, 19, 20, 14, 12) rồi tới 21/25, 15, 17, 26, cuối
cùng 18, 13. Mục 16 không gỡ.

## Danh sách ứng viên

22 ứng viên (gỡ riêng từ `clean`, mỗi nhiệm vụ một bản sao nên các ứng viên được phép chồng lên nhau):

| # | id | cỡ | nặng quy tắc |
|---|---|---|---|
| 2 | password-reset | vừa (~300) | có |
| 3 | phone-sign-in | vừa (~350) | có |
| 5 | profile-and-password | vừa (~370) | có (nhẹ) |
| 6 | contact-change | vừa (~360) | có |
| 7 | active-sessions (chỉ liệt kê/thu hồi) | vừa (~250) | không |
| 8 | rate-limiting | vừa (~420) | có |
| 9 | message-feedback | lớn (~720) | không |
| 10 | citation-detail | vừa (~360) | không |
| 11 | conversation-history | vừa (~500) | không |
| 12 | conversation-source-scope | vừa (~330) | có |
| 14 | member-management | vừa (~370) | có |
| 15 | invitations | lớn (~1400) | có |
| 17 | audit-log (gỡ cả lời gọi ghi) | lớn (~800) | có |
| 19 | collection-visibility (mức tổ chức + chỉ superadmin công khai) | nhỏ–vừa (~150) | có |
| 20 | content-quotas | vừa (~500) | có |
| 23 | glossary | vừa (~320) | có (nhẹ) |
| 24 | colloquial-names | vừa (~450) | có (nhẹ) |
| 25 | publish-and-releases | lớn (~1100) | có |
| 26 | admin-console (gộp được với 27) | lớn (~1000; gộp ~1280) | có |
| 27 | admin-user-conversations | vừa (~280) | có (nhẹ) |
| 28 | theme-switch | nhỏ (~110) | không |
| 29 | language-switch | nhỏ (~110) | không |

Thêm phương án gộp: **31 authoring-and-publishing** (lớn, ~2.500, có).

**Thiếu nhiệm vụ lớn**: theo bản review chỉ có 4 nhiệm vụ lớn gỡ sạch: 15, 17 (gỡ đủ, kể cả lời gọi ghi), 25, và
26+27 gộp thành một nhiệm vụ admin. Đếm lại 9 và 11 (2026-11-26, `wc -l` và `git grep` trên đúng phần sẽ gỡ):

- **#9 message-feedback ≈ 720 dòng mã → lớn.** File riêng 422 dòng (`B/domain/feedback/*`,
  `B/application/feedback/*`, `PG/feedback_repository.py`, `B/api/routers/feedback.py`, migration `0003` 45 dòng,
  `feedback-dialog.tsx` 108, `feedback-note.ts` 14). Phần trong file dùng chung backend ~90 (`FeedbackTable` 22,
  `MessageFeedback` và trường trong `ui_message.py`, `conversation/service.py`, `record_feedback` ở `tracing.py` và
  `langfuse_tracing.py`, wiring `container.py`/`deps.py`/`app.py`/`errors.py`, `FeedbackRequest`, `ui_stream.py`).
  Phần trong file dùng chung frontend ~210 (`MessageActions.tsx` ~120 trên 171 dòng, `ChatSession.tsx` ~15,
  `withFeedback` trong `chat-messages.ts` ~12, `message-view.ts` ~5, `setMessageFeedbackInCache` ~20, `MessageParts`/
  `ReadOnlyThread` ~4, i18n `chat.json.feedback` 13 + 3 khóa `actions` × 2 ngôn ngữ ~32). Test ~680 (333 dòng file
  riêng + ~350 trong 20 file dùng chung).
- **#11 conversation-history ≈ 500 dòng mã → vừa, không đủ lớn.** Frontend ~430
  (`ConversationSidebar` + `RenameConversationDialog` + `DeleteConversationDialog` = 379, `removeConversationFromCache` 9,
  chỗ gắn trong `AppSidebar` ~5, i18n `chat.json.conversations` 18 × 2). Backend chỉ ~50 nếu giữ mục 27 (route list,
  nhánh title của `PATCH`, `rename`, `delete` ở service/repository/port); ~100 nếu gỡ cả `list_conversations`/
  `list_for_user` (khi đó phải gỡ 27). `update_title`, route `PATCH` và các hàm cache mà ChatSession dùng ở lại.
  Test ~330.

**Kết quả: 5 nhiệm vụ lớn** (9, 15, 17, 25, 26+27); **6** nếu thêm 31 `authoring-and-publishing` (chồng với 25 nhưng
là nhiệm vụ khác trên bản sao khác). 11 vẫn là vừa.

## Rủi ro

1. **Việc dọn ngoài tính năng trở thành một phần của thí nghiệm.** Mỗi lần gỡ đều sửa file dùng chung (migration,
   client sinh, i18n, fake test, bảng kiến trúc). Nếu làm tay, mỗi bản sao khác nhau một cách không kiểm soát. Cần
   script gỡ cho từng nhiệm vụ, grep rò rỉ ra rỗng, và bản sao gốc chạy xanh trước khi giao.
2. **Ghép nối ẩn.** 2 → 7 (`reset_password` gọi `SessionStore.delete_all`); 11 → chat (`update_title` tự đặt tiêu đề,
   cache sidebar do ChatSession cập nhật); 21 ↔ 25 và 20 (xuất bản đọc tài liệu, hạn mức đọc `text_usage`); 19 và
   collection hệ thống (`formulary` luôn public, ràng buộc `ck_collections_system_is_public`); 1 và helper đăng ký dùng
   chung của test. Bỏ sót một chỗ là bản sao gốc không chạy hoặc lộ lời giải.
3. **Một câu yêu cầu không mang được hằng số chính xác.** Với các nhiệm vụ nặng quy tắc (8, 15, 19, 20), agent không thể
   đoán "60 giây, 5 mã/giờ" hay "5 collection, 1 MB". Phải chấm theo hành vi (có giới hạn, có trả 429, có chặn vượt hạn
   mức), và chỉ coi một hằng số là ý định người dùng nếu người dùng thật sẽ nói ra nó.

## Các mục kém chắc chắn nhất

- **16 access-policy**: không có ranh giới sạch; gỡ thì vỡ hầu hết test tổ chức/collection. Dùng 14, 19 hoặc 15 cho
  yêu cầu "phân quyền".
- **17 audit-log**: phần ghi sự kiện cắt ngang 6 service; gỡ chỉ phần đọc thì lộ lời giải, gỡ đủ thì nhiệm vụ rất
  rộng. Cỡ ±40%.
- **8 rate-limiting**: logic xen trong `AccountService` và `users.py`; ước lượng dòng và danh sách test bị ảnh hưởng
  có thể thiếu.
- **18 collections-core**: bảng `corpus.collections` là nền của corpus hệ thống; không rõ gỡ đến đâu thì app vẫn chạy
  và chat vẫn có dữ liệu.
- **19 collection-visibility**: đã thu hẹp còn mức "tổ chức" + quyền đặt công khai; sau khi gỡ, quy tắc nháp
  (private của tổ chức chỉ editor thấy) phải giữ hoặc bỏ có chủ ý, và điều đó ảnh hưởng tới việc chấm.
- **20 content-quotas**: rải trong 4 service và 2 trang frontend; con số ~500 là ước lượng thô.
- **1 email-verification** (đã đánh dấu không chọn): helper đăng ký của test gọi route xác minh.
- **9, 11**: số dòng phần dùng chung trong `MessageActions.tsx`, `ChatSession.tsx` là ước lượng theo khối, ±20%.
- Cột "commit" của mọi mục: lịch sử đã gộp, không mục nào có một commit `feat` sạch riêng.
- Đã cân nhắc nhưng bỏ khỏi danh mục: hiển thị bằng chứng truy xuất (`EvidencePanel`, gắn với hợp đồng stream của
  pipeline), nút sao chép câu trả lời (~40 dòng, quá nhỏ), guardrail chặn câu hỏi ngoài phạm vi (nằm trong pipeline
  LangGraph).
