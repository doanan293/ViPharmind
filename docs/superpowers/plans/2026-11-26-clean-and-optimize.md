# Làm sạch và tối ưu ViPharmind Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ViPharmind chạy local bằng một lệnh, tám tính năng đúng và có video demo, nhanh hơn có số đo, giao diện
có thương hiệu, mã gọn, rồi lịch sử `main` được viết lại theo tính năng.

**Architecture:** Làm trên nhánh `clean` (worktree `~/personal/vipharmind-clean`). Stack demo là một project compose
riêng (`vipharmind-demo`) dựng bằng `scripts/demo-stack.sh`. Demo là kịch bản Playwright trong `frontend/tests/demo/`
có ghi video. Mỗi lỗi sửa theo TDD thành một commit. Viết lại lịch sử ở cuối bằng `git commit-tree` trên các đoạn
liên tục của lịch sử `v2.0.0`.

**Tech Stack:** Python 3.12, uv, FastAPI, LangGraph, Postgres, Qdrant, React Router, shadcn (Base UI), Tailwind,
Playwright, Docker Compose, llama.cpp, CLIProxyAPI; pharma-lab cho đo chất lượng.

**Spec:** `docs/superpowers/specs/2026-11-26-clean-and-optimize-design.md`

## Global Constraints

- Quy tắc `AGENTS.md` và README root: không `# noqa`, không `# type: ignore`, không `ignore_imports`, không tắt rule;
  test backend và pharma-lab trong `tests/` theo cây gương; test frontend cạnh code trong `app/`, e2e và demo trong
  `frontend/tests/`.
- Commit không thêm dòng ghi công AI. Commit theo kiểu repo: `fix(<phạm vi>): ...`, `feat(...)`, `test(...)`, `chore(...)`, `docs(...)`.
- Không ghi, checkout hay xóa gì trong `~/personal/vipharmind` (chỉ đọc dữ liệu và GGUF ở đó) và
  `~/personal/vipharmind-camera-ready`.
- Không push khi chưa được chủ dự án đồng ý ngay lúc đó.
- Compose project demo: `vipharmind-demo`; không đụng volume `vipharmind_*`.
- `GGUF_DIR` mặc định `~/personal/vipharmind/ai-models/gguf`; `PHARMA_DATA_DIR` mặc định
  `~/personal/vipharmind/pharma-lab/data`.
- Embedding `qwen3-embedding-4b-q8_0.gguf` (`qwen3-embedding:4b-q8_0`, 2560 chiều), không đổi; không index lại.
- Email, SMS local: `PHARMA_EMAIL__PROVIDER=log`, `PHARMA_SMS__PROVIDER=log`.
- Tag của bài báo `v1.0.0`, `v1.1.0`, `soict-camera-ready` không được di chuyển hay xóa.
- UI chỉ dùng shadcn (thêm component bằng `npx shadcn add`) và thư viện đã có trong `frontend/package.json`.
- Người review là Opus (`claude-opus-5-5`, medium), phiên khác người sửa. Không dùng Fable.
- Kiểm tra đầy đủ một project Python (chạy trong `backend/` hoặc `pharma-lab/`):
  `uv run ruff check src tests && uv run ruff format --check src tests && uv run pyrefly check --min-severity warn && uv run lint-imports && uv run pytest -q`.
  Frontend: `npm run typecheck && npm run lint && npm run format && npm test`.

## Review Focus

- Gemini qua proxy chậm hoặc trả 429: chat phải báo lỗi rõ trong giao diện, không treo; kịch bản demo có timeout đủ dài
  và không coi một lần 429 là lỗi của app (thử lại một lần).
- Chạy lại kịch bản demo lần hai trên cùng database (email, tên tổ chức trùng) vẫn đạt: dữ liệu demo dùng hậu tố ngẫu nhiên.
- Mã OTP đọc từ log: hai mã cho cùng một email trong log thì lấy mã mới nhất; log của lần chạy trước không được làm sai.
- `/health` không được báo `CORPUS_NOT_READY` sau `reset-db` (reset chỉ xóa dữ liệu người dùng, không xóa corpus).
- Gỡ mã thí nghiệm paper v2 không được làm hỏng cấu hình mặc định của agent và các test e2e của pharma-lab còn dùng.

