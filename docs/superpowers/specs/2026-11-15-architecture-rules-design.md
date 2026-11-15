# Quy tắc kiến trúc và bố cục cho frontend, backend và pharma-lab

Ngày: 2026-11-15. Trạng thái: hiện hành, mô tả mã của nhánh `v2.0.0` (commit `9732e8e`).

Spec này gom bản thiết kế `2026-10-16-architecture-rules-design.md` và plan cùng tên (đã chạy xong)
thành một mô tả của thứ mã đang có. Bản tóm tắt ngắn cho người và agent vẫn là `AGENTS.md` ở root
(`CLAUDE.md` chỉ có dòng `@AGENTS.md`). Spec này nói rõ hơn: quy tắc nào được máy kiểm tra, bằng công
cụ nào, ở file nào, chạy lúc nào; quy tắc nào chỉ là quy ước.

## 1. Mục tiêu và phạm vi

- Ba project `frontend/`, `backend/`, `pharma-lab/` mỗi project có bố cục và ranh giới import viết
  rõ ở một chỗ.
- Mỗi ranh giới import có một công cụ kiểm tra tự động. Muốn thêm một hướng import mới thì sửa cấu
  hình và README cùng lúc, không bỏ qua rule.
- Không có vòng import giữa các package của pharma-lab.
- File test nằm đúng chỗ để test runner thực sự thu thập nó.

Phạm vi là cấu trúc mã và công cụ ép cấu trúc. Nội dung nghiệp vụ của từng tầng thuộc spec của mảng
tương ứng (mục 6).

## 2. Nguyên tắc chung

- Không `# noqa`, không `# type: ignore`, không `ignore_imports` trong contract import-linter, không
  tắt rule lint. Lỗi được sửa trong mã. Trên `v2.0.0` không có `# noqa`, `# type: ignore` hay
  `ignore_imports` nào.
- Ngoại lệ duy nhất đang có: một `# pyrefly: ignore[bad-argument-type]` ở
  `backend/src/pharma_agent/infrastructure/auth/users.py` cho lỗi dương tính giả của pyrefly 1.3.0,
  có chú thích lý do. `pyrefly.toml` bật `unused-ignore = true`, nên khi pyrefly sửa lỗi này thì
  comment đó thành lỗi và phải gỡ.
- Dev tool pin một lần ở dev group của `pyproject.toml` root: `import-linter==2.15`,
  `pre-commit==4.6.2`, `pyrefly==1.3.0`, `pytest==9.1.1`, `pytest-asyncio==1.4.0`, `ruff==0.16.7`.

## 3. Bố cục hiện hành

### 3.1 Frontend (feature-based)

- `app/routes/`: route module, mỏng, ghép feature. `app/routes.ts`, `root.tsx`, `entry.*.tsx` ở gốc
  `app/`.
- `app/features/<feature>/`: 11 feature `admin`, `audit`, `auth`, `chat`, `collections`,
  `conversations`, `landing`, `legal`, `organizations`, `settings`, `shell`. Mỗi feature chỉ có các
  thư mục con `components/`, `hooks/`, `lib/` (không bắt buộc đủ cả ba).
- Mã dùng chung: `app/api/` (trong đó `app/api/gen/` do orval sinh từ OpenAPI của backend),
  `app/components/`, `app/hooks/`, `app/i18n/`, `app/lib/`.
- Test Vitest (`*.test.ts`, `*.test.tsx`, `*.browser.test.tsx`) nằm trong `app/`, cạnh mã được test.
  `vitest.config.ts` thu thập `app/**/*.test.{ts,tsx}` (project `unit`) và
  `app/**/*.browser.test.tsx` (project `browser`).
- `tests/` chỉ chứa mã hỗ trợ (`setup/`, `msw/`, `utils/`, `chat/`, `public/` cho MSW service worker)
  và e2e Playwright ở `tests/e2e/*.e2e.ts`.

Frontend không theo Clean Architecture kiểu domain/application/infrastructure; bố cục feature-based
đủ cho một SPA cỡ này.

### 3.2 Backend (Clean Architecture bốn tầng)

`backend/src/pharma_agent/`:

