# Chạy Kaggle nối lại được, chia nhiều account: Kế hoạch triển khai

> **Cho người thực thi:** BẮT BUỘC dùng superpowers:subagent-driven-development (khuyến nghị) hoặc superpowers:executing-plans để làm từng task. Các bước dùng checkbox (`- [ ]`).

**Mục tiêu:** Mọi bước dùng Kaggle (embed corpus, embed truy vấn, rerank, e2e) lập kế hoạch từ trạng thái ở máy, chia shard chạy song song trên nhiều account, dừng và nối lại bất kỳ lúc nào, đổi account không mất gì; cấu hình thương mại chạy trong kernel qua `cli-proxy-api`.

**Kiến trúc:** Một lớp điều phối chung ở `integrations/kaggle` (lập kế hoạch shard, đăng ký kernel đang chạy, vòng chạy song song theo quota) và một bộ chuyển đổi cho mỗi bước ở tầng của nó (`e2e`, `evaluation`, `embeddings`). Trạng thái là cache và `answers.jsonl` cục bộ; Kaggle chỉ là chỗ tính toán tạm. Kernel biết hạn phiên và chụp kết quả định kỳ.

**Công nghệ:** Python 3.12, typer, pydantic, pytest, Kaggle CLI hiện có, llama.cpp, `CLIProxyAPI_8.0.28_linux_amd64`.

**Spec:** `docs/superpowers/specs/2026-10-23-kaggle-resumable-runs-design.md`

## Ràng buộc chung