---

### Task 1: Hiện trạng

**Files:** Create: `docs/cleanup/baseline.md`

- [ ] **Step 1: Chạy kiểm tra đầy đủ ở `backend/`, `pharma-lab/`, `frontend/`, `uv run pre-commit run --all-files` ở root; e2e Playwright (`npm --prefix frontend run e2e`, cần Postgres và Qdrant của project demo: `docker compose -p vipharmind-demo up -d postgres qdrant`)**
- [ ] **Step 2: Ghi `baseline.md`: từng lệnh, đạt hay trượt, số lỗi, danh sách test trượt**
- [ ] **Step 3: Commit** — `docs(cleanup): baseline of the clean branch`

### Task 2: Stack demo một lệnh

**Files:** Create: `scripts/demo-stack.sh`, `compose.demo.yaml`; Modify: `backend/.env.example` (khối "Demo local"), `README.md` (mục "Demo local")

**Interfaces:**
- Produces: `scripts/demo-stack.sh up|down|status|reset-db|logs`. `up` chạy
  `docker compose -p vipharmind-demo -f compose.yaml -f compose.llm-proxy.yaml -f compose.local-models.yaml -f compose.demo.yaml up -d`,
  chờ healthy, nạp corpus nếu `pharma-agent check` báo thiếu. `compose.demo.yaml`: mount `PHARMA_DATA_DIR/corpus`
  chỉ đọc vào backend tại `/data/corpus`, đặt provider email và SMS `log`, `LLAMA_RERANKER_MODEL` theo biến
  `DEMO_RERANKER` (mặc định `qwen3-reranker-0.6b-q8_0-vimed.gguf`). Web `http://localhost:8080`.
- `reset-db`: xóa và tạo lại database ứng dụng rồi `migrate`, giữ schema corpus và Qdrant; nếu corpus nằm cùng database
  thì chỉ `TRUNCATE` các bảng người dùng (liệt kê bảng trong script, lấy từ migration).

- [ ] **Step 1: Chép token Gemini một lần (chỉ đọc nguồn)**

```bash
docker volume create vipharmind-demo_cli_proxy_auth
docker run --rm -v vipharmind_cli_proxy_auth:/src:ro -v vipharmind-demo_cli_proxy_auth:/dst alpine cp -a /src/. /dst/
```

- [ ] **Step 2: Viết `compose.demo.yaml`, `demo-stack.sh`; `up`**

Run: `scripts/demo-stack.sh up && scripts/demo-stack.sh status`
Expected: mọi service `healthy`.

- [ ] **Step 3: Kiểm đầu-cuối**

Run: `docker compose -p vipharmind-demo exec backend pharma-agent check && docker compose -p vipharmind-demo exec backend pharma-agent ask "Paracetamol người lớn uống tối đa bao nhiêu một ngày?"`
Expected: không `CORPUS_NOT_READY`; câu trả lời tiếng Việt có trích dẫn.
Lỗi nào lộ ra: test tái hiện trong `backend/tests` → sửa → commit `fix(...)`, ghi `docs/cleanup/log.md`.

- [ ] **Step 4: `reset-db` rồi lặp Step 3; vẫn đạt**
- [ ] **Step 5: Commit** — `chore(demo): one-command local stack with Gemini proxy and self-hosted models`

### Task 3: Đo mốc hiệu năng và chất lượng

**Files:** Create: `docs/performance-local.md`, `pharma-lab/data/evaluation/slices/demo-latency-20.jsonl` (id 20 câu; nếu thư mục bị gitignore thì đặt ở `docs/cleanup/demo-latency-20.txt`)

