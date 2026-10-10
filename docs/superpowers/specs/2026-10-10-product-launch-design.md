# Thiết kế hoàn thiện sản phẩm và ra mắt (mảng 3, 4 và 5 gộp)

Ngày: 2026-10-10. Trạng thái: đã duyệt qua brainstorming, chờ người dùng duyệt spec.

Spec này gộp ba mảng còn lại của lộ trình: **tổ chức và phân quyền** (mảng 3), **tự nạp nội dung** (mảng 4) và **triển khai, ra mắt** (mảng 5). Nó dùng lại hạ tầng của mảng 2: gửi email, rate limit trong Postgres, cookie session, pipeline nạp corpus hiện có. Sau spec này sản phẩm chạy thật cho người dùng.

## 1. Mục tiêu

1. Người dùng tự tạo **tổ chức**, mời người khác vào qua email, với ba vai trò **owner**, **editor**, **member**.
2. Mỗi collection thuộc **một người dùng**, **một tổ chức**, hoặc **hệ thống**. Collection có ba mức hiển thị: **riêng tư**, **trong tổ chức**, **công khai**.
3. Người dùng **tự nạp nội dung**: soạn tài liệu trực tiếp hoặc tải lên, thêm bảng thuật ngữ và tên gọi dân gian, rồi xuất bản collection qua đúng pipeline hiện có, có hạn mức.
4. Chat mặc định tìm trong **mọi collection người dùng được thấy**. Người dùng có thể thu hẹp phạm vi theo từng hội thoại.
5. **Superadmin** đọc và ghi được mọi dữ liệu, có trang quản trị riêng.
6. Mọi thao tác thay đổi quyền và dữ liệu được ghi vào **nhật ký** mà người liên quan xem được.
7. Dữ liệu được **chuẩn hoá** giữa Postgres và Qdrant, mỗi dữ liệu nằm đúng một nơi, để vừa các gói miễn phí.
8. Sản phẩm **chạy thật** trên Vercel và Google Cloud với chi phí gần bằng không ở quy mô ra mắt, và scale bằng cấu hình.

## 2. Quyết định đã chốt

| Chủ đề | Quyết định |
| --- | --- |
| Ai đặt collection công khai | **Chỉ superadmin.** Nội dung công khai xuất hiện trong câu trả lời của mọi người, nên với dữ liệu thuốc phải có người kiểm soát |
| Vai trò trong tổ chức | Bảng quyền ở mục 3. Một tổ chức có thể có nhiều owner và luôn có ít nhất một owner. Người tạo tổ chức là owner đầu tiên |
| Ai mời được | **Mọi thành viên.** Lời mời của owner hoặc editor gửi email ngay. Lời mời của member chờ owner hoặc editor duyệt |
| Vai trò được cấp qua lời mời | owner mời với mọi vai trò. editor mời với vai trò member hoặc editor. member chỉ mời với vai trò member |
| Lời mời | Hạn 7 ngày. Chỉ người dùng có **email đã xác minh** trùng email được mời mới nhận được. Mỗi tổ chức chỉ có một lời mời đang mở cho một email |
| Nhật ký tổ chức | owner và editor xem toàn bộ, kể cả thao tác của người khác và của superadmin. member không xem |
| Nhật ký cá nhân | Mỗi người xem sự kiện về tài khoản và collection riêng của mình |
| Thu hẹp phạm vi chat | Chọn từng collection cho từng hội thoại, đổi được bất cứ lúc nào. Quyền được kiểm tra lại ở mỗi lượt hỏi |
| Superadmin và hội thoại | Xem và quản lý như dữ liệu khác, **không ghi nhật ký khi đọc**. Thao tác ghi của superadmin trên collection và tổ chức vẫn vào nhật ký. Chính sách quyền riêng tư nêu rõ điều này |
| Cấp quyền superadmin | Chỉ bằng lệnh CLI. Không có nút trên giao diện |
| Xoá tổ chức | Xoá luôn các collection của tổ chức. Phải gõ lại tên tổ chức để xác nhận |
| Tính quyền khi tìm kiếm | Tính trong Postgres ở mỗi lượt hỏi, rồi lọc Qdrant theo release. Không chép quyền vào Qdrant, không dùng Row-Level Security |
| Cách nhập nội dung | Soạn trực tiếp bằng **Tiptap**, hoặc tải lên `.txt` và `.md`. Cả hai cho ra Markdown. Không nhận `.docx` và PDF |
| Metadata | Bảng thuật ngữ và tên gọi dân gian thuộc collection, quản lý ở hai tab riêng trên trang collection |
| Đơn vị xuất bản | Cả collection thành một release mới, đúng như pipeline hiện có. Người dùng bấm Xuất bản sau khi soạn xong |
| Job xuất bản | **Cloud Tasks** gọi ngược backend; job chạy trong request đó. Local và test dùng bộ chạy trong tiến trình |
| Hạn mức mặc định | 200.000 ký tự mỗi tài liệu, 100 tài liệu mỗi collection, 1 MB chữ và 5 collection mỗi người dùng, 5 MB chữ và 20 collection mỗi tổ chức. Superadmin chỉnh riêng cho từng người dùng và tổ chức |
| Chuẩn hoá dữ liệu | Postgres giữ chữ và cấu trúc. Qdrant giữ vector và payload định tuyến. Bỏ `embedding_cache`, bỏ cột `embedding_text`, bỏ bảng `public.skills` |
| Dữ liệu `formulary` hiện có | Thành collection công khai của hệ thống, nạp bằng CLI như cũ |
| Embedding production | Qwen3-Embedding-4B, 2560 chiều, trên DeepInfra. Giống bản đã đánh giá |
| Reranker production | Qwen3-Reranker-4B trên DeepInfra, qua endpoint inference của họ |
| LLM production | Qwen3.5-9B trên DeepInfra cho mọi bước, tắt chế độ suy luận. Giống run `e2e-qwen35-9b` đã đánh giá |
| SMS | Tắt khi ra mắt bằng `PHARMA_SMS__PROVIDER=none`; tab số điện thoại ẩn. Code giữ nguyên, bật lại khi có nhà cung cấp |
| Nơi chạy | Frontend trên **Vercel Hobby** (sản phẩm phi thương mại lúc ra mắt). Backend trên **Google Cloud Run**. Đường lùi cho frontend là Cloud Run bằng Dockerfile hiện có |
| Dịch vụ xung quanh | Neon Postgres, Qdrant Cloud, DeepInfra, Gmail SMTP, Cloud Tasks, Secret Manager, Artifact Registry |

