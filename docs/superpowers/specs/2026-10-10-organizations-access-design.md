# Thiết kế tổ chức và phân quyền (mảng 3)

Ngày: 2026-10-10. Trạng thái: đã duyệt qua brainstorming (bốn phần), chờ người dùng duyệt spec.

Mảng 3 trong lộ trình đưa ViPharMind lên production. Mảng này dùng lại hạ tầng của mảng 2: gửi email, rate limit trong Postgres, cookie session. Mảng 4 (tự nạp dữ liệu) sẽ nạp nội dung vào các collection mà mảng này tạo ra và phân quyền.

## 1. Mục tiêu

1. Người dùng tự tạo **tổ chức**, mời người khác vào qua email, với ba vai trò **owner**, **editor**, **member**.
2. Mỗi collection thuộc **một người dùng**, **một tổ chức**, hoặc **hệ thống**. Collection có ba mức hiển thị: **riêng tư**, **trong tổ chức**, **công khai**.
3. Chat mặc định tìm trong **mọi collection người dùng được thấy**. Người dùng có thể thu hẹp phạm vi theo từng hội thoại.
4. **Superadmin** đọc và ghi được mọi dữ liệu, có trang quản trị riêng.
5. Mọi thao tác thay đổi quyền và dữ liệu được ghi vào **nhật ký** mà người liên quan xem được.

## 2. Quyết định đã chốt

| Chủ đề | Quyết định |
| --- | --- |
| Ai đặt collection công khai | **Chỉ superadmin.** Người dùng và tổ chức chỉ dùng mức riêng tư hoặc trong tổ chức. Nội dung công khai xuất hiện trong câu trả lời của mọi người, nên với dữ liệu thuốc phải có người kiểm soát |
| Vai trò trong tổ chức | Như bảng quyền ở mục 3. Một tổ chức có thể có nhiều owner và luôn có ít nhất một owner. Người tạo tổ chức là owner đầu tiên |
| Ai mời được | **Mọi thành viên.** Lời mời của owner hoặc editor gửi email ngay. Lời mời của member chờ owner hoặc editor duyệt, được duyệt thì email mới đi |
| Vai trò được cấp qua lời mời | owner mời với mọi vai trò. editor mời với vai trò member hoặc editor. member chỉ mời với vai trò member |
| Lời mời | Hạn 7 ngày. Chỉ người dùng có **email đã xác minh** trùng email được mời mới nhận được. Mỗi tổ chức chỉ có tối đa một lời mời đang mở cho một email |
| Nhật ký tổ chức | owner và editor xem toàn bộ, kể cả thao tác của người khác và của superadmin. member không xem |
| Nhật ký cá nhân | Mỗi người xem sự kiện về tài khoản và collection riêng của mình |
| Thu hẹp phạm vi chat | Chọn từng collection cho từng hội thoại, đổi được bất cứ lúc nào. Quyền được kiểm tra lại ở mỗi lượt hỏi |
| Superadmin và hội thoại | Superadmin xem và quản lý hội thoại của mọi người như dữ liệu khác. **Không ghi nhật ký khi đọc.** Thao tác ghi của superadmin trên collection và tổ chức vẫn vào nhật ký |
| Cấp quyền superadmin | Chỉ bằng lệnh CLI trên server. Không có nút cấp quyền trên giao diện |
| Xoá tổ chức | Xoá luôn các collection của tổ chức. Phải gõ lại tên tổ chức để xác nhận |
| Tính quyền khi tìm kiếm | Tính trong Postgres ở mỗi lượt hỏi, rồi lọc Qdrant theo release (cách A). Không chép quyền vào payload của Qdrant, không dùng Row-Level Security |
| Dữ liệu `formulary` hiện có | Thành collection công khai của hệ thống |

## 3. Bảng quyền

| Hành động | owner | editor | member | người ngoài | superadmin |
| --- | --- | --- | --- | --- | --- |
| Thấy tổ chức, danh sách thành viên | ✓ | ✓ | ✓ | | ✓ |
| Tìm và chat trên collection mức "trong tổ chức" | ✓ | ✓ | ✓ | | ✓ |
| Tạo, đổi tên, xoá collection của tổ chức | ✓ | ✓ | | | ✓ |
| Đổi mức hiển thị riêng tư ↔ trong tổ chức | ✓ | ✓ | | | ✓ |
| Đặt hoặc bỏ mức công khai | | | | | ✓ |
| Mời, gửi ngay | ✓ | ✓ | | | ✓ |
| Mời, chờ duyệt | | | ✓ | | |
| Duyệt hoặc từ chối lời mời chờ duyệt | ✓ | ✓ | | | ✓ |
| Thu hồi hoặc gửi lại lời mời | ✓ | ✓ | người mời | | ✓ |
| Đổi vai trò, xoá thành viên | ✓ | | | | ✓ |
| Đổi tên, xoá tổ chức | ✓ | | | | ✓ |
| Xem nhật ký tổ chức | ✓ | ✓ | | | ✓ |
| Tự rời tổ chức | ✓ khi còn owner khác | ✓ | ✓ | | |

