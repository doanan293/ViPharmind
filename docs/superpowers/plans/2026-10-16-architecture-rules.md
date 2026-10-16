# Quy tắc kiến trúc cho frontend, backend và pharma-lab

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ba project có quy tắc bố cục và ranh giới import viết ở một chỗ (`AGENTS.md`) và được công cụ ép: oxlint cộng `app/architecture.test.ts` ở frontend, import-linter ở backend và pharma-lab; pharma-lab hết vòng import giữa các package.

**Architecture:** Frontend giữ nguyên bố cục feature-based và test cạnh code, chỉ thêm hai test về vị trí file test. Backend đổi 8 rule trong `tests/architecture/test_layering.py` thành contract import-linter trong `pyproject.toml`. pharma-lab nhận thứ tự 11 tầng; sáu chỗ đặt sai tầng được dời xuống (`hashing.py`, `artifacts/manifest.py`, `cache/paths.py`, `cache/file_locks.py`, `cache/text_embeddings.py`, `runtime/scheduling.py`) để contract layers pass. Mọi việc đụng tới `pharma-lab/src` làm trong git worktree riêng vì ba chuỗi Kaggle trong tmux còn khởi chạy `uv run pharma-lab` từ checkout chính.

**Tech Stack:** uv workspace (Python 3.12, ruff, pyrefly, pytest), import-linter 2.15, pre-commit; frontend React Router với Vitest 5 và oxlint.

**Spec:** `docs/superpowers/specs/2026-10-16-architecture-rules-design.md`.

## Global Constraints

- Không dời file test nào của frontend; không đổi ranh giới feature frontend hay tầng backend (spec §8).
- `import-linter==2.15` pin ở dev group của `pyproject.toml` root, như ruff và pyrefly (spec §4).
- Không `# noqa`, không `# type: ignore`, không `ignore_imports` trong contract import-linter (spec §2).
- Module dời chỗ giữ nguyên tên hàm, class, chữ ký; không để module re-export ở chỗ cũ (spec §5.2).
- Nhóm A (Task 1 đến 5) làm trực tiếp trên `dev` ở checkout chính. Nhóm B (Task 6 đến 11) làm trên nhánh `arch/pharma-lab-layers` trong worktree `../vipharmind-arch`. Task 12 gộp vào `dev` chỉ sau khi cả ba file `pharma-lab/data/work/logs-t7/{embed-acc1,rerank-acc1,rerank-acc3}.log` có dòng `ALL_DONE` và tmux session `rerank-4b` đã kết thúc.
- Gate trước mỗi commit Python, chạy trong project đó: `uv run ruff check src tests && uv run ruff format --check src tests && uv run pyrefly check --min-severity warn && uv run pytest -q`. Gate frontend: `npm run lint && npm run typecheck && npm run format && npm run test:unit`.
- Commit không có trailer Co-Authored-By. Văn bản tiếng Việt như README root, trừ `frontend/README.md` tiếng Anh.

## Review Focus

- Một file `*.test.ts` lạc vào `frontend/tests/` phải làm test kiến trúc fail, không im lặng bị bỏ qua (Task 2, test "tests/ holds only support code").
- `rerank_log_path` sau khi dời sang `cache/paths.py` vẫn phải theo `paths.LOGS_DIR` đã bị conftest đổi hướng, nếu không log của test ghi vào `data/work/logs` thật (Task 8, `tests/cache/test_paths.py`).
- Khóa publish và khóa job sau khi tách phải vẫn nằm trong thư mục `isolated_lock_dir` của conftest (Task 9, `tests/artifacts/test_publisher.py` và `tests/integrations/kaggle/test_job_lock.py`).
- `artifacts.manifest.sha256_file` với file thiếu phải vẫn ném `ArtifactContractError`, không phải `OSError` trần (Task 7, `tests/artifacts/test_manifest.py`).
- Digest `native_rerank_contract().sha256` không được đổi khi `_canonical_sha256` của `model_profiles` thay bằng `hashing.canonical_sha256` (Task 6, test có sẵn `tests/evaluation/test_rerank_contract.py`).

---

## Nhóm A: trên `dev`, checkout chính

### Task 1: AGENTS.md và CLAUDE.md

**Files:**
- Create: `AGENTS.md`
- Create: `CLAUDE.md`

- [ ] **Step 1: Viết `AGENTS.md`**

```markdown
# Quy tắc chung cho mọi project trong repo

Ba project `frontend/`, `backend/`, `pharma-lab/` có bố cục và ranh giới import riêng, nhưng cùng
một nguyên tắc: mỗi quy tắc dưới đây có một công cụ ép tự động, và muốn thêm một hướng import mới
thì sửa cấu hình cùng README, không bỏ qua rule. Không `# noqa`, không `# type: ignore`, không
`ignore_imports` trong contract import-linter, không tắt rule lint.

## Bố cục

- `frontend/`: feature-based. `app/routes/` mỏng và ghép feature; `app/features/<feature>/` có
  `components/`, `hooks/`, `lib/`; mã dùng chung ở `app/{api,components,hooks,i18n,lib}`.
  Chi tiết và bảng hướng import giữa feature: `frontend/README.md`, mục "Structure".
- `backend/`: Clean Architecture bốn tầng `api` → `infrastructure` → `application` → `domain`,
  mỗi feature trong `application/` độc lập. Chi tiết: `backend/README.md`, mục "Bố cục".
- `pharma-lab/`: 11 tầng từ `cli` xuống `config` và `hashing`, tầng trên import tầng dưới.
  Chi tiết: `pharma-lab/README.md`, mục "Cấu trúc project".

## Vị trí test

- Frontend đặt `*.test.ts`, `*.test.tsx` và `*.browser.test.tsx` trong `app/`, cạnh code được
  test (quy ước Vitest). `frontend/tests/` chỉ chứa mã hỗ trợ (setup, MSW, fixture, helper
  render) và e2e Playwright `tests/e2e/*.e2e.ts`. Ép bằng `app/architecture.test.ts`.
- Backend và pharma-lab đặt test trong `tests/` theo cây gương của `src/<package>/`; không có
  `test_*.py`, `*_test.py` hay `conftest.py` dưới `src/`. Ép bằng `tests/test_layout.py` của
  từng project.

## Ranh giới import

- Frontend: `no-restricted-imports` trong `.oxlintrc.json` và `app/architecture.test.ts`.
  Thêm một hướng import giữa hai feature nghĩa là sửa cả bảng trong test lẫn override oxlint;
  test kiểm tra hai chỗ khớp nhau.
- Backend và pharma-lab: import-linter, contract trong `[tool.importlinter]` của
  `pyproject.toml` từng project. Chạy `uv run lint-imports` trong project; pre-commit chạy nó
  khi file `.py` hoặc `.toml` của project đổi.

## Kiểm tra

Lệnh kiểm tra của từng project và pre-commit chung cho cả repo nằm ở `README.md` root, mục
"Chuẩn tooling chung" và "Kiểm tra". Mọi quy ước tooling Python (ruff, pyrefly, pytest, phiên
bản dev tool pin ở root) cũng ở đó.
```

- [ ] **Step 2: Viết `CLAUDE.md`**

```markdown
@AGENTS.md
```

- [ ] **Step 3: Chạy pre-commit trên hai file và commit**

```bash
uv run pre-commit run --files AGENTS.md CLAUDE.md
git add AGENTS.md CLAUDE.md
git commit -m "docs: AGENTS.md states the layout, test placement and import rules of every project"
```

### Task 2: Frontend, test vị trí file test

**Files:**
- Modify: `frontend/app/architecture.test.ts` (thêm sau `describe("frontend architecture", ...)`)
- Modify: `frontend/README.md:5-9`

- [ ] **Step 1: Thêm hai test vào cuối `frontend/app/architecture.test.ts`**

```ts
const TESTS = path.join(APP, "..", "tests")
const TEST_FILE = /\.test\.tsx?$/

function allFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name)
    return statSync(full).isDirectory() ? allFiles(full) : [full]
  })
}

describe("frontend test placement", () => {
  test("test files sit in app/ next to the code they test", () => {
    const misplaced = sourceFiles(APP)
      .filter((file) => TEST_FILE.test(file))
      .filter(
        (file) =>
          !readdirSync(path.dirname(file)).some(
            (name) => /\.tsx?$/.test(name) && !TEST_FILE.test(name)
          )
      )
    expect(misplaced.map((file) => path.relative(APP, file))).toEqual([])
  })

  test("tests/ holds only support code and Playwright e2e specs", () => {
    const stray = allFiles(TESTS).filter(
      (file) =>
        TEST_FILE.test(file) ||
        (/\.e2e\.ts$/.test(file) &&
          path.dirname(file) !== path.join(TESTS, "e2e"))
    )
    expect(stray.map((file) => path.relative(TESTS, file))).toEqual([])
  })
})
```

- [ ] **Step 2: Chứng minh test bắt được lỗi**

```bash
cd frontend
mkdir -p app/features/chat/lonely && echo 'import { test } from "vitest"; test("x", () => {})' > app/features/chat/lonely/x.test.ts
echo 'import { test } from "vitest"; test("x", () => {})' > tests/stray.test.ts
npx vitest run --project unit app/architecture.test.ts
```
Expected: FAIL, hai test mới báo `features/chat/lonely/x.test.ts` và `stray.test.ts`.

- [ ] **Step 3: Xóa file tạm, chạy lại**

```bash
rm -r app/features/chat/lonely tests/stray.test.ts
npx vitest run --project unit app/architecture.test.ts
```
Expected: PASS, 8 tests.

- [ ] **Step 4: Sửa mục "Structure" trong `frontend/README.md`**

Thay dòng

```markdown
- `app/features/<feature>/`: one folder per feature, with `components/` (React components), `hooks/` and `lib/` (logic without UI). Tests sit next to the code they test.
```

bằng

```markdown
- `app/features/<feature>/`: one folder per feature, with `components/` (React components), `hooks/` and `lib/` (logic without UI). Tests sit next to the code they test, the Vitest convention: `foo.test.ts` beside `foo.ts`, `Foo.browser.test.tsx` beside `Foo.tsx`; `vitest.config.ts` collects them with `app/**/*.test.*`.
- `tests/`: support code only (Vitest setup, MSW handlers, fixtures, render helpers) and the Playwright specs in `tests/e2e/*.e2e.ts`. No `*.test.*` file lives here.
```

và trong đoạn "`npm run lint` enforces the rules ..." thêm câu cuối: "It also checks that every test file sits in `app/` beside source code and that `tests/` holds no `*.test.*` file."

- [ ] **Step 5: Gate và commit**

```bash
cd frontend && npm run lint && npm run typecheck && npm run format && npm run test:unit
git add app/architecture.test.ts README.md
git commit -m "test(frontend): architecture test checks where test files live"
```

### Task 3: Backend, contract import-linter thay test tự viết

**Files:**
- Modify: `pyproject.toml` (root, dev group)
- Modify: `backend/pyproject.toml` (thêm `[tool.importlinter]`)
- Delete: `backend/tests/architecture/__init__.py`, `backend/tests/architecture/test_layering.py`
- Modify: `backend/README.md:202-235`

- [ ] **Step 1: Thêm import-linter vào dev group root và lock**

Trong `pyproject.toml` root, dev group thành:

```toml
dev = [
    "import-linter==2.15",
    "pre-commit==4.6.2",
    "pyrefly==1.3.0",
    "pytest==9.1.1",
    "pytest-asyncio==1.4.0",
    "ruff==0.16.7",
]
```

```bash
uv lock && uv sync --frozen
uv run lint-imports --version
```
Expected: in ra `2.15`.

- [ ] **Step 2: Khai báo contract trong `backend/pyproject.toml`** (thêm sau `[tool.pytest.ini_options]`)

```toml
[tool.importlinter]
root_package = "pharma_agent"
include_external_packages = true

[[tool.importlinter.contracts]]
name = "api > infrastructure > application > domain"
type = "layers"
layers = [
    "pharma_agent.api",
    "pharma_agent.infrastructure",
    "pharma_agent.application",
    "pharma_agent.domain",
]

[[tool.importlinter.contracts]]
name = "domain is framework-free"
type = "forbidden"
source_modules = ["pharma_agent.domain"]
forbidden_modules = [
    "langgraph",
    "langchain_core",
    "openai",
    "qdrant_client",
    "sqlalchemy",
    "fastapi",
    "langfuse",
    "httpx",
]

[[tool.importlinter.contracts]]
name = "application reaches databases, SDKs and transports only through domain ports"
type = "forbidden"
source_modules = ["pharma_agent.application"]
forbidden_modules = [
    "openai",
    "qdrant_client",
    "sqlalchemy",
    "psycopg",
    "alembic",
    "fastapi",
    "fastapi_users",
    "starlette",
    "langfuse",
    "httpx",
    "typer",
]

[[tool.importlinter.contracts]]
name = "application features are independent"
type = "independence"
modules = [
    "pharma_agent.application.access",
    "pharma_agent.application.account",
    "pharma_agent.application.admin",
    "pharma_agent.application.audit",
    "pharma_agent.application.chat",
    "pharma_agent.application.conversation",
    "pharma_agent.application.corpus",
    "pharma_agent.application.feedback",
    "pharma_agent.application.memory",
    "pharma_agent.application.organizations",
]

[[tool.importlinter.contracts]]
name = "api calls application, never domain"
type = "forbidden"
source_modules = ["pharma_agent.api"]
forbidden_modules = ["pharma_agent.domain"]
allow_indirect_imports = true

[[tool.importlinter.contracts]]
name = "routers reach infrastructure only through api.deps and api.app"
type = "forbidden"
source_modules = ["pharma_agent.api.routers"]
forbidden_modules = ["pharma_agent.infrastructure"]
allow_indirect_imports = true
```

`langchain`, `fastembed` và `uvicorn` trong test cũ bị bỏ vì backend không import chúng ở đâu (kiểm kê 2026-10-16). `allow_indirect_imports = true` ở hai contract cuối vì test cũ chỉ xét import trực tiếp và chuỗi `api → application → domain`, `routers → api.deps → infrastructure` là cố ý.

- [ ] **Step 3: Chạy lint-imports**

```bash
cd backend && uv run lint-imports
```
Expected: `Contracts: 6 kept, 0 broken.` Nếu báo `Module 'X' does not exist` cho một package ngoài, backend chưa import X ở đâu: bỏ X khỏi danh sách và chạy lại.

- [ ] **Step 4: Chứng minh contract bắt lỗi**

Thêm tạm dòng `import sqlalchemy  # noqa` vào đầu `backend/src/pharma_agent/domain/shared/__init__.py`, chạy `uv run lint-imports`.
Expected: `1 broken`, contract "domain is framework-free" nêu `pharma_agent.domain.shared -> sqlalchemy`. Gỡ dòng tạm.