- Nhánh `v2.0.0`; không đụng `camera-ready`, `main`, tag `v1.1.0`, `vipharma-rag`, `vipharmind-data-v1`.
- `AGENTS.md`: test nằm trong `tests/` theo cây gương của `src/`; không `# noqa`, `# type: ignore`, `ignore_imports`; ruff, pyrefly, `uv run lint-imports`, pytest xanh trong `pharma-lab` (và `backend` nếu chạm).
- Tầng import (pyproject): `cli` > `e2e | data_archive` > `evaluation | orchestration` > `bundle` > `embeddings` > `integrations` > ... Lớp chung ở `integrations/kaggle` không được import `e2e`, `evaluation`, `embeddings`.
- Kaggle: hai phiên GPU batch mỗi account (`SESSION_CAPACITY_MARKER`), `MINIMUM_SESSION_SECONDS = 3600`, `QUOTA_MARGIN_SECONDS = 1800`.
- Không tunnel, không cổng nghe ngoài `127.0.0.1` (`tests/integrations/kaggle/test_no_external_exposure.py` phải xanh).
- `run.json` của các run đã có giữ nguyên danh tính; trường mới chỉ ghi khi dùng.
- Thử lại tối đa 3 lần thất bại mỗi cặp rồi "kẹt"; chụp định kỳ mặc định 300 giây (`0` tắt); ngân sách phiên mặc định 7200 giây; đủ hai phiên mỗi account.
- Credential của proxy: chỉ khi có `--with-proxy-credentials`, dataset private, xoá sau khi thu, không vào git, `data/`, archive, log.
- Commit: `git add` đúng đường dẫn file của task (không `git add <thư mục>`), thông điệp kết thúc bằng `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Trọng tâm rà soát (mỗi dòng có test ở task sở hữu)

1. Kernel bị kill để lại dòng JSONL cụt cuối file: gộp phải bỏ dòng cụt chứ không hỏng cả file (T6).
2. Hai lệnh `e2e run` chạy cùng lúc trên một run: cặp đã giao cho kernel đang chạy không được giao lần nữa (T4, T5).
3. `kaggle quota` báo dùng giờ chậm: nhiều phiên song song trên một account không được vượt quota còn lại (T2).
4. Xoá dataset credential thất bại: phải báo to và thử lại, không bao giờ để public (T12).
5. Đổi `--limit`, `--category` hoặc sửa câu golden giữa các lần chạy: không xoá bản ghi cũ, câu bị thay thế chạy lại (T6).
6. Không còn gì để làm (tập thiếu rỗng) hoặc mọi cặp đã kẹt: thoát ngay, mã "xong" hoặc "kẹt", không mở kernel (T5, T11).

---

## Pha 1: Hạ tầng dùng chung (`integrations/kaggle`)

### Task 1: Lập kế hoạch shard (hàm thuần)

**Files:**
- Create: `pharma-lab/src/pharma_lab/integrations/kaggle/shards.py`
- Test: `pharma-lab/tests/integrations/kaggle/test_shards.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class WorkUnit: key: str; seconds: float; group: str = ""` (`group` ví dụ tên cấu hình hoặc bố cục; một shard chỉ chứa một `group`).
  - `@dataclass(frozen=True) class Shard: shard_id: str; units: tuple[WorkUnit, ...]; group: str` với thuộc tính `seconds`.
  - `def plan_shards(units: Sequence[WorkUnit], *, setup_seconds: float, budget_seconds: float, margin_seconds: float, slots: int, effective_parallelism: float = 1.0) -> list[Shard]`.

- [ ] **Bước 1: Viết test lỗi** (tên và khẳng định):
  - `test_plan_is_deterministic`: gọi hai lần với danh sách đầu vào xáo trộn thứ tự, kết quả `shard_id` và thành phần giống nhau.
  - `test_no_unit_lost_or_duplicated`: hợp các `units` của mọi shard bằng đúng tập đầu vào, không trùng `key`.
  - `test_shard_respects_budget`: mọi shard có `seconds / effective_parallelism + setup_seconds <= budget_seconds - margin_seconds`, trừ khi một đơn vị đơn lẻ vượt (khi đó shard chỉ có đơn vị đó).
  - `test_work_below_setup_is_not_split`: tổng việc nhỏ hơn `setup_seconds` thì ra đúng một shard dù `slots = 6`.
  - `test_uses_available_slots_when_work_is_large`: việc 20 giờ, `slots = 6` cho ít nhất 6 shard, các shard lệch nhau không quá 25%.
  - `test_groups_are_never_mixed`.
  - `test_shard_id_depends_only_on_unit_keys`.
- [ ] **Bước 2:** `uv run pytest tests/integrations/kaggle/test_shards.py -q`. Kỳ vọng: FAIL (chưa có module).
- [ ] **Bước 3:** Cài `plan_shards`: gom theo `group`, sắp xếp ổn định theo `key`, chia tham lam theo `seconds` (đơn vị lớn trước, vào shard đang nhẹ nhất) với số shard `k = clamp(ceil(W / cap), 1, slots)` nếu `W >= setup_seconds`, ngược lại `k = 1`; `cap = (budget - margin - setup) * effective_parallelism`; `shard_id` là sha256 rút gọn 16 ký tự của các `key` đã sắp xếp.
- [ ] **Bước 4:** Chạy lại test. Kỳ vọng: PASS.
- [ ] **Bước 5: Commit** `feat(pharma-lab): deterministic shard planning for Kaggle runs` (file: `shards.py`, `test_shards.py`).

### Task 2: Phiên song song trên một account và quota đã cam kết

**Files:**
- Modify: `integrations/kaggle/job_lock.py` (`kaggle_account_lock`), `integrations/kaggle/quota.py` (`select_session_account`), `integrations/kaggle/sessions.py` (`reserve_session_account`, `_lock_best`, `_lock_preferred`)
- Test: `tests/integrations/kaggle/test_quota.py`, `test_sessions.py`, `test_job_lock.py` (thêm ca)

**Interfaces:**
- Produces:
  - `kaggle_account_lock(profile: str, slot: int = 0)`: khoá riêng cho mỗi `(profile, slot)`; `slot = 0` giữ nguyên tên file khoá hiện có.
  - `select_session_account(quotas, *, locked, requested_budget_seconds, committed_seconds: Mapping[str, int] | None = None, margin_seconds=..., minimum_seconds=...) -> SessionAccount | None`: `usable = floor(remaining * 3600) - margin - committed_seconds.get(profile, 0)`.
  - `reserve_session_account(..., slots_per_account: int = 1, committed_seconds: Callable[[], Mapping[str, int]] | None = None)`: thử lần lượt `slot` từ `0` đến `slots_per_account - 1`; `locked` của quota là tập account mà **mọi** slot đã bị giữ.

- [ ] **Bước 1: Viết test lỗi:**
  - `test_two_sessions_can_hold_one_account`: với `slots_per_account=2` hai lần `reserve` liên tiếp đều lấy `acc1`; lần thứ ba lấy account khác hoặc `QuotaExhausted`.
  - `test_committed_hours_reduce_the_budget`: `remaining=3.0 h`, `committed={"acc1": 5400}` cho `usable = 10800 - 1800 - 5400 = 3600`, ngân sách `min(requested, 3600)`; `committed={"acc1": 9000}` trả `None`.
  - `test_slot_zero_keeps_the_existing_lock_name`.
  - `test_busy_slot_is_skipped_not_fatal`.
- [ ] **Bước 2:** `uv run pytest tests/integrations/kaggle/test_quota.py tests/integrations/kaggle/test_sessions.py tests/integrations/kaggle/test_job_lock.py -q`. Kỳ vọng: FAIL ở các ca mới.
- [ ] **Bước 3:** Cài các tham số mới, mặc định giữ hành vi cũ (mọi lệnh gọi hiện có không đổi).
- [ ] **Bước 4:** Chạy lại toàn bộ test trên cùng ba file và `tests/evaluation/test_rerank_service.py`. Kỳ vọng: PASS.
- [ ] **Bước 5: Commit** `feat(pharma-lab): several GPU sessions per Kaggle account, quota-aware`.

### Task 3: Chọn tập account (`auto` hoặc danh sách)

**Files:**
- Modify: `integrations/kaggle/service.py` (`resolve_session_contexts`)
- Test: `tests/integrations/kaggle/test_service.py`

**Interfaces:**
- Produces: `resolve_session_contexts(kaggle_account: str | None, *, env_file=...) -> tuple[KaggleExecutionContext, ...]` nhận `None` (mặc định `auto`), `"auto"`, một tên (`"acc2"`) hoặc danh sách cách nhau dấu phẩy (`"acc1,acc3"`); tên không tồn tại hay trùng lặp thì `ValueError` nêu các profile có sẵn.

- [ ] **Bước 1: Viết test lỗi:** `test_list_selects_exactly_those_profiles` (thứ tự theo `accN`), `test_unknown_profile_is_rejected_with_available_names`, `test_none_means_auto_for_sessions`, `test_duplicates_are_rejected`.
- [ ] **Bước 2:** chạy `pytest tests/integrations/kaggle/test_service.py -q`; kỳ vọng FAIL.
- [ ] **Bước 3:** Cài phân tích danh sách; các nơi gọi hiện có (`KaggleTextEmbeddingBackend`... dùng `hold_pinned_account`) giữ nguyên cho đến task của chúng.
- [ ] **Bước 4:** chạy lại; PASS. **Bước 5: Commit** `feat(pharma-lab): choose a set of Kaggle accounts with --kaggle-account`.

### Task 4: Sổ đăng ký kernel đang chạy

**Files:**
- Create: `integrations/kaggle/job_registry.py`
- Test: `tests/integrations/kaggle/test_job_registry.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class ShardRecord: shard_id: str; stage: str; profile: str; unit_keys: tuple[str, ...]; submitted_at: str; budget_seconds: int; kernel_reference: str | None = None`.
  - `class JobRegistry`: `__init__(path: Path)`; `register(record) -> None`; `finish(shard_id) -> None`; `live() -> list[ShardRecord]`; `committed_seconds() -> dict[str, int]` (theo profile, tổng `budget_seconds` của shard còn sống); `assigned_keys(stage: str) -> frozenset[str]`; `clear_stale(older_than_seconds: float, now: datetime) -> list[ShardRecord]`.
  - Ghi nguyên tử (tệp tạm rồi `os.replace`) dưới `kaggle_cache_lock(path)`; đọc file hỏng hoặc thiếu trả danh sách rỗng và không làm hỏng dữ liệu khác.

- [ ] **Bước 1: Viết test lỗi:** `test_register_and_finish_roundtrip`, `test_two_registries_see_each_others_records` (hai đối tượng cùng một file), `test_corrupt_file_is_treated_as_empty`, `test_committed_seconds_sum_by_profile`, `test_assigned_keys_are_per_stage`, `test_clear_stale_returns_removed_records`.
- [ ] **Bước 2:** chạy; FAIL. **Bước 3:** cài. **Bước 4:** PASS. **Bước 5: Commit** `feat(pharma-lab): registry of running Kaggle shards`.

### Task 5: Bộ điều phối song song

**Files:**
- Create: `integrations/kaggle/scheduler.py`
- Test: `tests/integrations/kaggle/test_scheduler.py`

**Interfaces:**
- Consumes: `plan_shards`, `JobRegistry`, `reserve_session_account(..., slots_per_account, committed_seconds)`, `QuotaExhausted`, `KaggleSessionCapacityReached`, `PipelineResult`.
- Produces:
  - `class ShardAdapter(Protocol)`: `stage: str`; `def missing(self) -> Sequence[WorkUnit]`; `def setup_seconds(self) -> float`; `def run_shard(self, shard: Shard, reserved: ReservedAccount) -> PipelineResult`; `def merge(self, shard: Shard, result: PipelineResult) -> int` (số đơn vị mới hoàn thành, idempotent); `def preferred_profile(self, shard: Shard, record: ShardRecord | None) -> str | None`.
  - `@dataclass(frozen=True) class SchedulerSettings: parallel: int; budget_seconds: int; margin_seconds: int; max_sessions: int | None; drain: bool = False; backoff_seconds: float = 30.0; backoff_max: int = 6`.
  - `class StopReason(StrEnum)` thêm `DRAINED`, `STUCK`, `NOTHING_MISSING` (hoặc tái dùng `sessions.StopReason` mở rộng).
  - `def run_shards(adapter: ShardAdapter, contexts: Sequence[KaggleExecutionContext], registry: JobRegistry, settings: SchedulerSettings, *, log: SessionLog, clock=time.monotonic, sleep=time.sleep) -> SchedulerReport` với `SchedulerReport(stop: StopReason, shards_run: int, merged_units: int, remaining: int, quota_table: tuple[str, ...])`.

- [ ] **Bước 1: Viết test lỗi** (bộ chuyển đổi giả, không chạm Kaggle):
  - `test_nothing_missing_returns_immediately`: không gọi `reserve`/`run_shard`, `stop == NOTHING_MISSING`.
  - `test_runs_shards_in_parallel_up_to_parallel`: 6 shard, `parallel=3`, đỉnh đồng thời đo được bằng 3.
  - `test_units_of_live_shards_are_not_planned_again` (trọng tâm 2): sổ đã có shard sống giữ khoá A, `missing()` vẫn trả A, lập kế hoạch không chứa A.
  - `test_orphan_shard_is_relaunched_with_its_account`: bản ghi sổ cũ → `run_shard` được gọi với `preferred_profile` = account trong bản ghi, cùng `shard_id`.
  - `test_quota_exhausted_with_nothing_live_stops`; `test_quota_exhausted_waits_for_live_shards_then_stops`.
  - `test_drain_stops_launching_but_waits_for_live`.
  - `test_tail_rebalance`: khi một shard xong sớm, lập ngay shard từ phần chưa giao.
  - `test_no_progress_twice_stops`: `merge` trả `0` hai lần cho cùng đơn vị → `STUCK`, không lặp vô hạn.
  - `test_429_is_backed_off`: lỗi chứa `429` → `sleep` được gọi với thời gian tăng dần, tối đa `backoff_max` lần.
  - `test_registry_is_cleaned_after_each_shard` kể cả khi `run_shard` ném lỗi.
- [ ] **Bước 2:** `uv run pytest tests/integrations/kaggle/test_scheduler.py -q`; FAIL. **Bước 3:** cài vòng điều phối bằng `ThreadPoolExecutor`, mỗi luồng giữ `reserve_session_account` trong lúc `run_shard`, cập nhật ước lượng giây từ kết quả. **Bước 4:** PASS. **Bước 5: Commit** `feat(pharma-lab): parallel scheduler for sharded Kaggle work`.

---

## Pha 2: e2e

### Task 6: Trạng thái làm việc của run e2e (tập thiếu, kẹt, gộp)

**Files:**
- Create: `pharma-lab/src/pharma_lab/e2e/work_state.py`
- Test: `tests/e2e/test_work_state.py`

**Interfaces:**
- Consumes: `GoldenItem`, `Category`, `spread`, `JsonlStore`, `AnswerRecord`, `SUPERSEDED`, `config_label`.
- Produces:
  - `MAX_FAILURES = 3`.
  - `def select_universe(golden: Sequence[GoldenItem], *, categories: Sequence[Category] | None, limit: int | None) -> list[GoldenItem]`: lọc theo nhóm (hợp, giữ thứ tự golden) rồi `spread(…, limit)`; với một nhóm thì bằng `select_items`.
  - `@dataclass(frozen=True) class Pair: label: str; item_id: str`.
  - `@dataclass(frozen=True) class WorkReport: missing: tuple[Pair, ...]; stuck: tuple[Pair, ...]; done: int`.
  - `def missing_pairs(run_root: Path, labels: Sequence[str], universe: Sequence[GoldenItem], *, retry_stuck: bool = False) -> WorkReport`.
  - `@dataclass(frozen=True) class MergeReport: appended: int; skipped: int; truncated_lines: int`.
  - `def merge_shard(archive: Path, run_root: Path, labels: Sequence[str], *, software_check: bool = True) -> MergeReport`.

- [ ] **Bước 1: Viết test lỗi:**
  - `test_missing_follows_run_items_semantics`: câu không bản ghi, `superseded`, và `error` retryable (còn ít hơn 3 dòng `error`) đều thiếu; câu hoàn thành không thiếu.
  - `test_three_errors_make_a_pair_stuck_and_retry_stuck_includes_it`.
  - `test_universe_equals_select_items_for_one_category`; `test_limit_change_does_not_touch_existing_records` (trọng tâm 5).
  - `test_merge_never_lets_error_replace_completed`; `test_merge_is_idempotent` (gộp hai lần cùng kết quả byte-for-byte).
  - `test_merge_ignores_a_truncated_last_line` (trọng tâm 1): tar có dòng cụt cuối, `truncated_lines == 1`, mọi dòng đầy đủ vẫn được gộp.
  - `test_merge_rejects_unexpected_members` (giữ luật `extract_outputs`: chỉ `<label>/answers.jsonl|run.json`).
  - `test_merge_refuses_a_different_identity` (golden sha, release, settings, pipeline khác).
  - `test_merge_refuses_different_model_sha_or_llama_build` và `test_merge_warns_on_different_proxy_version` (đọc `run.json["software"]`).
- [ ] **Bước 2:** `uv run pytest tests/e2e/test_work_state.py -q`; FAIL. **Bước 3:** cài; đếm thất bại bằng số dòng `status == "error"` của câu. **Bước 4:** PASS. **Bước 5: Commit** `feat(pharma-lab): local-first work state for e2e runs`.

### Task 7: Harness chạy một lát, dừng theo hạn, ghi phần mềm

**Files:**
- Modify: `e2e/harness.py` (`run_items`, `E2ERunRequest`, `run_e2e`), `e2e/kernel_harness.py`, `e2e/run_identity.py` (nếu cần `extra`)
- Test: `tests/e2e/test_executor.py` (ca mới ở `run_items`), `tests/e2e/test_kernel_harness.py` (mới)

**Interfaces:**
- Produces:
  - `run_items(..., stop_at: float | None = None, clock: Callable[[], float] = time.time)`: trước mỗi câu, nếu `stop_at is not None and clock() >= stop_at` thì bỏ qua (câu đó vẫn "thiếu").
  - `E2ERunRequest.only_ids: frozenset[str] | None = None`, `E2ERunRequest.stop_at: float | None = None`, `E2ERunRequest.software: Mapping[str, str] = {}` (ghi vào `run.json["software"]` qua `extra`, chỉ khi không rỗng).
  - Định dạng `e2e_job.json` của shard: `{"run": str, "shards": [{"config": str, "pipeline_options": [str], "item_ids": [str]}], "deadline_seconds": float, "commit": str | None, "stop_at": float | None, "software": {…}}`; `kernel_harness.run_job` chạy mỗi phần tử, nhãn thư mục bằng `config_label`, hai lượt (lỗi thử lại một lần) như cũ.

- [ ] **Bước 1: Viết test lỗi:** `test_run_items_stops_starting_new_items_after_stop_at` (đồng hồ giả: chỉ 2 trong 5 câu chạy, 3 câu còn thiếu và không có bản ghi `error`), `test_only_ids_limits_the_items`, `test_run_json_records_software_only_when_given`, `test_kernel_harness_runs_each_shard_entry_with_its_label` (`full+guard=false` được tạo đúng thư mục), `test_existing_run_identity_unchanged` (so `run.json` của run mẫu).
- [ ] **Bước 2-4:** FAIL → cài → PASS. **Bước 5: Commit** `feat(pharma-lab): e2e harness runs a slice and stops at a deadline`.

### Task 8: Worker trong kernel: hạn phiên, chụp định kỳ, mốc thời gian

**Files:**
- Modify: `e2e/kernel_worker.py`
- Test: `tests/e2e/test_kernel_worker.py`

**Interfaces:**
- Consumes: `worker_deadline(config, clock)`, `artifact_from_output`, `pack_outputs`, `completed_answers`.
- Produces:
  - `def run_with_snapshots(command: list[str], *, env: Mapping[str, str], run_root: Path, labels: Sequence[str], output_dir: Path, total: int, identity, snapshot_seconds: float, clock=time.monotonic, sleep=time.sleep) -> int`: chạy harness bằng `Popen`, mỗi `snapshot_seconds` gọi `write_snapshot`; trả mã thoát.
  - `def write_snapshot(run_root, labels, output_dir, *, total, identity) -> CloudArtifact`: ghi `e2e_output.tar` và manifest bằng tệp tạm rồi `os.replace`.
  - `def stop_at_from_config(config: Mapping, clock=time.time) -> float` = `worker_deadline(config, clock)`.
  - `class PhaseLog`: ghi `[e2e] phase=<tên> seconds=<n>` cho `install_venv`, `postgres`, `qdrant`, `corpus_import`, `servers`, `harness`.
  - `run_e2e_worker` truyền `stop_at` và `software` (sha256 các model, bản `llama-server`, bản backend) vào `e2e_job.json` trước khi chạy harness; completion của artifact là `total = số cặp của shard`, `complete = số cặp không phải error`.

- [ ] **Bước 1: Viết test lỗi:** `test_snapshot_is_written_atomically` (không để lại tệp tạm, manifest khớp tar), `test_snapshot_every_interval_with_fake_clock`, `test_snapshot_survives_kill`: giả lập harness bị kill, thư mục output vẫn có snapshot cuối đọc được bằng `load_cloud_artifact(allow_partial=True)`, `test_snapshot_zero_disables`, `test_final_artifact_completion_counts_non_error_pairs`, `test_phase_log_lines_for_every_setup_step`, `test_stop_at_uses_the_session_budget_and_margin`.
- [ ] **Bước 2-4:** FAIL → cài → PASS. **Bước 5: Commit** `feat(pharma-lab): e2e kernel worker snapshots results and stops at the session deadline`.

### Task 9: Preset LLM và `kernel_env` theo vai

**Files:**
- Create: `e2e/llm_presets.py`
- Modify: `e2e/kernel_env.py`
- Test: `tests/e2e/test_llm_presets.py`, `tests/e2e/test_kernel_env.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class RoleEndpoint: base_url: str; model: str; api_key: str; extra_body: Mapping[str, object] = {}; reasoning_effort: str | None = None`.
  - `@dataclass(frozen=True) class LlmPreset: name: str; roles: Mapping[str, RoleEndpoint]; needs_proxy: bool; providers: frozenset[str]` (loại credential cần, ví dụ `{"antigravity"}`, `{"claude"}`).
  - `PRESETS: Mapping[str, LlmPreset]` gồm `qwen` (mọi vai kể cả `AGENT` tới llama-server cục bộ như hiện nay, `enable_thinking: false`), `gemini` (`gemini-3.8-flash-high`, `thinkingLevel` do config proxy), `opus` (`claude-opus-5-5`, `reasoning_effort="minimal"`); khoá `proxypal-local` và `http://127.0.0.1:8317/v1` cho preset qua proxy.
  - `kernel_backend_env(..., preset: LlmPreset = PRESETS["qwen"]) -> dict[str, str]` (giữ chữ ký cũ, đối số mới có mặc định).

