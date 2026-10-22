# E2E trong một kernel Kaggle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `pharma-lab e2e run --backend kaggle` chạy cấu hình e2e của setting Qwen trọn trong một kernel Kaggle theo lô, và không còn đường tunnel nào.

**Architecture:** Thêm stage `E2E_RUN` vào hạ tầng batch sẵn có: dataset input mang golden, bundle corpus và requirements backend; dataset model cho từng GGUF. Worker trong kernel cài Postgres/Qdrant, import corpus, chạy ba llama-server trên localhost rồi gọi đúng `run_e2e` của harness, đóng gói các thư mục cấu hình thành một tar. CLI tải tar về và giải nén vào thư mục run.

**Tech Stack:** Python 3.12, Typer, pytest, Kaggle CLI, llama.cpp runtime dataset, PostgreSQL (apt), Qdrant v1.19.1 binary, qdrant-client + fastembed (BM25).

**Spec:** `docs/superpowers/specs/2026-10-20-kaggle-batch-e2e-design.md`

## Global Constraints

- Không kernel nào mở cổng hay tunnel; internet chỉ để tải (pip, apt, binary Qdrant, model BM25).
- Model: `qwen3.5:9b-q8_0` mọi role, `qwen3-reranker:4b-q8_0`, `qwen3-embedding:4b-fp16`; GPU0 cho LLM, GPU1 cho reranker và embedding.
- Qdrant `v1.19.1` (như `compose.yaml`).
- Một job = một phiên kernel = một lần import corpus = một release.
- Thư mục cấu hình đích đã có `answers.jsonl` thì CLI từ chối.
- Identity của run cũ không đổi; test trước; ruff, pyrefly, không `noqa`, không `type: ignore`.

## Review Focus

- Tar tải về chứa thư mục cấu hình lạ hoặc đường dẫn `..`: giải nén phải từ chối (test ở Task 6).
- Kernel hết giờ giữa chừng: artifact báo `complete < total`, CLI báo lỗi rõ ràng và không ghép kết quả dở (Task 6).
- Hai model cùng GPU1 không đủ VRAM: server không healthy thì worker dừng với log server (đã có ở `managed_model_servers`).
- `--category` không có câu nào trong golden: CLI từ chối trước khi đẩy job (Task 5).
- Account bị khóa hoặc hết quota: dùng account trong `.env`, không `auto` mặc định (Task 6).

---

### Task 1: Xóa đường tunnel

**Files:** xóa `pharma-lab/src/pharma_lab/integrations/kaggle/workers/serve.py`, `pharma-lab/src/pharma_lab/e2e/model_server.py`, `pharma-lab/tests/e2e/test_model_server.py`, `pharma-lab/tests/integrations/kaggle/test_model_serve.py`; sửa `integrations/kaggle/stages.py` (bỏ `ModelServeStage`, `_serve_api_key`, hai adapter), `integrations/kaggle/models.py` (bỏ `RERANK_SERVE`, `LLM_SERVE`), `cli/commands/e2e.py` (bỏ `rerank-server`, `llm-server`, `_serve`), `tests/integrations/kaggle/test_worker_bundle_imports.py`, `pharma-lab/docs/guides/e2e-evaluation.md`, `pharma-lab/docs/guides/cli-reference.md`, `docs/superpowers/plans/2026-10-19-camera-ready.md`; xóa thư mục `pharma-lab/data/work/serve/`.

- [ ] Xóa và sửa như trên; `serve_runtime` trong catalog đổi chú thích thành layout cố định của model chat khi chạy trong kernel.
- [ ] `rg -n "cloudflared|tunnel|rerank-server|llm-server|RERANK_SERVE|LLM_SERVE" pharma-lab/src pharma-lab/tests pharma-lab/docs` không còn kết quả.
- [ ] `uv run pytest -q`, ruff, pyrefly pass. Commit `refactor(pharma-lab): remove the tunnel model servers`.

### Task 2: Nhiều llama-server trong một kernel

**Files:** `integrations/kaggle/workers/runtime.py`, `tests/integrations/kaggle/test_worker_runtime.py` (hoặc file test runtime hiện có).

**Produces:** `managed_model_servers(config)` đọc thêm hai khóa tùy chọn: `model_filename` (tìm đúng file này dưới input root thay vì một `*.gguf` duy nhất) và `visible_devices` (một server duy nhất trên các GPU này, bỏ qua `server_layout`).

- [ ] Test `test_model_filename_picks_one_gguf_among_several` và `test_visible_devices_overrides_the_layout` (giả lập `subprocess.Popen` và health như các test runtime hiện có): hai file GGUF trong input, server được gọi với đúng file và `CUDA_VISIBLE_DEVICES=1`.
- [ ] Cài đặt; pytest, ruff, pyrefly; commit `feat(pharma-lab): several model servers in one kernel`.

### Task 3: Dataset model cho nhiều model, bundle có backend

**Files:** `integrations/kaggle/dependencies.py`, `integrations/kaggle/kernels.py`, test tương ứng.

**Produces:** `default_desired_datasets` tạo một dataset model cho mỗi tên trong `job.worker_config["models"]` khi khóa này có (giữ nguyên hành vi một model khi không có). `PipelineKernelService` nhận thêm `backend_source_root: Path | None`; khi `job.worker_config.get("bundle_backend")` thì zip thêm `pharma_agent/**/*.py` và các file không phải `.py` mà backend cần lúc chạy (migrations).

- [ ] Test: ba model trong `models` cho ba `DesiredDataset` kind `model`, `model-1`, `model-2` cùng một input; bundle có `pharma_agent/__init__.py` chỉ khi cờ bật (test cấm `pharma_agent` hiện có vẫn đúng cho các stage khác).
- [ ] Cài đặt; pytest, ruff, pyrefly; commit `feat(pharma-lab): model datasets and backend source for multi-model kernels`.

