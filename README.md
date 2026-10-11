# ViPharMind: trợ lý AI tra cứu thuốc cho người Việt

| Thư mục | Nội dung |
| --- | --- |
| `pharma-lab/` | Công cụ offline: nguồn nội bộ (Dược thư Quốc gia, tờ hướng dẫn sử dụng thuốc) → knowledge bundle, embedding trên Kaggle, đánh giá retrieval |
| `backend/` | Backend AI agent (LangGraph, OpenAI SDK, Qdrant) |
| `frontend/` | Web app (React Router, SSR) |
| `devops/` | Cấu hình cho image bên thứ ba mà compose dùng: nginx, CLIProxyAPI |
| `compose.yaml` | Stack local: Postgres, Qdrant, backend, frontend, nginx. Model gọi DeepInfra theo `backend/.env` |
| `compose.local-models.yaml` | Override: embedding và reranker llama.cpp chạy CPU trên máy |
| `compose.gemini-proxy.yaml` | Override: LLM là Gemini qua CLIProxyAPI |

## Chạy local

Chạy từ repo root. Không có `.env` ở root: mọi biến của compose (port, file model, số luồng CPU) có
giá trị mặc định ngay trong file compose, muốn ghi đè thì đặt biến shell, ví dụ
`WEB_PORT=8081 docker compose up -d`. Ba file cấu hình của repo là `backend/.env`, `frontend/.env` và
`pharma-lab/.env`, mỗi file có `.env.example` bên cạnh.

Mặc định LLM, embedding và reranker đều gọi DeepInfra (Qwen3.5-9B, Qwen3-Embedding-4B,
Qwen3-Reranker-4B), giống production. Tạo `backend/.env` từ `backend/.env.example`, điền cùng một key
DeepInfra vào ba biến `..._API_KEY`, rồi `PHARMA_AUTH__JWT_SECRET`, `PHARMA_AUTH__CSRF_SECRET`,
`PHARMA_AUTH__OTP_SECRET` và `PHARMA_JOBS__INTERNAL_TOKEN`.

Cách làm việc hằng ngày: chỉ chạy dữ liệu trong Docker, backend và frontend chạy trên máy.

```bash
docker compose up -d postgres qdrant
uv run --directory backend pharma-agent migrate
uv run --directory backend pharma-agent serve          # http://127.0.0.1:8000
npm --prefix frontend run dev                          # http://localhost:3000, Vite chuyển /api sang backend
```

Chạy cả stack trong Docker (trình duyệt vào qua nginx ở `http://localhost:8080`):

```bash
docker compose up -d --build
docker compose ps                              # chờ mọi service healthy
docker compose exec backend pharma-agent check
docker compose exec backend pharma-agent ask "Paracetamol người lớn uống tối đa bao nhiêu một ngày?"
```

- `backend-migrate` chạy `pharma-agent migrate` một lần trước khi backend khởi động.
- Cookie phiên có cờ `Secure`, trình duyệt chỉ nhận qua `http://localhost`; mở stack qua HTTP bằng
  tên máy khác (ví dụ IP LAN) thì chạy với `COOKIE_SECURE=false`.
- Lần đầu cần nạp corpus: `uv run --directory backend pharma-agent corpus import ../pharma-lab/data/corpus/formulary --collection formulary --publish`
  (trong Docker: `docker compose cp pharma-lab/data/corpus/formulary backend:/tmp/bundle` rồi
  `docker compose exec backend pharma-agent corpus import /tmp/bundle --collection formulary --publish`).
  Embedding phải là model đã dùng khi import corpus; `/health` báo `CORPUS_NOT_READY` nếu metadata
  collection không khớp.

### Chạy model trên CPU (`compose.local-models.yaml`)

Embedding và reranker chạy bằng llama.cpp trên máy thay cho DeepInfra, cần file GGUF trong
`ai-models/gguf` (xem `pharma-lab`).

```bash
docker compose -f compose.yaml -f compose.local-models.yaml up -d                      # cả stack
docker compose -f compose.yaml -f compose.local-models.yaml up -d llama-embedding llama-reranker  # chỉ model, backend chạy trên máy
```

Backend chạy trên máy thì đổi các biến embedding và rerank trong `backend/.env` sang khối
"llama.cpp" có sẵn trong `backend/.env.example`; container backend thì file override tự đặt.

- Hai model 4B chạy trên CPU nên lần đầu nạp model mất vài phút; backend chỉ khởi động khi
  embedding và reranker đã healthy.
- Đổi sang GGUF nhẹ hơn: đặt `LLAMA_EMBEDDING_MODEL` hoặc `LLAMA_RERANKER_MODEL` là tên file trong
  `ai-models/gguf`. Reranker chỉ chạy qua `/v1/rerank`, nên file GGUF phải là bản convert
  classifier (có tensor `cls.output.weight`); đặt `LLAMA_RERANKER_PROTOCOL=none` để bỏ rerank.
- Reranker trên CPU: `LLAMA_RERANKER_PARALLEL` (`-np`), `LLAMA_RERANKER_UBATCH_SIZE` (dùng chung cho `-b`
  và `-ub`, tối thiểu 4096 và phải chứa được prompt dài nhất), `LLAMA_RERANKER_CONTEXT_SIZE` (`-c`, bằng
  `-ub` nhân số slot cộng một) và `LLAMA_RERANKER_THREADS`; `RERANK_TIMEOUT_SECONDS` là timeout của
  backend cho một request rerank. Đo lại cho máy khác trong `pharma-lab/`:
  `uv run pharma-lab rerank --run hybrid-qwen4b-p50-k30-rrf2 --backend local --benchmark --model qwen3-reranker:4b-fp16`,
  rồi đặt các biến trong dòng `env=` lệnh in ra, với `RERANK_TIMEOUT_SECONDS` ít nhất gấp đôi
  `latency_p95_seconds`.