- [ ] **Step 5: Xóa test tự viết**

```bash
git rm -r backend/tests/architecture
```

- [ ] **Step 6: Sửa `backend/README.md`**

Khối "Kiểm tra" thành:

```bash
uv run ruff check src tests && uv run ruff format --check src tests
uv run pyrefly check
uv run lint-imports            # ranh giới tầng, contract trong pyproject.toml
uv run pytest -q                 # unit
uv run pytest -q -m integration  # cần Docker (Qdrant thật)
```

Dòng "Quy tắc phụ thuộc được kiểm tra bởi `tests/architecture/test_layering.py`:" thành "Quy tắc phụ thuộc được ép bằng import-linter, contract trong `[tool.importlinter]` của `pyproject.toml`, chạy `uv run lint-imports`:". Danh sách quy tắc giữ nguyên.

- [ ] **Step 7: Gate và commit**

```bash
cd backend && uv run ruff check src tests && uv run ruff format --check src tests && uv run pyrefly check --min-severity warn && uv run lint-imports && uv run pytest -q
cd .. && git add pyproject.toml uv.lock backend/pyproject.toml backend/tests/architecture backend/README.md
git commit -m "test(backend): import-linter contracts replace the hand-written layering test"
```

### Task 4: `tests/test_layout.py` cho backend và pharma-lab

**Files:**
- Create: `backend/tests/test_layout.py`
- Create: `pharma-lab/tests/test_layout.py`

Thêm file vào `pharma-lab/tests/` không ảnh hưởng tiến trình Kaggle đang chạy, nên task này làm ở checkout chính.

- [ ] **Step 1: Viết test (nội dung giống nhau ở hai project)**

```python
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
TEST_NAMES = ("test_", "conftest.py")


def test_src_holds_no_test_modules() -> None:
    """pytest collects tests/ only, so a test under src/ would never run."""
    stray = sorted(
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if path.name.startswith(TEST_NAMES[0])
        or path.name.endswith("_test.py")
        or path.name == TEST_NAMES[1]
    )
    assert stray == []
```

- [ ] **Step 2: Chứng minh test bắt lỗi**

```bash
cd backend && touch src/pharma_agent/test_stray.py && uv run pytest -q tests/test_layout.py; rm src/pharma_agent/test_stray.py
```
Expected: FAIL với `['pharma_agent/test_stray.py']`. Lặp lại trong `pharma-lab/` với `src/pharma_lab/test_stray.py`.

- [ ] **Step 3: Chạy pass và commit**

```bash
cd backend && uv run pytest -q tests/test_layout.py && cd ../pharma-lab && uv run pytest -q tests/test_layout.py
cd .. && git add backend/tests/test_layout.py pharma-lab/tests/test_layout.py
git commit -m "test: no test module may live under src/ in backend or pharma-lab"
```

### Task 5: Pre-commit hook backend và README root

**Files:**
- Modify: `.pre-commit-config.yaml` (sau hook `pyrefly-backend`)
- Modify: `README.md:147-180`

- [ ] **Step 1: Thêm hook**

Ngay sau hook `pyrefly-backend`:

```yaml
      - id: lint-imports-backend
        name: lint-imports (backend)
        entry: uv run --directory backend lint-imports
        language: system
        files: ^backend/.*\.(py|toml)$
        pass_filenames: false
        require_serial: true
```

- [ ] **Step 2: Sửa README root**

Mục "Chuẩn tooling chung": bullet "**Phiên bản dev tool**" thêm `import-linter` vào danh sách trong ngoặc. Thêm bullet mới sau bullet Pytest:

```markdown
- **import-linter**: ranh giới tầng của backend và pharma-lab là contract trong
  `[tool.importlinter]` của `pyproject.toml` từng project; `uv run lint-imports` kiểm tra,
  pre-commit chạy nó khi file `.py` hoặc `.toml` của project đổi. Không thêm `ignore_imports`.
```

Khối lệnh mục "Kiểm tra" thành:

```bash
uv run ruff check src tests && uv run ruff format --check src tests
uv run pyrefly check --min-severity warn
uv run lint-imports
uv run pytest -q
```

Thêm câu ngay trên khối: "Quy tắc bố cục, vị trí test và ranh giới import của cả ba project tóm tắt ở `AGENTS.md`."

- [ ] **Step 3: Chạy pre-commit toàn repo và commit**

```bash
uv run pre-commit run --all-files
git add .pre-commit-config.yaml README.md
git commit -m "chore: pre-commit runs lint-imports for backend; README names import-linter"
```
Expected: mọi hook Passed hoặc Skipped.

---

## Nhóm B: worktree `../vipharmind-arch`, nhánh `arch/pharma-lab-layers`

### Task 6: Worktree, contract layers (đỏ) và `pharma_lab/hashing.py`

**Files:**
- Create: `pharma-lab/src/pharma_lab/hashing.py`
- Create: `pharma-lab/tests/test_hashing.py`
- Delete: `pharma-lab/src/pharma_lab/evaluation/query_hash.py`, `pharma-lab/src/pharma_lab/evaluation/rerank_contract.py`
- Modify: `pharma-lab/pyproject.toml`; `runtime/runtime_profiles.py:16-24`; `runtime/model_profiles.py:8-15,48`; `integrations/kaggle/models.py:19-31,50,67`; `integrations/kaggle/artifacts.py:19,26-35`; `integrations/kaggle/service.py:50`; `artifacts/contract.py:21-26`; `orchestration/build_corpus.py:12-19`; `evaluation/local_rerank_benchmark.py:38`; `evaluation/variant_identity.py:6`; `evaluation/cached_query_embedder.py:17`; `evaluation/query_embedding_cache.py:9,21-23`; `evaluation/rerank_score_cache.py:23-24`; `evaluation/retrieval_candidate_artifact.py:16-17`; `integrations/kaggle/workers/query_embed.py:10`; `integrations/kaggle/workers/rerank.py:13-14`; `tests/integrations/kaggle/test_artifacts.py:132`

**Interfaces:**
- Produces `pharma_lab.hashing`: `sha256_file(path: Path) -> str` (ném `OSError` trần), `canonical_sha256(value: object) -> str`, `normalize_query_for_hash(query: str) -> str`, `query_hash(query: str) -> str`, `model_slug(model_name: str) -> str`, `document_hash(document_text: str) -> str`.

- [ ] **Step 1: Tạo worktree từ `dev` (sau khi Nhóm A đã commit)**

```bash
cd /home/andv/personal/vipharmind
git worktree add -b arch/pharma-lab-layers ../vipharmind-arch dev
cd ../vipharmind-arch && uv sync --frozen
cd pharma-lab && uv run pytest -q
```
Expected: pass như trên `dev`. Mọi lệnh của Nhóm B chạy trong `../vipharmind-arch/pharma-lab`.

- [ ] **Step 2: Khai báo contract layers trong `pharma-lab/pyproject.toml`** (sau `[tool.pytest.ini_options]`)

```toml
[tool.importlinter]
root_packages = ["pharma_lab", "pharma_agent"]

[[tool.importlinter.contracts]]
name = "pharma_lab layers, top to bottom"
type = "layers"
layers = [
    "pharma_lab.cli",
    "pharma_lab.e2e | pharma_lab.data_archive",
    "pharma_lab.evaluation | pharma_lab.orchestration",
    "pharma_lab.bundle",
    "pharma_lab.embeddings",
    "pharma_lab.integrations",
    "pharma_lab.corpus",
    "pharma_lab.artifacts",
    "pharma_lab.cache",
    "pharma_lab.runtime",
    "pharma_lab.config | pharma_lab.hashing",
]
```