- [ ] **Bước 1: Viết test lỗi:** `test_qwen_preset_env_is_byte_identical_to_current` (so với kết quả cũ của `kernel_backend_env`), `test_every_llm_role_is_covered_by_every_preset` (dùng `LlmRole`), `test_proxy_presets_point_at_localhost_only`, `test_opus_sets_minimal_reasoning_effort`, `test_unknown_preset_lists_the_valid_names`.
- [ ] **Bước 2-4:** FAIL → cài → PASS. **Bước 5: Commit** `feat(pharma-lab): LLM presets for kernel runs`.

### Task 10: Đầu vào tĩnh dùng lại theo nội dung

**Files:**
- Modify: `integrations/kaggle/dependencies.py` (`default_desired_datasets`, `kaggle_input_root`), `integrations/kaggle/models.py` (`StageJob.worker_config` khoá `static_input_keys`), `integrations/kaggle/e2e_stage.py`, `e2e/kernel_worker.py` (`restore_inputs`)
- Test: `tests/integrations/kaggle/test_dependencies.py`, `test_e2e_stage.py`

**Interfaces:**
- Produces:
  - Job có `worker_config["static_input_keys"]` (danh sách khoá file thuộc phần tĩnh) thì `default_desired_datasets` trả **hai** dataset đầu vào: `pipeline-static-<sha16>` (sha16 chỉ phụ thuộc nội dung các file tĩnh, tạo một lần cho mỗi account) và `pipeline-input-<sha16 job>` (chỉ phần còn lại), cả hai private.
  - `kaggle_input_root(job)` trở thành `kaggle_input_roots(job) -> Mapping[str, Path]` (khoá file → thư mục mount); worker `restore_inputs` đọc theo bản đồ này.
  - `E2ERunStage.build_job` đánh dấu `golden`, `requirements`, `corpus/*` là tĩnh; `job` là động.

