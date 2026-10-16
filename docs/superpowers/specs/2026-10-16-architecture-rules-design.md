# Spec: Quy tắc kiến trúc và bố cục cho frontend, backend và pharma-lab

Ngày: 2026-10-16. Trạng thái: chờ duyệt.

## 0. Mục tiêu và phạm vi

Ba project trong repo phải có quy tắc bố cục và ranh giới import rõ ràng, viết ở một chỗ, và mọi
quy tắc đều được một công cụ ép tự động. Kết quả gồm:

- Một file quy tắc chung `AGENTS.md` ở root, `CLAUDE.md` trỏ sang nó.
- Frontend giữ nguyên bố cục, bổ sung kiểm tra vị trí file test.
- Backend chuyển 8 quy tắc tầng từ test tự viết sang contract của import-linter.
- pharma-lab có thứ tự tầng, hết vòng import giữa các package, và contract import-linter ép.
- `lint-imports` chạy trong pre-commit và trong mục "Kiểm tra" của README.

Không đổi hành vi runtime của project nào. Không dời file test của frontend.

## 1. Hiện trạng (kiểm kê 2026-10-16)

- Frontend theo bố cục feature-based (`app/routes`, `app/features/<feature>/{components,hooks,lib}`,
  mã dùng chung ở `app/{api,components,hooks,i18n,lib}`). Ranh giới import được ép bằng
  `no-restricted-imports` trong `.oxlintrc.json` và `app/architecture.test.ts`. Sáu test đang pass.
  Test đặt cạnh file được test theo quy ước Vitest, README đã ghi. Không phải Clean Architecture
  kiểu domain/application/infrastructure và không cần.
- Backend theo Clean Architecture bốn tầng `api`, `application`, `infrastructure`, `domain`.
  `tests/architecture/test_layering.py` ép 8 quy tắc bằng duyệt AST tự viết, đang pass. README ghi
  đủ quy tắc.
- pharma-lab có 13 package dưới `src/pharma_lab/` nhưng không có quy tắc tầng. Đồ thị import giữa
  các package có sáu vòng: `artifacts` ↔ `evaluation`, `artifacts` ↔ `integrations`,
  `evaluation` ↔ `integrations`, `embeddings` ↔ `integrations`, `evaluation` ↔ `bundle` và
  `config` ↔ `runtime`. Nguyên nhân là sáu chỗ đặt sai tầng (mục 5.2). Ngoài ra `sha256_file` và `canonical_sha256`
  mỗi hàm có ba bản chép, và `Completion` có hai bản giống hệt nhau.
- Repo không có `AGENTS.md` hay `CLAUDE.md`. Quy tắc nằm rải trong README root và README từng
  project.

## 2. File quy tắc chung

`AGENTS.md` ở root, viết tiếng Việt như README root. `CLAUDE.md` ở root chỉ có một dòng `@AGENTS.md`.
Nội dung `AGENTS.md`, mỗi quy tắc nêu rõ công cụ ép nó:

1. Bố cục từng project, một đoạn ngắn mỗi project và link sang mục chi tiết trong README của
   project đó (`frontend/README.md#structure`, `backend/README.md#bố-cục`,
   `pharma-lab/README.md#cấu-trúc-project`).
2. Vị trí test. Frontend đặt `*.test.ts`, `*.test.tsx` và `*.browser.test.tsx` cạnh file được test
   trong `app/`; `frontend/tests/` chỉ chứa mã hỗ trợ (setup, MSW, fixture, helper render) và e2e
   Playwright `tests/e2e/*.e2e.ts`. Backend và pharma-lab đặt test trong `tests/` theo cây gương
   của `src/<package>/`, không có file test trong `src/`. Ép bằng `app/architecture.test.ts`
   (frontend) và một test ngắn `tests/test_layout.py` ở mỗi project Python khẳng định dưới `src/`
   không có `test_*.py`, `*_test.py` hay `conftest.py` (pytest chỉ thu thập `tests/`, nên một file
   test lạc vào `src/` sẽ im lặng không chạy nếu không có kiểm tra này).
3. Ranh giới import. Frontend: ép bằng oxlint và `app/architecture.test.ts`. Backend và pharma-lab:
   ép bằng import-linter, contract trong `pyproject.toml` của từng project. Muốn thêm một hướng
   import mới thì sửa cấu hình và README cùng lúc, không bỏ qua rule, không `# noqa`,
   không `import-linter: ignore`.
4. Lệnh kiểm tra của từng project và lệnh pre-commit chung (link sang README root, mục
   "Chuẩn tooling chung" và "Kiểm tra").
5. Các quy ước đã có ở README root (ruff, pyrefly, pytest, không tắt rule) nhắc bằng link, không
   chép lại.

## 3. Frontend

Không dời file. `app/architecture.test.ts` thêm hai test:

- Mọi file khớp `*.test.ts`, `*.test.tsx` nằm trong `app/`, và thư mục chứa nó có ít nhất một
  file nguồn `.ts` hoặc `.tsx` không phải test. Không đòi test trùng tên file nguồn, vì bảy test
  hiện có là test hợp đồng hay test gộp của cả thư mục (`architecture`, `public-page-locale`,
  `ui-stream-contract`, `history-prepend`, `test-support`, `elements`).