- [ ] **Step 1: Xác định file golden e2e và gold retrieval có hash bundle khớp `pharma-lab/data/corpus/formulary/manifest.json`; ghi tên file vào `performance-local.md`**
- [ ] **Step 2: Chọn 20 câu trả lời được, phủ các nhóm của golden, hạt giống 20261126; ghi id**
- [ ] **Step 3: Tìm trong `uv run pharma-lab e2e run --help` cách chạy một tập con trên cấu hình trỏ vào stack local (Gemini proxy, embedding 4B, rerank theo `DEMO_RERANKER`). Nếu chưa có tùy chọn tập con hoặc cấu hình local: thêm theo TDD trong `pharma-lab` (test trong `pharma-lab/tests/` theo cây gương), commit `feat(e2e): ...`**
- [ ] **Step 4: Đo độ trễ: 20 câu × 3 lần, p50 và p95 của thời gian tới chữ đầu và tổng mỗi lượt, tách theo bước, với rerank 0.6B và 4B**
- [ ] **Step 5: Đo chất lượng: retrieval (Recall@k, nDCG trên gold retrieval) với rerank 0.6B và 4B; e2e (`pharma-lab e2e judge`) trên 20 câu với mỗi reranker**
- [ ] **Step 6: Chọn reranker theo quy tắc của spec mục 7 (0.6B nếu chất lượng tụt ít), ghi lý do và mọi số vào `performance-local.md`; đặt mặc định `DEMO_RERANKER`**
- [ ] **Step 7: Commit** — `docs(perf): local latency and quality baseline`

### Task 4: Hạ tầng quay demo

**Files:** Create: `frontend/playwright.demo.config.ts`, `frontend/tests/demo/support/demo.ts`, `frontend/tests/demo/00-smoke.demo.ts`; Modify: `frontend/package.json` (script `demo`), `frontend/.gitignore` (`demo-videos/`)

**Interfaces:**
- Config: `testDir: tests/demo`, `testMatch: **/*.demo.ts`, `baseURL` `http://localhost:8080`, `video: "on"`,
  viewport 1440×900, `launchOptions.slowMo` 150, `timeout` 300 s, `outputDir: demo-videos`, một worker, locale `vi-VN`.
- `demo.ts`: `uniqueEmail(prefix: string): string`; `latestCode(to: string): Promise<string>` (đọc
  `scripts/demo-stack.sh logs backend`, lấy mã mới nhất gửi tới `to`, chờ tối đa 30 s);
  `signUp(page: Page, opts: {email: string; name: string; password: string}): Promise<void>`;
  `caption(page: Page, text: string): Promise<void>` (dải chú thích tiếng Việt cuối màn hình 2,5 s, chèn bằng
  `page.evaluate`, không sửa mã app).
- `npm --prefix frontend run demo [-- <tên>]`.

- [ ] **Step 1: Viết `00-smoke.demo.ts`: mở `/`, `caption("ViPharmind")`, khẳng định tiêu đề trang**
- [ ] **Step 2: Chạy** — `npm --prefix frontend run demo -- 00-smoke` — Expected: PASS, có `.webm` trong `frontend/demo-videos/`.
- [ ] **Step 3: Viết `latestCode` và một kịch bản thử đăng ký; chạy hai lần liên tiếp; PASS cả hai**
- [ ] **Step 4: Commit** — `test(demo): Playwright demo config with video, captions and log-read codes`

### Task 5: Thương hiệu và theme

**Files:** Modify: `frontend/app/app.css` (biến màu shadcn), `frontend/public/` (logo SVG, favicon), component dùng tên sản phẩm (sidebar header, trang đăng nhập, `<title>`), `frontend/app/i18n` (chuỗi tên)

- [ ] **Step 1: Dựng 3 phương án (màu chủ đạo, logo chữ hoặc biểu tượng, trang đăng nhập và màn chat mẫu) dưới dạng trang HTML tĩnh dùng đúng token shadcn; trình cho chủ dự án chọn (visual companion hoặc ảnh chụp)**
- [ ] **Step 2: Áp phương án được chọn: biến `--primary`, `--ring`, `--sidebar-*` cho sáng và tối; tương phản chữ trên nền ≥ 4.5:1 (ghi tỉ lệ đo được vào commit message)**
- [ ] **Step 3: Đổi mọi chỗ "Pharma Agent" hiển thị cho người dùng thành "ViPharmind"; test: `grep -rn "Pharma Agent" frontend/app --include=*.tsx --include=*.json` không còn chuỗi hiển thị**
- [ ] **Step 4: Kiểm tra frontend đầy đủ; e2e đạt**
- [ ] **Step 5: Commit** — `feat(ui): ViPharmind brand, logo and theme`

### Task 6–13: Mỗi tính năng: review, sửa, video

