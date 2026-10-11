# Checklist ra mắt

Những việc chỉ chủ tài khoản làm được (thẻ thanh toán, đăng nhập dịch vụ, secret). Làm theo thứ
tự; mỗi bước ghi lệnh hoặc chỗ bấm. Kiến trúc: frontend trên Vercel, backend trên Cloud Run, dữ
liệu trên Neon và Qdrant Cloud, model trên DeepInfra, thư qua Gmail SMTP.

## Trạng thái (cập nhật 2026-10-11)

Đã xong, không mất phí:

- [x] Google Cloud CLI và Vercel CLI cài trên máy, đã đăng nhập.
- [x] Project Google Cloud `vipharmind` đã tạo (chưa gắn thanh toán).
- [x] Neon: project ở Singapore, database `neondb`, DSN có pooler trong `backend/.env.production`; đã migrate tới `0020`.
- [x] Qdrant Cloud: cluster miễn phí `vipharmind` ở AWS US Oregon (gói Free không có châu Á), URL và API key trong `backend/.env.production`. Cluster Free tự tạm dừng sau 1 tuần không có truy vấn; uptime check vào `/health` giữ nó chạy.

**Để sau, cần thẻ hoặc tốn tiền** (làm khi đã có thẻ Visa):

- [ ] Mở lại tài khoản thanh toán Google Cloud `0135D1-DC225E-BD2890` (đang đóng), gắn vào project `vipharmind`, đặt cảnh báo ngân sách 1 USD và 5 USD.
- [ ] Bật API, Artifact Registry, Cloud Tasks, service account, Workload Identity, Secret Manager, job migrate và service Cloud Run (mục 3).
- [ ] Nạp corpus lên Neon và Qdrant (mục 2): gọi DeepInfra tính lại embedding cho 24.946 đoạn, khoảng 0,3 USD, vì embedding có sẵn trong bundle mang tên model local `qwen3-embedding:4b-fp16`.
- [ ] Kiểm tra số dư DeepInfra (mọi câu trả lời trên production đều gọi DeepInfra).
- [ ] Sau này nếu cần nhanh hơn: chuyển Qdrant sang cluster trả phí ở GCP `asia-southeast1` (cùng khu vực Cloud Run), đổi URL và key rồi nạp lại corpus.

## 1. Tài khoản và dịch vụ

- [ ] **Google Cloud:** tạo project `vipharmind`, gắn thẻ thanh toán, đặt cảnh báo ngân sách 1 USD
      và 5 USD (Billing → Budgets & alerts).
- [x] **Neon:** tạo project ở khu vực Singapore (`aws-ap-southeast-1`), lấy connection string
      **có pooler** (`-pooler` trong host) kèm `sslmode=require`.
- [x] **Qdrant Cloud:** tạo cluster miễn phí, lấy URL (cổng 6333) và API key.
- [ ] **DeepInfra:** key đã có; kiểm tra số dư.
- [ ] **Gmail:** bật xác minh hai bước cho tài khoản gửi thư, tạo App password.
- [x] **Vercel:** tạo tài khoản (import repo ở bước 4).

## 2. Nạp dữ liệu lần đầu từ máy mình

```bash
cd backend
cp .env.production.example .env.production      # điền DSN Neon, Qdrant, key DeepInfra
uv run pharma-agent --env-file .env.production migrate
uv run pharma-agent --env-file .env.production corpus import ../pharma-lab/data/corpus/formulary --collection formulary --publish
uv run pharma-agent --env-file .env.production check
```

Database production bắt đầu trống (chưa có tài khoản, hội thoại). Import tính embedding qua
DeepInfra; bundle đã có embedding sẵn thì dùng lại, không gọi API.

## 3. Backend trên Cloud Run

- [ ] Làm hết mục *Tạo tài nguyên một lần* và *Secret* trong `devops/cloud-run/README.md`.
- [ ] Sửa `PROJECT_ID`, email gửi thư và URL Vercel trong `devops/cloud-run/service.yaml`, tạo job
      migration và service, rồi chạy workflow `deploy-backend` một lần (Actions → Run workflow).
- [ ] Lấy URL `run.app` của service, đặt vào `PHARMA_JOBS__BACKEND_URL` trong `service.yaml`,
      `gcloud run services replace` lại.
- [ ] `curl https://<url run.app>/api/v1/health` trả `"status": "ok"`.

## 4. Frontend trên Vercel

- [ ] Làm theo mục *Deploy to Vercel* trong `frontend/README.md`: Root Directory `frontend`, bốn biến
      môi trường, Max Duration 300 s, tắt preview deploy.
- [ ] Thêm hai redirect URI của Vercel vào OAuth client Google đã có
      (`/auth/google/callback`, `/auth/google/link-callback`).
- [ ] Đặt `PHARMA_AUTH__FRONTEND_URL` của backend bằng origin Vercel (trong `service.yaml`).

## 5. Kiểm tra sau khi lên

- [ ] Đăng ký bằng email trên trang Vercel, nhận mã qua Gmail, hỏi một câu và mở trích dẫn `[1]`.
- [ ] Cấp quyền quản trị cho mình:
      `uv run pharma-agent --env-file .env.production superadmin grant <email của bạn>`, tải lại
      trang và thấy mục **Quản trị**.
- [ ] Tạo một bộ tài liệu, thêm tài liệu, bấm **Xuất bản**: tác vụ chạy qua Cloud Tasks và kết thúc
      ở "Đã xuất bản bản 1.".
- [ ] **Kiểm tra IP người dùng:** sau khi đăng nhập qua Vercel, mở **Cài đặt → Phiên đăng nhập**
      (gọi `GET /api/v1/account/sessions`); `ip_address` phải là IP thật của bạn. Nếu là IP của
      Vercel thì `API_PROXY_SECRET` trên Vercel và `PHARMA_API__PROXY_SECRET` trên Cloud Run chưa
      khớp: sai chỗ này thì giới hạn theo IP gom mọi người vào một IP.
- [ ] Uptime check của Cloud Monitoring vào `/api/v1/health` mỗi 5 phút, gửi thư khi lỗi.

## Khi cần scale

| Thành phần | Giới hạn đầu tiên | Bước nâng |
| --- | --- | --- |
| Backend Cloud Run | `maxScale: 1` | tăng `maxScale` trong `service.yaml` |
| Frontend Vercel | điều khoản Hobby khi có thu phí | Vercel Pro (20 USD/tháng) hoặc Cloud Run bằng `frontend/Dockerfile` |
| Neon | 0,5 GB | gói Launch 10 GB (19 USD/tháng) |
| Qdrant Cloud | 1 GB, đầy trước Neon | cluster trả phí (từ 25 USD/tháng) |
| DeepInfra | không có giới hạn cứng | khoảng 2 USD mỗi 1.000 lượt hỏi |
| Gmail SMTP | 500 thư/ngày | Resend với domain riêng |
