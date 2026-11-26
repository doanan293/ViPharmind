# Làm sạch và tối ưu ViPharmind trước khi quay demo

Ngày: 2026-11-26. Trạng thái: đã duyệt (chủ dự án, 2026-11-26).

## 1. Mục đích

ViPharmind là ứng dụng được xây hoàn toàn bằng AI theo quy trình spec → plan → TDD. Nó sẽ là "ứng dụng được
xây theo quy trình spec-driven" trong nghiên cứu môn Chuyên đề nghiên cứu 1 (đề B3, HUST), và các nhiệm vụ
thí nghiệm của nghiên cứu đó sẽ được chọn từ lịch sử của repo này. Vì vậy ứng dụng phải chạy được trên máy
cá nhân, mọi tính năng hoạt động thật, giao diện đủ tốt để quay video demo, và lịch sử git gọn theo tính năng.

Chủ dự án muốn tối ưu **hết mức có thể**: chạy được, đúng, nhanh, đẹp, gọn. Nhiệm vụ thí nghiệm sẽ chọn lại sau
khi xong, nên không bị ràng buộc bởi lịch sử cũ hay bộ nhiệm vụ cũ.

## 2. Điểm xuất phát

- Nhánh làm việc `clean` = `v2.0.0` + merge `camera-ready` (chỉ tài liệu poster và thuyết trình), worktree
  `~/personal/vipharmind-clean`. Mã giống hệt `v2.0.0`; `docs/poster`, `docs/presentation` giống hệt `camera-ready`.
- `v2.0.0` đã gộp `camera-ready` ở `9732e8e`, có corpus dựng lại bằng pharma-lab 0.4.0 (3.120 tài liệu, 34.552
  mục), embedding tính sẵn trên Kaggle cho 5 model, golden v4, ablation D1 và D7. Paper v2 dừng từ 2026-11-15
  (D2, D4, D5 bỏ). Phần mã thí nghiệm của paper v2 (ReAct agent, decision model Jev qua OpenRouter, cấu hình e2e
  cho ablation) vẫn nằm trong repo.
- Tag `archive/main-2026-11-10` giữ `main` cũ.
- Đo nhanh ngày 2026-11-25 trên `camera-ready`: e2e Playwright 16/16 đạt (backend e2e với LLM và embedding giả).

## 3. Phạm vi

### 3.1 Chạy local một lệnh

`scripts/demo-stack.sh up|down|status|reset-db`:
- Postgres, Qdrant, backend, frontend, nginx qua `compose.yaml` + `compose.llm-proxy.yaml` +
  `compose.local-models.yaml`; web ở `http://localhost:8080`.
- LLM: Gemini qua CLIProxyAPI, token trong volume `vipharmind_cli_proxy_auth`.
- Embedding: `qwen3-embedding-4b-q8_0.gguf` (model `qwen3-embedding:4b-q8_0`, 2560 chiều). Rerank: chọn giữa
  `qwen3-reranker-4b-q8_0-vimed.gguf` và `qwen3-reranker-0.6b-q8_0-vimed.gguf` bằng số đo ở 3.4 (4B đúng hơn nhưng
  rất chậm trên CPU; 0.6B nhanh). GGUF đọc tại chỗ từ `GGUF_DIR` (mặc định `~/personal/vipharmind/ai-models/gguf`).
- **Dữ liệu chỉ đọc từ worktree cũ.** Corpus (`sections.jsonl`, embedding), golden và gold retrieval là file
  gitignore chỉ có ở `~/personal/vipharmind/pharma-lab/data/`; stack demo và các bước đo đọc tại chỗ qua biến
  `PHARMA_DATA_DIR` (mặc định đường dẫn đó), không chép, không ghi vào đó.
- **Stack demo tách riêng:** project compose `vipharmind-demo` (volume Postgres, Qdrant riêng), để `reset-db` và
  import corpus không đụng volume `vipharmind_*` của worktree cũ. Token Gemini chép một lần từ volume
  `vipharmind_cli_proxy_auth` sang `vipharmind-demo_cli_proxy_auth` (chỉ đọc nguồn).
- **Không index lại**: nạp gói `pharma-lab/data/corpus/formulary` bằng `pharma-agent corpus import` (chỉ nạp
  vector có sẵn); bỏ qua nếu Qdrant đã có collection khớp model.
