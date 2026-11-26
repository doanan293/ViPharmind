# Tài khoản, tổ chức và phân quyền, tự nạp nội dung, ra mắt sản phẩm

Ngày: 2026-11-15. Trạng thái: thiết kế hiện hành, mô tả đúng mã trên nhánh `v2.0.0`. Gom từ năm file
spec và plan ngày 2026-10-10 (xem mục Lịch sử quyết định).

## 1. Mục tiêu và phạm vi

ViPharmind chạy như một sản phẩm cho người dùng thật, không chỉ là bản demo của luận văn. Spec này
bao bốn phần dính nhau:

1. **Tài khoản.** Đăng ký, đăng nhập bằng email và mật khẩu, số điện thoại và mã SMS, hoặc Google, cả
   ba gắn vào một tài khoản. Mọi bước xác minh dùng mã OTP 6 số. Người dùng tự quản lý cách đăng nhập
   và phiên đăng nhập.
2. **Tổ chức và phân quyền.** Người dùng tạo tổ chức, mời người khác qua email với ba vai trò owner,
   editor, member. Collection thuộc một người dùng, một tổ chức hoặc hệ thống, với ba mức hiển thị.
   Superadmin quản trị mọi dữ liệu. Thao tác thay đổi quyền và dữ liệu được ghi nhật ký.
3. **Tự nạp nội dung.** Owner, editor soạn hoặc tải tài liệu Markdown, thêm thuật ngữ và tên gọi dân
   gian, rồi xuất bản collection qua đúng pipeline nạp corpus hiện có, trong hạn mức.
4. **Ra mắt.** Frontend và backend trên Vercel Hobby, dữ liệu trên Neon và Qdrant Cloud, model qua
   OpenRouter, thư qua Resend, chi phí gần bằng không ở quy mô ra mắt.

Yêu cầu chung: an toàn ở mức production (không lưu mã hay token gốc, giới hạn số lần thử và gửi, không
để lộ tài khoản hay tổ chức nào tồn tại), backend không giữ trạng thái (mọi trạng thái nằm trong
Postgres) để đổi host hay chạy nhiều instance mà không sửa mã.

Thuộc mảng khác, chỉ liên kết:

- Agent dược, luồng chat, `ReleaseScope` dùng trong retrieval: `2026-11-15-backend-agent-api-design.md`.
- Pipeline nạp corpus (`import_bundle`, release, chunk, embedding, Qdrant, chuẩn hoá dữ liệu corpus ở
  migration 0016 và 0021): `2026-11-15-corpus-data-pipeline-design.md`.
- Quy tắc giao diện shadcn, cấu trúc feature của frontend: `2026-11-15-frontend-design.md`.
- Luật import một chiều backend và frontend: `2026-11-15-architecture-rules-design.md`.

## 2. Tài khoản

### 2.1 Quyết định

| Chủ đề | Quyết định |
| --- | --- |
| Nền tảng | fastapi-users trong backend, session cookie và CSRF. Không dùng dịch vụ auth bên ngoài. Chỉ có cookie login; JWT bearer login đã bỏ vì nó bỏ qua việc thu hồi phiên |
| Xác minh | Mã OTP 6 số, hạn 10 phút, dùng một lần, sai quá 5 lần thì hết hiệu lực. Tạo mã mới huỷ mọi mã chưa dùng cùng `(purpose, destination)`. Không mount router verify, reset bằng link của fastapi-users |
| Lưu mã | HMAC-SHA256 với khoá `PHARMA_AUTH__OTP_SECRET`, gộp `purpose`, `destination` và mã; so bằng `hmac.compare_digest` |
| Xác minh email cần mật khẩu | `POST /auth/email/verify` nhận `{email, code, password}`; tài khoản có mật khẩu thì bắt buộc đúng mật khẩu, dùng chung giới hạn đăng nhập sai. Lý do: xác minh xong là đăng nhập, nên chỉ có mã thì chủ hộp thư chiếm được tài khoản người khác đăng ký bằng địa chỉ của họ. Không có mật khẩu thì đi đường quên mật khẩu, vốn thay mật khẩu |
| Tài khoản chỉ có số điện thoại | `user.email` NULL được; mật khẩu ngẫu nhiên không ai biết, `password_set = false` (giống tài khoản tạo qua Google) |
| Liên kết Google | Chỉ tự liên kết khi email Google trùng một email **đã xác minh**; email chưa xác minh trả `OAUTH_USER_ALREADY_EXISTS`. Tài khoản chưa có email liên kết Google thì nhận luôn email Google, trừ khi email đó thuộc tài khoản khác. Nút Google ẩn khi chưa cấu hình client (`google_sign_in_enabled`) |
| Gửi thư | Port `EmailSender`, adapter `resend` (production, HTTPS API) và `log` (local, test) |
| Gửi SMS | Port `SmsSender`, adapter `log`. Production chạy `PHARMA_SMS__PROVIDER=none`: API SMS trả `503 PHONE_SIGN_IN_DISABLED`, giao diện ẩn tab số điện thoại. Chỉ gửi tới số trong `allowed_country_codes` (mặc định `["VN"]`) |
| Cách gửi | Gửi ngay trong request, vì serverless function có thể bị đóng băng sau khi trả lời. Gửi lỗi thì mã bị huỷ, trả `503 DELIVERY_FAILED` |
| Ngôn ngữ thư | Lấy từ header `Accept-Language`; frontend đặt header này theo ngôn ngữ giao diện |
| Không lộ tài khoản | `forgot`, `verify/request` luôn trả `202`; giới hạn gửi áp dụng trước khi tra tài khoản |