## 3. Bảng quyền

| Hành động | owner | editor | member | người ngoài | superadmin |
| --- | --- | --- | --- | --- | --- |
| Thấy tổ chức, danh sách thành viên | ✓ | ✓ | ✓ | | ✓ |
| Tìm và chat trên collection mức "trong tổ chức" | ✓ | ✓ | ✓ | | ✓ |
| Tạo, đổi tên, xoá collection của tổ chức | ✓ | ✓ | | | ✓ |
| Soạn, sửa, xoá tài liệu, thuật ngữ, tên gọi dân gian; xuất bản | ✓ | ✓ | | | ✓ |
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

Collection riêng tư của một người dùng chỉ người đó và superadmin thấy. Collection riêng tư của một tổ chức chỉ owner, editor của tổ chức đó và superadmin thấy, dùng như bản nháp trước khi chuyển sang mức trong tổ chức. Collection công khai ai đăng nhập cũng thấy. Collection hệ thống chỉ superadmin sửa.

## 4. Mô hình dữ liệu

### 4.1 Bảng `organizations`

`id`, `name` (1–100 ký tự), `text_quota_bytes` (có thể rỗng, rỗng là dùng mặc định), `collection_quota` (có thể rỗng), `created_at`, `updated_at`.

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
| `decided_by`, `decided_at` | ai duyệt, từ chối, thu hồi hoặc nhận, và lúc nào |

Một unique index một phần bảo đảm mỗi (`organization_id`, `email`) chỉ có một lời mời ở trạng thái `pending_approval` hoặc `sent`. Lời mời quá hạn được coi là `expired` khi đọc, và lệnh dọn dẹp định kỳ cập nhật trạng thái.

### 4.4 Bảng `audit_events`

| Cột | Ý nghĩa |
| --- | --- |
| `id`, `occurred_at` | |
| `actor_user_id` | người thực hiện, có thể rỗng nếu tài khoản đã bị xoá |
| `actor_was_superadmin` | thao tác được thực hiện bằng quyền superadmin |
| `action` | ví dụ `organization.created`, `member.role_changed`, `invitation.approved`, `collection.visibility_changed`, `document.updated`, `collection.published` |
| `organization_id`, `subject_user_id`, `collection_id` | đối tượng liên quan, có thể rỗng |
| `details` | JSON, ví dụ vai trò cũ và mới, tên cũ và mới, số release |

Bảng chỉ ghi thêm. Có index theo (`organization_id`, `occurred_at`) và (`subject_user_id`, `occurred_at`). Sự kiện được ghi trong cùng transaction với thay đổi.

### 4.5 Bảng `user` (mở rộng)

Thêm `text_quota_bytes` và `collection_quota`, đều có thể rỗng. Cờ `is_superuser` có sẵn của fastapi-users là quyền superadmin.

