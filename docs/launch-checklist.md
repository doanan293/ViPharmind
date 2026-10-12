# Checklist ra mắt

Những việc chỉ chủ tài khoản làm được (đăng nhập dịch vụ, nạp tiền, secret). Kiến trúc: frontend
trên Vercel, backend trên Render Free, dữ liệu trên Neon và Qdrant Cloud, model trên DeepInfra, thư
qua Gmail API. Mọi dịch vụ đang dùng gói miễn phí; chỉ DeepInfra cần nạp tiền.

## Trạng thái (cập nhật 2026-10-11)

Đã xong, không mất phí:

- [x] Neon: project ở Singapore, database `neondb`, DSN có pooler trong `backend/.env.production`; đã migrate tới `0020`.
- [x] Qdrant Cloud: cluster miễn phí `vipharmind` ở AWS US Oregon (gói Free không có châu Á), URL và API key trong `backend/.env.production`. Cluster Free tự tạm dừng sau 1 tuần không có truy vấn; cron Vercel gọi `/api/v1/health` mỗi ngày giữ nó chạy.
- [x] Secret production (JWT, CSRF, OTP, proxy, token nội bộ) đã sinh trong `backend/.env.production`.
- [x] Render: service `vipharmind-api` (Free, Singapore) chạy ở https://vipharmind-api.onrender.com, tự deploy khi push `main` (ứng dụng GitHub của Render có quyền đọc repo). `/api/v1/health` báo Postgres ổn, `corpus` chưa sẵn sàng vì chưa nạp corpus. Đã đo `PHARMA_API__TRUSTED_PROXY_HOPS=3`: IP thật của khách được nhận đúng cả khi gọi thẳng lẫn qua Vercel.
- [x] Vercel: project `vipharmind`, preset React Router, Root Directory `frontend`, nối GitHub, https://vipharmind.vercel.app chạy; đã đặt `API_INTERNAL_URL`, `PUBLIC_SITE_URL`, `THEME_COOKIE_SECRET`, `API_PROXY_SECRET`. Đăng nhập sai mật khẩu qua Vercel trả đúng `LOGIN_BAD_CREDENTIALS`.

Việc miễn phí còn lại, cần bạn làm trên web:

- [ ] Đăng nhập Google (hoãn được, khi chưa có client thì nút Google tự ẩn): mọi app dùng chung project Google Cloud `andimus`. Tạo màn hình đồng ý (External, Publish app), rồi tạo OAuth client Web `ViPharMind` với redirect URI `https://vipharmind.vercel.app/auth/google/callback`, `https://vipharmind.vercel.app/auth/google/link-callback` và hai URI tương ứng trên `http://localhost:3000`. Ghi `PHARMA_AUTH__GOOGLE_CLIENT_ID` và `PHARMA_AUTH__GOOGLE_CLIENT_SECRET` vào `backend/.env.production`, rồi chạy `devops/render/configure.py`.
- [ ] Gửi thư qua Gmail API: trong project `andimus`, tạo màn hình đồng ý (External, **Publish app**, vì chế độ Testing làm refresh token hết hạn sau 7 ngày) và một OAuth client loại **Desktop app**. Ghi `PHARMA_EMAIL__GMAIL_CLIENT_ID`, `PHARMA_EMAIL__GMAIL_CLIENT_SECRET` và `PHARMA_EMAIL__SENDER` vào `backend/.env.production`, chạy `uv run --with google-auth-oauthlib python devops/google/gmail_refresh_token.py --account <gmail gửi thư>`, mở URL nó in ra và bấm cho phép, rồi chạy `devops/render/configure.py`.

**Để sau, tốn tiền:**

- [ ] Nạp tiền DeepInfra, rồi nạp corpus lên Neon và Qdrant (mục 2): gọi DeepInfra tính embedding `Qwen/Qwen3-Embedding-8B` cho 24.946 đoạn, khoảng 0,3–0,5 USD. Trước bước này chat chưa trả lời được.
- [ ] Kiểm tra số dư DeepInfra định kỳ (mọi câu trả lời trên production đều gọi DeepInfra).

## 1. Deploy backend

Render build `backend/Dockerfile` mỗi khi `main` đổi. Gói free không chạy lệnh trước deploy, nên
khi có migration mới thì chạy nó từ máy mình trước khi push:

```bash
cd backend
uv run pharma-agent --env-file .env.production migrate
```

Đổi biến môi trường: sửa `backend/.env.production` (hoặc `RENDER_SETTINGS` trong
`devops/render/configure.py`), rồi từ gốc repo chạy
`uv run --with httpx python devops/render/configure.py`. Script đẩy toàn bộ `PHARMA_*` lên Render
và deploy lại; lần đầu nó tạo service.

## 2. Nạp dữ liệu lần đầu từ máy mình

```bash
cd backend
uv run pharma-agent --env-file .env.production corpus import ../pharma-lab/data/corpus/formulary --collection formulary --publish
uv run pharma-agent --env-file .env.production check
```

Database production bắt đầu trống (chưa có tài khoản, hội thoại). Import tính embedding qua
DeepInfra; bundle đã có embedding sẵn thì dùng lại, không gọi API.

## 3. Kiểm tra sau khi lên

- [ ] `curl https://vipharmind.vercel.app/api/v1/health` trả `"status": "ok"` (lần đầu sau khi Render ngủ chờ khoảng một phút).
- [ ] Đăng ký bằng email trên trang Vercel, nhận mã qua Gmail, hỏi một câu và mở trích dẫn `[1]`.
- [ ] Cấp quyền quản trị cho mình:
      `uv run pharma-agent --env-file .env.production superadmin grant <email của bạn>`, tải lại
      trang và thấy mục **Quản trị**.
- [ ] Tạo một bộ tài liệu, thêm tài liệu, bấm **Xuất bản**: job chạy trong tiến trình backend và kết
      thúc ở "Đã xuất bản bản 1.".
- [ ] Mở **Cài đặt → Phiên đăng nhập**: `ip_address` phải là IP thật của bạn. Nếu là IP của
      Cloudflare hoặc Vercel thì `API_PROXY_SECRET` trên Vercel và `PHARMA_API__PROXY_SECRET` trên
      Render chưa khớp, hoặc Render đã đổi số proxy và phải đo lại `PHARMA_API__TRUSTED_PROXY_HOPS`.

## Khi cần scale

| Thành phần | Giới hạn đầu tiên | Bước nâng |
| --- | --- | --- |
| Backend Render Free | ngủ sau 15 phút, 512 MB | Render Starter không ngủ (khoảng 7 USD/tháng), hoặc Cloud Run với adapter Cloud Tasks |
| Frontend Vercel | điều khoản Hobby khi có thu phí | Vercel Pro (20 USD/tháng) hoặc chạy `frontend/Dockerfile` trên host khác |
| Neon | 0,5 GB | gói Launch 10 GB (19 USD/tháng) |
| Qdrant Cloud | 1 GB, đầy trước Neon | cluster trả phí (từ 25 USD/tháng) |
| DeepInfra | không có giới hạn cứng | khoảng 2 USD mỗi 1.000 lượt hỏi |
| Gmail API | khoảng 500 thư/ngày, gửi bằng Gmail cá nhân | Google Workspace với domain riêng (2.000 thư/ngày, cùng Gmail API) |
