# Kaggle runs: việc còn lại Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sửa lỗi nối lại shard trên tài khoản không còn được phép, rồi hoàn tất hai mục nghiệm thu còn thiếu của cơ chế chạy Kaggle local-first.

**Architecture:** `sessions.reserve_session_account` chỉ ưu tiên tài khoản đã ghi trong `jobs.json` khi tài khoản đó nằm trong tập `contexts` được phép; nếu không, chọn theo quota như shard mới. Hai mục nghiệm thu là job Kaggle thật, không đổi mã trừ khi lộ lỗi.

**Tech Stack:** Python 3.12, uv workspace, pytest, ruff, pyrefly, import-linter, Kaggle CLI.

**Spec:** `docs/superpowers/specs/2026-11-15-kaggle-runs-design.md`

## Global Constraints

- Nhánh `v2.0.0`; không đụng `camera-ready`, `main`, tag `v1.1.0`.
- `AGENTS.md`: test trong `pharma-lab/tests/` theo cây gương của `src/`; không `# noqa`, `# type: ignore`, `ignore_imports`.
- Cổng kiểm tra (chạy trong `pharma-lab/`): `uv run ruff check src tests && uv run ruff format --check src tests && uv run pyrefly check && uv run lint-imports && uv run pytest -q`.
- `integrations/kaggle` không import `e2e`, `evaluation`, `embeddings`.
- Test không gọi Kaggle thật, không đọc `pharma-lab/.env`; dùng fake trong `tests/integrations/kaggle/factories.py` và `QuotaBook` của `test_sessions.py`.
- Không tunnel, không cổng nghe ngoài `127.0.0.1` (`tests/integrations/kaggle/test_no_external_exposure.py` phải xanh).
- Credential proxy chỉ đi khi có `--with-proxy-credentials`; dataset `pipeline-cred-*` phải bị xóa khi lệnh kết thúc.
- Job Kaggle thật chạy trong tmux, mỗi job một cửa sổ.
- Commit: `git add` đúng đường dẫn của task, thông điệp kết thúc bằng dòng `Co-Authored-By` mà phiên làm việc quy định.

## Review Focus

1. `jobs.json` ghi shard trên `acc1`, lệnh chạy với `--kaggle-account acc3`: shard đi sang `acc3`, không lỗi `generator raised StopIteration` (Task 1).
2. Tài khoản đã ghi vẫn được phép nhưng bị lệnh khác khóa: giữ hành vi hiện có, chọn theo quota (test hiện có không đổi, Task 1).
3. Tài khoản đã ghi được phép và rảnh: vẫn nối lại vào đó, log "already runs this job's kernel; attaching" (Task 1).
4. Opus bị Anthropic trả 429 giữa run: lệnh dừng tạm (mã 10 hoặc 11), các câu đã xong được gộp, chạy lại nối tiếp (Task 2).
5. `--judge` với model không có trên proxy: lỗi judge không chặn việc gộp câu trả lời (Task 3, đã có trong mã, kiểm lại ở job thật).

---

### Task 1: Nối lại shard khi tài khoản đã ghi không còn được phép

**Files:**
- Modify: `pharma-lab/src/pharma_lab/integrations/kaggle/sessions.py` (`_lock_preferred`, `reserve_session_account`)
- Test: `pharma-lab/tests/integrations/kaggle/test_sessions.py`

**Interfaces:**
- Consumes: `reserve_session_account(contexts, *, requested_budget_seconds, log, read_quota, account_lock, preferred_profile, unavailable, slots_per_account, committed_seconds)` như hiện có.
- Produces: cùng chữ ký. `preferred_profile` không có trong `{context.profile.name for context in contexts}` thì bị bỏ qua, ghi log một dòng `account=<p> runs this job's kernel but is not allowed; choosing by quota`.

- [ ] **Step 1: Viết test lỗi**