Thứ tự: `auth` (6), `chat` (7), `history` (8), `orgs` (9), `collections` (10), `account` (11), `admin` (12),
`public` (13). Nội dung từng kịch bản theo bảng ở spec mục 3.2.

**Files:** Create: `frontend/tests/demo/<NN>-<tính năng>.demo.ts`; Modify: mã và test của tính năng; `docs/cleanup/log.md`

**Interfaces:** Consumes `demo.ts` (Task 4), `demo-stack.sh` (Task 2).

- [ ] **Step 1: Đọc spec hiện hành của tính năng (`2026-11-15-*-design.md`) và mã; chạy test backend và frontend của tính năng; ghi `log.md`**
- [ ] **Step 2: Rà UI tính năng theo danh sách của skill ui-ux-pro-max (nhãn nút chỉ có icon, focus thấy được, vùng bấm ≥ 44px, lỗi cạnh trường, trạng thái rỗng dùng `Empty`, popover không đè nội dung); mỗi vấn đề là một lỗi**
- [ ] **Step 3: Viết kịch bản demo; chạy** — `scripts/demo-stack.sh reset-db && npm --prefix frontend run demo -- <NN>-<tính năng>`
- [ ] **Step 4: Mỗi lỗi (Step 1–3): test tái hiện (pytest, vitest hoặc browser test) → sửa → test đạt → commit `fix(<tính năng>): ...` → ghi `log.md`**
- [ ] **Step 5: Kịch bản đạt hai lần liên tiếp không reset; kiểm tra đầy đủ của các project bị sửa đạt**
- [ ] **Step 6: Review bằng subagent Opus: diff của tính năng từ `v2.0.0`, phần `log.md`, video. Kiểm: mỗi sửa có test; không xóa assert để dễ đạt; không đổi hành vi spec nêu mà không cập nhật spec; kịch bản không dựa vào dữ liệu có sẵn. Lặp Step 4–6 tới khi `ĐẠT`**
- [ ] **Step 7: Commit kịch bản** — `test(demo): <tính năng> walkthrough`

### Task 14: Tối ưu hiệu năng

**Files:** theo điểm nghẽn đo được ở Task 3; `docs/performance-local.md`

- [ ] **Step 1: Từ bảng tách theo bước, liệt kê điểm nghẽn theo thời gian chiếm**
- [ ] **Step 2: Với mỗi thay đổi (tham số llama.cpp, số ứng viên rerank, song song bước độc lập, bớt hoặc gộp lời gọi LLM, model rẻ hơn cho guard và viết lại câu hỏi): test hành vi trước nếu đổi mã → đổi → đo lại độ trễ (20 câu × 3) và chất lượng (retrieval, e2e judge 20 câu) → giữ nếu nhanh hơn và chất lượng không tụt so với mốc, bỏ nếu không**
- [ ] **Step 3: Thay đổi hành vi thì cập nhật spec liên quan (`2026-11-15-backend-agent-api-design.md`)**
- [ ] **Step 4: Bảng trước và sau trong `performance-local.md`; commit theo từng thay đổi giữ lại** — `perf(<phạm vi>): ...`

### Task 15: Gọn

- [ ] **Step 1: Liệt kê mã thí nghiệm paper v2 (ReAct agent, Jev/systemone, cấu hình e2e ablation, enrichment switch); với mỗi phần: có đường gọi ở cấu hình mặc định hoặc lệnh pharma-lab còn dùng không, có test không**
- [ ] **Step 2: Gỡ phần chết (không đường gọi mặc định, chỉ phục vụ D2, D4, D5 đã bỏ); giữ phần còn dùng; ghi từng quyết định vào spec liên quan; kiểm tra đầy đủ cả ba project đạt sau mỗi lần gỡ; commit `refactor(...)`**
- [ ] **Step 3: README các project và spec hiện hành khớp mã (lệnh chạy, biến môi trường, file compose); commit `docs(...)`**

### Task 16: Rà soát cuối và quay lại toàn bộ

