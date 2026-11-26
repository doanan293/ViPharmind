# Nhật ký làm sạch

Mỗi dòng: tính năng · triệu chứng · nguyên nhân · sửa · test.

## auth

- Trang đăng ký ghi "Tạo tài khoản bằng email hoặc Google" trong khi có thể có cả số điện thoại (local bật SMS) ·
  câu chữ cố định không theo các cách đăng nhập server bật · đổi thành "Tạo tài khoản để tra cứu thông tin thuốc."
  (vi, en), đúng ở mọi cấu hình · không cần test (chỉ đổi chữ).
- Nút và ô nhập cao 32 px, dưới 44 px trên màn cảm ứng (ảnh chụp 390×844) · cỡ mặc định của shadcn · xử lý chung ở
  bước thương hiệu và theme (Task 5) cho mọi trang, không sửa riêng từng form.
- Đăng ký email, sai mật khẩu, quên mật khẩu, đăng nhập bằng số điện thoại: chạy đúng trên stack demo (chương `auth`).
- Chạy chương `auth` lần thứ hai thì không nhận được mã (backend trả 429) · giới hạn 20 lần gửi mã mỗi giờ mỗi IP ghi cứng
  trong `AccountPolicy`, mà mọi tài khoản demo gửi từ cùng một máy · thêm `PHARMA_AUTH__CODE_SENDS_PER_IP_PER_HOUR`
  (mặc định 20, production không đổi), `compose.demo.yaml` đặt 1000 · `tests/infrastructure/test_account_factory.py`.
- `compose.yaml` có nginx đứng trước backend nhưng không đặt `PHARMA_API__TRUSTED_PROXY_HOPS`, nên backend coi nginx là
  client và mọi trình duyệt chung một bộ đếm giới hạn theo IP · thêm `PHARMA_API__TRUSTED_PROXY_HOPS: "1"` cho backend
  trong `compose.yaml` · kiểm bằng chạy chương `auth` ba lần liên tiếp.

## chat

- Thẻ xem nhanh trích dẫn hiện markdown thô ("## Thai kỳ…") · đoạn trích dùng chung `make_snippet` với bằng chứng của
  judge · thêm `make_preview` (bỏ dấu heading, gạch đầu dòng, số thứ tự, dấu nhấn mạnh; giữ ">" vì trong Dược thư nó là
  ngưỡng "> 50 ml/phút") cho trích dẫn và sự kiện evidence gửi giao diện; `make_snippet` và đầu vào judge giữ nguyên ·
  `tests/domain/test_text.py` (3 test). Bản sửa đầu (f53c4b1) đổi thẳng `make_snippet`, làm mất ">" và đổi đầu vào
  judge; người soát Opus bắt được, đã sửa lại.
- Câu trả lời có trích dẫn gộp "[1, 2, 3, 4]", "[3; 5]" hiện thành chữ thô, không bấm được; kịch bản demo lần hai treo vì không thấy nút [1] · `CitationSanitizer` chỉ nhận "[n]" · chuẩn hóa dạng gộp thành "[1], [2]", bỏ số không hợp lệ, xử lý cả khi bị cắt giữa các delta stream · `tests/domain/test_citations.py` (3 test).

## history

- Danh sách, mở lại, đổi tên, xoá cuộc trò chuyện: chạy đúng trên stack demo (chương `history`); không có lỗi app.

## orgs

- Nhật ký tổ chức ghi "đã đổi vai trò một thành viên", "đã xoá một thành viên" thay vì tên người đó · `AuditEventView` chỉ có tên người thực hiện · thêm `subject_name` (tên tài khoản được nhắc tới, rỗng khi không còn) và câu chữ dùng tên, còn "một thành viên" khi không biết · `tests/application/test_audit_service.py`, `describe-event.test.ts`.
- Chủ sở hữu duy nhất bấm "Rời tổ chức": giao diện báo LAST_OWNER bằng câu giải thích rõ; giữ nguyên.

## tooling

- Hook pre-commit `frontend-api-drift` luôn trượt khi commit từ một git worktree phụ · git đặt `GIT_DIR` cho hook, `npm --prefix frontend` làm git coi `frontend/` là gốc work tree · hook đặt `GIT_WORK_TREE` trước khi chạy · kiểm bằng chạy hook với `GIT_DIR` đặt sẵn.

## collections

- Trình soạn tài liệu hiện ô chọn file mặc định của trình duyệt ("Choose File No file chosen", tiếng Anh, lệch kiểu) · `UploadButton` dùng `<Input type="file">` · nút `Button` của shadcn có icon và nhãn tiếng Việt mở một input ẩn (`sr-only`) · `DocumentEditorPage.browser.test.tsx` (nhãn hiện thành chữ).
- Tab Thuật ngữ và Tên gọi dân gian khi rỗng chỉ có hai nút trơn · không có trạng thái rỗng · thêm `Empty` của shadcn với câu "Chưa có thuật ngữ nào.", "Chưa có tên gọi dân gian nào." (vi, en) như tab Tài liệu · `CollectionPage.browser.test.tsx` (2 test).
- Nút "Xuất bản" bật cả khi bộ tài liệu rỗng; bấm thì backend báo lỗi có giải thích · giữ nguyên (nhỏ).
- Tạo bộ tài liệu của tổ chức, đặt quyền xem "trong tổ chức", soạn và xuất bản, thành viên hỏi được trích, người ngoài không thấy: chạy đúng (chương `collections`).