- [ ] **Step 3: Chạy lint-imports, ghi lại số vi phạm**

```bash
uv run lint-imports
```
Expected: báo `Module 'pharma_lab.hashing' does not exist` (chưa tạo) hoặc `1 broken` với các cạnh ngược: `artifacts → evaluation`, `artifacts → integrations`, `bundle → evaluation`, `embeddings → integrations`, `integrations → evaluation`, `integrations → embeddings`, `config → runtime`. Từ Task 7 trở đi, mỗi task làm số cạnh ngược giảm.

- [ ] **Step 4: Viết `tests/test_hashing.py`**

```python
import hashlib

import pytest

from pharma_lab.hashing import (
    canonical_sha256,
    document_hash,
    model_slug,
    query_hash,
    sha256_file,
)


def test_sha256_file_matches_hashlib_for_a_multi_block_file(tmp_path):
    data = b"x" * 3_000_000
    path = tmp_path / "a.bin"
    path.write_bytes(data)

    assert sha256_file(path) == hashlib.sha256(data).hexdigest()


def test_sha256_file_raises_os_error_for_a_missing_file(tmp_path):
    with pytest.raises(OSError):
        sha256_file(tmp_path / "missing.bin")


def test_canonical_sha256_ignores_key_order_and_whitespace():
    assert canonical_sha256({"b": 1, "a": [1, 2]}) == canonical_sha256(
        {"a": [1, 2], "b": 1}
    )
    assert canonical_sha256({"a": 1}) == hashlib.sha256(b'{"a":1}').hexdigest()


def test_query_hash_strips_surrounding_whitespace_only():
    assert query_hash("  paracetamol ") == query_hash("paracetamol")
    assert query_hash("Paracetamol") != query_hash("paracetamol")


def test_model_slug_replaces_separators_with_underscores():
    assert model_slug("qwen3-embedding:0.6b-q8_0") == "qwen3_embedding_0_6b_q8_0"


def test_document_hash_is_sha256_of_utf8_text():
    assert document_hash("thuốc") == hashlib.sha256("thuốc".encode()).hexdigest()
```

- [ ] **Step 5: Chạy test, xác nhận fail**

```bash
uv run pytest -q tests/test_hashing.py
```
Expected: FAIL `ModuleNotFoundError: pharma_lab.hashing`.

- [ ] **Step 6: Viết `src/pharma_lab/hashing.py`**

```python
"""Pure hash helpers shared by every layer, Kaggle workers included."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalize_query_for_hash(query: str) -> str:
    return query.strip()


def query_hash(query: str) -> str:
    normalized = normalize_query_for_hash(query)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def model_slug(model_name: str) -> str:
    return (
        model_name.replace(":", "_")
        .replace("-", "_")
        .replace(".", "_")
        .replace("/", "_")
    )


def document_hash(document_text: str) -> str:
    return hashlib.sha256(document_text.encode("utf-8")).hexdigest()
```

- [ ] **Step 7: Xóa hai module cũ và đổi mọi chỗ import**

```bash
git rm src/pharma_lab/evaluation/query_hash.py src/pharma_lab/evaluation/rerank_contract.py
```

Đổi import:
- `evaluation/cached_query_embedder.py`, `evaluation/rerank_score_cache.py`, `evaluation/retrieval_candidate_artifact.py`, `integrations/kaggle/workers/query_embed.py`, `integrations/kaggle/workers/rerank.py`: `from pharma_lab.evaluation.query_hash import query_hash` → `from pharma_lab.hashing import query_hash`; `from pharma_lab.evaluation.rerank_contract import document_hash` (dạng một dòng hoặc nhiều dòng) → `from pharma_lab.hashing import document_hash`. Gộp hai dòng thành `from pharma_lab.hashing import document_hash, query_hash` ở file nào import cả hai.
- `evaluation/query_embedding_cache.py`: dòng 9 `import pharma_lab.evaluation.query_hash as _query_hash` → `from pharma_lab import hashing as _query_hash` (ba alias ở dòng 21 đến 23 giữ nguyên).

- [ ] **Step 8: Một định nghĩa `canonical_sha256` và vòng lặp `sha256_file`**

- `runtime/runtime_profiles.py`: xóa `def canonical_sha256` (dòng 16 đến 24) và `import hashlib`, `import json` nếu không còn dùng; thêm `from pharma_lab.hashing import canonical_sha256`. Các chỗ gọi trong file giữ nguyên.
- `runtime/model_profiles.py`: xóa `_canonical_sha256` (dòng 8 đến 15), import `canonical_sha256` từ `pharma_lab.hashing`, dòng 48 gọi `canonical_sha256(self.canonical_payload())`.
- `integrations/kaggle/models.py`: xóa `canonical_sha256` và `_sha256_file`; `from pharma_lab.hashing import canonical_sha256, sha256_file`; dòng 50 và 67 gọi `sha256_file(...)`.
- `integrations/kaggle/artifacts.py`: dòng 19 import `canonical_sha256` từ `pharma_lab.hashing` thay vì `runtime_profiles`; thân `sha256_file` thành

```python
def sha256_file(path: Path) -> str:
    try:
        return hashing.sha256_file(path)
    except OSError as exc:
        raise ArtifactContractError(f"Cannot read artifact file: {path}") from exc
```
với `from pharma_lab import hashing` ở đầu file. Tên `sha256_file` của module này giữ nguyên vì `dependencies.py`, `model_artifacts.py`, `workers/runtime.py`, `evaluation/rerank_service.py` và test cần phiên bản ném `ArtifactContractError` của Kaggle.
- `integrations/kaggle/service.py:50`: `from pharma_lab.hashing import canonical_sha256` và `from pharma_lab.runtime.runtime_profiles import RuntimeCandidate`.
- `artifacts/contract.py`: xóa `def sha256_file` (dòng 21 đến 26); thêm `from pharma_lab.hashing import sha256_file` (file vẫn dùng nó trong `build_manifest`).
- `orchestration/build_corpus.py`: bỏ `sha256_file` khỏi khối import `artifacts.contract`, thêm `from pharma_lab.hashing import sha256_file`.
- `evaluation/local_rerank_benchmark.py`: bỏ `canonical_sha256` khỏi khối import `runtime_profiles`, thêm `from pharma_lab.hashing import canonical_sha256`.
- `evaluation/variant_identity.py:6`: `from pharma_lab.hashing import canonical_sha256`.
- `tests/integrations/kaggle/test_artifacts.py:132`: `from pharma_lab.hashing import canonical_sha256`.

Sau bước này `evaluation/artifact_contracts.py` vẫn còn `canonical_sha256` và `sha256_file` riêng; Task 7 xử lý.

- [ ] **Step 9: Gate và commit**

```bash
uv run ruff check src tests && uv run ruff format --check src tests && uv run pyrefly check --min-severity warn && uv run pytest -q
uv run lint-imports
```
Expected: pytest pass, gồm `tests/evaluation/test_rerank_contract.py::test_native_contract_digest_matches_existing_scores` (digest không đổi). lint-imports vẫn `1 broken` nhưng không còn cạnh `integrations → evaluation`.