- [ ] **Bước 1: Viết test lỗi:** `test_two_shards_of_one_run_share_the_static_dataset` (slug tĩnh bằng nhau, slug job khác nhau), `test_static_dataset_changes_when_the_corpus_changes`, `test_static_dataset_is_private`, `test_existing_stages_still_get_one_input_dataset`, `test_worker_restores_files_from_both_roots`.
- [ ] **Bước 2-4:** FAIL → cài → PASS (chạy cả `tests/integrations/kaggle`). **Bước 5: Commit** `feat(pharma-lab): reuse the static e2e inputs across shards`.

### Task 11: Bộ chuyển đổi e2e và lệnh `e2e run`, `e2e status`

**Files:**
- Create: `e2e/kaggle_shards.py` (bộ chuyển đổi), thay `e2e/kaggle_run.py` (giữ `trimmed_corpus`, `reranker_profile`, `_requirements`)
- Modify: `cli/commands/e2e.py` (lệnh `run`, thêm `status`)
- Test: `tests/e2e/test_kaggle_shards.py` (mới), `tests/cli/test_e2e_command.py` (mới, theo mẫu `tests/cli/test_embed_command.py`), `tests/e2e/test_kaggle_run.py` (cập nhật: bỏ các ca của `check_targets` và `run_on_kaggle` một job, giữ ca của `trimmed_corpus`, `extract` cũ chuyển sang `test_work_state.py`)