- `domain/`: `access`, `account`, `agent`, `audit`, `conversation`, `corpus`, `feedback`,
  `guardrail`, `llm`, `organizations`, `retrieval`, `shared`. Python không framework; được dùng
  `pydantic`, `phonenumbers` và thư viện chuẩn.
- `application/`: 10 feature `access`, `account`, `admin`, `audit`, `chat`, `conversation`,
  `corpus`, `feedback`, `memory`, `organizations`; module chung ở gốc: `errors.py`, `mail.py`,
  `pagination.py`, `progress.py`, `tracing.py`. Thư viện bên ngoài mà application import: `pydantic`,
  LangGraph và LangChain; mọi DB, SDK, HTTP khác đi qua port của `domain`.
- `infrastructure/`: adapter (`auth`, `jobs`, `llm`, `notifications`, `observability`,
  `persistence`, `retrieval`), `settings.py`, các factory và composition root (`composition.py`,
  `container.py`).
- `api/`: `app.py`, `asgi.py`, `deps.py`, `routers/`, `schemas.py`, `ui_stream.py`...
- `cli.py` nằm ngoài bốn tầng, là entrypoint Typer.

Test ở `backend/tests/`: cây gương `api/`, `application/`, `domain/`, `infrastructure/`, cộng
`contract/` (fixture SSE byte-exact), `e2e/`, `fixtures/` và các module fake, helper ở gốc.

### 3.3 pharma-lab (11 tầng)

`pharma-lab/src/pharma_lab/`, tầng trên được import tầng dưới, package cùng tầng không import nhau:

| Tầng | Package | Vai trò |
| --- | --- | --- |
| 1 | `cli` | Entrypoint `uv run pharma-lab`, chỉ gọi xuống |
| 2 | `e2e`, `data_archive` | Harness chạy agent end-to-end; lưu trữ dữ liệu lên Kaggle |
| 3 | `evaluation`, `orchestration` | Pipeline đánh giá retrieval; build và publish `rag-final` |
| 4 | `bundle` | Export, embed, evaluation chunks |
| 5 | `embeddings` | Embed local (llama.cpp) hoặc trên Kaggle |
| 6 | `integrations` | Kaggle: session, checkpoint, worker |
| 7 | `corpus` | Trích xuất PDF, crawl, canonical blocks, validation |
| 8 | `artifacts` | Contract `rag-final`, manifest artifact đánh giá, publisher |
| 9 | `cache` | Cache JSONL và embedding theo hash, đường dẫn cache theo model, khóa file |
| 10 | `runtime` | Catalog model, llama.cpp client, compose, helper asyncio |
| 11 | `config`, `hashing` | Đường dẫn, env; hàm hash thuần |

Test ở `pharma-lab/tests/` theo cây gương của các package trên, cộng các test cấp project ở gốc
(`test_layout.py`, `test_backend_public_api.py`, `test_dependency_pins.py`,
`test_repository_data_policy.py`, `test_docs.py`...).

## 4. Quy tắc được máy kiểm tra

Repo không có CI. Mọi kiểm tra dưới đây chỉ chạy khi có người chạy: qua pre-commit (cài bằng
`uv run pre-commit install`, chỉ chạy hook có file khớp trong commit) hoặc khi chạy test suite bằng
tay. Cột "Chạy lúc" ghi rõ điều đó.

### 4.1 Frontend