```bash
git add -A src tests pyproject.toml
git commit -m "refactor(pharma-lab): one hashing module at the bottom layer; layers contract declared"
```

### Task 7: Gộp `evaluation/artifact_contracts.py` vào `artifacts/manifest.py`

**Files:**
- Modify: `pharma-lab/src/pharma_lab/artifacts/manifest.py` (viết lại)
- Delete: `pharma-lab/src/pharma_lab/evaluation/artifact_contracts.py`, `pharma-lab/src/pharma_lab/artifacts/jsonl.py`
- Create: `pharma-lab/tests/artifacts/test_manifest.py`
- Modify (import): `artifacts/bundle.py:12-18`; `bundle/export.py:39`; `cli/commands/e2e.py:57`; `data_archive/unpack.py:20`; `e2e/calibration.py:37`; `e2e/golden.py:17`; `e2e/golden_changes.py:30`; `e2e/harness.py:27`; `e2e/judging/service.py:32`; `e2e/run_identity.py:15`; `evaluation/backend_retrieval.py:22`; `evaluation/local_rerank_benchmark.py:13`; `evaluation/metric_comparison.py:13,15`; `evaluation/metrics_artifacts.py:10-14`; `evaluation/metrics_service.py:8,11-14`; `evaluation/relevance_judgments.py:24,26-30`; `evaluation/rerank_artifacts.py:9-13`; `evaluation/rerank_score_cache.py:19-22`; `evaluation/retrieval_candidate_artifact.py:8-14`; `integrations/kaggle/workers/query_embed.py:8`; `integrations/kaggle/workers/rerank.py:11`; `tests/e2e/test_golden_changes.py:17`; `tests/evaluation/conftest.py:5`; `tests/evaluation/test_metric_comparison.py:6`; `tests/evaluation/test_metrics_artifacts.py:8-11`; `tests/evaluation/test_relevance_judgments.py:6-9`

**Interfaces:**
- Produces `pharma_lab.artifacts.manifest`: `ArtifactContractError`, `sha256_file(path) -> str` (cache cho file từ 1 MiB, file thiếu ném `ArtifactContractError`), `iter_jsonl_objects(path) -> Iterator[dict[str, Any]]`, `Completion`, `ArtifactManifest`, `write_json`, `load_manifest`, `validate_data_file`, `require_finite_number`. Chữ ký giữ nguyên như `artifact_contracts.py` hôm nay.

- [ ] **Step 1: Viết `tests/artifacts/test_manifest.py`**

```python
import json

import pytest

from pharma_lab.artifacts.manifest import (
    ArtifactContractError,
    ArtifactManifest,
    Completion,
    iter_jsonl_objects,
    load_manifest,
    sha256_file,
    validate_data_file,
    write_json,
)


def test_missing_file_is_a_contract_error(tmp_path):
    with pytest.raises(ArtifactContractError, match="Cannot read artifact file"):
        sha256_file(tmp_path / "missing.jsonl")


def test_completion_rejects_counts_that_do_not_add_up():
    with pytest.raises(ArtifactContractError, match="complete \\+ missing == total"):
        Completion(total=3, complete=1, missing=1)
    assert Completion(total=2, complete=2, missing=0).is_complete


def test_manifest_round_trips_through_json_and_validates_its_data_file(tmp_path):
    data = tmp_path / "rows.jsonl"
    data.write_text('{"a": 1}\n\n{"a": 2}\n', encoding="utf-8")
    manifest = ArtifactManifest.create(
        artifact_type="demo", data_path=data, record_count=2, identity={"k": "v"}
    )
    write_json(tmp_path / "manifest.json", manifest.to_dict())

    loaded = load_manifest(tmp_path / "manifest.json")

    assert loaded == manifest
    assert validate_data_file(data, loaded) == 2
    assert [row["a"] for row in iter_jsonl_objects(data)] == [1, 2]


def test_non_object_jsonl_line_is_a_contract_error(tmp_path):
    data = tmp_path / "rows.jsonl"
    data.write_text(json.dumps([1, 2]) + "\n", encoding="utf-8")
    with pytest.raises(ArtifactContractError, match="must be a JSON object"):
        list(iter_jsonl_objects(data))
```

- [ ] **Step 2: Chạy, xác nhận fail**

```bash
uv run pytest -q tests/artifacts/test_manifest.py
```
Expected: FAIL `ImportError` (manifest.py chưa có `sha256_file`, `iter_jsonl_objects`...).

- [ ] **Step 3: Viết lại `artifacts/manifest.py`**

Nội dung là `evaluation/artifact_contracts.py` hôm nay với ba thay đổi: docstring module `"""Evaluation artifact manifest: checksum, record count and identity of one JSONL file."""`; bỏ `def canonical_sha256` (dùng `pharma_lab.hashing`); `sha256_file` giữ cache và `ArtifactContractError` nhưng gọi vòng lặp của `hashing`:

```python
from pharma_lab import hashing

_DIGEST_CACHE: dict[tuple[str, int, int, int], str] = {}


def sha256_file(path: Path) -> str:
    """Digest of a data file, cached from 1 MiB; an unreadable file is a contract error."""
    try:
        resolved = Path(path).resolve()
        stat = resolved.stat()
        key = (str(resolved), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        large = stat.st_size >= 1024 * 1024
        if large and (cached := _DIGEST_CACHE.get(key)) is not None:
            return cached
        value = hashing.sha256_file(resolved)
        if large:
            _DIGEST_CACHE[key] = value
        return value
    except OSError as exc:
        raise ArtifactContractError(f"Cannot read artifact file: {path}") from exc
```

`Completion` của manifest.py cũ (docstring "Validated progress counters shared by every artifact backend.") giữ docstring đó; chỉ còn một class. `import hashlib` bỏ nếu không còn dùng.

```bash
git rm src/pharma_lab/evaluation/artifact_contracts.py src/pharma_lab/artifacts/jsonl.py
```

- [ ] **Step 4: Đổi import**

- Mọi `from pharma_lab.evaluation.artifact_contracts import ...` → `from pharma_lab.artifacts.manifest import ...` (cùng tên).
- Mọi `from pharma_lab.artifacts.jsonl import iter_jsonl_objects` → `from pharma_lab.artifacts.manifest import iter_jsonl_objects`; file nào đã import từ manifest thì gộp vào một khối.
- `artifacts/bundle.py`: khối import dòng 12 đến 18 từ `artifacts.manifest`, gộp với dòng 11 (`Completion`).

```bash
grep -rn "artifact_contracts\|artifacts.jsonl" src tests docs README.md
```
Expected: không còn kết quả.

- [ ] **Step 5: Gate và commit**

```bash
uv run ruff check src tests && uv run ruff format --check src tests && uv run pyrefly check --min-severity warn && uv run pytest -q
uv run lint-imports
```
Expected: pytest pass; lint-imports còn các cạnh `artifacts → integrations`, `embeddings → integrations`, `integrations → embeddings`, `config → runtime`.

```bash
git add -A src tests
git commit -m "refactor(pharma-lab): artifact manifest contract lives in artifacts, one Completion"
```

### Task 8: `cache/paths.py` phá vòng `config` ↔ `runtime`