```python
def test_a_preferred_account_outside_the_allowed_set_is_ignored(tmp_path: Path) -> None:
    book = QuotaBook(acc3=10.0)
    lines: list[str] = []
    with reserve_session_account(
        _contexts("acc3"),
        requested_budget_seconds=7_200,
        log=lines.append,
        read_quota=book,
        account_lock=_slot_locker(tmp_path),
        preferred_profile="acc1",
        slots_per_account=2,
    ) as reserved:
        assert reserved.profile == "acc3"
    assert book.reads == ["acc3"]
    assert any("acc1" in line and "not allowed" in line for line in lines)


def test_a_preferred_allowed_account_is_still_attached(tmp_path: Path) -> None:
    book = QuotaBook(acc1=2.0, acc2=30.0)
    with reserve_session_account(
        _contexts("acc1", "acc2"),
        requested_budget_seconds=7_200,
        log=lambda _message: None,
        read_quota=book,
        account_lock=_slot_locker(tmp_path),
        preferred_profile="acc1",
        slots_per_account=2,
    ) as reserved:
        assert reserved.profile == "acc1"
```

- [ ] **Step 2: Chạy test, thấy lỗi**

Run: `uv run pytest tests/integrations/kaggle/test_sessions.py -q -k preferred`
Expected: test đầu FAIL với `RuntimeError: generator raised StopIteration`; test thứ hai PASS.

- [ ] **Step 3: Sửa `reserve_session_account` trong `sessions.py`**

Truyền `preferred_profile if preferred_profile in by_profile else None` vào `_lock_preferred`, và ghi dòng log ở Interfaces khi bỏ qua. Không đổi thứ tự chọn hay hành vi khóa.

- [ ] **Step 4: Chạy lại**

Run: `uv run pytest tests/integrations/kaggle/test_sessions.py tests/integrations/kaggle/test_scheduler.py -q`
Expected: PASS. Sau đó chạy cổng kiểm tra ở Global Constraints, xanh.

- [ ] **Step 5: Commit**

```bash
git add pharma-lab/src/pharma_lab/integrations/kaggle/sessions.py pharma-lab/tests/integrations/kaggle/test_sessions.py
git commit -m "fix(pharma-lab): a recorded shard on an account outside --kaggle-account is planned by quota"
```

### Task 2: Nghiệm thu Opus qua proxy trong kernel

Cần: tài khoản Claude hết giới hạn tốc độ (kiểm từ máy trước bằng một lời gọi `claude-opus-5-5` qua proxy cục bộ), một tài khoản Kaggle còn ít nhất 1,5 giờ GPU.

- [ ] **Step 1:** Trong tmux: `uv run pharma-lab e2e run --backend kaggle --llm opus --with-proxy-credentials --run e2e-accept-opus --config full --limit 10 --kaggle-account acc1`.
  Expected: lệnh in đúng các file credential loại `claude`; `e2e status --run e2e-accept-opus --config full` báo 10/10; `kaggle status` không còn dataset `pipeline-cred-*`.
- [ ] **Step 2:** Mở `data/evaluation/e2e/runs/e2e-accept-opus/full/answers.jsonl`: các dòng `completed` có câu trả lời đầy đủ; `run.json` có khối `software` với bản proxy.
- [ ] **Step 3:** Ghi kết quả (đạt hay không, số câu, lỗi) vào mục 2.6 của spec, commit `docs(spec): Opus acceptance on Kaggle`.

### Task 3: Nghiệm thu `--judge` với judge chạy được

- [ ] **Step 1:** Trong tmux: `uv run pharma-lab e2e run --backend kaggle --run e2e-accept-judge --config closed-book --limit 20 --judge --judge-model gemini-3.1-flash-lite --judge-reasoning none`.
  Expected: mỗi shard về thì máy chấm ngay; sau lệnh, `e2e report --run e2e-accept-judge` đọc được điểm cho 20 câu, không câu nào lỗi judge.
- [ ] **Step 2:** Ghi kết quả vào mục 2.6 của spec, commit `docs(spec): --judge acceptance on Kaggle`.

### Task 4: Dọn dataset còn sót trên Kaggle (chờ An duyệt)

- [ ] **Step 1:** Khi An đồng ý: liệt kê `pipeline-static-*`, `pipeline-input-*` của từng tài khoản bằng Kaggle CLI, gửi danh sách cho An xem trước khi xóa.
- [ ] **Step 2:** Xóa các dataset An duyệt; chạy `uv run pharma-lab kaggle status` và xác nhận không còn `pipeline-cred-*`.