| Quy tắc | Công cụ | Ở đâu | Chạy lúc |
| --- | --- | --- | --- |
| Mã dùng chung (`app/{api,components,hooks,i18n,lib}`) không import `~/features` hay `~/routes` | oxlint `no-restricted-imports` | override đầu tiên trong `frontend/.oxlintrc.json` | pre-commit `frontend-lint`; `npm run lint` |
| Feature không import route | oxlint `no-restricted-imports` | override từng `app/features/<f>/**` | như trên |
| Feature chỉ import feature khác theo các hướng một chiều: `chat` → `conversations`; `shell` → `auth`, `conversations`; `organizations` → `audit`; `admin` → `auth`, `chat`, `audit` | oxlint `no-restricted-imports` | override từng feature | như trên |
| Không vòng import | oxlint `import/no-cycle` | `rules` trong `.oxlintrc.json` | như trên |
| Cả ba quy tắc ranh giới trên, kiểm tra lại bằng cách resolve mọi import (cả import tương đối, `import()` và `vi.mock()`), bỏ qua file test và `app/api/gen/` | Vitest | `frontend/app/architecture.test.ts`, bảng `ALLOWED_FEATURE_IMPORTS` | `npm test` / `npm run test:unit` (không có trong pre-commit) |
| Bảng hướng import trong test khớp với override oxlint, và mỗi feature có override | Vitest | `architecture.test.ts`, test "the oxlint boundary rules match..." | như trên |
| Mỗi feature chỉ có thư mục con `components`, `hooks`, `lib` | Vitest | `architecture.test.ts` | như trên |
| Mọi file `*.test.ts(x)` nằm trong `app/`, trong thư mục có ít nhất một file nguồn không phải test | Vitest | `architecture.test.ts`, khối "frontend test placement" | như trên |
| `tests/` không có `*.test.*`; file `*.e2e.ts` chỉ ở `tests/e2e/` | Vitest | như trên | như trên |
| `app/api/gen/` khớp `openapi.json` | orval + `git diff --exit-code` | `npm run api:check` | pre-commit `frontend-api-drift` |

Lint chạy `oxlint --type-aware --deny-warnings` với category `correctness` và `suspicious` ở mức
error. Thêm một hướng import giữa hai feature nghĩa là sửa cả `ALLOWED_FEATURE_IMPORTS` lẫn override
oxlint, và mục "Structure" của `frontend/README.md`.

### 4.2 Backend

Contract import-linter trong `[tool.importlinter]` của `backend/pyproject.toml`
(`root_package = "pharma_agent"`, `include_external_packages = true`):

| Contract (tên trong cấu hình) | Kiểu | Nội dung |
| --- | --- | --- |
| `api > infrastructure > application > domain` | `layers` | Tầng dưới không import tầng trên. Bao gồm: domain không import tầng nào khác; application không import infrastructure hay api; infrastructure không import api. |
| `domain is framework-free` | `forbidden` | `pharma_agent.domain` không import `langgraph`, `langchain`, `langchain_core`, `openai`, `qdrant_client`, `sqlalchemy`, `fastapi`, `langfuse`, `httpx`, `fastembed`, `typesafe_sdk` |
| `application reaches databases, SDKs and transports only through domain ports` | `forbidden` | `pharma_agent.application` không import `openai`, `qdrant_client`, `sqlalchemy`, `psycopg`, `alembic`, `fastapi`, `fastapi_users`, `starlette`, `langfuse`, `httpx`, `typesafe_sdk`, `typer`, `uvicorn` |
| `application features are independent` | `independence` | 10 feature trong `application/` không import nhau |
| `api calls application, never domain` | `forbidden`, `allow_indirect_imports = true` | `pharma_agent.api` không import trực tiếp `pharma_agent.domain` |
| `routers reach infrastructure only through api.deps and api.app` | `forbidden`, `allow_indirect_imports = true` | `pharma_agent.api.routers` không import trực tiếp `pharma_agent.infrastructure` |

Kiểm tra khác:

| Quy tắc | Công cụ | Ở đâu | Chạy lúc |
| --- | --- | --- | --- |
| Các contract trên | `lint-imports` | `backend/pyproject.toml` | pre-commit `lint-imports-backend` khi file `backend/**/*.py` hoặc `.toml` đổi; `uv run lint-imports` |
| Contract không bị nới: domain vẫn cấm `langchain`, `fastembed`; application vẫn cấm `uvicorn`; danh sách `independence` đúng bằng mọi package con có `__init__.py` của `application/` | pytest | `backend/tests/test_import_contracts.py` | `uv run pytest -q` |
| Không có `test_*.py`, `*_test.py`, `conftest.py` dưới `src/` (pytest chỉ thu thập `tests/`, nên test lạc vào `src/` sẽ im lặng không chạy) | pytest | `backend/tests/test_layout.py` | `uv run pytest -q` |
| Kiểu và cảnh báo bằng 0 | pyrefly | `backend/pyrefly.toml` | pre-commit `pyrefly-backend` |
| Lint, format | ruff | `ruff.toml` root, `backend/pyproject.toml` chỉ `extend` | pre-commit `ruff-check`, `ruff-format` |