- `tests/` không chứa file khớp `*.test.*`; file e2e chỉ nằm ở `tests/e2e/*.e2e.ts`.

Mục "Structure" trong `frontend/README.md` thêm một câu nêu lý do đặt test cạnh code (quy ước
Vitest và React, `vitest.config.ts` gom theo glob `app/**/*.test.*`) và nói rõ `tests/` chỉ chứa mã
hỗ trợ.

## 4. Backend

Thêm `import-linter==2.15` vào dev group ở `pyproject.toml` root. Trong `backend/pyproject.toml`
khai báo `[tool.importlinter]` với `root_package = "pharma_agent"` và
`include_external_packages = true`, cùng các contract thay đúng 8 test hiện có:

| Contract | Kiểu | Nội dung |
| --- | --- | --- |
| layers | `layers` | `pharma_agent.api` > `pharma_agent.infrastructure` > `pharma_agent.application` > `pharma_agent.domain` |
| domain không dùng framework | `forbidden` | source `pharma_agent.domain`; forbidden `langgraph`, `langchain`, `langchain_core`, `openai`, `qdrant_client`, `sqlalchemy`, `fastapi`, `langfuse`, `httpx`, `fastembed` |
| application chỉ qua port | `forbidden` | source `pharma_agent.application`; forbidden `openai`, `qdrant_client`, `sqlalchemy`, `psycopg`, `alembic`, `fastapi`, `fastapi_users`, `starlette`, `langfuse`, `httpx`, `typer`, `uvicorn` |
| feature độc lập | `independence` | mọi package con có `__init__.py` trong `pharma_agent.application` |
| api không chạm domain | `forbidden` | source `pharma_agent.api`; forbidden `pharma_agent.domain` |
| router không chạm infrastructure | `forbidden` | source `pharma_agent.api.routers`; forbidden `pharma_agent.infrastructure` |

Contract layers đã bao gồm "domain không import tầng ngoài", "application không import
infrastructure hay api" và "infrastructure không import api". Khi `uv run lint-imports` pass trong
`backend/`, xóa `backend/tests/architecture/`. Mục "Bố cục" trong `backend/README.md` đổi câu
"Quy tắc phụ thuộc được kiểm tra bởi `tests/architecture/test_layering.py`" thành import-linter và
giữ nguyên danh sách quy tắc.

## 5. pharma-lab

### 5.1 Thứ tự tầng

Tầng trên được import tầng dưới. Package cùng tầng độc lập nhau.

| Tầng | Package | Vai trò |
| --- | --- | --- |
| 1 | `cli` | Entrypoint Typer, chỉ gọi xuống |
| 2 | `e2e`, `data_archive` | Harness chạy agent và lưu trữ dữ liệu |
| 3 | `evaluation`, `orchestration` | Pipeline đánh giá; build và publish rag-final |
| 4 | `bundle` | Export, embed, evaluation chunks |
| 5 | `embeddings` | Service embed local hoặc Kaggle |
| 6 | `integrations` | Kaggle (CLI, session, worker) |
| 7 | `corpus` | Trích xuất PDF, crawl, canonical, validation |
| 8 | `artifacts` | Contract artifact, manifest, JSONL, publisher |
| 9 | `cache` | Cache JSONL và embedding theo hash, khóa file |
| 10 | `runtime` | Catalog model, llama.cpp client, compose, helper asyncio |
| 11 | `config`, `hashing` | Đường dẫn, env, hàm hash thuần |

### 5.2 Module dời chỗ

| Từ | Đến | Lý do |
| --- | --- | --- |
| `evaluation/artifact_contracts.py` | gộp vào `artifacts/manifest.py` | `artifacts/` và `bundle/` đang import nó; hai class `Completion` giống hệt nhau gộp làm một. `artifacts/jsonl.py` (chỉ re-export `iter_jsonl_objects`) bị xóa, mọi chỗ import từ `artifacts/manifest.py`. |
| `evaluation/query_hash.py`, `evaluation/rerank_contract.py` | `pharma_lab/hashing.py` | Worker Kaggle đang import; là hàm thuần trên chuỗi. |
| `sha256_file` (3 bản), `canonical_sha256` (4 bản kể cả bản private) | một vòng lặp hash cho mỗi hàm trong `pharma_lab/hashing.py` | `runtime/runtime_profiles.py` dùng `canonical_sha256`, nên nơi định nghĩa phải ở dưới `runtime`. `artifacts/manifest.py` và `integrations/kaggle/artifacts.py` giữ wrapper `sha256_file` của riêng mình chỉ để đổi `OSError` thành `ArtifactContractError` (và cache digest ở manifest), vì gọi tới loại lỗi đó. |
| `embeddings/text_cache.py` | `cache/text_embeddings.py` | Worker `corpus_embed` đang import; `embeddings/service.py` gọi Kaggle nên cache phải nằm dưới `integrations`. |
| `integrations/kaggle/workers/scheduling.py` | `runtime/scheduling.py` | Helper asyncio thuần, `text_cache` cần nó. |
| `query_embedding_cache_path`, `text_embedding_cache_path`, `rerank_score_cache_path`, `rerank_log_path` trong `config/paths.py` | `cache/paths.py` | Bốn hàm này gọi `runtime.catalog.require_model`, tạo vòng `config` ↔ `runtime`. Hằng thư mục (`QUERY_EMBEDDING_CACHE_DIR`...) ở lại `config/paths.py`. Test tương ứng trong `tests/config/test_paths.py` sang `tests/cache/test_paths.py`. |
| `lock_file_name`, `_flock` (thành `flock`), `_LockHeldError` (thành `LockHeldError`) trong `integrations/kaggle/job_lock.py` | `cache/file_locks.py` | `artifacts/publisher.py` chỉ cần tên file khóa và thư mục khóa. `_acquire` và phần khóa tài khoản Kaggle (`kaggle_job_lock`, `kaggle_cache_lock`, `kaggle_account_lock`, `wait_for_kaggle_account`, `hold_pinned_account`, `KaggleAccountBusy`) ở lại `job_lock.py`, import từ `cache/file_locks.py`, và đọc thư mục khóa mặc định qua `config.paths.LOCK_DIR` lúc gọi để conftest đổi hướng ở một chỗ. |