Cách đăng nhập còn hiệu lực: mật khẩu (khi `password_set` và email đã xác minh), số điện thoại đã
xác minh, Google đã liên kết. Không thao tác nào được đưa số cách đăng nhập về 0
(`LAST_SIGN_IN_METHOD`).

### 2.2 Luồng

| Luồng | Quy tắc |
| --- | --- |
| Đăng ký email | Tên, email, mật khẩu (8–128 ký tự) → tài khoản chưa xác minh, gửi mã → nhập mã và mật khẩu → xác minh và đăng nhập |
| Đăng nhập email | Email chưa xác minh trả `403 EMAIL_NOT_VERIFIED`; frontend tự gửi mã và chuyển sang bước nhập mã |
| Đăng nhập số điện thoại | Số (chuẩn hoá E.164 bằng `phonenumbers`, "0912 345 678" và "+84 91 234 5678" là một số) → mã SMS → số mới thì tạo tài khoản, có rồi thì đăng nhập |
| Quên mật khẩu | Email → mã → mật khẩu mới, mọi phiên cũ bị đăng xuất |
| Đổi email, số điện thoại | Mã gửi tới địa chỉ mới, xác nhận xong mới đổi; địa chỉ thuộc tài khoản khác báo `EMAIL_ALREADY_USED`, `PHONE_ALREADY_USED` |
| Đặt, đổi mật khẩu | Chưa từng đặt thì không cần mật khẩu cũ; đã đặt thì bắt buộc (`CURRENT_PASSWORD_INVALID`) |
| Gỡ Google | `409` nếu đó là cách đăng nhập cuối cùng |
| Phiên | Danh sách (user agent, IP, lần dùng gần nhất), đăng xuất một phiên hoặc mọi phiên khác; thu hồi phiên đang dùng thì request sau nhận `401` |

### 2.3 Dữ liệu

- `user`: `email` NULL được, unique không phân biệt hoa thường (index `lower(email)`, migration 0014);
  `phone_number` E.164 unique; `email_verified_at`, `phone_verified_at`; `password_set`;
  `display_name`; `CHECK (email IS NOT NULL OR phone_number IS NOT NULL)`. `is_verified` của
  fastapi-users đúng khi một trong hai địa chỉ đã xác minh. `is_superuser` là cờ superadmin.
  `text_quota_bytes`, `collection_quota` ghi đè hạn mức (mục 4.4).
- `one_time_codes`: `purpose` (`verify_email`, `reset_password`, `change_email`, `phone_login`,
  `change_phone`), `channel`, `destination`, `user_id` NULL được, `code_hash`, `expires_at`, `attempts`,
  `consumed_at`; index `(purpose, destination, created_at)`.
- `rate_limit_buckets`: một dòng mỗi `key` (khoá chính), cửa sổ mở ở lần đầu của key (migration 0015),
  tăng bằng `INSERT ... ON CONFLICT DO UPDATE`.
- `access_tokens`: thêm `user_agent`, `ip_address`, `last_used_at`.

Giới hạn: gửi mã tới một địa chỉ 5 lần mỗi giờ, cách nhau tối thiểu 60 giây; từ một IP 20 lần mỗi giờ
(`PHARMA_AUTH__CODE_SENDS_PER_IP_PER_HOUR`; stack demo local đặt 1000 vì mọi tài khoản demo gửi từ cùng một máy);
đăng nhập sai 10 lần trong 15 phút theo tài khoản và theo IP (`PHARMA_AUTH__LOGIN_FAILURES_PER_WINDOW`; stack demo
đặt 1000). Vượt thì `429 RATE_LIMITED` kèm
`Retry-After`; nút "Gửi lại" ở frontend đếm ngược theo đúng số giây đó.

IP của khách: chỉ tin `X-Forwarded-For` khi request đi qua proxy của chính frontend (header secret
`API_PROXY_SECRET` khớp `PHARMA_API__PROXY_SECRET`), với `PHARMA_API__TRUSTED_PROXY_HOPS=1` trên Vercel. Stack
`compose.yaml` đặt `PHARMA_API__TRUSTED_PROXY_HOPS=1` cho nginx, không cần secret: backend không mở cổng ra ngoài nên
mọi request đều qua nginx, và backend đọc entry phải nhất do nginx thêm, nên khách không giả được IP.