Vì `test_import_contracts.py` so danh sách feature với thư mục, thêm một feature mới vào
`application/` mà quên thêm vào contract `independence` sẽ làm pytest fail.

### 4.3 pharma-lab

Contract import-linter trong `[tool.importlinter]` của `pharma-lab/pyproject.toml`
(`root_packages = ["pharma_lab", "pharma_agent"]` để contract nhìn thấy backend):

| Contract | Kiểu | Nội dung |
| --- | --- | --- |
| `pharma_lab layers, top to bottom` | `layers`, `containers = ["pharma_lab"]`, `exhaustive = true` | 11 tầng ở mục 3.3. `exhaustive` nghĩa là một package mới ngay dưới `pharma_lab/` làm lint fail cho tới khi được xếp vào một tầng. |
| `Kaggle workers import neither the backend nor the local data layout` | `forbidden` | `pharma_lab.integrations.kaggle.workers` không import `pharma_agent` và `pharma_lab.config.paths` (kernel Kaggle không có workspace pharma-lab; `config.paths` ném `ConfigurationError` ở đó) |
| `pharma_lab uses the backend's public surface only` | `forbidden`, `allow_indirect_imports = true` | `pharma_lab` không import trực tiếp `pharma_agent.api`, `pharma_agent.infrastructure.persistence` |

Kiểm tra khác:

| Quy tắc | Công cụ | Ở đâu | Chạy lúc |
| --- | --- | --- | --- |
| Các contract trên | `lint-imports` | `pharma-lab/pyproject.toml` | pre-commit `lint-imports-pharma-lab` khi file `pharma-lab/**/*.py` hoặc `.toml` đổi |
| Worker Kaggle (`workers.benchmark`, `query_embed`, `corpus_embed`, `rerank` và `e2e.kernel_worker`) import được từ source bundle mà không nạp `pharma_lab.config.paths` hay `pharma_agent` | pytest, chạy subprocess | `pharma-lab/tests/integrations/kaggle/test_worker_bundle_imports.py` | `uv run pytest -q` |
| Các module backend mà pharma-lab dùng vẫn import được và giữ tên, chữ ký được ghim | pytest | `pharma-lab/tests/test_backend_public_api.py` (`PUBLIC_MODULES`) | như trên |
| Không có module test dưới `src/` | pytest | `pharma-lab/tests/test_layout.py` | như trên |
| Dependency trực tiếp được pin chính xác hoặc dùng đúng specifier của backend; `pharma-agent` là dependency runtime duy nhất | pytest | `pharma-lab/tests/test_dependency_pins.py` | như trên |
| Luật `.gitignore` của `data/` theo bố cục dữ liệu; không file dữ liệu tracked nào quá 5 MiB | pytest | `pharma-lab/tests/test_repository_data_policy.py` | như trên |
| Kiểu, lint, format | pyrefly, ruff | `pharma-lab/pyrefly.toml`, `ruff.toml` root | pre-commit |

Contract `exhaustive` chỉ kiểm tra package ngay dưới `pharma_lab/`; `e2e.kernel_worker` không nằm
dưới `integrations.kaggle.workers` nên không thuộc contract forbidden thứ hai, nhưng được
`test_worker_bundle_imports.py` kiểm tra lúc chạy.

### 4.4 Toàn repo

- `.pre-commit-config.yaml`: pre-commit-hooks chung, ruff, pyrefly và lint-imports cho từng project
  Python, oxlint, prettier, typecheck và api drift cho frontend, hadolint cho Dockerfile, build LaTeX
  của report, gitleaks, `uv-lock`.
- `ruff.toml` root: `target-version = "py312"`, chọn `E, W, F, I, B, C4, UP, SIM, RUF`, chỉ bỏ
  `E501` (formatter lo độ dài dòng) và `RUF001`-`RUF003` (ký tự tiếng Việt).