**Interfaces:**
- Consumes: `ShardAdapter`, `run_shards`, `missing_pairs`, `merge_shard`, `select_universe`, `LlmPreset`.
- Produces:
  - `class E2EShardAdapter` cài `ShardAdapter` (`stage = "e2e-run"`); `missing()` trả `WorkUnit(key=f"{label}\x1f{item_id}", seconds=ước lượng từ latency_seconds đã có theo (nhãn, nhóm câu), group=bố cục)`; `run_shard` dựng thư mục job (golden, requirements, corpus rút gọn, `e2e_job.json` tất định) và gọi `run_kaggle_stage(stage=E2E_RUN, max_runs=1, resume_remote=<theo shard>, artifact_sink=…)`; `merge` gọi `merge_shard`.
  - Lệnh: `e2e run --backend kaggle --run R --config C… [--category …] [--limit N] [--pipeline-option k=v…] [--llm qwen|gemini|opus] [--kaggle-account auto|accN[,accM]] [--parallel N] [--budget-seconds S] [--max-sessions K] [--drain] [--retry-stuck] [--judge] [--latency] [--with-proxy-credentials]`. `--latency` là lượt đo độ trễ (spec §4.7): đúng một shard, `--concurrency 1`, bố cục A, ghi vào run `<run>-c1`; kết hợp với `--parallel` lớn hơn 1 hoặc nhiều bố cục thì lệnh từ chối. Bỏ `check_targets` và việc từ chối thư mục đã có `answers.jsonl`.
  - `e2e status --run R [--config C…]`: in bảng nhãn × (xong/tổng/kẹt), các kernel đang chạy (từ sổ), quota từng account, số giờ GPU ước tính còn cần.
  - Mã thoát: `0` xong, `10` tạm dừng (hết quota hoặc `--drain`), `11` có cặp kẹt.