### 2.4 Thành phần

`domain/account` (models, `phone`, `codes`, `passwords`, ports), `application/account` (`AccountService`,
`AccountPolicy`, `AccountView`, nội dung thư hai ngôn ngữ), `infrastructure/notifications`
(email, sms, factory), `infrastructure/auth/users.py` (`UserManager` ghi đè: chặn email chưa xác minh,
giới hạn đăng nhập sai, quy tắc liên kết Google; phiên có theo dõi), adapter Postgres cho tài khoản,
mã, giới hạn, phiên. Router `api/routers/account.py` phục vụ luồng OTP, `/users/me` (trả `AccountView`
vì `UserRead` của fastapi-users không cho email NULL) và cài đặt tài khoản.

`AccountView` gồm `email`, `phone_number` (NULL được), `email_verified`, `phone_verified`,
`password_set`, `google_linked`, `is_superadmin`, `memberships`, `phone_sign_in_enabled`,
`google_sign_in_enabled`. `/api/v1/health` cũng báo hai cờ `*_sign_in_enabled` để trang công khai biết
mà không cần đăng nhập.

## 3. Tổ chức và phân quyền

### 3.1 Quyết định

| Chủ đề | Quyết định |
| --- | --- |
| Ai đặt mức công khai | Chỉ superadmin. Nội dung công khai vào câu trả lời của mọi người, với dữ liệu thuốc phải có người kiểm soát |
| Owner | Nhiều owner được, luôn còn ít nhất một (`LAST_OWNER`). Người tạo là owner đầu tiên |
| Ai mời | Mọi thành viên. Lời mời của owner, editor gửi thư ngay; của member chờ owner hoặc editor duyệt rồi thư mới đi |
| Vai trò qua lời mời | owner mời mọi vai trò; editor mời editor hoặc member; member chỉ mời member |
| Lời mời | Hạn 7 ngày từ lúc gửi thư. Token chỉ lưu sha256. Chỉ tài khoản có email **đã xác minh** trùng email được mời mới nhận được. Mỗi tổ chức tối đa một lời mời đang mở cho một email. Lời mời thuộc tổ chức, nên vẫn nhận được sau khi người mời rời đi |
| Nhật ký | Tổ chức: owner, editor xem toàn bộ, kể cả thao tác của superadmin; member không xem. Cá nhân: mỗi người xem sự kiện về tài khoản và collection riêng |
| Superadmin | Cấp, thu hồi chỉ bằng CLI trên server (`pharma-agent superadmin grant|revoke|list`). Đọc và ghi mọi dữ liệu. Đọc hội thoại người khác **không ghi nhật ký**; thao tác ghi vẫn vào nhật ký với `actor_was_superadmin`. Trang Chính sách quyền riêng tư nêu rõ điều này |
| Khoá tài khoản | `is_active = false`, xoá luôn mọi phiên |
| Xoá tổ chức | Gõ lại tên để xác nhận. Collection của tổ chức bị **xoá mềm** (`deleted_at`), không cascade, vì chunk đã được hội thoại trích dẫn phải còn để câu trả lời cũ giữ nguồn. Bảo trì hằng ngày gỡ index và retire release của chúng |
| Tính quyền khi tìm kiếm | Tính trong Postgres ở mỗi lượt hỏi rồi lọc Qdrant theo release. Không chép quyền vào payload Qdrant, không dùng Row-Level Security. Rời tổ chức có hiệu lực ngay lượt hỏi kế tiếp |
| Phạm vi chat | Mặc định mọi collection người dùng thấy; thu hẹp theo từng hội thoại (`conversations.collection_ids`, NULL là tất cả, `{}` không hợp lệ). Phạm vi rỗng thì trả lời rằng không có nguồn, không gọi Qdrant |
| `formulary` | Collection công khai của hệ thống, chỉ nạp bằng CLI |

### 3.2 Bảng quyền

Cài trong `domain/access/policy.py` (hàm thuần, superadmin qua mọi kiểm tra về dữ liệu; rời tổ chức
và quy tắc chờ duyệt chỉ áp cho superadmin qua thành viên thật).