## account

- Test `SessionsList` "cannot be loaded, retries" trượt chập chờn (khoảng 1/3 lần chạy cả bộ) · request refetch còn sót từ test trước tới lúc handler vừa reset, MSW ghi lỗi request không có handler và fail-on-console đánh trượt test · `beforeEach` đặt handler mặc định cho `/account/sessions` · 0/30 lần trượt sau khi sửa.

## brand

- Tên hiển thị "Pharma Agent" khác tên sản phẩm; không logo, không màu thương hiệu · i18n `appName` và tiêu đề trang · đổi thành ViPharmind; thêm `BrandMark` (logo viên nang, ẩn với trình đọc màn hình khi có chữ đi kèm) ở sidebar, trang giới thiệu, thẻ đăng nhập; theme "Xanh dược" qua biến màu shadcn (`--primary` green-700 sáng, green-500 tối; sidebar xanh nhạt); favicon SVG · `resources.test.ts`, `brand-mark.browser.test.tsx`.
- Nút, ô nhập cao 32 px, dưới 44 px trên màn cảm ứng · cỡ mặc định của shadcn · thêm `pointer-coarse:h-11` (nút sm: h-10, nút icon: size-11) trong `button.tsx`, `input.tsx`; màn hình chuột không đổi · kiểm bằng ảnh chụp 390×844 có cảm ứng.
- Hồ sơ, đổi mật khẩu, phiên đăng nhập (đăng xuất thiết bị khác từ xa), giao diện sáng và tối: chạy đúng (chương `account`). Đổi mật khẩu đăng xuất mọi phiên khác, đúng spec.

## admin

- Bảng tác vụ xuất bản hiện bộ tài liệu bằng 8 ký tự đầu của mã · `JobView` chỉ có `collection_id` · ô lấy tên từ danh sách bộ tài liệu mà trang quản trị đã tải (`useAdminCollectionsList`), không có tên thì vẫn hiện mã ngắn · `AdminPage.browser.test.tsx`.
- Trang quản trị 404 với người thường; cấp superadmin bằng CLI; khoá người dùng làm phiên của họ kết thúc: chạy đúng (chương `admin`). Thêm lệnh `scripts/demo-stack.sh exec`.
- Chạy chương `auth` nhiều lần trong 15 phút thì đăng nhập trả 429 · giới hạn 10 lần đăng nhập sai mỗi IP ghi cứng, mà mỗi lần chạy demo cố ý nhập sai một lần từ cùng một máy · thêm `PHARMA_AUTH__LOGIN_FAILURES_PER_WINDOW` (mặc định 10), `compose.demo.yaml` đặt 1000 · `tests/infrastructure/test_account_factory.py`.

## public

- Trang giới thiệu chỉ giới thiệu 2 tính năng trong lưới 3 cột; hai tính năng nổi bật (bộ tài liệu có phân quyền, chặn câu hỏi ngoài phạm vi) không được nhắc · thêm hai thẻ, mỗi thẻ có icon lucide, lưới 2 cột (vi, en) · `LandingPage.test.tsx`.
- Trang giới thiệu tiếng Việt và tiếng Anh, chuyển ngôn ngữ, trang chính sách: chạy đúng (chương `public`).

## review 2

- (Opus soát) Kích thước cảm ứng làm vỡ input group: ô nhập 44 px trong khung 32 px, nút trong nhóm cao 44 px · `InputGroup` thêm `pointer-coarse:h-11`, `InputGroupInput` `pointer-coarse:h-full`, nút trong nhóm `pointer-coarse:h-9`/`size-9` · kiểm bằng ảnh chụp 390×844 có cảm ứng.
- (Opus soát) Nút chính khi rê chuột mờ đi `bg-primary/80`, chữ trắng chỉ 3,36:1 · `button`, `badge`, `bubble` sẫm lại bằng `color-mix` thay vì mờ · ghi trong frontend README như file cố ý khác registry.
- Logo trong sidebar bị `[&_svg]:size-4` của sidebar đè còn 16 px · `size-7!`. Favicon dùng đúng mã màu của theme. Câu "bị chặn trước khi agent tìm kiếm" nói quá (guard fail-open) · "được nhận diện".
- Kịch bản demo: chương bộ tài liệu kiểm đúng popover "Trích từ mục Giảm đau sau mổ"; chương tổ chức kiểm câu "đã đổi vai trò của <tên>".