### 4.6 Sửa `corpus.collections`

1. Thêm `owner_organization_id`, xoá theo tổ chức.
2. Ràng buộc: `owner_user_id` và `owner_organization_id` không cùng có giá trị. Cả hai rỗng nghĩa là collection của hệ thống.
3. `visibility` thêm giá trị `organization`.
4. Ràng buộc nhất quán: `organization` chỉ hợp lệ khi chủ là tổ chức. Collection của hệ thống luôn là `public`.
5. `key` vẫn duy nhất toàn hệ thống. Collection do người dùng tạo có key sinh tự động dạng `u-<8 ký tự>` hoặc `o-<8 ký tự>`, người dùng chỉ đặt `title`.

### 4.7 Nội dung do người dùng soạn (schema `corpus`)

Pipeline hiện có nhận một bundle và sinh ra `documents`, `sections`, `chunk_versions` theo nội dung đã băm. Những bảng đó là **ảnh chụp đã xuất bản**, không sửa được. Nội dung người dùng soạn cần nguồn riêng, sửa được, rồi được dựng thành bundle khi xuất bản.

| Bảng | Cột chính |
| --- | --- |
| `source_documents` | `id`, `collection_id`, `key` (slug từ tiêu đề, duy nhất trong collection), `title`, `kind` (các giá trị của `DocumentKind`), `source_title`, `source_url` (có thể rỗng), `markdown`, `char_count`, `created_by`, `created_at`, `updated_by`, `updated_at` |
| `glossary_entries` | `id`, `collection_id`, `term`, `case_sensitive`, `vietnamese_expansions[]`, `english_expansions[]`, `aliases[]`, `category`. Một `term` chỉ xuất hiện một lần trong một collection |
| `colloquial_mappings` | `id`, `collection_id`, `key`, `aliases[]`, `visual_sign`, `product_names[]`, `section_keys[]` |
| `ingest_jobs` | `id`, `collection_id`, `release_id` (có thể rỗng), `status` (`queued`, `running`, `ready`, `failed`), `step` (`bundle`, `chunk`, `embed`, `index`, `publish`), `progress` (0–100), `error`, `requested_by`, `attempts`, `created_at`, `started_at`, `finished_at` |

`section_keys` của tên gọi dân gian được chọn từ các tiêu đề trong tài liệu. Key của mục được sinh xác định từ key tài liệu và đường dẫn tiêu đề, cùng một quy tắc ở trình dựng bundle và ở giao diện, nên đổi tiêu đề thì key đổi và giao diện báo tên gọi dân gian nào đang trỏ vào mục không còn tồn tại.

Collection hệ thống (như `formulary`) không có `source_documents`; giao diện hiện nó ở dạng chỉ đọc và vẫn nạp bằng CLI.

### 4.8 Sửa `conversations`

Thêm `collection_ids uuid[]`, có thể rỗng. Rỗng (NULL) nghĩa là mọi collection người dùng được thấy. Danh sách rỗng `{}` không hợp lệ.

### 4.9 Chuẩn hoá corpus

Đo ngày 2026-10-10 sau `VACUUM FULL`: database 403 MB, trong đó `embedding_cache` 302 MB và `chunk_versions` 81 MB. Qdrant đã đúng vai: vector dày, vector BM25 và payload định tuyến (`collection_id`, `release_ids`), không chứa chữ.

1. **Xoá bảng `embedding_cache`** và port `EmbeddingCache`. Trình đánh index đổi sang embedding từng lô rồi ghi ngay vào Qdrant. Chạy lại sau lỗi vẫn bỏ qua các chunk đã có nhờ `existing_ids` của Qdrant. Cache không còn ích vì tính lại toàn bộ `formulary` bằng DeepInfra tốn khoảng 0,25 USD.
2. **Xoá cột `chunk_versions.embedding_text`.** Hàm thuần `compose_embedding_text` dựng lại nó từ `context_header`, `chunk_text` và `colloquial` khi đọc, cho reranker và cho BM25 lúc đánh index. Giữ `embedding_text_sha256` vì id của chunk version được tính từ nó.
3. **Xoá bảng `public.skills`** sót lại từ các migration đã bỏ.
4. Migration kết thúc bằng `VACUUM FULL` các bảng corpus để trả chỗ trống.

Kết quả đo sau migration 0016 ngày 2026-10-11: cả database local còn 66 MB, trong đó `chunk_versions` 46 MB. Qdrant là nút thắt tiếp theo: `formulary` chiếm 250 MB trong 1 GB miễn phí, nên toàn bộ người dùng có khoảng 120 MB chữ, đúng với hạn mức ở mục 2.