- [ ] **Bước 1: Viết test lỗi:** `test_missing_units_cost_uses_existing_latencies` (nguồn: các `answers.jsonl` có `latency_seconds`; thiếu thì hằng số mặc định), `test_job_json_is_deterministic_for_the_same_pairs` (cùng cặp → cùng danh tính job, cơ sở của việc nối lại), `test_run_shard_calls_the_stage_with_the_reserved_account`, `test_rerun_merges_into_existing_answers_instead_of_refusing`, `test_cli_exit_codes_for_done_paused_and_stuck`, `test_status_lists_live_shards_and_quota` (hai account giả), `test_decision_roles_in_local_env_stop_the_command` (vai `systemone` + chế độ kernel), `test_nothing_missing_exits_zero_without_touching_kaggle` (trọng tâm 6), `test_limit_and_category_define_the_universe` (trọng tâm 5), `test_latency_mode_forces_one_shard_with_concurrency_one`, `test_latency_mode_rejects_parallel_above_one`, `test_latency_run_lands_in_the_c1_directory`.
- [ ] **Bước 2-4:** FAIL → cài → PASS (kèm `tests/e2e`, `tests/cli`). **Bước 5: Commit** `feat(pharma-lab): resumable multi-account e2e runs on Kaggle`.

### Task 12: `cli-proxy-api` trong kernel và dataset credential (tùy chọn)

**Files:**
- Create: `e2e/proxy_kernel.py` (phía kernel), `e2e/proxy_credentials.py` (phía máy)
- Modify: `integrations/kaggle/api.py` (lệnh xoá dataset), `integrations/kaggle/dataset_service.py` (`delete_dataset`), `e2e/kernel_worker.py` (khởi động proxy), `e2e/kaggle_shards.py`, `cli/commands/e2e.py`
- Test: `tests/e2e/test_proxy_kernel.py`, `tests/e2e/test_proxy_credentials.py`, `tests/integrations/kaggle/test_dataset_service.py`

**Interfaces:**
- Produces (kernel): `PROXY_VERSION = "8.0.28"`; `def proxy_release_url(version: str = PROXY_VERSION) -> str` (`…/releases/download/v8.0.28/CLIProxyAPI_8.0.28_linux_amd64.tar.gz`); `def write_proxy_config(template: Path, target: Path, auth_dir: Path) -> Path` (ép `host: 127.0.0.1`, `port: 8317`, `auth-dir`); `def install_credentials(source: Path, auth_dir: Path) -> list[str]` (thư mục `0700`, file `0600`, trả tên file, không đọc nội dung); `def start_proxy(binary: Path, config: Path, *, wait_seconds: float = 60) -> subprocess.Popen` chờ `/v1/models` trên localhost.
- Produces (máy): `@dataclass(frozen=True) class CredentialFile: name: str; type: str; size: int`; `def list_credentials(directory: Path) -> list[CredentialFile]` (chỉ đọc trường `type`); `def export_credentials_from_volume(volume: str, target: Path) -> None` (docker, chỉ đọc); `class CredentialDataset` (context manager) tạo dataset **private** `pipeline-cred-<ngẫu nhiên>` cho account chạy, và xoá nó khi thoát kể cả khi lỗi, thử lại `3` lần với thông báo to nếu xoá thất bại; `DatasetService.delete_dataset(reference: str) -> None`.
- Cờ `--with-proxy-credentials` bắt buộc cho preset `needs_proxy`; thiếu cờ thì lệnh dừng. Lệnh in `name (type)` của từng file sẽ lên. Log không bao giờ in nội dung; job và `jobs.json` không chứa khoá.

- [ ] **Bước 1: Viết test lỗi:** `test_release_url_is_pinned`, `test_config_forces_localhost_binding`, `test_credentials_are_copied_with_private_modes`, `test_start_proxy_waits_for_models_endpoint` (máy chủ HTTP giả), `test_list_credentials_reads_only_the_type_field` (file chứa chuỗi bí mật; kết quả và log không có chuỗi đó), `test_credential_dataset_is_never_public` (khẳng định `public=False` ở lệnh tạo), `test_credential_dataset_is_deleted_on_exit_and_on_error`, `test_failed_deletion_is_retried_and_reported` (trọng tâm 4), `test_credentials_never_enter_archive_listing` (`list_archive_files` không liệt kê thư mục credential), `test_proxy_preset_without_the_flag_is_refused`, `test_no_tunnel_guard_still_green` (chạy lại `test_no_external_exposure`).
- [ ] **Bước 2-4:** FAIL → cài → PASS. **Bước 5: Commit** `feat(pharma-lab): run cli-proxy-api inside the Kaggle kernel with per-run private credentials`.

---

## Pha 3: các bước còn lại

### Task 13: Rerank chia shard

**Files:**
- Create: `evaluation/rerank_shards.py`
- Modify: `evaluation/rerank_service.py` (`_run_kaggle_unlocked`: thay `run_account_sessions` bằng `run_shards`), `cli/commands/rerank.py` (cờ)
- Test: `tests/evaluation/test_rerank_shards.py`, `tests/evaluation/test_rerank_service.py`