| Hành động | owner | editor | member | người ngoài | superadmin |
| --- | --- | --- | --- | --- | --- |
| Thấy tổ chức, thành viên | ✓ | ✓ | ✓ | | ✓ |
| Tìm, chat trên collection mức "trong tổ chức" | ✓ | ✓ | ✓ | | ✓ |
| Thấy collection riêng tư của tổ chức (bản nháp) | ✓ | ✓ | | | ✓ |
| Tạo, đổi tên, xoá collection; soạn nội dung; xuất bản | ✓ | ✓ | | | ✓ |
| Đổi riêng tư ↔ trong tổ chức | ✓ | ✓ | | | ✓ |
| Đặt, bỏ mức công khai | | | | | ✓ |
| Mời, gửi ngay | ✓ | ✓ | | | ✓ |
| Mời, chờ duyệt | | | ✓ | | |
| Duyệt, từ chối lời mời | ✓ | ✓ | | | ✓ |
| Thu hồi, gửi lại lời mời | ✓ | ✓ | người mời | | ✓ |
| Đổi vai trò, xoá thành viên | ✓ | | | | ✓ |
| Đổi tên, xoá tổ chức | ✓ | | | | ✓ |
| Xem nhật ký tổ chức | ✓ | ✓ | | | ✓ |
| Tự rời | ✓ khi còn owner khác | ✓ | ✓ | | |

Collection riêng tư của một người chỉ người đó và superadmin thấy. Collection công khai mọi người
đăng nhập thấy. Collection hệ thống luôn công khai, không ai đổi được mức hiển thị, và chỉ superadmin
sửa được; người khác nhận `403 SYSTEM_COLLECTION_READ_ONLY`.

### 3.3 Dữ liệu

- `organizations`: `id`, `name` (1–100), `text_quota_bytes`, `collection_quota` (NULL là mặc định),
  `created_at`, `updated_at`.
- `organization_members`: khoá chính `(organization_id, user_id)`, `role`, `joined_at`; xoá theo tổ chức
  hoặc người dùng.
- `organization_invitations`: `email` chuẩn hoá, `role`, `invited_by`, `status` (`pending_approval`,
  `sent`, `accepted`, `declined`, `rejected`, `revoked`, `expired`), `token_hash` unique, `expires_at`,
  `decided_by`, `decided_at`. Unique index một phần: một lời mời `pending_approval` hoặc `sent` mỗi
  `(organization_id, email)`. Quá hạn được coi là `expired` khi đọc.
- `audit_events`: chỉ ghi thêm, ghi cùng transaction với thay đổi (port `Transaction` dùng chung).
  Cột `actor_user_id`, `actor_was_superadmin`, `action`, `organization_id`, `subject_user_id`,
  `collection_id`, `details` JSON. Action trong `domain/audit/models.py`: tổ chức, thành viên, lời mời,
  collection (tạo, đổi tên, xoá, đổi mức hiển thị, xuất bản, quay lại bản trước), tài liệu, thuật ngữ,
  tên gọi dân gian, khoá và mở tài khoản, đổi hạn mức.
- `corpus.collections`: `owner_user_id` hoặc `owner_organization_id` (không cùng có giá trị; cả hai
  NULL là hệ thống), `visibility` (`private`, `organization`, `public`; `organization` chỉ khi chủ là tổ
  chức; hệ thống luôn `public`), `deleted_at`. `key` duy nhất toàn hệ thống; collection người dùng tạo
  có key `u-<8 hex>` hoặc `o-<8 hex>`, người dùng chỉ đặt `title`.

Migration: 0017 (tổ chức, lời mời, nhật ký, hạn mức), 0018 (chủ sở hữu collection, phạm vi hội thoại),
0019 (xoá mềm collection, bỏ FK cascade từ tổ chức).

### 3.4 Lỗi

Tài nguyên không được thấy trả **404**, không lộ sự tồn tại. Thấy nhưng thiếu quyền trả
**403 `FORBIDDEN_ROLE`**. Mã riêng: `LAST_OWNER`, `ALREADY_MEMBER`, `INVITATION_ALREADY_OPEN`,
`INVITATION_EXPIRED`, `INVITATION_EMAIL_MISMATCH`, `INVITATION_NOT_FOUND`, `INVITATION_NOT_PENDING`
(nhận lần hai), `ORGANIZATION_NAME_INVALID`. Gửi thư lời mời có rate limit theo người mời và theo địa
chỉ nhận, `429` kèm `Retry-After`.

## 4. Tự nạp nội dung

### 4.1 Luồng

1. Owner hoặc editor tạo collection (mặc định riêng tư).
2. Soạn tài liệu trong Tiptap (tiêu đề các cấp, đậm, nghiêng, danh sách, bảng) cùng tiêu đề, loại tài
   liệu, nguồn; hoặc tải lên `.md`, `.markdown`, `.txt` (UTF-8, tối đa 1 MB), nội dung mở trong trình
   soạn thảo để xem lại trước khi lưu. Không nhận `.docx`, PDF.
3. Lưu ghi Markdown vào `source_documents`. Thuật ngữ và tên gọi dân gian là hai bảng thêm, sửa, xoá
   dòng; `section_keys` của tên gọi dân gian chọn từ danh sách mục (`GET .../sections`).