### Task 4: Stage `E2E_RUN`

**Files:** `integrations/kaggle/models.py` (`StageName.E2E_RUN = "e2e-run"`), tạo `integrations/kaggle/e2e_stage.py`, `integrations/kaggle/stages.py` (đăng ký adapter), test `tests/integrations/kaggle/test_e2e_stage.py`.

**Produces:** `E2ERunStage.build_job(request) -> StageJob`. `request.input_path` là một file JSON `e2e_job.json` do CLI ghi: `{"run": str, "configs": [str], "categories": [str], "item_ids": [str]}`. Input bundle: `e2e_job.json`, `golden_e2e.jsonl`, `backend_requirements.txt` và mọi file của bundle `data/corpus/formulary` (khóa `corpus/<đường dẫn tương đối>`, filename phẳng `corpus__<đường dẫn với / thay bằng __>`). `expected_total = len(item_ids) * len(configs)`. `data_filename = "e2e_output.tar"`. `worker_config`: `models` (ba tên ở Global Constraints), `servers` (danh sách `{model, model_filename, port, visible_devices, runtime_overrides}` với cổng 11434 LLM, 11435 rerank, 11436 embedding), `bundle_backend: true`, `enable_internet: true`, `qdrant_version: "v1.19.1"`.

- [ ] Test: job có đúng các khóa trên; đổi `configs` thì identity đổi; model không thuộc catalog thì `ValueError`.
- [ ] Cài đặt; pytest, ruff, pyrefly; commit `feat(pharma-lab): e2e-run stage`.

### Task 5: Worker trong kernel

**Files:** tạo `integrations/kaggle/workers/e2e.py`, tạo `e2e/kernel_env.py`, test `tests/e2e/test_kernel_env.py`, `tests/integrations/kaggle/test_e2e_worker.py`.

**Produces:**
- `kernel_backend_env(*, llm_port: int, rerank_port: int, embedding_port: int, postgres_dsn: str, qdrant_url: str) -> dict[str, str]`: mọi role LLM trỏ `http://127.0.0.1:{llm_port}/v1`, model `qwen3.5:9b-q8_0`, `EXTRA_BODY` tắt thinking như các run Qwen trước, timeout chat 600 giây; rerank `native_rerank` tới cổng rerank với model `qwen3-reranker:4b-q8_0`; embedding `qwen3-embedding:4b-fp16`, chiều 2560; DSN và Qdrant URL.
- `run_e2e_worker(config: dict) -> CloudArtifact`: giải nén corpus về cây thư mục gốc; `pip install -r backend_requirements.txt`; cài và khởi động Postgres, tải và chạy Qdrant `v1.19.1`; `pharma-agent migrate`, `pharma-agent corpus import <bundle> --collection formulary --publish`; mở ba server (Task 2); gọi `run_e2e` cho từng cấu hình với `category`/item theo `e2e_job.json`; tar các thư mục `<run>/<config>/` (chỉ `answers.jsonl`, `run.json`) thành `e2e_output.tar`; `artifact_from_output` với `complete` = số câu `completed`.

- [ ] Test `kernel_backend_env` với các giá trị trên; test đóng gói tar chỉ chứa `<config>/answers.jsonl` và `<config>/run.json`.
- [ ] Cài đặt; pytest, ruff, pyrefly; commit `feat(pharma-lab): e2e worker that runs the whole system in one kernel`.

### Task 6: CLI `e2e run --backend kaggle`

**Files:** `cli/commands/e2e.py`, tạo `e2e/kaggle_run.py`, test `tests/e2e/test_kaggle_run.py`, `pharma-lab/docs/guides/e2e-evaluation.md`.

**Produces:** `e2e run` nhận `--backend [local|kaggle]` (mặc định `local`), `--config` và `--category` lặp được với `kaggle`, `--kaggle-account` (mặc định account trong `.env`). `run_on_kaggle(request) -> list[Path]`: kiểm thư mục đích chưa có `answers.jsonl`, ghi `e2e_job.json`, gọi `run_kaggle_stage(stage=E2E_RUN, ...)`, kiểm `completion.is_complete`, giải nén `e2e_output.tar` vào `data/evaluation/e2e/runs/<run>/` bằng `extract_outputs(tar, run_root, configs)` từ chối mọi thành viên ngoài `<config>/answers.jsonl|run.json`.

- [ ] Test: đích có sẵn `answers.jsonl` thì lỗi; tar có `../x` hoặc cấu hình lạ thì lỗi; category rỗng thì lỗi; artifact chưa đủ thì lỗi và không ghi gì.
- [ ] Guide: thay phần llm-server/rerank-server bằng `--backend kaggle`, ghi giới hạn setting Gemini có reranker.
- [ ] pytest, ruff, pyrefly, `tests/test_docs.py`; commit `feat(pharma-lab): e2e run on Kaggle inside one kernel`.

### Task 7: Chạy thật và điền số

- [ ] `uv run pharma-lab e2e run --backend kaggle --run e2e-qwen35-9b-cr --config no-rerank --config no-guard-no-rerank --category injection --category out_of_scope --category unanswerable --kaggle-account acc1` trong tmux; theo dõi log kernel.
- [ ] `e2e judge` cho hai cấu hình (nạp `data/work/v1-stack.env` không cần vì judge chỉ cần proxy và embedding local); `e2e report --run e2e-qwen35-9b-cr`.
- [ ] Điền số guard Qwen vào `report/tables/e2e-layers.tex`, không sửa câu văn; commit file run nhỏ (`run.json`, `reports/`).