### 4.10 Migration

Một migration `0016_organizations_and_ingest` tạo các bảng ở 4.1–4.7, sửa 4.6 và 4.8, và dọn 4.9. Collection hiện có `owner_user_id` giữ chủ cá nhân và mức hiển thị hiện tại. Collection không có chủ thành collection hệ thống `public`.

## 5. Tự nạp nội dung

### 5.1 Luồng

1. Owner hoặc editor tạo collection, đặt tiêu đề. Collection mới ở mức riêng tư.
2. Soạn tài liệu: trang soạn thảo Tiptap với thanh công cụ gồm tiêu đề các cấp, đậm, nghiêng, danh sách và bảng, cùng các trường tiêu đề, loại tài liệu, nguồn. Hoặc tải lên `.txt`, `.md`; nội dung tải lên mở trong cùng trình soạn thảo để xem lại trước khi lưu.
3. Lưu tài liệu ghi Markdown vào `source_documents`. Tiptap xuất Markdown qua phần mở rộng Markdown của nó. Tiêu đề Markdown chia tài liệu thành các mục; không có tiêu đề thì cả tài liệu là một mục.
4. Tab Thuật ngữ và tab Tên gọi dân gian là hai bảng thêm, sửa, xoá dòng.
5. Bấm **Xuất bản**: backend kiểm tra hạn mức và quyền, tạo `ingest_jobs` ở trạng thái `queued`, đẩy một task lên Cloud Tasks, trả về id job.
6. Cloud Tasks gọi `POST /internal/ingest-jobs/{id}/run`. Backend dựng `KnowledgeBundle` từ `source_documents`, `glossary_entries`, `colloquial_mappings` của collection, rồi chạy `import_bundle` với `publish=True`. Trạng thái và bước được cập nhật vào `ingest_jobs` sau mỗi bước.
7. Giao diện poll job mỗi 2 giây và hiện tiến độ theo bước. Xong thì trang collection hiện release mới là bản đang được tìm kiếm.
8. Người dùng quay về bản trước bằng nút Quay lại bản trước, dùng `rollback` sẵn có.

### 5.2 Trình dựng bundle

Hàm thuần trong domain `corpus`: `build_bundle(collection, documents, glossary, colloquial) -> KnowledgeBundle`. Mỗi `source_document` thành một `DocumentRecord`; Markdown được chia theo tiêu đề thành `SectionRecord`, mỗi mục có `context_path` là đường dẫn tiêu đề và một hoặc nhiều `BlockRecord` (đoạn văn và bảng tách riêng, giống pharma-lab). `bundle_digest` tính từ nội dung, nên xuất bản lại khi không có gì đổi cho kết quả `NO_CHANGE` và không tạo release mới.

### 5.3 Job chạy nền

- Port `JobDispatcher` với một phương thức `enqueue(job_id)`. Adapter production đẩy lên Cloud Tasks, đích là endpoint nội bộ, xác thực bằng token OIDC của service account. Adapter local chạy job trong một task asyncio của cùng tiến trình. Test dùng adapter local.
- Endpoint nội bộ từ chối request không có token hợp lệ. Trong local, token là một chuỗi bí mật trong `.env`.
- Job idempotent: chạy lại thì `import_bundle` tiếp tục release `building`, các chunk đã có trong Qdrant được bỏ qua. Cloud Tasks gọi lại tối đa 3 lần với khoảng cách tăng dần; `attempts` ghi lại số lần. Hết lần thì job thành `failed` kèm lý do ngắn gọn cho người dùng.
- Một collection chỉ có một job `queued` hoặc `running` tại một thời điểm.
- Timeout request của Cloud Run cho endpoint này là 600 giây; quá hạn mức ở mục 2 thì không bao giờ tới mức đó.

### 5.4 Hạn mức

Mặc định trong cấu hình `PHARMA_QUOTAS__*`; giá trị riêng trong `user.text_quota_bytes`, `organizations.text_quota_bytes` và hai cột `collection_quota`. Mức đã dùng là tổng `char_count` của `source_documents` trong các collection của chủ đó. Lưu tài liệu hoặc tạo collection vượt hạn mức trả 422 với mã `QUOTA_EXCEEDED` kèm mức đã dùng và hạn mức. Trang collection hiện thanh "đã dùng x / y".

## 6. Thành phần backend