- Email và SMS ở local: provider `log` có sẵn (`PHARMA_EMAIL__PROVIDER=log`, `PHARMA_SMS__PROVIDER=log`) ghi mã ra log
  backend; kịch bản demo đọc mã từ `docker compose logs backend`. Không thêm endpoint mới vào backend.
- `reset-db`: xóa dữ liệu người dùng, giữ corpus.

### 3.2 Tính năng phải chạy đúng (mỗi tính năng là một chương của video demo)

| Mã | Tính năng | Nội dung chính |
| --- | --- | --- |
| `auth` | Tài khoản | Đăng ký email (OTP), đăng nhập email và số điện thoại, quên mật khẩu, đăng xuất, phiên hết hạn |
| `chat` | Hỏi đáp thuốc | Câu trả lời stream, trạng thái từng bước, trích dẫn, xem nguồn đầy đủ, câu hỏi nối tiếp, câu lạc đề bị từ chối, đánh giá câu trả lời, chọn nguồn tìm |
| `history` | Lịch sử hội thoại | Danh sách mới nhất trước, đổi tên, mở lại, xóa |
| `orgs` | Tổ chức | Tạo, thành viên và vai trò, lời mời qua email (gửi lại, thu hồi, nhận), rời, xóa, nhật ký hoạt động |
| `collections` | Bộ tài liệu | Tập riêng và của tổ chức, soạn tài liệu, glossary, cách gọi dân gian, xuất bản, quyền xem, câu trả lời trích tài liệu riêng |
| `account` | Cài đặt | Tên, đổi email hoặc số điện thoại bằng mã, mật khẩu, phiên đăng nhập, ngôn ngữ, giao diện sáng tối |
| `admin` | Quản trị | Danh sách người dùng, khóa người dùng (phiên kết thúc), 404 với người không phải superadmin |
| `public` | Trang công khai | Trang giới thiệu, trang pháp lý, đa ngôn ngữ |

### 3.3 Đúng

- Mọi kiểm tra của README root (ruff, ruff format, pyrefly mức warn, lint-imports, pytest) đạt ở `backend/` và
  `pharma-lab/`; frontend đạt `typecheck`, `lint`, `format`, `test`; e2e Playwright đạt; pre-commit
  `--all-files` đạt.
- Review từng tính năng ở 3.2 theo spec hiện hành (`2026-11-15-*-design.md`). Mỗi lỗi: test tái hiện trước, sửa
  sau, commit `fix(<phạm vi>): ...`.
- Mã thí nghiệm của paper v2: giữ phần đang được dùng ở chế độ mặc định hoặc có test và cờ rõ ràng; gỡ phần chết
  (không đường gọi, không test, chỉ phục vụ ablation đã bỏ). Mỗi quyết định gỡ hay giữ ghi trong spec liên quan.

### 3.4 Nhanh

- Bộ golden: file golden e2e và gold retrieval hiện hành có hash bundle khớp manifest corpus 0.4.0; tên file cụ
  thể ghi vào `docs/performance-local.md` trước lần đo đầu, mọi lần đo trước và sau dùng đúng các file đó.
- Đo trên stack local ở 3.1 với 20 câu cố định lấy từ golden đó (câu trả lời được, nhiều nhóm): thời gian tới chữ
  đầu tiên và tổng thời gian một lượt, p50 và p95, tách theo bước (guard, hiểu câu hỏi, tìm, rerank, trả lời).
- **Mốc chất lượng** là một lần đo mới trên máy này với cấu hình demo ban đầu (không phải số của bài báo): đánh giá
  retrieval của pharma-lab (Recall@k, nDCG) và đánh giá e2e câu trả lời trên golden. Số của rerank 4B ghi kèm làm
  tham chiếu.
- Tối ưu điểm nghẽn có số đo chứng minh: tham số llama.cpp, số ứng viên rerank, song song hóa bước độc lập, và cả
  thay đổi hành vi (bỏ hoặc gộp lời gọi LLM, model rẻ hơn cho guard và viết lại câu hỏi) nếu điểm e2e và retrieval
  không tụt so với mốc. Thay đổi hành vi thì cập nhật spec liên quan. Không đổi model embedding (ràng buộc không
  index lại). Độ trễ của Gemini qua proxy dao động: mỗi số đo lặp 3 lần, báo trung vị.