4. **Xuất bản**: kiểm tra quyền và hạn mức, tạo `ingest_jobs`, giao cho `JobDispatcher`. Job dựng
   `KnowledgeBundle` bằng `build_bundle` (hàm thuần trong `domain/corpus/authoring.py`: chia Markdown
   theo tiêu đề ngoài code fence, đoạn văn và bảng thành block riêng, key mục xác định từ key tài liệu
   và đường dẫn tiêu đề) rồi chạy `import_bundle` với `publish=True`. Nội dung không đổi cho cùng
   `bundle_digest`, không tạo release mới.
5. Giao diện poll job và hiện tiến độ theo bước (`bundle`, `chunk`, `embed`, `index`, `publish`).
6. **Quay lại bản trước** dùng `rollback` sẵn có (`NO_EARLIER_RELEASE` khi không có bản trước).

Collection hệ thống không có `source_documents`; giao diện hiện ở dạng chỉ đọc.

### 4.2 Job

- Port `JobDispatcher.enqueue(job_id)`, hai adapter chọn bằng `PHARMA_JOBS__DISPATCHER`:
  `inline` (production) chạy job ngay trong request xuất bản rồi mới trả lời, vì Vercel Function có
  thể bị đóng băng sau khi trả lời; `inprocess` (local, test) chạy trong task asyncio sau khi trả lời.
- Tối đa `max_attempts` (3) lần chạy, mọi lần trong cùng request nên `maxDuration` 300 giây của Vercel
  giới hạn tất cả. Job tự ghi lỗi; hết lần thì `failed` kèm lý do ngắn.
- Một collection chỉ có một job `queued` hoặc `running` (`PUBLISH_IN_PROGRESS`, 409). Job quá
  `stale_after_seconds` (330, dài hơn `maxDuration`) được coi là treo và lần xuất bản sau tiếp quản.
- Job idempotent: chạy lại tiếp tục release `building`, chunk đã có trong Qdrant được bỏ qua.

### 4.3 Dữ liệu (schema `corpus`, migration 0020)

`source_documents` (`key` slug duy nhất trong collection, `title`, `kind`, `source_title`, `source_url`,
`markdown`, `char_count`, người và lúc tạo, sửa), `glossary_entries` (`term` duy nhất trong collection,
`case_sensitive`, mở rộng tiếng Việt, tiếng Anh, `aliases`, `category`), `colloquial_mappings` (`key`,
`aliases`, `visual_sign`, `product_names`, `section_keys`), `ingest_jobs` (`status` `queued`, `running`,
`ready`, `failed`; `step`; `progress`; `error`; `attempts`; `release_id`).

Xoá collection: ẩn ngay, xoá nội dung soạn (để hạn mức không còn tính và kho không phình), retire
release và gỡ point khỏi Qdrant; dòng mà hội thoại trích dẫn được giữ.

### 4.4 Hạn mức

Mặc định trong `PHARMA_QUOTAS__*`: 200.000 ký tự mỗi tài liệu, 100 tài liệu mỗi collection,
1.000.000 byte chữ và 5 collection mỗi người dùng, 5.000.000 byte chữ và 20 collection mỗi tổ chức.
Superadmin ghi đè cho từng người dùng, tổ chức. Mức đã dùng là tổng `char_count` trong các collection
của chủ đó. Vượt thì `422 QUOTA_EXCEEDED` kèm mức đã dùng và hạn mức; `GET /collections/quota` cho
thanh "đã dùng x / y". Lý do chọn các mức: Qdrant Cloud Free 1 GB là nút thắt đầu tiên.

## 5. API

Tiền tố `/api/v1`, lỗi `application/problem+json`. Mọi route cần đăng nhập, trừ luồng auth công khai,
`GET /invitations/{token}`, `/health` và `/maintenance/daily` (cần `CRON_SECRET`).