**Interfaces:**
- Produces: `class RerankShardAdapter` (`stage = "rerank"`): `missing()` liệt kê truy vấn còn thiếu điểm từ `RerankScoreCache` (đơn vị là truy vấn, `seconds` = số ứng viên còn thiếu × giây mỗi cặp ước lượng từ profile đã chọn); `run_shard` ghi thư mục con `shard-<id>/` chứa `candidates.jsonl` (tập con các dòng truy vấn) và bản sao `manifest.json`, rồi `run_kaggle_stage(stage=RERANK, local_checkpoint=RerankCacheCheckpoint(...), artifact_sink=…)`; `merge` dùng `_merge_remote_rerank_scores` hiện có. Lệnh `rerank` nhận `--parallel`, `--drain`, `--kaggle-account auto|accN[,accM]`.

- [ ] **Bước 1: Viết test lỗi:** `test_missing_queries_come_from_the_score_cache`, `test_shard_input_is_a_subset_with_the_candidate_manifest` (worker chỉ cần `candidate_manifest` tồn tại), `test_checkpoint_source_counts_only_the_shard_pairs`, `test_merge_is_idempotent_and_keeps_existing_scores`, `test_service_runs_two_shards_on_two_accounts` (giả), `test_complete_cache_needs_no_session` (giữ ca hiện có).
- [ ] **Bước 2-4:** FAIL → cài → PASS (toàn bộ `tests/evaluation`). **Bước 5: Commit** `feat(pharma-lab): shard rerank across Kaggle accounts`.

### Task 14: Embed corpus chia shard

**Files:**
- Create: `embeddings/shards.py`; Modify: `embeddings/service.py` (`KaggleTextEmbeddingBackend`), `cli/commands/bundle.py` (cờ)
- Test: `tests/embeddings/test_shards.py`, `tests/embeddings/test_service.py`

**Interfaces:**
- Produces: `class TextEmbeddingShardAdapter` (`stage = "corpus-embed"`): `missing()` từ `open_text_cache(...).missing(read_embedding_inputs(...))` (đơn vị là một văn bản, `seconds` tỉ lệ độ dài); `run_shard` ghi `missing_inputs.shard-<id>.jsonl` rồi `run_kaggle_stage(stage=CORPUS_EMBED, …)`; `merge` dùng `merge_records(..., key=cache_record_key, ...)` hiện có. Bỏ `hold_pinned_account` (thay bằng khoá account của lớp chung). `ensure_runtime_profile` vẫn gọi một lần trước khi chia.

- [ ] **Bước 1: Viết test lỗi:** `test_missing_texts_only_are_units`, `test_shards_cover_all_missing_texts_once`, `test_merge_keeps_one_vector_per_text`, `test_force_sends_everything`, `test_default_account_is_auto`.
- [ ] **Bước 2-4:** FAIL → cài → PASS. **Bước 5: Commit** `feat(pharma-lab): shard corpus embedding across Kaggle accounts`.

### Task 15: Embed truy vấn chia shard

**Files:**
- Create: `evaluation/query_embedding_shards.py`; Modify: `evaluation/query_embedding_service.py`, `cli/commands/embed.py`
- Test: `tests/evaluation/test_query_embedding_shards.py`, `tests/evaluation/test_query_embedding_service.py`

**Interfaces:**
- Produces: `class QueryEmbeddingShardAdapter` (`stage = "query-embed"`): `missing()` từ `QueryEmbeddingCache.get(...) is None` (đơn vị là một dòng truy vấn); `run_shard` ghi `*.shard-<id>.jsonl`; `merge` dùng `merge_records` với khoá `(model, query_id, query_hash)` hiện có. Giữ quy tắc "bản vector đã có trong cache là bản duy nhất" (không ghi đè vector khác chữ số cuối).

- [ ] **Bước 1: Viết test lỗi:** `test_cached_queries_are_never_resent`, `test_recomputed_vector_does_not_replace_the_cached_one`, `test_shards_partition_the_missing_queries`, `test_default_account_is_auto`.
- [ ] **Bước 2-4:** FAIL → cài → PASS. **Bước 5: Commit** `feat(pharma-lab): shard query embedding across Kaggle accounts`.

### Task 16: `pharma-lab kaggle status`

**Files:**
- Create: `cli/commands/kaggle.py`; Modify: `cli/main.py` (đăng ký); Test: `tests/cli/test_kaggle_command.py`

**Interfaces:**
- Produces: lệnh `kaggle status [--kaggle-account auto|accN[,accM]]` liệt kê mọi shard sống trong các sổ (`data/work/**/jobs.json`) theo bước và account, bảng quota từng account (`quota_table`), giờ reset, và các dataset credential còn sót (tên bắt đầu `pipeline-cred-`) kèm gợi ý xoá.

- [ ] **Bước 1: Viết test lỗi:** `test_status_groups_live_shards_by_stage_and_account`, `test_status_reports_leftover_credential_datasets`, `test_status_works_with_one_account_unreachable` (account lỗi API không làm hỏng cả bảng).
- [ ] **Bước 2-4:** FAIL → cài → PASS. **Bước 5: Commit** `feat(pharma-lab): kaggle status command`.

### Task 17: Chấm điểm gối đầu (`--judge`)

**Files:**
- Create: `e2e/judge_follower.py`; Modify: `cli/commands/e2e.py`
- Test: `tests/e2e/test_judge_follower.py`

**Interfaces:**
- Produces: `class JudgeFollower`: `start(run_root, labels, judge_request_factory)`, `notify_merged(labels)`, `stop() -> None`; chạy `run_judge` cho các câu mới về trong một luồng nền, nối lại theo từng câu (hành vi sẵn có của `e2e judge`), lỗi của judge không làm hỏng việc gộp.

- [ ] **Bước 1: Viết test lỗi:** `test_judges_only_items_without_judgements`, `test_judge_error_does_not_stop_merging`, `test_stop_waits_for_the_running_judge`, `test_judge_off_by_default`.
- [ ] **Bước 2-4:** FAIL → cài → PASS. **Bước 5: Commit** `feat(pharma-lab): optional overlapped judging while shards return`.

