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
