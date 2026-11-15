# Rerank CPU Defaults Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline, with checkpoints). Task 1 is a long CPU measurement on the owner's machine and must not run in a subagent. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đo lại reranker CPU ở `-ub 4096` với file `qwen3-reranker-4b-q8_0-vimed.gguf`, ghi mặc định mới vào `compose.local-models.yaml`, và sửa một dòng lỗi thời trong `pharma-lab/README.md`.

**Architecture:** Không đổi mã. Dùng lệnh benchmark local sẵn có (`pharma-lab rerank --backend local --benchmark`), mức duy nhất của catalog là `(-np 4, -ub 4096, 1 request)` với 15 tài liệu mỗi request. Kết quả vào chú thích và giá trị mặc định của service `llama-reranker` và biến `RERANK_TIMEOUT_SECONDS` của backend trong compose.

**Tech Stack:** Docker Compose, llama.cpp `server-b10920`, pharma-lab CLI, tmux.

**Spec:** `docs/superpowers/specs/2026-11-15-corpus-data-pipeline-design.md` (mục 4.5 và 6).

## Global Constraints

- Mọi server reranker chạy `--reranking --kv-unified -np <slots> -c <ub × (slots + 1)> -b <ub> -ub <ub>`, `-ub` tối thiểu 4096 (spec 4.5).
- Backend local: `PHARMA_RETRIEVAL__RERANK__MAX_CONCURRENT = 1`, `MAX_CANDIDATES = 15`, timeout ít nhất 2 lần p95 CPU đo được (spec 3.7).
- Chú thích trong compose ghi rõ máy đo (Intel i5-13420H, 12 luồng), image llama.cpp và lệnh đo.
- Lệnh chạy lâu chạy trong tmux; log rerank ở `pharma-lab/data/work/logs/rerank/<model>.log`.
- Trước commit: `pre-commit run --all-files` từ gốc repo sạch; commit không có trailer Co-Authored-By.

## Review Focus

1. Mức `-ub 4096` không được báo `input is too large` cho chunk dài nhất của corpus hiện tại (khoảng 3.100 token): benchmark phải ghi trạng thái `ok`, không `invalid`.
2. Timeout mới phải lớn hơn hoặc bằng 2 lần `latency_p95_seconds` của profile local, làm tròn lên.
3. Máy khác vẫn ghi đè được mọi giá trị bằng biến shell như trước; tên biến không đổi.

---

### Task 1: Đo lại reranker CPU ở `-ub 4096` (hỏi chủ dự án trước)

**Files:**
- Tạo (không commit, Git bỏ qua): `pharma-lab/data/cache/local_profiles/rerank/qwen3_reranker_4b_q8_0.json`

- [ ] **Step 1: Hỏi An có muốn chạy không.** Phép đo trước mất nhiều giờ (p95 448,7 giây mỗi request); máy phải rảnh. Production dùng OpenRouter nên đây chỉ là cấu hình cho dev chạy model trên CPU. Không chạy khi chưa được đồng ý.
- [ ] **Step 2: Kiểm điều kiện.** Có `ai-models/gguf/qwen3-reranker-4b-q8_0-vimed.gguf` (sha256 khớp catalog `424c3a97…`); `pharma-lab data pull` đã khôi phục `data/evaluation/runs/hybrid-qwen4b-v3-p50-k20-rrf2/candidates/candidates.jsonl`.
- [ ] **Step 3: Chạy benchmark trong tmux.**

Run (từ `pharma-lab/`): `uv run pharma-lab rerank --backend local --benchmark --model qwen3-reranker:4b-q8_0 --run hybrid-qwen4b-v3-p50-k20-rrf2`
Expected: mức `(4, 4096, 1)` trạng thái `ok`; lệnh in cấu hình được chọn và ghi profile local.

- [ ] **Step 4: Chép số đo** (cặp/giây, p50, p95, số luồng) từ profile vào ghi chú cho Task 2. Nếu mức lỗi vì hết RAM, dừng và báo An kèm đuôi log server.

### Task 2: Ghi mặc định mới vào compose và sửa README

**Files:**
- Modify: `compose.local-models.yaml` (khối `llama-reranker` và biến `RERANK_TIMEOUT_SECONDS` của `backend`)
- Modify: `pharma-lab/README.md` (dòng `pharma-lab bundle embed` trong mục "Luồng dữ liệu")

- [ ] **Step 1: Sửa chú thích đo** trong `llama-reranker`: thay câu "That run used -ub 2048 … rerun the benchmark to measure it" bằng số đo mới ở `-ub 4096` (p95, cặp/giây, máy, image, lệnh). Giữ `LLAMA_ARG_N_PARALLEL`, `CTX_SIZE`, `BATCH`, `UBATCH`, `THREADS` nếu profile chọn đúng các giá trị đó; khác thì đặt theo profile.
- [ ] **Step 2: Đặt `RERANK_TIMEOUT_SECONDS` mặc định** bằng `ceil(2 × latency_p95_seconds)`.
- [ ] **Step 3: Sửa README pharma-lab:** `chunk_section của backend` thành `chunk_document của backend`.
- [ ] **Step 4: Kiểm.**

Run: `docker compose -f compose.yaml -f compose.local-models.yaml config --quiet && pre-commit run --all-files`
Expected: không lỗi.

- [ ] **Step 5: Commit**

```bash
git add compose.local-models.yaml pharma-lab/README.md
git commit -m "perf(compose): CPU reranker defaults measured at -ub 4096"
```