| Nhóm | Route |
| --- | --- |
| Auth | `POST /auth/register`, `POST /auth/cookie/login`, `/auth/cookie/logout`, `POST /auth/email/verify/request`, `/auth/email/verify`, `POST /auth/password/forgot`, `/auth/password/reset`, `POST /auth/phone/request`, `/auth/phone/login`, `/auth/google/*`, `/auth/google/associate/*` |
| Tài khoản | `GET/PATCH /users/me`, `POST /account/email`, `/account/email/confirm`, `POST /account/phone`, `/account/phone/confirm`, `PUT /account/password`, `DELETE /account/oauth/google`, `GET/DELETE /account/sessions`, `DELETE /account/sessions/{id}`, `GET /account/audit` |
| Tổ chức | `GET/POST /organizations`, `GET/PATCH/DELETE /organizations/{id}`, `GET /organizations/{id}/members`, `PATCH/DELETE /organizations/{id}/members/{user_id}`, `POST /organizations/{id}/leave`, `GET /organizations/{id}/audit` |
| Lời mời | `GET/POST /organizations/{id}/invitations`, `POST .../{invitation_id}/approve`, `/reject`, `/revoke`, `/resend`; `GET /invitations/{token}`, `POST /invitations/{token}/accept`, `/decline` |
| Collection | `GET/POST /collections`, `GET /collections/quota`, `GET/PATCH/DELETE /collections/{id}`, `GET /collections/{id}/releases`, `POST /collections/{id}/publish`, `POST /collections/{id}/rollback`, `GET /ingest-jobs/{id}` |
| Nội dung | `GET/POST /collections/{id}/documents`, `POST .../documents/upload` (trả Markdown, chưa lưu), `GET/PUT/DELETE .../documents/{doc_id}`, `GET/PUT .../glossary`, `GET/PUT .../colloquial`, `GET .../sections` |
| Hội thoại | `PATCH /conversations/{id}` nhận `collection_ids`; request chat nhận `collection_ids` cho tin nhắn đầu của hội thoại mới |
| Admin | `GET /admin/users`, `PATCH /admin/users/{id}` (khoá, mở, hạn mức), `GET /admin/organizations`, `PATCH /admin/organizations/{id}` (hạn mức), `GET /admin/collections`, `GET /admin/ingest-jobs`, `GET /admin/users/{id}/conversations`, `GET /admin/conversations/{id}`, `GET /admin/audit` |
| Bảo trì | `GET /maintenance/daily` (không có trong OpenAPI): dọn phiên, mã, bucket hết hạn và gỡ collection đã xoá mềm, ngân sách 180 giây |

## 6. Frontend

Feature `auth`, `settings`, `organizations`, `collections`, `audit`, `admin`, `legal` (quy tắc chung của
frontend ở spec `frontend`). Route:

- Công khai: `/login`, `/register`, `/forgot-password`, `/auth/google/callback`,
  `/auth/google/link-callback`, `/invitations/:token`, `/privacy`, `/terms` (và bản `/en/...`,
  prerender).
- Sau đăng nhập: `/settings` (mục Tài khoản: email, số điện thoại, mật khẩu, Google, phiên),
  `/activity`, `/organizations`, `/organizations/:organizationId/:tab?` (Thành viên, Lời mời,
  Collection, Nhật ký; tab không có quyền thì ẩn), `/collections`, `/collections/:collectionId/:tab?`
  (Tài liệu, Thuật ngữ, Tên gọi dân gian, Bản phát hành, nút Xuất bản, hộp tiến độ),
  `/collections/:collectionId/documents/:documentId` (`new` để tạo), `/admin/:section?` (người không
  phải superadmin nhận 404).
- Ô nhập mã `input-otp` (dán cả mã, nút gửi lại đếm ngược theo `Retry-After`), ô số điện thoại
  `libphonenumber-js` mặc định `+84`. Tab số điện thoại ẩn khi `phone_sign_in_enabled` là false.
- Trang nhận lời mời hiện tên tổ chức, người mời, vai trò; chưa đăng nhập thì có Đăng nhập, Đăng ký kèm
  `next=`; sai email thì báo lời mời dành cho email nào, che bớt ký tự.