- `pyrefly.toml` của backend và pharma-lab: `unused-ignore = true`; riêng `tests/` tắt
  `implicit-any` và `missing-override-decorator`.

## 5. Quy tắc chỉ là quy ước (không công cụ nào kiểm tra)

| Quy ước | Ghi ở đâu | Hiện trạng trên `v2.0.0` |
| --- | --- | --- |
| Test Python đặt theo cây gương của `src/<package>/` | `AGENTS.md` | Phần lớn đúng; backend còn `contract/`, `e2e/`, `fixtures/` và helper ở gốc `tests/`. `test_layout.py` chỉ cấm test trong `src/`, không kiểm tra cây gương. |
| Test frontend đặt cạnh đúng file nó test (`foo.test.ts` cạnh `foo.ts`) | `frontend/README.md` | Test chỉ đòi cùng thư mục có một file nguồn, không đòi trùng tên, vì một số test là test hợp đồng hoặc test gộp cả thư mục. |
| Mỗi feature trong `application/<feature>/` có `service.py` với class `<Feature>Service`; mỗi method công khai là một use case; use case lớn mới tách class riêng | `backend/README.md` | `application/memory/` không có `service.py` (chỉ `summarize.py`). |
| Router gọi service qua `Container`, không gọi thẳng repository | `backend/README.md` | Chỉ phần "router không import infrastructure" được contract ép. |
| Route frontend mỏng, chỉ ghép feature | `frontend/README.md` | Không có kiểm tra; `app/routes/` được import mọi thứ. |
| `cli.py` của backend nằm ngoài các tầng | (không ghi) | Không thuộc contract `layers`; import tự do. |
| Không `# noqa`, `# type: ignore`, không tắt rule | `AGENTS.md`, README root | Không có công cụ cấm; ruff `RUF100` chỉ bắt `# noqa` thừa. Hiện đang được tuân thủ. |
| Hai `pyrefly.toml` giống hệt nhau | README root | Đang giống hệt; không test nào so sánh. |
| Thêm hướng import mới thì sửa README cùng lúc | `AGENTS.md` | Chỉ frontend có test so cấu hình với bảng trong test, không so với README. |
| Không để module re-export ở chỗ cũ khi dời module | spec 2026-10-16 | Được làm đúng khi dời; không có kiểm tra. |

## 6. Ngoài phạm vi và liên kết

- Nội dung từng tầng backend (agent, API, SSE): `2026-11-15-backend-agent-api-design.md`.
- Bố cục và luồng dữ liệu corpus, `rag-final`, rerank: `2026-11-15-corpus-data-pipeline-design.md`.
- Thành phần, route và test UI của frontend: `2026-11-15-frontend-design.md`.
- Feature `access`, `account`, `organizations`, `admin`, `audit`: `2026-11-15-product-accounts-orgs-design.md`.
- Worker Kaggle, source bundle, chạy tiếp được: `2026-11-15-kaggle-runs-design.md`.
- Pipeline đánh giá trong `evaluation/` và `e2e/`: `2026-11-15-evaluation-design.md`.
- Build LaTeX trong pre-commit: `2026-11-15-soict-paper-design.md`.

Không gộp `artifacts/contract.py` (contract `rag-final`) với `artifacts/manifest.py` (manifest
artifact đánh giá): hai contract khác mục đích.

## 7. Lịch sử quyết định