---

## Pha 4: Tài liệu, dọn tư duy tunnel, nghiệm thu

### Task 18: Cập nhật spec, plan, docs, memory

**Files:**
- Modify: `docs/superpowers/specs/2026-10-14-paper-v2-design.md` (§2.1b, §2.5, §3 nhắc "tự host", bảng A và C, §7 pha 0, §8), các plan `2026-10-16-paper-v2-phase-0-measurement.md`, `…-phase-1-decision-model.md`, `…-phase-2-react.md`, `2026-10-20-kaggle-batch-e2e.md`, spec `2026-10-20-kaggle-batch-e2e-design.md` (sửa các bước nhắc `llm-server`, `rerank-server`, `embed-server`); thêm ghi chú đầu trang cho tài liệu camera-ready (không sửa nội dung); `pharma-lab/docs/guides/e2e-evaluation.md`, `cli-reference.md`, `workflow-local-kaggle.md`, `evaluation.md`.
- Test: `pharma-lab/tests/test_docs.py` (đã có) phải xanh; thêm ca khẳng định các hướng dẫn không còn nhắc `llm-server|rerank-server|embed-server|cloudflared|trycloudflare`.

- [ ] **Bước 1:** thêm ca vào `test_docs.py` (tên `test_guides_do_not_mention_removed_serve_commands`); chạy, kỳ vọng FAIL ở các guide cũ.
- [ ] **Bước 2:** sửa tài liệu theo spec §5, mô tả quy trình mới: `e2e run`, `e2e status`, dừng bằng Ctrl-C hoặc `--drain`, nối lại, đổi account, `--parallel`, `--with-proxy-credentials`, `kaggle status`.
- [ ] **Bước 3:** chạy `uv run pytest tests/test_docs.py -q`; PASS.
- [ ] **Bước 4:** cập nhật memory (`versioning-camera-ready-v2.md`, `kaggle-no-public-urls.md`, `proxy-credentials-on-kaggle.md`) với quy trình mới.
- [ ] **Bước 5: Commit** `docs: Kaggle runs resume, shard and run the proxy inside the kernel`.

### Task 19: Nghiệm thu bằng job Kaggle thật (cần quota sau reset 2026-10-24)

Không có test tự động; ghi kết quả vào `docs/superpowers/specs/2026-10-23-kaggle-resumable-runs-design.md` (mục "Kết quả nghiệm thu").

- [ ] **Bước 1: Đo dựng môi trường.** `uv run pharma-lab e2e run --backend kaggle --run accept-1 --config full --config no-rerank --limit 20 --kaggle-account acc1 --parallel 1 --budget-seconds 7200`. Đọc log `phase=…` của kernel; ghi thời gian từng bước, VRAM của từng server. Kỳ vọng: job xong, `e2e status` báo 40/40.
- [ ] **Bước 2: Kiểm chứng giả định output của kernel lỗi.** Chạy lại với `--limit 100 --budget-seconds 3600` để ép dừng theo hạn; kỳ vọng: kernel kết thúc trước khi bị kill, artifact đủ phần đã làm, `e2e status` thấy thiếu đúng phần chưa chạy. Nếu sai giả định (không có output khi kernel lỗi), ghi lại và đặt `snapshot_seconds` mặc định thành `0`.
- [ ] **Bước 3: Dừng và nối lại.** Chạy ba shard, Ctrl-C giữa chừng, chạy lại cùng lệnh; kỳ vọng: nối lại kernel đang chạy, không cặp nào chạy thừa, kết quả cuối khớp tổng.
- [ ] **Bước 4: Đổi account.** Chạy phần còn thiếu với `--kaggle-account acc3`; kỳ vọng: nhận tiếp đúng phần thiếu.
- [ ] **Bước 5: Proxy.** Chạy `--llm gemini --with-proxy-credentials` với `--limit 10` rồi kiểm tra: credential dataset đã bị xoá (`kaggle status` không còn `pipeline-cred-`), và credential cục bộ vẫn dùng được (thử gọi proxy cục bộ một lần) để kiểm tra xoay vòng refresh token.
- [ ] **Bước 6: Commit** kết quả nghiệm thu vào spec, đẩy `v2.0.0`.

---

## Tự rà soát

**Phủ spec:** §4.1 gộp và độ chính xác → T6; §4.2 shard → T1, T5, T11; §4.3 kernel → T7, T8; §4.4 điều phối và đầu vào tĩnh → T4, T5, T10, T11; §4.5 tốc độ → T1, T5, T10, T17 (hàng đợi chung trong kernel và bố cục hai bản LLM là giai đoạn 2, **không có task**, chỉ làm sau số đo ở T19); §4.6 an toàn → T12 và ràng buộc chung; §4.7 độ trễ → cờ `--latency` ở T11 (lát 100 câu `spread` mỗi cấu hình qua `--limit 100`); §4.8 proxy → T9, T12; §4.9 lớp chung và các bước còn lại → T13 đến T16; §5 dọn tài liệu → T18; §7 nghiệm thu → T19.

**Chữ ký nhất quán:** `WorkUnit`, `Shard`, `plan_shards` (T1) dùng nguyên ở T5, T11, T13 đến T15; `ShardRecord`/`JobRegistry` (T4) dùng ở T5, T16; `reserve_session_account(..., slots_per_account, committed_seconds)` (T2) dùng ở T5; `select_universe`/`missing_pairs`/`merge_shard` (T6) dùng ở T11, T17; `LlmPreset` (T9) dùng ở T11, T12.

**Khoảng trống đã biết:** bố cục hai bản LLM và hàng đợi chung trong kernel hoãn đến sau T19 (spec §4.2, §4.5); xử lý khoá API trực tiếp (Jev qua OpenRouter) do người dùng cung cấp sau, `RoleEndpoint` (T9) chừa chỗ.
