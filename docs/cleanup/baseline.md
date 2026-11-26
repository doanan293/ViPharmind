# Hiện trạng nhánh `clean` trước khi làm sạch

Ngày đo: 2026-11-26. Commit: `f2138a3` (mã giống hệt `v2.0.0`). Máy: Intel i5-13420H, 12 luồng, 21 GB RAM, WSL2.

| Project | Lệnh | Kết quả |
| --- | --- | --- |
| backend | `ruff check src tests` | đạt |
| backend | `ruff format --check src tests` | đạt (373 file) |
| backend | `pyrefly check --min-severity warn` | 0 diagnostics (1 suppressed) |
| backend | `lint-imports` | 6 contract giữ, 0 vỡ |
| backend | `pytest -q` | 735 đạt, 114 bỏ chọn (`integration`) |
| backend | `pytest -q -m integration` | 114 đạt |
| pharma-lab | `ruff check`, `ruff format --check` | đạt (342 file) |
| pharma-lab | `pyrefly check --min-severity warn` | 0 diagnostics |
| pharma-lab | `lint-imports` | 3 contract giữ, 0 vỡ |
| pharma-lab | `pytest -q` | 1.411 đạt, 1 bỏ chọn |
| frontend | `typecheck`, `lint`, `format` | đạt |
| frontend | `test` (vitest) | 327 đạt |
| root | `pre-commit run --all-files` | đạt |
| frontend | `e2e` (Playwright, Postgres và Qdrant của project `vipharmind-demo`) | **15 đạt, 1 trượt** |

## Test trượt

- `tests/e2e/chat.e2e.ts` › "ask, see the phase, read the [1] answer, preview and open the full source": trượt ổn
  định (3/3 lần). Bảng "Nguồn [1]" mở và hiện đoạn trích, nhưng không còn nhãn phạm vi ("Toàn bộ mục", "Đoạn và các
  đoạn lân cận", "Một đoạn"). Trên `camera-ready` (2026-11-25) test này đạt. Xử lý ở chương `chat`.

## Ghi chú

- Pyrefly backend có 1 chỗ bị suppress: tìm và xử lý ở bước "Gọn".
