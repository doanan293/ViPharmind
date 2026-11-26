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