| Tầng | Thành phần | Trách nhiệm |
| --- | --- | --- |
| domain | `access` | `Role`, `Actor(user_id, is_superadmin, memberships)`, các hàm quyết định quyền đúng bảng ở mục 3. Không phụ thuộc framework |
| domain | `organizations` | Model tổ chức, thành viên, lời mời, trạng thái lời mời, port repository |
| domain | `audit` | `AuditEvent`, các hằng `action`, port `AuditLog` |
| domain | `corpus` (đã có) | Thêm `build_bundle`, chia Markdown theo tiêu đề, quy tắc key của mục, model `SourceDocument`, `IngestJob`, port `SourceRepository`, `IngestJobRepository`, `JobDispatcher`. Bỏ port `EmbeddingCache` |
| application | `organizations` | Tổ chức, thành viên, lời mời, kiểm tra luôn còn một owner, gửi email lời mời qua `EmailSender` với rate limit của mảng 2 |
| application | `audit` | Đọc nhật ký tổ chức, nhật ký cá nhân và nhật ký toàn hệ thống, phân trang theo cursor |
| application | `corpus` (đã có) | Thêm tạo, đổi tên, xoá collection, đổi mức hiển thị, `visible_collections(actor)`, CRUD tài liệu và metadata, hạn mức, xuất bản (tạo job), chạy job, quay lại bản trước. `import_bundle` đổi sang embedding và ghi theo lô |
| application | `chat` (đã có) | Trước mỗi lượt hỏi tính `phạm vi = visible ∩ collection_ids của hội thoại`, rồi lấy release hiện hành. Phạm vi rỗng thì trả lời rằng không có nguồn để tìm, không gọi Qdrant |
| application | `admin` | Liệt kê người dùng, tổ chức, collection, job. Khoá và mở tài khoản. Chỉnh hạn mức. Đọc hội thoại của người khác. Thao tác ghi đi qua chính các service ở trên với `Actor` là superadmin |
| infrastructure | repository Postgres | Cho các port mới. Một unit of work chung để thay đổi và sự kiện nhật ký cùng commit |
| infrastructure | retrieval | `CorpusReader.current_releases` nhận id collection thay vì key. Bỏ cấu hình `PHARMA_RETRIEVAL__COLLECTIONS`. Thêm adapter reranker cho endpoint inference của DeepInfra, chọn bằng `PHARMA_RETRIEVAL__RERANK__PROTOCOL=deepinfra` |
| infrastructure | jobs | `CloudTasksDispatcher` và `InProcessDispatcher` |
| infrastructure | notifications | `PHARMA_SMS__PROVIDER=none` tắt SMS: API SMS trả 503, `/users/me` báo `phone_sign_in_enabled=false` |
| api | routers mới | `organizations`, `invitations`, `collections`, `documents`, `audit`, `admin`, `internal` |
| cli | `superadmin grant|revoke <email>` | Cấp và thu hồi quyền superadmin |

Khoá tài khoản (`is_active = false`) xoá luôn mọi phiên của người đó. Lệnh `corpus import` ở CLI vẫn nạp vào collection hệ thống.

## 7. API

Mọi route cần đăng nhập, trừ xem trước lời mời và endpoint nội bộ.

| Nhóm | Route |
| --- | --- |
| Tổ chức | `GET/POST /organizations`, `GET/PATCH/DELETE /organizations/{id}` |
| Thành viên | `GET /organizations/{id}/members`, `PATCH/DELETE /organizations/{id}/members/{user_id}`, `POST /organizations/{id}/leave` |
| Lời mời trong tổ chức | `GET/POST /organizations/{id}/invitations`, `POST /organizations/{id}/invitations/{invitation_id}/approve`, `/reject`, `/revoke`, `/resend` |
| Người được mời | `GET /invitations/{token}` (công khai, xem trước), `POST /invitations/{token}/accept`, `POST /invitations/{token}/decline` |
| Collection | `GET /collections` (những gì tôi thấy, nhóm theo nguồn, kèm mức dùng hạn mức), `POST /collections`, `GET/PATCH/DELETE /collections/{id}`, `GET /collections/{id}/releases`, `POST /collections/{id}/publish` (trả job), `POST /collections/{id}/rollback` |
| Tài liệu | `GET/POST /collections/{id}/documents`, `GET/PATCH/DELETE /collections/{id}/documents/{doc_id}`, `POST /collections/{id}/documents/upload` (multipart `.txt` hoặc `.md`, trả Markdown để xem lại, chưa lưu) |
| Metadata | `GET/PUT /collections/{id}/glossary`, `GET/PUT /collections/{id}/colloquial` (PUT thay cả danh sách), `GET /collections/{id}/sections` (key và tiêu đề các mục để chọn) |
| Job | `GET /ingest-jobs/{id}` |
| Nội bộ | `POST /internal/ingest-jobs/{id}/run`, chỉ Cloud Tasks hoặc bộ chạy local gọi |
| Hội thoại | `PATCH /conversations/{id}` thêm trường `collection_ids`. Request chat thêm `collection_ids` cho tin nhắn đầu tiên của hội thoại mới |
| Nhật ký | `GET /organizations/{id}/audit`, `GET /account/audit` |
| Admin | `GET /admin/users`, `PATCH /admin/users/{id}` (khoá, mở, hạn mức), `GET /admin/organizations`, `PATCH /admin/organizations/{id}` (hạn mức), `GET /admin/collections`, `GET /admin/ingest-jobs`, `GET /admin/users/{id}/conversations`, `GET /admin/conversations/{id}`, `GET /admin/audit` |
| Tài khoản | `GET /users/me` trả thêm `is_superadmin`, `memberships`, `phone_sign_in_enabled` |