Collection riêng tư của một người dùng chỉ người đó và superadmin thấy. Collection riêng tư của một tổ chức chỉ owner, editor của tổ chức đó và superadmin thấy, dùng như bản nháp trước khi chuyển sang mức trong tổ chức. Collection công khai ai đăng nhập cũng thấy.

## 4. Mô hình dữ liệu

### 4.1 Bảng `organizations`

`id`, `name` (1–100 ký tự), `created_at`, `updated_at`.

### 4.2 Bảng `organization_members`

`organization_id`, `user_id`, `role` (`owner`, `editor`, `member`), `joined_at`. Khoá chính là (`organization_id`, `user_id`). Xoá tổ chức hoặc xoá người dùng thì dòng thành viên bị xoá theo.

### 4.3 Bảng `organization_invitations`

| Cột | Ý nghĩa |
| --- | --- |
| `id` | uuid |
| `organization_id` | tổ chức, xoá theo tổ chức |
| `email` | đã chuẩn hoá bằng `normalize_email` |
| `role` | vai trò sẽ cấp |
| `invited_by` | người mời |
| `status` | `pending_approval`, `sent`, `accepted`, `declined`, `rejected`, `revoked`, `expired` |
| `token_hash` | sha256 của token gửi trong email. Token gốc không lưu |
| `created_at`, `expires_at` | hạn 7 ngày tính từ lúc gửi email |
| `decided_by`, `decided_at` | ai duyệt, từ chối, thu hồi, hoặc nhận lời mời, và lúc nào |

Một unique index một phần bảo đảm mỗi (`organization_id`, `email`) chỉ có một lời mời ở trạng thái `pending_approval` hoặc `sent`. Lời mời quá hạn được coi là `expired` khi đọc, và lệnh dọn dẹp định kỳ cập nhật trạng thái.

### 4.4 Bảng `audit_events`

| Cột | Ý nghĩa |
| --- | --- |
| `id`, `occurred_at` | |
| `actor_user_id` | người thực hiện, có thể rỗng nếu tài khoản đã bị xoá |
| `actor_was_superadmin` | thao tác được thực hiện bằng quyền superadmin |
| `action` | ví dụ `organization.created`, `member.role_changed`, `invitation.approved`, `collection.visibility_changed` |
| `organization_id`, `subject_user_id`, `collection_id` | đối tượng liên quan, có thể rỗng |
| `details` | JSON, ví dụ vai trò cũ và mới, tên cũ và mới |

Bảng chỉ ghi thêm. Có index theo (`organization_id`, `occurred_at`) và (`subject_user_id`, `occurred_at`). Sự kiện được ghi trong cùng transaction với thay đổi.

### 4.5 Sửa `corpus.collections`

1. Thêm `owner_organization_id`, xoá theo tổ chức.
2. Ràng buộc: `owner_user_id` và `owner_organization_id` không cùng có giá trị. Cả hai rỗng nghĩa là collection của hệ thống.
3. `visibility` thêm giá trị `organization`.
4. Ràng buộc nhất quán: `organization` chỉ hợp lệ khi chủ là tổ chức. Collection của hệ thống luôn là `public`.
5. `key` vẫn duy nhất toàn hệ thống. Collection do người dùng tạo có key sinh tự động, người dùng chỉ đặt `title`.

### 4.6 Sửa `conversations`

Thêm `collection_ids uuid[]`, có thể rỗng. Rỗng (NULL) nghĩa là mọi collection người dùng được thấy. Danh sách rỗng `{}` không hợp lệ.

### 4.7 Migration 0016

Tạo các bảng ở mục 4.1–4.4 và thêm cột, ràng buộc ở mục 4.5–4.6. Collection hiện có `owner_user_id` giữ chủ cá nhân và mức hiển thị hiện tại. Collection không có chủ thành collection hệ thống `public`.