- Chat có nút **Nguồn** (combobox nhiều lựa chọn, nhóm Công khai, từng tổ chức, Của tôi, cùng "Tất cả
  nguồn tôi được thấy"), lưu optimistic.
- Trang quản trị theo block `dashboard-01`: thẻ số liệu (gồm số point Qdrant để biết sớm khi đầy),
  bảng Người dùng, Tổ chức, Collection, Job, Nhật ký. Thao tác của superadmin có nhãn "Quản trị viên".
- Mọi chuỗi có tiếng Việt và tiếng Anh; mã lỗi backend có khoá trong `errors.json`.

## 7. Triển khai và ra mắt

| Thành phần | Nơi chạy |
| --- | --- |
| Frontend SSR | Vercel project `vipharmind` (Root Directory `frontend`), `https://vipharmind.vercel.app`. Không dùng gói `@vercel/react-router` (preset làm hỏng build với React Router 8). Route `api/*` của React Router chuyển tiếp sang backend để cookie là first-party, kèm `API_PROXY_SECRET`. Cron trong `frontend/vercel.json` gọi `/api/v1/health` mỗi ngày để cluster Qdrant Free không tự tạm dừng |
| Backend | Vercel Function `vipharmind-api`, region `sin1`, Large Functions (đóng gói thư viện lúc build), `maxDuration` 300 giây (`backend/vercel.json`), khởi động lạnh khoảng 10 giây. Cron gọi `/api/v1/maintenance/daily` với `CRON_SECRET` |
| Postgres | Neon miễn phí, Singapore, DSN có pooler. DB mới dựng bằng migration |
| Vector | Qdrant Cloud Free (1 GB RAM), vector dày trên đĩa (`PHARMA_QDRANT__ON_DISK_VECTORS=true`) |
| Model | OpenRouter: Qwen3.5-9B tắt suy luận cho mọi role LLM, Qwen3-Embedding-8B 4096 chiều, Qwen3-Reranker-8B (bản Qwen3 reranker duy nhất OpenRouter phục vụ) qua `native_rerank` |
| Thư | Resend. Trước khi xác minh domain chỉ gửi được tới email chủ tài khoản Resend |
| SMS | Tắt (`PHARMA_SMS__PROVIDER=none`) |
| Google OAuth | Client Web trong project Google Cloud dùng chung `andimus`; tuỳ chọn |
| Secrets | Biến môi trường Vercel. Backend đẩy từ `backend/.env.production` bằng `devops/vercel/sync_env.py` (đẩy `PHARMA_*` rồi redeploy) |

Deploy: Vercel build cả hai project khi `main` đổi. Vercel không chạy migration, nên chạy
`uv run pharma-agent --env-file .env.production migrate` từ máy mình trước khi push. Không deploy backend
bằng `vercel deploy` từ máy vì CLI tải cả file `.env`. Corpus `formulary` nạp lần đầu từ máy mình bằng
`pharma-agent --env-file .env.production corpus import ... --publish`; corpus phải được nạp bằng đúng
model embedding mà backend production dùng. CLI nhận `--env-file` chung cho mọi lệnh.

Các bước chỉ chủ tài khoản làm được, trạng thái từng bước và đường scale nằm ở
[`docs/launch-checklist.md`](../../launch-checklist.md). Spec này không chép lại checklist.

Đường scale tóm tắt: Vercel Hobby chỉ hợp lệ khi phi thương mại (lên Pro), Qdrant 1 GB đầy trước Neon
0,5 GB, Resend Free 100 thư mỗi ngày. Đường lùi khỏi Vercel: Dockerfile của frontend và backend vẫn còn,
backend không giữ trạng thái.

## 8. Kiểm thử

| Lớp | Nội dung chính |
| --- | --- |
| domain | Bảng quyền phủ mọi ô; chuẩn hoá số điện thoại; `build_bundle` (không tiêu đề, chỉ có bảng, key ổn định, digest không đổi) |
| application (fake in-memory) | Mã hết hạn, đã dùng, sai 5 lần, mã mới huỷ mã cũ; quên mật khẩu không lộ tài khoản; cách đăng nhập cuối cùng; luôn còn một owner kể cả hai owner cùng rời; vòng đời lời mời; mỗi thao tác ghi sinh đúng sự kiện, thất bại không sinh; hạn mức; xuất bản song song chỉ tạo một job |
| Postgres | Migration lên, xuống; ràng buộc chủ sở hữu, mức hiển thị, email hoặc số điện thoại; nhật ký cùng transaction |
| API | Mỗi luồng qua HTTP, đọc mã từ hộp thư giả; không thấy 404, thiếu quyền 403; người ngoài gọi route tổ chức đều 404 |
| retrieval (Qdrant thật) | A không nhận chunk từ collection riêng tư của B; rời tổ chức thì lượt sau không còn thấy; thu hẹp phạm vi chỉ trả collection đã chọn |
| frontend | Vitest browser + MSW cho form, nút Nguồn, ẩn tab theo vai trò, trình soạn Markdown, trang admin |
| e2e (Playwright) | `auth`, `account`, `settings`, `organizations`, `collections`, `admin`, `public`; server e2e dùng hộp thư trong bộ nhớ |

## 9. Ngoài phạm vi

- Xác thực hai lớp, đăng nhập GitHub, CAPTCHA cho bước gửi SMS.
- Nhà cung cấp SMS thật (bật lại bằng cấu hình khi có).
- Nhận `.docx`, PDF.
- Chuyển collection giữa chủ sở hữu; chia sẻ collection riêng tư cho từng người; quy trình xin công
  khai (superadmin tự đặt).
- Smoke test sau deploy trong GitHub Actions: repo không còn workflow CI (xem Lịch sử quyết định).

## 10. Lịch sử quyết định

Nguồn đọc bằng `git -C <repo> show <sha>:<path>`. Spec, plan đã xoá ở `2f0bc2e`; bản cuối nằm ở commit
cha `d71e192`.

| Ngày | Quyết định | Thay cho | Lý do | Nguồn |
| --- | --- | --- | --- | --- |
| 2026-10-10 | Luồng tài khoản OTP 6 số trên fastapi-users, ba cách đăng nhập một tài khoản | Xác minh bằng link của fastapi-users; `associate_by_email=True` liên kết cả email chưa xác minh | Link dài, khó dùng trên điện thoại; liên kết email chưa xác minh cho phép chiếm tài khoản | `d71e192:docs/superpowers/specs/2026-10-10-account-flows-design.md` |
| 2026-10-10 | Plan account-flows (17 task, migration 0013) đã chạy xong, bỏ | | Kết quả đã nằm trong mã (commit `7b9a88d`…`81d75d5`) | `d71e192:docs/superpowers/plans/2026-10-10-account-flows.md` |
| 2026-10-10 | `/users/me` trả `AccountView` từ router riêng; bỏ route admin `/users/{id}` của fastapi-users | `UserRead` của fastapi-users | `UserRead` không cho email NULL | plan account-flows, mục "Điều chỉnh so với spec" |
| 2026-10-10 | Xác minh email cần mật khẩu tài khoản | Chỉ cần mã | Chủ hộp thư chiếm tài khoản người khác đăng ký bằng địa chỉ của họ | commit `81d75d5` |
| 2026-10-10 | Gộp tổ chức (mảng 3), tự nạp nội dung (mảng 4), ra mắt (mảng 5) vào một spec | Spec riêng cho tổ chức và phân quyền | Ba phần dùng chung dữ liệu collection và hạn mức | `c378004:docs/superpowers/specs/2026-10-10-organizations-access-design.md`; commit `06d4b6e` |
| 2026-10-10 | Tách migration thành 0016–0020 | Một migration 0016 | Mỗi lớp có commit xanh với test schema khớp model | `d71e192:docs/superpowers/plans/2026-10-10-product-launch.md` |
| 2026-10-10 | Plan product-launch (lớp A–G) đã chạy xong, bỏ | | Đánh dấu xong ở `dc527c3`; mã có đủ | `d71e192:docs/superpowers/plans/2026-10-10-product-launch.md` |
| 2026-10-10 | Giao diện chỉ dùng shadcn core và block `dashboard-01` | Widget tự dựng, AI Elements | Một nguồn component; chi tiết ở spec frontend | `d71e192:docs/superpowers/specs/2026-10-10-product-launch-design.md` §8.1 |
| 2026-10-11 | Xoá mềm collection; tổ chức không cascade vào collection | Xoá cascade theo tổ chức | Chunk đã trích dẫn phải còn | migration `0019_collection_soft_delete.py`; commit `46938a2` |
| 2026-10-11 | Embedding production Qwen3-Embedding-8B 4096 chiều, vector trên đĩa | Qwen3-Embedding-4B 2560 chiều (bản đã đánh giá) | Chủ dự án chọn; Qdrant Free chỉ 1 GB RAM | commit `d621b01` |
| 2026-10-11 → 10-12 | Backend chạy trên Vercel Function | Cloud Run + Cloud Tasks (10-10), rồi Render Free (10-11) | Google Cloud bắt nạp trước; Render Free ngủ sau 15 phút và chặn SMTP; Vercel miễn phí, không ngủ | commit `2fbc098`, `b43d1fc`, `a917d83`, `c2fb2ad` |
| 2026-10-11 | Bỏ workflow GitHub Actions deploy Cloud Run và smoke test | `.github/workflows/deploy-backend.yml` | Rời Cloud Run; Vercel tự build khi push | thêm ở `2fbc098`, xoá ở `b43d1fc` |
| 2026-10-12 | Resend là nhà cung cấp thư duy nhất | SMTP (aiosmtplib), rồi Gmail API | Render chặn cổng SMTP; Gmail API bị bỏ sau một ngày, Resend gửi qua HTTPS | commit `0a6b1f0`, `a43716f`, `c6a4cf3` |
| 2026-10-13 | Bỏ endpoint `/internal/ingest-jobs/{id}/run`, token nội bộ, JWT bearer login; thêm cron bảo trì hằng ngày; `stale_after_seconds` thay `dispatch_deadline_seconds` | Cloud Tasks gọi endpoint nội bộ; khoá collection 25 phút khi job bị cắt | Không còn Cloud Tasks; JWT bỏ qua thu hồi phiên | commit `99981a0` |
| 2026-10-16 | Model production đi qua OpenRouter; reranker Qwen3-Reranker-8B | DeepInfra (LLM, embedding, adapter rerank `deepinfra`), Qwen3-Reranker-4B | Gom về một gateway; OpenRouter chỉ phục vụ bản 8B | commit `3eb0eb4`, `8318bf7` |

## 11. Liên kết

- `2026-11-15-backend-agent-api-design.md`: chat, `ReleaseScope`, API cho web nói chung.
- `2026-11-15-corpus-data-pipeline-design.md`: `import_bundle`, release, chunk, embedding, migration
  0016 và 0021.
- `2026-11-15-frontend-design.md`: quy tắc shadcn, i18n, cấu trúc feature.
- `2026-11-15-architecture-rules-design.md`: luật import một chiều.
- `docs/launch-checklist.md`: việc chủ tài khoản làm và trạng thái production.