Lỗi:

1. Tài nguyên không được phép thấy trả **404**, để không lộ sự tồn tại của tổ chức hay collection.
2. Thấy được nhưng không đủ quyền trả **403** với mã `FORBIDDEN_ROLE`.
3. Mã riêng: `LAST_OWNER`, `ALREADY_MEMBER`, `INVITATION_EXPIRED`, `INVITATION_EMAIL_MISMATCH` (409), `INVITATION_NOT_FOUND`, `QUOTA_EXCEEDED` (422), `PUBLISH_IN_PROGRESS` (409), `SYSTEM_COLLECTION_READ_ONLY` (403), `PHONE_SIGN_IN_DISABLED` (503).
4. Gửi email lời mời dùng rate limit theo người mời và theo địa chỉ nhận, trả 429 với `Retry-After` như mảng 2.

## 8. Frontend

| Feature | Nội dung |
| --- | --- |
| `organizations` | Danh sách tổ chức, tạo tổ chức, trang chi tiết có tab Thành viên, Lời mời, Collection, Nhật ký. Tab không có quyền thì ẩn |
| `collections` | Danh sách collection kèm thanh hạn mức. Trang collection có tab Tài liệu, Thuật ngữ, Tên gọi dân gian, Bản phát hành, cùng nút Xuất bản và hộp tiến độ job. Trang soạn tài liệu dùng Tiptap với nút tải lên. Lựa chọn "Công khai" chỉ hiện với superadmin. Collection hệ thống chỉ đọc |
| `audit` | Component danh sách sự kiện dùng chung. Mỗi sự kiện là một câu dựng từ `action` và `details`. Thao tác của superadmin có nhãn "Quản trị viên" |
| `admin` | Người dùng (tìm, khoá, mở, hạn mức, xem hội thoại), Tổ chức, Collection, Job, Nhật ký toàn hệ thống. Dùng lại component hiển thị tin nhắn của `chat` ở chế độ chỉ đọc, nên thêm hướng import `admin → chat` vào luật kiến trúc |
| `legal` | Trang Chính sách quyền riêng tư và Điều khoản sử dụng, hai ngôn ngữ, prerender |

Route mới:

1. `/organizations`, `/organizations/:id/:tab?`, `/collections`, `/collections/:id/:tab?`, `/collections/:id/documents/new`, `/collections/:id/documents/:docId`, `/activity` trong layout đăng nhập.
2. `/admin/:section?` có guard. Người không phải superadmin nhận trang 404.
3. `/invitations/:token` công khai. Hiện tên tổ chức, người mời, vai trò. Chưa đăng nhập thì có nút Đăng nhập và Đăng ký kèm `next=`. Đăng nhập sai email thì báo lời mời dành cho email nào, có che bớt ký tự.
4. `/privacy` và `/terms` công khai, có link ở footer trang chủ, trang đăng ký và trang cài đặt.

Chat có nút **Nguồn** cạnh ô nhập. Popover chứa checkbox nhóm theo Công khai, từng tổ chức, Của tôi, cùng lựa chọn mặc định "Tất cả nguồn tôi được thấy". Khi đang thu hẹp, nút hiện số nguồn đã chọn.

Thanh điều hướng thêm Tổ chức, Collection, Hoạt động, và Quản trị (chỉ superadmin). Tab Số điện thoại ở trang đăng nhập, đăng ký và mục Số điện thoại trong cài đặt ẩn khi `phone_sign_in_enabled` là false. Mọi chuỗi mới có tiếng Việt và tiếng Anh.

Thư viện mới: `@tiptap/react`, `@tiptap/starter-kit`, phần mở rộng bảng và Markdown của Tiptap, chọn bản chính thức của Tiptap. `@vercel/react-router` cho deploy.

## 9. Triển khai và ra mắt

### 9.1 Kiến trúc chạy thật