### LLM Gemini qua CLIProxyAPI (`compose.gemini-proxy.yaml`)

1. Tạo `devops/cli-proxy-api/config.yaml` từ `config.example.yaml` cùng thư mục và thay `api-keys`;
   `PHARMA_LLM__DEFAULT__API_KEY` phải là một trong các key đó, model Gemini đặt theo khối
   "Gemini" trong `backend/.env.example`.
2. Đăng nhập tài khoản Antigravity (Google) cho CLIProxyAPI. Lệnh in ra một URL: mở URL bằng trình
   duyệt trên cùng máy và đăng nhập; Google chuyển về `localhost:51121`, token được lưu vào volume
   `cli_proxy_auth` và lệnh tự kết thúc.

   ```bash
   docker compose -f compose.yaml -f compose.gemini-proxy.yaml run --rm -p 51121:51121 cli-proxy-api ./CLIProxyAPI --antigravity-login -no-browser
   ```

   Nhà cung cấp khác dùng cờ tương ứng (`--codex-login`, `--claude-login`, ...), cổng callback đổi
   được bằng `--oauth-callback-port`.
3. `docker compose -f compose.yaml -f compose.gemini-proxy.yaml up -d`. Hai override dùng chung
   được: thêm cả `-f compose.local-models.yaml`.

## Production

Frontend chạy trên Vercel, backend trên Render Free (Docker, Singapore, tác vụ xuất bản chạy
trong tiến trình API), Postgres trên Neon (Singapore), vector trên Qdrant Cloud, LLM, embedding và
reranker trên DeepInfra, thư qua Gmail SMTP. Trình duyệt chỉ gọi origin Vercel; route `/api/*` của
frontend chuyển tiếp sang Render nên cookie là first-party. Gói free của Render ngủ sau 15 phút
không có request, lần gọi kế tiếp chờ khoảng một phút; cron Vercel gọi `/api/v1/health` mỗi ngày để
Qdrant free không bị xoá vì không hoạt động.

- Các bước dựng lần đầu và đường scale: `docs/launch-checklist.md`.
- Backend: Render tự build `backend/Dockerfile` khi push `main`. Chạy migration trước bằng
  `uv run pharma-agent --env-file .env.production migrate` trong `backend/`. Tạo service hoặc đẩy
  lại biến môi trường từ `backend/.env.production` (kèm `RENDER_API_KEY`):
  `uv run --with httpx python devops/render/configure.py`.
- Frontend: mục *Deploy to Vercel* trong `frontend/README.md`.
- CLI trỏ vào production từ máy mình: `uv run pharma-agent --env-file .env.production <lệnh>`
  (mẫu ở `backend/.env.production.example`).

## Môi trường Python

`backend` và `pharma-lab` là member của một uv workspace (`pyproject.toml` ở root): chung một
`uv.lock` và một `.venv` ở root. Runtime chỉ là `backend`; `pharma-lab` là công cụ nội bộ nên
mọi thư viện của nó nằm trong dev group, image Docker của backend không chứa chúng.

Cài một lần ở root:

```bash
uv sync
```

Chỉ chạy `uv sync` ở root: chạy trong một project sẽ gỡ khỏi `.venv` chung các gói của project
kia. Trong từng project dùng `uv run ...`, lệnh này không gỡ gói nào. Trong IDE, mở thư mục root
và chọn interpreter `.venv/bin/python`.

## Chuẩn tooling chung

Mọi project Python trong repo dùng cùng một chuẩn, không project nào được tắt rule riêng:

- **Python** 3.12, ghi trong `.python-version` ở root; môi trường do `uv` quản lý.
- **uv** pin bằng `required-version` trong `pyproject.toml` ở root; image backend và hook
  `uv-lock` dùng đúng phiên bản đó.
- **Build backend** `uv_build`.
- **Ruff**: cấu hình duy nhất ở `ruff.toml` tại root; `pyproject.toml` của từng project chỉ
  `extend` file này và khai báo `src`.
- **Pyrefly**: `pyrefly.toml` giống hệt nhau ở mọi project, không tắt nhóm lỗi nào;
  cảnh báo cũng phải bằng 0.
- **Pytest**: `asyncio_mode = "auto"`, `--import-mode=importlib`, test cần Docker gắn marker
  `integration`.
- **Phiên bản dev tool** (`ruff`, `pyrefly`, `pytest`, `pytest-asyncio`, `pre-commit`) pin một lần
  trong dev group của `pyproject.toml` ở root.
- **Dockerfile** nằm cạnh code nó build, kèm `Dockerfile.dockerignore`; hadolint kiểm tra trong
  pre-commit.

Lỗi lint hoặc lỗi kiểu được sửa trong code, không dùng `# noqa`, `# type: ignore` hay tắt rule.

## Kiểm tra

Chạy trong từng project:

```bash
uv run ruff check src tests && uv run ruff format --check src tests
uv run pyrefly check --min-severity warn
uv run pytest -q
```

Pre-commit dùng chung cho cả repo, cài một lần từ root:

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```