- Báo cáo số trước và sau trong `docs/performance-local.md`.

### 3.5 Đẹp

Đánh giá 2026-11-25 từ ảnh chụp e2e: nền shadcn tốt (sidebar, tabs, card, combobox, popover, empty state) nhưng
nhạt. Việc cần làm:
- Thống nhất tên **ViPharmind** (sidebar đang ghi "Pharma Agent"), thêm logo và favicon.
- Theme thương hiệu qua biến màu của shadcn (`app/app.css`), giữ chế độ sáng và tối, tương phản đạt WCAG AA.
- Sửa popover trích dẫn và bảng nguồn đè lên nội dung chat; nút chính thống nhất một kiểu (nút "Mời" đang lệch).
- Trang đăng nhập và đăng ký có thương hiệu; trạng thái rỗng dùng component `Empty` có nội dung hướng dẫn.
- Kiểm theo danh sách accessibility và UX của skill ui-ux-pro-max: nhãn cho nút chỉ có icon, focus nhìn thấy,
  kích thước vùng bấm, thông báo lỗi cạnh trường.
- **Chỉ dùng component shadcn và thư viện đã có** (Base UI, lucide, streamdown, tanstack, react-hook-form, zod).
  Thiếu component thì thêm từ registry shadcn, không tự viết lại.

### 3.6 Gọn

- Không còn mã chết, cấu hình thừa, tài liệu mô tả sai mã (README các project, spec hiện hành khớp mã).
- Opus review toàn bộ diff từ `v2.0.0` trước khi viết lại lịch sử.

### 3.7 Video demo

- Playwright với config riêng `frontend/playwright.demo.config.ts`: video bật, viewport 1440×900, `slowMo`, kịch bản
  trong `frontend/tests/demo/*.demo.ts` (đặt trong `tests/` theo quy tắc vị trí test của `AGENTS.md`), chạy trên
  stack local ở 3.1, có dải chú thích tiếng Việt từng bước.
- **Một video duy nhất** đi qua mọi tính năng ở 3.2 theo thứ tự bảng (chủ dự án, 2026-11-26). Kịch bản
  `frontend/tests/demo/walkthrough.demo.ts` là một test, một trang trình duyệt, nên một file video liền mạch; mỗi
  tính năng là một chương (hàm trong `frontend/tests/demo/chapters/<mã>.ts`) mở đầu bằng dải tiêu đề chương. Việc cần
  người dùng thứ hai (nhận lời mời, người ngoài tổ chức) làm bằng đăng xuất rồi đăng nhập tài khoản khác trên cùng
  trang, để mọi thứ nằm trong một video.
- Khi phát triển, từng chương chạy riêng được qua `frontend/tests/demo/chapters.demo.ts` (mỗi chương một test, không
  cần video). Video cuối chạy lại được hai lần liên tiếp trên cùng database.
- Video không vào git; lưu ngoài repo và đưa vào GitHub Release.

### 3.8 Lịch sử git và nhánh

Chủ dự án (2026-11-26) chỉ giữ hai nhánh: **`main`** = bài SoICT (đầu nhánh `camera-ready` cũ cộng sửa poster cuối,
`15b7267`, tag `soict-poster`), không đổi nữa; **`v2.0.0`** = hướng mới, nhận toàn bộ việc làm sạch này. Nhánh
`camera-ready`, `dev`, `ci` đã xóa cả trên GitHub lẫn trên máy. Không giữ bản lưu trữ: dữ liệu đã có trên Kaggle
và GitHub (chủ dự án).

- Sau khi 3.1–3.7 xong: dựng nhánh `v2-new`. Phần lịch sử chung với `main` (tới điểm rẽ `3f0a46d`) giữ nguyên. Phần
  riêng của `v2.0.0` (first-parent từ `3f0a46d`, bỏ các merge từ `camera-ready`/`main`) gộp theo đoạn liên tục:
  **không sắp xếp lại commit cũ**, nên cây ở mỗi mốc là trạng thái cũ đã từng tồn tại. Ranh giới đoạn đặt ở chỗ chủ
  đề commit đổi (phạm vi trong tiêu đề commit cũ và thư mục bị sửa); đoạn chủ yếu là app (`backend`, `frontend`)
  thành `feat(<tính năng>)`, đoạn chủ yếu là nghiên cứu (`pharma-lab`, bài báo, dữ liệu) thành `docs(...)` hoặc
  `chore(lab)`. Sau đó là các commit làm sạch của nhánh `clean` (phát lại theo cây của từng commit); cây cuối giống
  hệt `clean`. Chạy test ở mọi commit `feat` và ghi lại commit nào trượt, không sửa ngược.