| Thành phần | Nơi chạy | Ghi chú |
| --- | --- | --- |
| Frontend SSR | Vercel Hobby | `vercelPreset()` trong `react-router.config.ts`; `vercel.json` rewrite `/api/*` sang URL backend để cookie first-party. Tự deploy khi `main` đổi |
| Backend API | Cloud Run, `asia-southeast1` | scale về 0, `max-instances=1` lúc đầu, `concurrency=40`, timeout 600 giây cho stream và job, cảnh báo ngân sách 1 USD |
| Job xuất bản | Cloud Tasks | queue `ingest`, gọi endpoint nội bộ bằng OIDC |
| Postgres | Neon miễn phí, Singapore | DB mới dựng bằng migration, không chép DB local |
| Vector | Qdrant Cloud miễn phí | vùng gần Singapore nhất có sẵn |
| LLM, embedding, rerank | DeepInfra | Qwen3.5-9B, Qwen3-Embedding-4B, Qwen3-Reranker-4B |
| Email | Gmail SMTP | app password của một tài khoản Gmail; giới hạn 500 thư mỗi ngày |
| SMS | tắt | `PHARMA_SMS__PROVIDER=none` |
| Google OAuth | credential đã có từ andv-lms | thêm redirect URI mới |
| Secrets | Secret Manager cho backend, Environment Variables trên Vercel cho frontend | |

Backend là một container không giữ trạng thái: session, rate limit, job, hạn mức đều trong Postgres, nên tăng `max-instances` không đổi gì trong code.

### 9.2 Deploy

- Backend: GitHub Actions khi `main` đổi: build image, đẩy lên Artifact Registry, chạy `pharma-agent migrate` bằng một Cloud Run Job, rồi deploy service. Xác thực bằng Workload Identity Federation, không lưu key JSON trong repo. Workflow nằm ở `.github/workflows/deploy-backend.yml`.
- Frontend: Vercel nhận GitHub, build và deploy khi `main` đổi. Preview deploy tắt.
- Nạp dữ liệu lần đầu: `pharma-agent corpus import` chạy từ máy người dùng với `backend/.env.production` trỏ vào Neon, Qdrant Cloud và DeepInfra, nạp `formulary` thành collection công khai của hệ thống. Tốn khoảng 0,25 USD embedding.
- `PHARMA_API__TRUSTED_PROXY_HOPS` đo thật sau khi deploy, vì request đi qua cả Vercel lẫn Cloud Run.

### 9.3 Dọn dẹp trước khi ra mắt

1. Production không có llama.cpp và cli-proxy-api. `compose.yaml` local chuyển hai nhóm đó thành profile `local-models` và `gemini-proxy`; mặc định chỉ bật Postgres và Qdrant, backend chạy trên host và gọi DeepInfra.
2. Migration 0016 dọn corpus như mục 4.9.
3. README gốc, backend và frontend cập nhật theo bố cục mới: ba file `.env`, profile compose, cách deploy.
4. Trang Chính sách quyền riêng tư và Điều khoản sử dụng nêu rõ: dữ liệu lưu ở đâu, quản trị viên có thể đọc hội thoại và dữ liệu để vận hành và không ghi nhật ký việc đọc, nội dung do người dùng nạp thuộc người dùng hoặc tổ chức, câu trả lời của hệ thống không thay thế tư vấn của dược sĩ.
5. Loại khỏi image production mọi thứ chỉ dùng cho local: tài liệu e2e, script Kaggle.

### 9.4 Giám sát

Log Cloud Run, uptime check của Cloud Monitoring vào `/health` mỗi 5 phút, cảnh báo ngân sách 1 USD và 5 USD, Langfuse tùy chọn.

### 9.5 Checklist việc người dùng tự làm

1. Tạo project Google Cloud `vipharmind`, gắn thẻ, bật Cloud Run, Cloud Tasks, Artifact Registry, Secret Manager, Cloud Build.
2. Tạo tài khoản Vercel, nhập repo GitHub, đặt Environment Variables theo danh sách trong README frontend.
3. Tạo project Neon ở Singapore, lấy DSN có pooler.
4. Tạo cluster Qdrant Cloud miễn phí, lấy URL và API key.
5. Tạo app password Gmail cho tài khoản gửi thư.
6. Thêm redirect URI của Vercel vào Google OAuth client đã có.
7. Nạp các giá trị trên vào Secret Manager theo danh sách trong README backend, và `backend/.env.production` trên máy mình để nạp dữ liệu lần đầu.
8. Chạy `pharma-agent superadmin grant <email của bạn>` trỏ vào production.

### 9.6 Đường scale