**Files:**
- Create: `pharma-lab/src/pharma_lab/cache/paths.py`
- Create: `pharma-lab/tests/cache/test_paths.py`
- Modify: `pharma-lab/src/pharma_lab/config/paths.py:6,94-108`; `tests/config/test_paths.py:33-39`
- Modify (import): `bundle/embed.py:22`; `cli/commands/embed.py`; `evaluation/backend_retrieval.py:21`; `evaluation/rerank_log.py:11`; `evaluation/rerank_service.py`; `tests/cli/test_rerank_command.py:9`; `tests/evaluation/test_rerank_service.py:15`

**Interfaces:**
- Produces `pharma_lab.cache.paths`: `query_embedding_cache_path(model: str) -> Path`, `text_embedding_cache_path(model: str) -> Path`, `rerank_score_cache_path(model: str) -> Path`, `rerank_log_path(model: str) -> Path`. Đọc thư mục qua `pharma_lab.config.paths` tại lúc gọi, nên monkeypatch `paths.LOGS_DIR` của conftest vẫn có hiệu lực.

- [ ] **Step 1: Viết `tests/cache/test_paths.py`**

```python
from pharma_lab.cache import paths as cache_paths
from pharma_lab.config import paths


def test_cache_files_are_named_after_the_model_slug() -> None:
    model = "qwen3-embedding:0.6b-q8_0"
    slug = "qwen3_embedding_0_6b_q8_0"

    assert cache_paths.text_embedding_cache_path(model) == (
        paths.TEXT_EMBEDDING_CACHE_DIR / f"{slug}.jsonl"
    )
    assert cache_paths.query_embedding_cache_path(model) == (
        paths.QUERY_EMBEDDING_CACHE_DIR / f"{slug}.jsonl"
    )
    assert cache_paths.rerank_score_cache_path("qwen3-reranker:0.6b-q8_0") == (
        paths.RERANK_SCORE_CACHE_DIR / "qwen3_reranker_0_6b_q8_0.jsonl"
    )


def test_rerank_logs_live_under_work(isolated_logs_dir) -> None:
    # tests/conftest.py redirects LOGS_DIR for every test; the original is the real value.
    assert isolated_logs_dir.original == paths.WORK_DIR / "logs"
    assert cache_paths.rerank_log_path("qwen3-reranker:0.6b-q8_0") == (
        isolated_logs_dir.root / "rerank" / "qwen3_reranker_0_6b_q8_0.log"
    )
```

- [ ] **Step 2: Chạy, xác nhận fail**

```bash
uv run pytest -q tests/cache/test_paths.py
```
Expected: FAIL `ImportError: cannot import name 'paths' from 'pharma_lab.cache'`.

- [ ] **Step 3: Viết `cache/paths.py`, cắt bốn hàm khỏi `config/paths.py`**

```python
"""Cache and log files of one model, named after the catalog slug."""

from __future__ import annotations

from pathlib import Path

from pharma_lab.config import paths as layout
from pharma_lab.runtime.catalog import require_model


def query_embedding_cache_path(model: str) -> Path:
    return layout.QUERY_EMBEDDING_CACHE_DIR / f"{require_model(model).slug}.jsonl"


def text_embedding_cache_path(model: str) -> Path:
    return layout.TEXT_EMBEDDING_CACHE_DIR / f"{require_model(model).slug}.jsonl"


def rerank_score_cache_path(model: str) -> Path:
    return layout.RERANK_SCORE_CACHE_DIR / f"{require_model(model).slug}.jsonl"


def rerank_log_path(model: str) -> Path:
    return layout.LOGS_DIR / "rerank" / f"{require_model(model).slug}.log"
```

Trong `config/paths.py`: xóa dòng 6 (`from pharma_lab.runtime.catalog import require_model`) và bốn hàm cuối (từ `query_embedding_cache_path` đến hết). `run_dir`, `e2e_run_dir` ở lại.

- [ ] **Step 4: Đổi import và test cũ**

- `bundle/embed.py:22`: `from pharma_lab.config.paths import BUNDLE_EMBED_WORK_DIR` và `from pharma_lab.cache.paths import text_embedding_cache_path`.
- `evaluation/backend_retrieval.py:21`: `from pharma_lab.config.paths import DATA_DIR` và `from pharma_lab.cache.paths import query_embedding_cache_path`.
- `evaluation/rerank_log.py:11`: `from pharma_lab.cache.paths import rerank_log_path`.
- `cli/commands/embed.py:16-18`: bỏ `query_embedding_cache_path` khỏi khối import `config.paths`, thêm `from pharma_lab.cache.paths import query_embedding_cache_path`.
- `evaluation/rerank_service.py:12-16`: bỏ `rerank_score_cache_path` khỏi khối import `config.paths`, thêm `from pharma_lab.cache.paths import rerank_score_cache_path`.
- `tests/cli/test_rerank_command.py:9`: `from pharma_lab.config.paths import run_dir` và `from pharma_lab.cache.paths import rerank_log_path`.
- `tests/evaluation/test_rerank_service.py:15`: `from pharma_lab.cache.paths import rerank_log_path`.
- `tests/config/test_paths.py`: xóa `test_rerank_logs_live_under_work` (đã sang `tests/cache/test_paths.py`).

```bash
grep -rn "config.paths import.*\(cache_path\|rerank_log_path\)\|paths\.\(query_embedding_cache_path\|text_embedding_cache_path\|rerank_score_cache_path\|rerank_log_path\)" src tests
```
Expected: chỉ còn các dòng trong `cache/paths.py`.

- [ ] **Step 5: Gate và commit**

```bash
uv run ruff check src tests && uv run ruff format --check src tests && uv run pyrefly check --min-severity warn && uv run pytest -q
uv run lint-imports
```
Expected: pytest pass; lint-imports không còn cạnh `config → runtime`.

```bash
git add -A src tests
git commit -m "refactor(pharma-lab): per-model cache paths move under cache, config no longer imports runtime"
```

### Task 9: `cache/file_locks.py` tách khóa file thuần khỏi khóa tài khoản Kaggle

**Files:**
- Create: `pharma-lab/src/pharma_lab/cache/file_locks.py`
- Create: `pharma-lab/tests/cache/test_file_locks.py`
- Modify: `integrations/kaggle/job_lock.py` (bỏ dòng 11, 14-15, 29-72; đổi mặc định `LOCK_DIR`)
- Modify: `artifacts/publisher.py:9,53`; `tests/conftest.py:13,24`; `tests/integrations/kaggle/test_pinned_account.py:20`; `tests/artifacts/test_publisher.py:4`; `tests/integrations/kaggle/test_job_lock.py` (bỏ hai test `lock_file_name`)

**Interfaces:**
- Produces `pharma_lab.cache.file_locks`: `LockKind = Literal["job", "cache", "publish"]`, `MAX_LOCK_FILE_NAME_BYTES = 255`, `class LockHeldError(Exception)`, `lock_file_name(target: Path, kind: LockKind, *, data_dir: Path | None = None) -> str`, `flock(lock_path: Path, content: str, *, non_blocking: bool)` context manager.
- `job_lock.py` giữ `KaggleAccountBusy`, `kaggle_job_lock`, `kaggle_cache_lock`, `kaggle_account_lock`, `wait_for_kaggle_account`, `hold_pinned_account`, `ACCOUNT_POLL_SECONDS`, `ACCOUNT_LOCK_DIRNAME`; thư mục khóa mặc định đọc `paths.LOCK_DIR` lúc gọi.

- [ ] **Step 1: Viết `tests/cache/test_file_locks.py`**