## 5. Thành phần backend

| Tầng | Thành phần | Trách nhiệm |
| --- | --- | --- |
| domain | `access` | `Role`, `Actor(user_id, is_superadmin, memberships)`, các hàm quyết định quyền đúng bảng ở mục 3. Không phụ thuộc framework |
| domain | `organizations` | Model tổ chức, thành viên, lời mời, trạng thái lời mời, port repository |
| domain | `audit` | `AuditEvent`, các hằng `action`, port `AuditLog` |
| application | `organizations` | Tổ chức, thành viên, lời mời, kiểm tra luôn còn một owner, gửi email lời mời qua `EmailSender` với rate limit của mảng 2 |
| application | `audit` | Đọc nhật ký tổ chức và nhật ký cá nhân, phân trang theo cursor như danh sách hội thoại |
| application | `corpus` (đã có) | Thêm tạo, đổi tên, xoá collection, đổi mức hiển thị, `visible_collections(actor)` |
| application | `chat` (đã có) | Trước mỗi lượt hỏi tính `phạm vi = visible ∩ collection_ids của hội thoại`, rồi lấy release hiện hành. Phạm vi rỗng thì trả lời rằng không có nguồn để tìm, không gọi Qdrant |
| application | `admin` | Liệt kê người dùng, tổ chức, collection. Khoá và mở tài khoản. Đọc hội thoại của người khác. Thao tác ghi đi qua chính các service ở trên với `Actor` là superadmin |
| infrastructure | repository Postgres | Cho các port mới. Một unit of work chung để thay đổi và sự kiện nhật ký cùng commit |
| infrastructure | retrieval | `CorpusReader.current_releases` nhận id collection thay vì key. Bỏ cấu hình `PHARMA_RETRIEVAL__COLLECTIONS` |
| api | routers mới | `organizations`, `invitations`, `collections`, `audit`, `admin` |
| cli | `superadmin grant/revoke <email>` | Cấp và thu hồi quyền superadmin |

Lệnh `corpus import` ở CLI vẫn nạp vào collection hệ thống như hiện tại. Nạp nội dung cho collection của người dùng và tổ chức thuộc mảng 4.

Khoá tài khoản (`is_active = false`) xoá luôn mọi phiên của người đó.

## 6. API

Mọi route cần đăng nhập, trừ xem trước lời mời.

| Nhóm | Route |
| --- | --- |
| Tổ chức | `GET/POST /organizations`, `GET/PATCH/DELETE /organizations/{id}` |
| Thành viên | `GET /organizations/{id}/members`, `PATCH/DELETE /organizations/{id}/members/{user_id}`, `POST /organizations/{id}/leave` |
| Lời mời trong tổ chức | `GET/POST /organizations/{id}/invitations`, `POST /organizations/{id}/invitations/{invitation_id}/approve`, `/reject`, `/revoke`, `/resend` |
| Người được mời | `GET /invitations/{token}` (công khai, xem trước), `POST /invitations/{token}/accept`, `POST /invitations/{token}/decline` |
| Collection | `GET /collections` (những gì tôi thấy, nhóm theo nguồn), `POST /collections`, `PATCH/DELETE /collections/{id}` |
| Hội thoại | `PATCH /conversations/{id}` thêm trường `collection_ids`. Request chat thêm `collection_ids` cho tin nhắn đầu tiên của hội thoại mới |
| Nhật ký | `GET /organizations/{id}/audit`, `GET /account/audit` |
| Admin | `GET /admin/users`, `PATCH /admin/users/{id}`, `GET /admin/organizations`, `GET /admin/collections`, `GET /admin/users/{id}/conversations`, `GET /admin/conversations/{id}`, `GET /admin/audit` |
| Tài khoản | `GET /users/me` trả thêm `is_superadmin` và `memberships` |

Lỗi:

1. Tài nguyên không được phép thấy trả **404**, để không lộ sự tồn tại của tổ chức hay collection.
2. Thấy được nhưng không đủ quyền trả **403** với mã `FORBIDDEN_ROLE`.
3. Mã riêng: `LAST_OWNER`, `ALREADY_MEMBER`, `INVITATION_EXPIRED`, `INVITATION_EMAIL_MISMATCH` (409), `INVITATION_NOT_FOUND`.
4. Gửi email lời mời dùng rate limit theo người mời và theo địa chỉ nhận, trả 429 với `Retry-After` như mảng 2.

## 7. Frontend

