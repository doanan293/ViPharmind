# Checklist ra mắt

Những việc chỉ chủ tài khoản làm được (đăng nhập dịch vụ, nạp tiền, secret). Kiến trúc: frontend
và backend trên Vercel, dữ liệu trên Neon và Qdrant Cloud, model trên DeepInfra, thư qua Resend. Mọi dịch vụ đang dùng gói miễn phí; chỉ DeepInfra cần nạp tiền.

## Trạng thái (cập nhật 2026-10-12)

Đã xong, không mất phí:

- [x] Neon: project ở Singapore, database `neondb`, DSN có pooler trong `backend/.env.production`; đã migrate tới `0020`.
- [x] Qdrant Cloud: cluster miễn phí `vipharmind` ở AWS US Oregon (gói Free không có châu Á), URL và API key trong `backend/.env.production`. Cluster Free tự tạm dừng sau 1 tuần không có truy vấn; cron Vercel gọi `/api/v1/health` mỗi ngày giữ nó chạy.
- [x] Secret production (JWT, CSRF, OTP, proxy, token nội bộ) đã sinh trong `backend/.env.production`.
- [x] Backend trên Vercel: project `vipharmind-api` (FastAPI Function, region `sin1`, Large Functions, nối GitHub) chạy ở https://vipharmind-api.vercel.app, tự deploy khi push `main`. Không ngủ như Render; khởi động lạnh khoảng 10 giây, sau đó dưới 1 giây. `/api/v1/health` báo Postgres ổn, `corpus` chưa sẵn sàng vì chưa nạp corpus. Đã đo `PHARMA_API__TRUSTED_PROXY_HOPS=1`: IP thật của khách được nhận đúng cả khi gọi thẳng lẫn qua frontend.
- [x] Vercel: project `vipharmind`, preset React Router, Root Directory `frontend`, nối GitHub, https://vipharmind.vercel.app chạy; đã đặt `API_INTERNAL_URL`, `PUBLIC_SITE_URL`, `THEME_COOKIE_SECRET`, `API_PROXY_SECRET`. Đăng nhập sai mật khẩu qua Vercel trả đúng `LOGIN_BAD_CREDENTIALS`.

Việc miễn phí còn lại, cần bạn làm trên web:

- [ ] Đăng nhập Google (hoãn được, khi chưa có client thì nút Google tự ẩn): mọi app dùng chung project Google Cloud `andimus`. Tạo màn hình đồng ý (External, Publish app), rồi tạo OAuth client Web `ViPharMind` với redirect URI `https://vipharmind.vercel.app/auth/google/callback`, `https://vipharmind.vercel.app/auth/google/link-callback` và hai URI tương ứng trên `http://localhost:3000`. Ghi `PHARMA_AUTH__GOOGLE_CLIENT_ID` và `PHARMA_AUTH__GOOGLE_CLIENT_SECRET` vào `backend/.env.production`, rồi chạy `uv run python devops/vercel/sync_env.py`.
- [x] Gửi thư qua Resend: key `andimus` (dùng chung cho các app) đã đặt trên backend, gửi từ `onboarding@resend.dev`; thư thử tới `andoan020903@gmail.com` có trạng thái `sent`.
- [ ] Domain cho thư: `onboarding@resend.dev` chỉ gửi tới email chủ tài khoản Resend, nên người khác chưa nhận được mã. Mua domain, xác minh `mail.<domain>` trên Resend (bản ghi SPF, DKIM, MX), đổi `PHARMA_EMAIL__SENDER` sang `no-reply@mail.<domain>`, rồi chạy `devops/vercel/sync_env.py`. Không dùng được `*.vercel.app` vì không sửa được DNS của nó.

**Để sau, tốn tiền:**

- [ ] Nạp tiền DeepInfra, rồi nạp corpus lên Neon và Qdrant (mục 2): gọi DeepInfra tính embedding `Qwen/Qwen3-Embedding-8B` cho 24.946 đoạn, khoảng 0,3–0,5 USD. Trước bước này chat chưa trả lời được.
- [ ] Kiểm tra số dư DeepInfra định kỳ (mọi câu trả lời trên production đều gọi DeepInfra).

## 1. Deploy backend

Vercel build backend mỗi khi `main` đổi. Vercel không chạy migration, nên khi có migration mới thì
chạy nó từ máy mình trước khi push:

```bash
cd backend
uv run pharma-agent --env-file .env.production migrate
```

Đổi biến môi trường: sửa `backend/.env.production` (hoặc `VERCEL_SETTINGS` trong
`devops/vercel/sync_env.py`), rồi từ gốc repo chạy `uv run python devops/vercel/sync_env.py`.
Script đẩy toàn bộ `PHARMA_*` lên project `vipharmind-api` và redeploy. Không deploy backend
bằng `vercel deploy` từ máy, vì CLI tải cả file `.env` lên.

## 2. Nạp dữ liệu lần đầu từ máy mình

```bash
cd backend
uv run pharma-agent --env-file .env.production corpus import ../pharma-lab/data/corpus/formulary --collection formulary --publish
uv run pharma-agent --env-file .env.production check
```

Database production bắt đầu trống (chưa có tài khoản, hội thoại). Import tính embedding qua
DeepInfra; bundle đã có embedding sẵn thì dùng lại, không gọi API.

## 3. Kiểm tra sau khi lên

- [ ] `curl https://vipharmind.vercel.app/api/v1/health` trả `"status": "ok"`.
- [ ] Đăng ký bằng email trên trang Vercel, nhận mã qua email, hỏi một câu và mở trích dẫn `[1]`.
- [ ] Cấp quyền quản trị cho mình:
      `uv run pharma-agent --env-file .env.production superadmin grant <email của bạn>`, tải lại
      trang và thấy mục **Quản trị**.
- [ ] Tạo một bộ tài liệu, thêm tài liệu, bấm **Xuất bản**: job chạy ngay trong request xuất bản
      (tối đa 300 giây) và kết thúc ở "Đã xuất bản bản 1.".
- [ ] Mở **Cài đặt → Phiên đăng nhập**: `ip_address` phải là IP thật của bạn. Nếu là IP của
      Vercel thì `API_PROXY_SECRET` của project `vipharmind` và `PHARMA_API__PROXY_SECRET` của
      `vipharmind-api` chưa khớp, hoặc phải đo lại `PHARMA_API__TRUSTED_PROXY_HOPS`.

## Khi cần scale

| Thành phần | Giới hạn đầu tiên | Bước nâng |
| --- | --- | --- |
| Vercel Hobby (frontend và backend) | chỉ dùng phi thương mại; function tối đa 300 giây, 4 giờ CPU mỗi tháng | Vercel Pro (20 USD/tháng) |
| Neon | 0,5 GB | gói Launch 10 GB (19 USD/tháng) |
| Qdrant Cloud | 1 GB, đầy trước Neon | cluster trả phí (từ 25 USD/tháng) |
| DeepInfra | không có giới hạn cứng | khoảng 2 USD mỗi 1.000 lượt hỏi |
| Resend Free | 3.000 thư/tháng, 100 thư/ngày | gói Pro (20 USD/tháng, 50.000 thư) |