```python
from pathlib import Path

import pytest

from pharma_lab.cache.file_locks import LockHeldError, flock, lock_file_name


def test_lock_file_is_named_after_the_target_inside_data(tmp_path: Path) -> None:
    data = tmp_path / "data"
    target = data / "cache" / "text_embeddings" / "qwen3_embedding_4b_q8_0.jsonl"

    assert (
        lock_file_name(target, "job", data_dir=data)
        == "cache__text_embeddings__qwen3_embedding_4b_q8_0.jsonl.job.lock"
    )


def test_lock_file_for_a_target_outside_data_is_marked_external(tmp_path: Path) -> None:
    data = tmp_path / "data"
    target = tmp_path / "elsewhere" / "run.json"
    expected = "_external/" + target.resolve().as_posix().lstrip("/")

    assert lock_file_name(target, "cache", data_dir=data) == (
        expected.replace("/", "__") + ".cache.lock"
    )


def test_flock_reports_a_held_lock_without_blocking(tmp_path: Path) -> None:
    lock_path = tmp_path / "locks" / "x.lock"

    with flock(lock_path, "first", non_blocking=True):
        with (
            pytest.raises(LockHeldError),
            flock(lock_path, "second", non_blocking=True),
        ):
            raise AssertionError("a held lock must not be entered")
        assert lock_path.read_text(encoding="utf-8") == "first"
    with flock(lock_path, "third", non_blocking=True):
        assert lock_path.read_text(encoding="utf-8") == "third"
```

- [ ] **Step 2: Chạy, xác nhận fail**

```bash
uv run pytest -q tests/cache/test_file_locks.py
```
Expected: FAIL `ModuleNotFoundError: pharma_lab.cache.file_locks`.

- [ ] **Step 3: Viết `cache/file_locks.py`**

```python
"""flock-based lock files named after the file they protect."""

from __future__ import annotations

import fcntl
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pharma_lab.config import paths

LockKind = Literal["job", "cache", "publish"]
MAX_LOCK_FILE_NAME_BYTES = 255


class LockHeldError(Exception):
    """A non-blocking flock found the lock taken."""


def lock_file_name(
    target: Path, kind: LockKind, *, data_dir: Path | None = None
) -> str:
    """Name a lock after its target: the path under data/ with "/" replaced by "__".

    The kind is part of the name because one command holds a job lock and a cache lock on
    the same target, and flock locks belong to the open handle, not to the process.
    """
    resolved = Path(target).resolve(strict=False)
    base = Path(paths.DATA_DIR if data_dir is None else data_dir).resolve(strict=False)
    try:
        relative = resolved.relative_to(base).as_posix()
    except ValueError:
        relative = "_external/" + resolved.as_posix().lstrip("/")
    name = f"{relative.replace('/', '__')}.{kind}.lock"
    if len(name.encode("utf-8")) > MAX_LOCK_FILE_NAME_BYTES:
        raise ValueError(f"Lock target path is too long for a lock file name: {target}")
    return name


@contextmanager
def flock(
    lock_path: Path, content: str, *, non_blocking: bool
) -> Generator[None, None, None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if non_blocking else 0)
        try:
            fcntl.flock(handle.fileno(), flags)
        except BlockingIOError as exc:
            raise LockHeldError(str(lock_path)) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(content)
        handle.flush()
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
```

- [ ] **Step 4: Rút gọn `job_lock.py`**

Đầu file:

```python
from pharma_lab.cache.file_locks import LockHeldError, LockKind, flock, lock_file_name
from pharma_lab.config import paths
from pharma_lab.integrations.kaggle.config import ACCOUNT_NAME

ACCOUNT_LOCK_DIRNAME = "kaggle-accounts"
```

Xóa `LockKind`, `MAX_LOCK_FILE_NAME_BYTES`, `_LockHeldError`, `lock_file_name`, `_flock`; `import fcntl` bỏ. `_acquire` và `_account_lock` gọi `flock(...)` và bắt `LockHeldError`. Ba chỗ `root = LOCK_DIR if lock_root is None else lock_root` thành `root = paths.LOCK_DIR if lock_root is None else lock_root`.

- [ ] **Step 5: publisher và các test đổi hướng khóa**

- `artifacts/publisher.py`: dòng 9 thành `from pharma_lab.cache.file_locks import lock_file_name` và `from pharma_lab.config import paths`; dòng 53 thành `lock_path = paths.LOCK_DIR / lock_file_name(final, "publish")`.
- `tests/conftest.py`: bỏ dòng 13 (`from pharma_lab.integrations.kaggle import job_lock`); dòng 24 thành `monkeypatch.setattr(paths, "LOCK_DIR", root)`.
- `tests/integrations/kaggle/test_pinned_account.py:20`: `monkeypatch.setattr(paths, "LOCK_DIR", tmp_path / "locks")` với `from pharma_lab.config import paths`; bỏ import `job_lock` nếu không còn dùng.
- `tests/artifacts/test_publisher.py:4`: `from pharma_lab.cache.file_locks import lock_file_name`.
- `tests/integrations/kaggle/test_job_lock.py`: xóa `test_lock_file_is_named_after_the_target_inside_data` và `test_lock_file_for_a_target_outside_data_is_marked_external` (đã sang `tests/cache/test_file_locks.py`), bỏ `lock_file_name` khỏi import.

- [ ] **Step 6: Gate và commit**

```bash
uv run ruff check src tests && uv run ruff format --check src tests && uv run pyrefly check --min-severity warn && uv run pytest -q
uv run lint-imports
```
Expected: pytest pass, gồm `tests/artifacts/test_publisher.py::test_publish_keeps_its_lock_under_the_lock_directory`; lint-imports không còn cạnh `artifacts → integrations`.

```bash
git add -A src tests
git commit -m "refactor(pharma-lab): plain file locks live in cache; Kaggle account locks stay in integrations"
```

### Task 10: `runtime/scheduling.py` và `cache/text_embeddings.py`

**Files:**
- Move: `integrations/kaggle/workers/scheduling.py` → `runtime/scheduling.py`; `embeddings/text_cache.py` → `cache/text_embeddings.py`
- Move: `tests/integrations/kaggle/test_worker_scheduling.py` → `tests/runtime/test_scheduling.py`; `tests/embeddings/test_text_cache.py` → `tests/embeddings/test_service.py`
- Modify (import): `cache/text_embeddings.py:22`; `embeddings/service.py:12-18`; `embeddings/__init__.py`; `bundle/embed.py:28`; `integrations/kaggle/workers/benchmark.py:18`; `integrations/kaggle/workers/corpus_embed.py:9`; `integrations/kaggle/workers/query_embed.py:25`; `integrations/kaggle/workers/rerank.py:33`; `tests/bundle/test_embed.py:24`; `tests/embeddings/test_service.py:15`; `tests/runtime/test_scheduling.py:6`

- [ ] **Step 1: Dời file**

```bash
git mv src/pharma_lab/integrations/kaggle/workers/scheduling.py src/pharma_lab/runtime/scheduling.py
git mv src/pharma_lab/embeddings/text_cache.py src/pharma_lab/cache/text_embeddings.py
git mv tests/integrations/kaggle/test_worker_scheduling.py tests/runtime/test_scheduling.py
git mv tests/embeddings/test_text_cache.py tests/embeddings/test_service.py
```

- [ ] **Step 2: Đổi import**