- **Cập nhật 2026-11-26 (chủ dự án: "cứ tối ưu viết lại lịch sử thoải mái, research topic ngon là được"):** mục tiêu
  số một của lịch sử mới là cho nhiệm vụ thí nghiệm tốt. Được phép sắp xếp lại commit, gộp bản sửa test vào đúng commit
  tính năng của nó, chọn lại ranh giới, miễn mỗi commit `feat` là một tính năng trọn vẹn, test backend đạt ở commit cha
  và ở chính nó, và cây cuối vẫn giống hệt `clean`. Ràng buộc "không sắp xếp lại commit cũ" ở trên được nới theo cập
  nhật này; commit nào vẫn trượt test thì ghi lại.
- Ranh giới tính năng chọn sao cho thuận cho việc chọn nhiệm vụ thí nghiệm về sau: mỗi commit một tính năng trọn
  vẹn có test, không lồng nhau.
- Thay `v2.0.0` bằng `v2-new`: force-push lên GitHub chỉ khi chủ dự án đồng ý ngay lúc đó; không tạo tag lưu
  trữ cho `v2.0.0` cũ (chủ dự án: không cần archive). Tag của bài báo (`v1.0.0`, `v1.1.0`, `soict-camera-ready`,
  `soict-poster`) không đổi. Video demo đưa vào một GitHub Release gắn với tag trên `v2.0.0` mới.

## 4. Không làm

- Không đổi model embedding hay dựng lại corpus. Không chạy lại pipeline Kaggle.
- Không triển khai lại production (Vercel, Neon, Qdrant Cloud, DeepInfra).
- Không sửa nội dung bài SoICT, poster, slide.
- Không tiếp tục paper v2.

## 5. Ràng buộc

- Quy tắc của `AGENTS.md` và README root: không `# noqa`, không `# type: ignore`, không `ignore_imports`, không tắt
  rule; test đúng vị trí.
- Commit không thêm dòng ghi công AI.
- Không đụng worktree `~/personal/vipharmind` (nhánh `v2.0.0`, có file chưa commit) và
  `~/personal/vipharmind-camera-ready` (có thay đổi poster chưa commit).
- Không push khi chưa được đồng ý.
- Người review là Opus, phiên khác người sửa. Không dùng Fable.

## 6. Các hướng đã cân nhắc

- **Gốc nhánh:** `camera-ready` (bị loại: thiếu corpus 0.4.0 mà vector tính sẵn trên máy thuộc về, thiếu các sửa
  lỗi của `v2.0.0`); **`v2.0.0` + tài liệu của `camera-ready` (chọn)**.
- **Thứ tự:** viết lại lịch sử trước rồi sửa (bị loại: mỗi sửa lỗi phải viết lại các commit sau); chỉ sửa, không
  viết lại lịch sử (bị loại: lịch sử vụn); **sửa trên bản chạy được, viết lại lịch sử một lần ở cuối (chọn)**.
- **Quay demo:** quay tay (bị loại: phải quay lại mỗi khi sửa); **Playwright có kịch bản (chọn)**.
- **UI:** tự thiết kế component (bị loại theo yêu cầu chủ dự án); **shadcn và thư viện có sẵn, chỉ thêm theme và
  thương hiệu (chọn)**.

## 7. Quyết định Claude đã chọn (chủ dự án có thể sửa)

- Rerank chọn bằng số đo (3.4), mặc định đề xuất 0.6B nếu chất lượng tụt ít, vì 4B trên CPU quá chậm cho demo.
- Stack demo tách volume riêng (`vipharmind-demo`); dữ liệu và GGUF đọc tại chỗ từ worktree cũ.
- Lịch sử mới không sắp xếp lại commit cũ; tính năng trải nhiều đoạn thành nhiều commit.
- Tối ưu được phép đổi hành vi nếu chất lượng đo được không tụt.
- Màu thương hiệu, logo: Claude đề xuất 2–3 phương án bằng mockup để chủ dự án chọn trước khi áp dụng.
