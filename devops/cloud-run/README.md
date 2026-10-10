# Backend trên Google Cloud Run

Backend chạy thành service `vipharmind-api` ở `asia-southeast1`, tối đa một instance, không có
instance nào khi không có request. Mỗi lần `main` đổi phần backend, workflow
`.github/workflows/deploy-backend.yml` build image, chạy migration bằng job `vipharmind-migrate`, rồi
deploy image mới. Tác vụ xuất bản bộ tài liệu đi qua Cloud Tasks (queue `ingest`), Cloud Tasks gọi lại
backend bằng OIDC token của service account `vipharmind-tasks`.

## Tạo tài nguyên một lần

Đặt biến rồi chạy từng khối. `PROJECT_ID` là project đã gắn thẻ thanh toán.

```bash
PROJECT_ID=vipharmind
REGION=asia-southeast1
REPO=<owner>/<repo trên GitHub>
gcloud config set project "$PROJECT_ID"

gcloud services enable run.googleapis.com cloudtasks.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com \
  iamcredentials.googleapis.com cloudbuild.googleapis.com

# Image
gcloud artifacts repositories create vipharmind --repository-format docker --location "$REGION"

# Service account của API, của Cloud Tasks và của GitHub Actions
gcloud iam service-accounts create vipharmind-api
gcloud iam service-accounts create vipharmind-tasks
gcloud iam service-accounts create vipharmind-deploy
API_SA="vipharmind-api@$PROJECT_ID.iam.gserviceaccount.com"
TASKS_SA="vipharmind-tasks@$PROJECT_ID.iam.gserviceaccount.com"
DEPLOY_SA="vipharmind-deploy@$PROJECT_ID.iam.gserviceaccount.com"

# API: đọc secret, đẩy task, ký OIDC token thay cho TASKS_SA
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:$API_SA" --role roles/secretmanager.secretAccessor
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:$API_SA" --role roles/cloudtasks.enqueuer
gcloud iam service-accounts add-iam-policy-binding "$TASKS_SA" --member "serviceAccount:$API_SA" --role roles/iam.serviceAccountUser

# Queue: một tác vụ chạy một lúc, tối đa 3 lần thử
gcloud tasks queues create ingest --location "$REGION" \
  --max-concurrent-dispatches 1 --max-attempts 3

# GitHub Actions: Workload Identity Federation, không có key JSON
gcloud iam workload-identity-pools create github --location global
gcloud iam workload-identity-pools providers create-oidc github --location global \
  --workload-identity-pool github --issuer-uri https://token.actions.githubusercontent.com \
  --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition "assertion.repository == '$REPO'"
POOL="$(gcloud iam workload-identity-pools describe github --location global --format 'value(name)')"
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --member "principalSet://iam.googleapis.com/$POOL/attribute.repository/$REPO" \
  --role roles/iam.workloadIdentityUser
for role in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:$DEPLOY_SA" --role "$role"
done
```

Trên GitHub (Settings → Secrets and variables → Actions):

| Loại | Tên | Giá trị |
| --- | --- | --- |
| Variable | `GCP_PROJECT_ID` | `$PROJECT_ID` |
| Secret | `GCP_WORKLOAD_IDENTITY_PROVIDER` | `$POOL/providers/github` |
| Secret | `GCP_DEPLOY_SERVICE_ACCOUNT` | `$DEPLOY_SA` |

## Secret

Mỗi biến là một secret cùng tên trong Secret Manager; `DEEPINFRA_API_KEY` dùng chung cho LLM,
embedding và reranker.

```bash
printf '%s' 'giá trị' | gcloud secrets create TÊN --data-file=-
```

| Secret | Nội dung |
| --- | --- |
| `PHARMA_POSTGRES__DSN` | DSN Neon có pooler, dạng `postgresql+psycopg://...?sslmode=require` |
| `PHARMA_QDRANT__URL`, `PHARMA_QDRANT__API_KEY` | Cluster Qdrant Cloud |
| `DEEPINFRA_API_KEY` | Key DeepInfra |
| `PHARMA_AUTH__JWT_SECRET`, `PHARMA_AUTH__CSRF_SECRET`, `PHARMA_AUTH__OTP_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` cho mỗi cái |
| `PHARMA_AUTH__GOOGLE_CLIENT_ID`, `PHARMA_AUTH__GOOGLE_CLIENT_SECRET` | OAuth client Google đã có |
| `PHARMA_EMAIL__SMTP_PASSWORD` | App password Gmail của tài khoản gửi thư |

Biến thường (model, URL, Cloud Tasks) nằm ngay trong `service.yaml`.

## Service và job migration

Thay `PROJECT_ID`, `SENDER@gmail.com` và hai URL trong `service.yaml` rồi tạo lần đầu. Image đầu
tiên phải có sẵn, nên chạy workflow một lần bằng *Run workflow* sau khi tạo job, hoặc build tay.

```bash
gcloud run jobs replace devops/cloud-run/migrate-job.yaml --region "$REGION"
gcloud run services replace devops/cloud-run/service.yaml --region "$REGION"
gcloud run services add-iam-policy-binding vipharmind-api --region "$REGION" \
  --member allUsers --role roles/run.invoker
```

`PHARMA_JOBS__BACKEND_URL` là URL `run.app` của service (xem bằng
`gcloud run services describe vipharmind-api --region $REGION --format 'value(status.url)'`), sau khi
có URL thì sửa `service.yaml` và `replace` lại. Đổi biến thường về sau cũng làm như vậy.

## Chi phí

`maxScale: 1` giới hạn chi phí, CPU chỉ tính khi có request. Đặt cảnh báo ngân sách 1 USD và 5 USD
trong Billing → Budgets & alerts. Uptime check của Cloud Monitoring vào `/api/v1/health` mỗi 5 phút.