- `from pharma_lab.integrations.kaggle.workers.scheduling import ...` → `from pharma_lab.runtime.scheduling import ...` (5 chỗ: `cache/text_embeddings.py`, `workers/benchmark.py`, `workers/query_embed.py`, `workers/rerank.py`, `tests/runtime/test_scheduling.py`).
- `from pharma_lab.embeddings.text_cache import ...` → `from pharma_lab.cache.text_embeddings import ...` (4 chỗ: `embeddings/service.py`, `bundle/embed.py`, `workers/corpus_embed.py`, `tests/bundle/test_embed.py`, `tests/embeddings/test_service.py`).
- `embeddings/__init__.py` docstring: `"""Text embedding service: local llama.cpp or a Kaggle stage over pharma_lab.cache.text_embeddings."""`.
- Docstring đầu `cache/text_embeddings.py` giữ nguyên.

```bash
grep -rn "text_cache\|workers.scheduling" src tests docs README.md
```
Expected: không còn kết quả.

- [ ] **Step 3: Gate**

```bash
uv run ruff check src tests && uv run ruff format --check src tests && uv run pyrefly check --min-severity warn && uv run pytest -q
uv run lint-imports
```
Expected: pytest pass; lint-imports `Contracts: 1 kept, 0 broken.`

- [ ] **Step 4: Commit**

```bash
git add -A src tests
git commit -m "refactor(pharma-lab): embedding cache and asyncio scheduling sit below integrations; layers contract passes"
```

### Task 11: Hai contract còn lại, README pharma-lab, hook pre-commit

**Files:**
- Modify: `pharma-lab/pyproject.toml` (thêm 2 contract)
- Modify: `pharma-lab/README.md:63-83`
- Modify: `.pre-commit-config.yaml` (sau hook `pyrefly-pharma-lab`)

- [ ] **Step 1: Thêm contract**

```toml
[[tool.importlinter.contracts]]
name = "Kaggle workers never import the backend"
type = "forbidden"
source_modules = ["pharma_lab.integrations.kaggle.workers"]
forbidden_modules = ["pharma_agent"]

[[tool.importlinter.contracts]]
name = "pharma_lab uses the backend's public surface only"
type = "forbidden"
source_modules = ["pharma_lab"]
forbidden_modules = [
    "pharma_agent.api",
    "pharma_agent.infrastructure.persistence",
]
allow_indirect_imports = true
```

```bash
uv run lint-imports
```
Expected: `Contracts: 3 kept, 0 broken.`

- [ ] **Step 2: Chứng minh contract worker bắt lỗi**

Thêm tạm dòng `from pharma_agent.domain.corpus import bundle as _bundle  # noqa` vào đầu `integrations/kaggle/workers/topology.py`, chạy `uv run lint-imports`.
Expected: `1 broken`, contract "Kaggle workers never import the backend" nêu `pharma_lab.integrations.kaggle.workers.topology -> pharma_agent.domain.corpus.bundle`. Gỡ dòng tạm.

- [ ] **Step 3: Viết lại mục "Cấu trúc project" trong `pharma-lab/README.md`**

```markdown
## Cấu trúc project

`src/pharma_lab/` xếp thành 11 tầng. Tầng trên được import tầng dưới; package cùng tầng không
import nhau.

| Tầng | Package | Vai trò |
| --- | --- | --- |
| 1 | `cli/` | Entrypoint `uv run pharma-lab`, chỉ gọi xuống |
| 2 | `e2e/`, `data_archive/` | Harness chạy agent end-to-end; lưu trữ dữ liệu lên Kaggle |
| 3 | `evaluation/`, `orchestration/` | Dataset, retrieval qua backend, rerank, metrics; build và atomic publish `rag-final` |
| 4 | `bundle/` | Export, embed và evaluation chunks dựa trên `pharma_agent.domain.corpus` |
| 5 | `embeddings/` | Service embed local (llama.cpp) hoặc trên Kaggle |
| 6 | `integrations/kaggle/` | Reconciliation, checkpoint, session và worker chạy trên Kaggle |
| 7 | `corpus/` | Trích xuất PDF, crawl tờ hướng dẫn, canonical blocks, validation |
| 8 | `artifacts/` | Contract rag-final, manifest artifact đánh giá, publisher |
| 9 | `cache/` | Cache JSONL và embedding theo hash, đường dẫn cache theo model, khóa file |
| 10 | `runtime/` | Catalog model, llama.cpp client, compose, helper asyncio |
| 11 | `config/`, `hashing.py` | Đường dẫn, env; hàm hash thuần |

Quy tắc phụ thuộc được ép bằng import-linter (`[tool.importlinter]` trong `pyproject.toml`,
chạy `uv run lint-imports`):

- Thứ tự tầng ở bảng trên.
- `integrations/kaggle/workers/` không import backend (`pharma_agent`); mã worker được tải lên
  kernel Kaggle.
- `pharma_lab` chỉ dùng mặt công khai của backend: không `pharma_agent.api`, không
  `pharma_agent.infrastructure.persistence`. Danh sách module backend được dùng nằm trong
  `tests/test_backend_public_api.py`.
```

Khối "Kiểm tra" thêm dòng `uv run lint-imports` sau `pyrefly`.

- [ ] **Step 4: Hook pre-commit** (sau `pyrefly-pharma-lab`)

```yaml
      - id: lint-imports-pharma-lab
        name: lint-imports (pharma-lab)
        entry: uv run --directory pharma-lab lint-imports
        language: system
        files: ^pharma-lab/.*\.(py|toml)$
        pass_filenames: false
        require_serial: true
```

- [ ] **Step 5: Gate và commit**

```bash
uv run ruff check src tests && uv run ruff format --check src tests && uv run pyrefly check --min-severity warn && uv run lint-imports && uv run pytest -q
cd .. && uv run pre-commit run --all-files
git add pharma-lab/pyproject.toml pharma-lab/README.md .pre-commit-config.yaml
git commit -m "chore(pharma-lab): import-linter contracts in pre-commit; README describes the 11 layers"
```
Expected: pre-commit toàn bộ Passed hoặc Skipped (hook frontend cần `npm ci` trong `frontend/` của worktree; nếu chưa có, chạy `npm --prefix frontend ci` trước).

### Task 12: Gộp vào `dev` sau khi chuỗi Kaggle xong

- [ ] **Step 1: Xác nhận chuỗi đã xong**

```bash
cd /home/andv/personal/vipharmind/pharma-lab/data/work/logs-t7
grep -c ALL_DONE embed-acc1.log rerank-acc1.log rerank-acc3.log
tmux ls
```
Expected: mỗi file `1`; không còn session `embed-acc1`, `rerank-4b`, `rerank-acc1`, `rerank-acc3` (hoặc session chỉ còn shell nhàn rỗi). Chưa đủ thì dừng ở đây, không gộp.

- [ ] **Step 2: Gộp và kiểm tra ở checkout chính**

```bash
cd /home/andv/personal/vipharmind
git merge --ff-only arch/pharma-lab-layers
uv sync --frozen
cd pharma-lab && uv run lint-imports && uv run pytest -q && cd ..
cd backend && uv run lint-imports && uv run pytest -q && cd ..
cd frontend && npm run test:unit && cd ..
uv run pre-commit run --all-files
```
Expected: mọi lệnh pass. Nếu `dev` đã có commit mới sau Task 5, dùng `git rebase dev` trong worktree trước rồi mới `--ff-only`.

- [ ] **Step 3: Dọn worktree**

```bash
git worktree remove ../vipharmind-arch
git branch -d arch/pharma-lab-layers
```