| Feature | Nội dung |
| --- | --- |
| `organizations` | Danh sách tổ chức, tạo tổ chức, trang chi tiết có tab Thành viên, Lời mời, Collection, Nhật ký. Tab không có quyền thì ẩn |
| `collections` | Danh sách collection, tạo, đổi tên, xoá, đổi mức hiển thị. Lựa chọn "Công khai" chỉ hiện với superadmin |
| `audit` | Component danh sách sự kiện dùng chung. Mỗi sự kiện là một câu dựng từ `action` và `details`. Thao tác của superadmin có nhãn "Quản trị viên" |
| `admin` | Người dùng (tìm, khoá, mở, xem hội thoại), Tổ chức, Collection, Nhật ký toàn hệ thống. Dùng lại component hiển thị tin nhắn của `chat` ở chế độ chỉ đọc, nên thêm hướng import `admin → chat` vào luật kiến trúc |

Route mới:

1. `/organizations`, `/organizations/:id/:tab?`, `/collections`, `/activity` trong layout đăng nhập.
2. `/admin/:section?` có guard. Người không phải superadmin nhận trang 404.
3. `/invitations/:token` công khai. Hiện tên tổ chức, người mời, vai trò. Chưa đăng nhập thì có nút Đăng nhập và Đăng ký kèm `next=` để quay lại. Đăng nhập sai email thì báo lời mời dành cho email nào, có che bớt ký tự.

Chat có nút **Nguồn** cạnh ô nhập. Popover chứa checkbox nhóm theo Công khai, từng tổ chức, Của tôi, cùng lựa chọn mặc định "Tất cả nguồn tôi được thấy". Khi đang thu hẹp, nút hiện số nguồn đã chọn.

Thanh điều hướng thêm Tổ chức, Collection, Hoạt động, và Quản trị (chỉ superadmin). Mọi chuỗi mới có tiếng Việt và tiếng Anh.

## 8. Kiểm thử

| Lớp | Nội dung |
| --- | --- |
| domain `access` | Test dạng bảng phủ mọi ô của bảng quyền ở mục 3 |
| application | Fake in-memory. Luôn còn một owner, kể cả khi hai owner cùng rời. Vòng đời lời mời: chờ duyệt, gửi, nhận, hết hạn, sai email, mời người đã là thành viên. Mỗi thao tác ghi sinh đúng sự kiện nhật ký, thao tác thất bại không sinh sự kiện |
| Postgres | Migration 0016 chuyển dữ liệu cũ đúng. Ràng buộc chủ sở hữu và mức hiển thị chặn dữ liệu sai. Nhật ký cùng transaction với thay đổi |
| API | Không thấy thì 404, thiếu quyền thì 403. Người ngoài gọi mọi route của một tổ chức đều nhận 404 |
| retrieval (Qdrant thật) | A không bao giờ nhận chunk từ collection riêng tư của B. Rời tổ chức thì câu hỏi kế tiếp không còn thấy collection của tổ chức. Thu hẹp phạm vi chỉ trả về collection đã chọn |
| kiến trúc | `test_layering` và `app/architecture.test.ts` thêm luật cho các feature mới |
| frontend | Vitest browser: popover Nguồn, ẩn hiện tab theo vai trò, trang nhận lời mời, trang admin |
| e2e | (1) Tạo tổ chức, mời qua email, người được mời đăng ký và nhận lời mời, thấy collection của tổ chức trong Nguồn. (2) member mời, owner duyệt, email được gửi. (3) Superadmin khoá tài khoản, người đó bị đăng xuất |

## 9. Rủi ro

1. Mỗi lượt hỏi thêm một truy vấn tính quyền. Đây là một câu SQL có index, nhỏ so với thời gian gọi LLM. Chưa cần cache.
2. Superadmin đọc hội thoại không ghi nhật ký. **Mảng 5 phải nêu rõ điều này trong chính sách quyền riêng tư trước khi ra mắt.**
3. Phạm vi lớn. Plan chia theo lớp: domain và dữ liệu, service, API, frontend, e2e. Mỗi lớp kết thúc bằng commit xanh.

## 10. Ngoài phạm vi

1. Nạp nội dung vào collection qua giao diện, hạn mức dung lượng (mảng 4).
2. Chuyển collection giữa các chủ sở hữu.
3. Chia sẻ một collection riêng tư cho từng người cụ thể.
4. Quy trình xin công khai collection. Superadmin tự đặt mức công khai khi cần.