- [ ] **Step 1: Subagent Opus đọc toàn bộ diff `v2.0.0..clean`, liệt kê vấn đề; sửa theo TDD tới khi `ĐẠT`**
- [ ] **Step 2: Kiểm tra đầy đủ ba project, pre-commit `--all-files`, e2e Playwright: đạt, không tệ hơn `baseline.md` ở bất kỳ dòng nào**
- [ ] **Step 3: Quay lại toàn bộ** — `scripts/demo-stack.sh reset-db && npm --prefix frontend run demo` — Expected: 9 PASS (smoke + tám tính năng). Xem từng video, ghi danh sách vào `docs/cleanup/demo.md`

### Task 17: Công cụ viết lại lịch sử

**Files:** Create: `devops/history/rewrite.py`, `devops/history/README.md`; Test: `devops/history/test_rewrite.py` (chạy bằng `uv run --with pytest pytest devops/history`)

**Interfaces:**
- `def segments(repo: Path, old_ref: str) -> list[Segment]` với `Segment(start: str, end: str, kind: str, scope: str, n: int)`:
  đi lịch sử first-parent của `old_ref` từ gốc, gom các commit liên tiếp cùng `kind` (`app` nếu đa số file thuộc
  `backend/`, `frontend/`, `compose*`, `devops/`; ngược lại `research`) và cùng `scope` (phạm vi trong tiêu đề
  conventional commit, ví dụ `chat`, `auth`; không có thì thư mục cấp hai bị sửa nhiều nhất).
- `def rewrite(repo: Path, old_ref: str, tail_base: str, tail_ref: str, branch: str) -> list[str]`: mỗi segment một
  commit qua `git commit-tree <tree của end> -p <commit trước>`, tiêu đề `feat(<scope>): <tóm tắt>` cho `app`,
  `docs(<scope>): ...` cho `research`, thân liệt kê tiêu đề các commit cũ đã gộp; tác giả và ngày lấy từ `end`; sau
  đó phát lại từng commit của `tail_base..tail_ref` (first-parent) bằng cây của chính nó. Trả danh sách SHA.

- [ ] **Step 1: Test hỏng trên repo git tạm**

```python
def test_segments_group_consecutive_scope(
    tmp_repo,
):  # 6 commit: feat(chat) x2, docs(report), feat(chat), feat(auth) x2
    assert [(s.kind, s.scope, s.n) for s in segments(tmp_repo, "main")] == [
        ("app", "chat", 2),
        ("research", "report", 1),
        ("app", "chat", 1),
        ("app", "auth", 2),
    ]


def test_rewrite_keeps_trees_and_tail(tmp_repo):
    shas = rewrite(tmp_repo, "main", "main", "tail", "new")
    assert tree("new") == tree("tail")
    assert {tree(s) for s in shas} >= {tree(c) for c in segment_ends(tmp_repo, "main")}


def test_rewrite_is_deterministic(tmp_repo):
    assert rewrite(tmp_repo, "main", "main", "tail", "a") == rewrite(
        tmp_repo, "main", "main", "tail", "b"
    )
```

- [ ] **Step 2: Chạy, xác nhận hỏng; cài đặt; chạy, xác nhận đạt**
- [ ] **Step 3: Commit** — `chore(history): rewrite tool for one commit per feature run`

### Task 18: Viết lại lịch sử và thay `main`

- [ ] **Step 1: Dựng** — `uv run python devops/history/rewrite.py --old-ref v2.0.0 --tail-base v2.0.0 --tail-ref clean --branch main-new` — Expected: `git diff --quiet clean main-new` thoát 0.
- [ ] **Step 2: Chạy test backend ở mọi commit `feat(...)` của `main-new` (xuất cây bằng `git archive` vào thư mục tạm); ghi `docs/cleanup/history.md`: số commit cũ và mới, bảng commit mới, commit nào trượt test nào**
- [ ] **Step 3: Commit `history.md` lên `clean`, dựng lại `main-new` (Step 1) để có commit đó**
- [ ] **Step 4: `git branch -f main main-new` (từ worktree `clean`); `git diff --quiet main clean`**
- [ ] **Step 5: Hỏi chủ dự án: force-push `main`, đẩy `archive/main-2026-11-10`, xóa nhánh remote nào (`dev`, `ci`, `v2.0.0`, `camera-ready`), tạo GitHub Release gắn tag mới kèm video. Chỉ làm phần được đồng ý (`git push --force-with-lease origin main`, ...). Tag `v1.0.0`, `v1.1.0`, `soict-camera-ready` không đổi**