| Ngày | Quyết định | Thay cho | Lý do | Nguồn |
| --- | --- | --- | --- | --- |
| 2026-09-11 | Backend có test tầng tự viết ngay từ lúc dựng project | (chưa có) | Ép Clean Architecture từ đầu | `1c67209` (commit scaffold) |
| 2026-10-10 | Test `tests/architecture/test_layering.py` duyệt AST, ép 8 quy tắc tầng của backend | Test scaffold | Quy tắc phụ thuộc phải giữ được mà không cần review; mỗi test được thử với một vi phạm cố ý | `fcc3e33:backend/tests/architecture/test_layering.py` |
| 2026-10-10 | Frontend ép ranh giới feature bằng oxlint `no-restricted-imports` và `app/architecture.test.ts`, bố cục `components/hooks/lib` cho mọi feature | Không kiểm tra | `features/citations` và `features/chat` import lẫn nhau; gộp citations vào chat rồi chỉ cho phép import một chiều | `3e6e95f:frontend/app/architecture.test.ts` |
| 2026-10-16 | Một file quy tắc `AGENTS.md` ở root, `CLAUDE.md` trỏ sang | Quy tắc rải ở README root và README từng project | Một chỗ cho người và agent đọc; README giữ chi tiết | `19a4d20:docs/superpowers/specs/2026-10-16-architecture-rules-design.md` §2; `d1ac297` |
| 2026-10-16 | Backend dùng contract import-linter, xóa `tests/architecture/` | Test AST tự viết | Contract khai báo thay cho mã tự duy trì; cùng một công cụ với pharma-lab; chạy được trong pre-commit | spec trên §4; `b51957d` |
| 2026-10-16 | Thêm `test_import_contracts.py` canh contract | Chỉ dựa vào contract | Contract có thể bị nới im lặng; feature mới có thể quên đưa vào `independence` | `50f48e9` |
| 2026-10-16 | pharma-lab xếp 11 tầng, gỡ 6 vòng import (`artifacts` ↔ `evaluation`, `artifacts` ↔ `integrations`, `evaluation` ↔ `integrations`, `embeddings` ↔ `integrations`, `evaluation` ↔ `bundle`, `config` ↔ `runtime`) bằng cách dời module xuống đúng tầng: `hashing.py`, gộp `evaluation/artifact_contracts.py` vào `artifacts/manifest.py`, `cache/paths.py`, `cache/file_locks.py`, `cache/text_embeddings.py`, `runtime/scheduling.py` | 13 package không thứ tự, hàm hash chép 3-4 bản | Không có thứ tự thì không ép được ranh giới; bản chép dễ lệch nhau | spec trên §5; `19a4d20:docs/superpowers/plans/2026-10-16-architecture-rules.md` Task 6-11; `dc7b52f` |
| 2026-10-16 | Contract `layers` của pharma-lab `exhaustive`; worker Kaggle cũng không được import `config.paths` | Spec chỉ cấm worker import `pharma_agent` | Rà soát sau khi làm: package mới phải được xếp tầng; `config.paths` hỏng trên kernel Kaggle | `46d368f` |
| 2026-10-16 | Giữ test frontend cạnh mã, thêm hai test vị trí file test | Phương án dời test sang `tests/` | Quy ước Vitest và React; `vitest.config.ts` gom theo glob `app/**`; test lạc vào `tests/` phải làm fail, không bị bỏ qua | spec trên §3; `acc6f0a` |
| 2026-10-16 | `tests/test_layout.py` ở backend và pharma-lab | Không kiểm tra | pytest chỉ thu thập `tests/`, test trong `src/` sẽ im lặng không chạy | spec trên §2; `f510028` |
| 2026-10-16 | lint-imports chạy trong pre-commit, ngay sau hook pyrefly của từng project | Chỉ chạy tay | Không có CI | `495a039`, `cd4e413` |
| 2026-10-24 | Xóa spec kiến trúc, plan đánh dấu xong; quy tắc chỉ còn ở `AGENTS.md` | Spec riêng | Gom spec quanh paper v2 | `414e317` (spec đọc ở `19a4d20`, plan bản cuối ở `414e317:docs/superpowers/plans/2026-10-16-architecture-rules.md`) |
| 2026-11-15 | Spec này thay plan 2026-10-16 (đã chạy xong, bỏ) và ghi rõ phần máy kiểm tra và phần quy ước | `AGENTS.md` là nguồn duy nhất | Gom spec theo mảng | (spec này) |

Phương án đã cân nhắc và bỏ trong spec 2026-10-16: áp Clean Architecture domain/application/
infrastructure cho frontend (không cần cho SPA feature-based); đổi tầng hay feature của backend
(chỉ đổi công cụ ép); gộp `artifacts/contract.py` với `artifacts/manifest.py` (khác mục đích).