| Thành phần | Nút thắt đầu tiên | Bước nâng | Chi phí |
| --- | --- | --- | --- |
| Backend Cloud Run | `max-instances=1` | nâng số instance | theo giây CPU thật dùng |
| Frontend Vercel | điều khoản Hobby khi thương mại | Vercel Pro, hoặc Cloud Run bằng Dockerfile frontend hiện có | 20 USD/tháng |
| Neon | 0,5 GB | gói Launch 10 GB | 19 USD/tháng |
| Qdrant Cloud | 1 GB, đầy trước Neon | cluster trả phí, hoặc cắt chiều embedding xuống 1024 sau khi đánh giá lại | từ 25 USD/tháng |
| DeepInfra | không có nút thắt cứng | | khoảng 2 USD mỗi 1.000 lượt hỏi |
| Gmail SMTP | 500 thư/ngày | Resend với domain riêng | miễn phí 3.000 thư/tháng |

## 10. Kiểm thử

| Lớp | Nội dung |
| --- | --- |
| domain `access` | Test dạng bảng phủ mọi ô của bảng quyền ở mục 3 |
| domain `corpus` | `build_bundle`: chia theo tiêu đề, tài liệu không có tiêu đề, bảng tách thành block riêng, key của mục ổn định, `bundle_digest` không đổi khi nội dung không đổi |
| application | Fake in-memory. Luôn còn một owner, kể cả khi hai owner cùng rời. Vòng đời lời mời. Mỗi thao tác ghi sinh đúng sự kiện nhật ký, thao tác thất bại không sinh sự kiện. Hạn mức chặn đúng chỗ. Xuất bản khi đang có job trả 409. Job chạy lại sau lỗi vẫn hoàn tất |
| Postgres | Migration 0016 chuyển dữ liệu cũ đúng và xoá đúng bảng, cột. Ràng buộc chủ sở hữu và mức hiển thị chặn dữ liệu sai. Nhật ký cùng transaction với thay đổi |
| API | Không thấy thì 404, thiếu quyền thì 403. Người ngoài gọi mọi route của một tổ chức đều nhận 404. Endpoint nội bộ từ chối request không có token |
| retrieval (Qdrant thật) | A không bao giờ nhận chunk từ collection riêng tư của B. Rời tổ chức thì câu hỏi kế tiếp không còn thấy collection của tổ chức. Thu hẹp phạm vi chỉ trả về collection đã chọn. Nạp theo lô không cần cache cho kết quả giống nạp qua cache |
| kiến trúc | `test_layering` và `app/architecture.test.ts` thêm luật cho các feature mới |
| frontend | Vitest browser: popover Nguồn, ẩn hiện tab theo vai trò, trang nhận lời mời, trình soạn thảo xuất Markdown đúng, tải lên `.md`, hộp tiến độ job, trang admin, ẩn tab Số điện thoại khi SMS tắt |
| e2e | (1) Tạo tổ chức, mời qua email, người được mời đăng ký và nhận lời mời, thấy collection của tổ chức trong Nguồn. (2) member mời, owner duyệt, email được gửi. (3) Soạn một tài liệu, xuất bản với bộ chạy local, hỏi một câu và nhận trích dẫn từ tài liệu đó. (4) Superadmin khoá tài khoản, người đó bị đăng xuất |
| triển khai | Smoke test sau deploy trong GitHub Actions: `/health` trả 200 và một câu hỏi mẫu trả lời được |

## 11. Rủi ro

1. Mỗi lượt hỏi thêm một truy vấn tính quyền. Một câu SQL có index, nhỏ so với thời gian gọi LLM. Chưa cần cache.
2. Superadmin đọc hội thoại không ghi nhật ký. Chính sách quyền riêng tư phải nêu rõ trước khi ra mắt; đây là một task của plan.
3. Qdrant 1 GB đầy trước mọi thứ khác. Trang admin hiện số điểm đang dùng để biết sớm.
4. Vercel Hobby chỉ hợp lệ khi phi thương mại. Đường lùi là Cloud Run bằng Dockerfile frontend hiện có.
5. Phạm vi rất lớn. Plan chia theo lớp và mỗi lớp kết thúc bằng commit xanh: dọn corpus và chuẩn hoá, domain `access` và dữ liệu, service tổ chức và nhật ký, service nội dung và job, API, frontend, triển khai, e2e.

## 12. Ngoài phạm vi

1. Nhận `.docx` và PDF.
2. Chuyển collection giữa các chủ sở hữu.
3. Chia sẻ một collection riêng tư cho từng người cụ thể.
4. Quy trình xin công khai collection. Superadmin tự đặt mức công khai khi cần.
5. Nhà cung cấp SMS thật; bật lại bằng cấu hình khi có.
6. Domain riêng và Resend; gắn vào khi có domain.