Mỗi module dời giữ nguyên tên hàm, class và chữ ký. Mọi chỗ import sửa sang đường dẫn mới, không để
lại module re-export ở chỗ cũ. Test dời theo cây gương: `tests/test_hashing.py` mới cho `hashing.py`
(`tests/evaluation/test_rerank_contract.py` ở lại vì nó test `runtime/model_profiles.py`, không
test `rerank_contract.py`); `tests/embeddings/test_text_cache.py` thành
`tests/embeddings/test_service.py` vì nó test `embeddings/service.py` là chính;
`tests/integrations/kaggle/test_worker_scheduling.py` sang `tests/runtime/test_scheduling.py`;
hai test `lock_file_name` trong `tests/integrations/kaggle/test_job_lock.py` sang
`tests/cache/test_file_locks.py`; `tests/artifacts/test_manifest.py` và `tests/cache/test_paths.py`
mới cho hai module nhận code.

### 5.3 Contract import-linter

`[tool.importlinter]` trong `pharma-lab/pyproject.toml`, `root_packages = ["pharma_lab", "pharma_agent"]`
để contract nhìn thấy backend:

| Contract | Kiểu | Nội dung |
| --- | --- | --- |
| layers | `layers` | 11 tầng ở 5.1, tầng nhiều package viết `a \| b` |
| worker không import backend | `forbidden` | source `pharma_lab.integrations.kaggle.workers`; forbidden `pharma_agent` |
| chỉ dùng mặt công khai của backend | `forbidden` | source `pharma_lab`; forbidden `pharma_agent.api`, `pharma_agent.infrastructure.persistence` |

Quy tắc "worker không import backend" README đang hứa nhưng chưa ép. Danh sách module backend mà
pharma-lab được dùng vẫn do `tests/test_backend_public_api.py` giữ.

### 5.4 README

Mục "Cấu trúc project" trong `pharma-lab/README.md` viết lại theo bảng 5.1, thêm đoạn "Quy tắc phụ
thuộc" nêu ba contract và câu `uv run lint-imports` trong mục "Kiểm tra".

## 6. Pre-commit và lệnh kiểm tra

`.pre-commit-config.yaml` thêm hai hook local `lint-imports-backend` và `lint-imports-pharma-lab`
(`uv run --directory <project> lint-imports`, `pass_filenames: false`, `files: ^<project>/.*\.(py|toml)$`),
đặt ngay sau hook pyrefly của project đó. README root, mục "Kiểm tra", thêm dòng
`uv run lint-imports` vào khối lệnh chạy trong từng project Python; mục "Chuẩn tooling chung" thêm
gạch đầu dòng "import-linter: contract trong `pyproject.toml` của từng project; không dùng
`import-linter: ignore`".

## 7. Tiêu chí xong

- `uv run lint-imports` pass ở `backend/` và `pharma-lab/`.
- `backend/tests/architecture/` không còn; `uv run pytest -q` pass ở backend và pharma-lab.
- `npm test` ở frontend pass, gồm hai test vị trí file mới.
- `uv run pre-commit run --all-files` sạch từ root.
- `grep -r "evaluation.artifact_contracts\|evaluation.query_hash\|evaluation.rerank_contract\|embeddings.text_cache\|workers.scheduling"`
  trong `pharma-lab/` không còn kết quả, và `config/` không import `runtime`.
- `tests/test_layout.py` có ở backend và pharma-lab và pass.
- `AGENTS.md`, `CLAUDE.md`, ba README và README root đã cập nhật theo mục 2 đến 6.

## 8. Ngoài phạm vi

- Không đổi bố cục `app/` của frontend, không đổi ranh giới feature hiện có.
- Không đổi tầng hay feature của backend, chỉ đổi công cụ ép.
- Không gộp `artifacts/contract.py` (contract rag-final) với `artifacts/manifest.py` (manifest
  artifact đánh giá); hai contract khác mục đích.
