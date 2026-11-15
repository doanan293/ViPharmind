# Đánh giá: phần còn lại (guide theo golden v4, D2, `metrics select` cho biến thể, D5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Trạng thái (2026-11-15):** chưa bắt đầu. Viết lại từ phần chưa làm của
`2026-10-26-retrieval-ablation-runs.md` (D2, D5) và các việc nhỏ ghi ở bảng tiến độ spec paper v2.
Task 1–3 làm được ngay. Task 4–7 (D5) chỉ làm sau khi An duyệt mục 3.7 của spec.

**Goal:** Guide khớp golden v4; có số D2 sau rerank; `metrics select` so được report `--gold-only` và
các file evaluation chỉ khác nhau ở `query`; có bảng D5 trên 1.500 câu `conversational`.

**Architecture:** Không đổi kiến trúc. D5 sinh file evaluation biến thể (giữ `query_id` và gold, chỉ
thay `query`) rồi đi qua chuỗi có sẵn `evaluation judgments` → `embed queries` → `retrieve` →
`rerank` → `metrics`. Hai mảnh mã mới: bộ dựng biến thể và viết lại câu hỏi
(`pharma_lab/evaluation/query_variants.py`), bước hợp hai artifact candidates bằng RRF
(`pharma_lab/evaluation/candidate_fusion.py`).

**Tech Stack:** Python 3.13, typer, pydantic, numpy, pytest; `uv run lint-imports`, `pyrefly`, `ruff`.

**Spec:** `docs/superpowers/specs/2026-11-15-evaluation-design.md` (mục 3.2, 3.4, 3.5, 3.7).

## Global Constraints

- Quy tắc repo trong `AGENTS.md`: không `# noqa`, `# type: ignore`, `ignore_imports`; test trong
  `pharma-lab/tests/` theo cây gương của `src/pharma_lab/`; contract import-linter xanh.
- Benchmark `9c6e4de6…`, judgments `rules_version: 2`; cặp agent hybrid RRF k=2, prefetch 50, giữ 20,
  Qwen3-Embedding-4B, rerank Qwen3-Reranker-4B giữ 5.
- Thống kê: `pharma_lab.evaluation.statistics` (bootstrap 10.000 lần, sign-flip ghép cặp, Holm, seed 0).
- Mỗi collection Qdrant của stack `vipharmind-eval` chỉ chứa corpus `formulary`; biến thể corpus chạy
  trên stack tạm riêng.
- Mọi model tự host (embedding, reranker, Qwen3.5-9B) chạy trên Kaggle; OpenRouter chỉ dành cho Jev.
- LLM chỉ gọi trên golden, trừ ngoại lệ đã khai báo; D5 viết lại 1.500 câu conversational là ngoại lệ
  mới cần An xác nhận khi duyệt mục 3.7 (xem câu hỏi mở trong ghi chú).
- Commit kết thúc bằng dòng attribution mà phiên làm việc quy định.

## Review Focus

1. Hai file evaluation lệch nhau ở gold hay ở tập `query_id` (không chỉ ở `query`) thì `metrics select`
   phải từ chối. Test: `test_variants_with_different_gold_are_refused` (Task 3).
2. Trộn report `--gold-only` với report có judgments trong cùng một lần chọn phải bị từ chối. Test:
   `test_gold_only_and_judged_reports_do_not_mix` (Task 3).
3. Câu viết lại rỗng hoặc LLM lỗi không được lặng lẽ thay bằng câu gốc: dòng đó ghi `status=error`,
   file biến thể chưa được ghi cho tới khi mọi dòng thành công. Test:
   `test_failed_rewrite_blocks_the_variant_file` (Task 5).
4. Viết lại chạy lại sau khi đứt giữa chừng phải bỏ qua dòng đã có, không gọi LLM lần nữa. Test:
   `test_rewrites_resume_by_query_id` (Task 5).
5. Hợp RRF hai run có tập `query_id` khác nhau phải từ chối. Test:
   `test_fusion_refuses_runs_over_different_queries` (Task 6).

---

### Task 1: Guide khớp golden v4

**Files:**
- Modify: `pharma-lab/docs/guides/e2e-evaluation.md` (câu mở đầu "bộ golden 500 câu"; ví dụ tên run
  `e2e-v2-*` chuyển sang `e2e-v4-*`; đoạn "Cặp model được chọn từ bảng retrieval v2... không cố định
  trước" thay bằng cặp đã chốt)
- Modify: `pharma-lab/docs/guides/e2e-golden-authoring.md` (mục multi_hop còn tả 150 câu và loại
  `retrieval_miss`, `noisy_retry`; mục answerable còn 30 mỗi nhóm, colloquial 20, glossary 10; lát 60;
  multi-turn 50 với quota 7/7/6; đoạn "Golden chỉ dùng cho run e2e khi lệnh trả `complete`")

- [ ] **Step 1:** Sửa mọi con số theo `ANSWERABLE_GROUP_QUOTAS`, `SLICE_QUOTAS`, `MULTI_TURN_QUOTAS`,
  `MULTI_HOP_QUOTAS` trong `pharma_lab/e2e/golden.py` và mục 3.6 của spec. Đoạn dược sĩ: ghi rằng
  golden v4 dùng cho run e2e sau hai vòng duyệt bằng model, lệnh `pharmacist-*` dành cho vòng duyệt
  dược sĩ đầy đủ nếu có (sửa theo câu trả lời của An, xem ghi chú).
- [ ] **Step 2:** `grep -n "500 câu\|150 câu\|retrieval_miss\|noisy_retry\|pronoun 7" pharma-lab/docs/guides/*.md`
  Expected: không còn dòng nào tả golden hiện hành bằng số cũ (dòng lịch sử ghi rõ "golden v1" thì được giữ).
- [ ] **Step 3: Commit** `docs(pharma-lab): guides describe golden v4`

### Task 2: D2 sau rerank (chạy, không có mã mới)

**Files:**
- Data: `pharma-lab/data/evaluation/runs/hybrid-qwen4b-v3-plain-p50-k20-rrf2/{rerank,reports/rerank}/qwen3_reranker_4b_q8_0/`
- Modify: `docs/research/paper-v2/08-phase-d-results.md` (phần bảng tự động và dòng D2)

- [ ] **Step 1:** Kiểm trên máy xem rerank D2 (tmux `d2acc3`, log `pharma-lab/data/work/logs-d2-acc3.log`)
  đã xong chưa: `uv run pharma-lab rerank --run hybrid-qwen4b-v3-plain-p50-k20-rrf2 --model qwen3-reranker:4b-q8_0 --dry-run`
  Expected: `missing_pairs=0`. Nếu lớn hơn 0: chạy lại lệnh trong `pharma-lab/data/work/d2-continue-acc3.sh`
  (bỏ dòng chờ) trên stack tạm `vipharmind-d2` (Postgres 5436, Qdrant 6337).
- [ ] **Step 2:** `uv run pharma-lab metrics --run hybrid-qwen4b-v3-plain-p50-k20-rrf2 --model qwen3-reranker:4b-q8_0 --top-k 20`
  Expected: có `reports/rerank/qwen3_reranker_4b_q8_0/top20/report.md`.
- [ ] **Step 3:** Kiểm định họ D: `uv run pharma-lab metrics select --top-k 20 --metric hit@5 --secondary ndcg@5 --config plain=hybrid-qwen4b-v3-plain-p50-k20-rrf2@qwen3-reranker:4b-q8_0 --config chosen=hybrid-qwen4b-v3-p50-k20-rrf2@qwen3-reranker:4b-q8_0`
  rồi `uv run python ../docs/research/paper-v2/08-phase-d-tables.py` từ `pharma-lab/`. Expected: dòng
  "D2 không enrichment + rerank 4B" không còn "chưa có".
- [ ] **Step 4:** Xoá stack tạm `vipharmind-d2` và `vipharmind-d7` sau khi hỏi An.
- [ ] **Step 5: Commit** `chore(pharma-lab): D2 reranked with Qwen3-Reranker-4B; phase D table`

### Task 3: `metrics select` cho report `--gold-only` và file evaluation biến thể

**Files:**
- Modify: `pharma-lab/src/pharma_lab/evaluation/config_selection.py` (`ConfigReport`, `_check_reports`, `select_config`)
- Modify: `pharma-lab/src/pharma_lab/cli/commands/metrics.py` (`select`: `--gold-only`; nhận `RUN` của evaluation khác)
- Modify: `pharma-lab/docs/guides/evaluation.md` (mục D7: kiểm định bằng `metrics select --gold-only`)
- Test: `pharma-lab/tests/evaluation/test_config_selection.py`

**Interfaces:**
- Produces: `ConfigReport(label: str, run_root: Path, model: str | None, gold_only: bool = False)`;
  `same_gold(paths: Sequence[Path]) -> None` trong `config_selection.py`: raise `ArtifactContractError`
  khi các file không cùng tập `query_id` hoặc khác nhau ở bất kỳ trường nào ngoài `query` (so từng dòng
  theo `query_id`). `_check_reports` dùng `same_gold` khi `evaluation_sha256` khác nhau, thay vì từ
  chối ngay; với report `gold_only` thì bỏ kiểm `judgments_sha256`. Nhóm của câu đọc từ file
  evaluation của config đầu (gold giống nhau nên nhóm giống nhau).

- [ ] **Step 1: Viết test**
  - `test_variants_that_differ_only_in_query_are_compared`: hai file chỉ khác `query`, A hơn B mọi câu
    → `chosen == "A"`.
  - `test_variants_with_different_gold_are_refused`: khác `expected_section_ids` ở một dòng → lỗi nêu `query_id`.
  - `test_gold_only_reports_skip_the_judgments_check`.
  - `test_gold_only_and_judged_reports_do_not_mix`.
- [ ] **Step 2:** `uv run pytest tests/evaluation/test_config_selection.py -v` → FAIL
- [ ] **Step 3:** Cài đặt như mục Interfaces; CLI `--gold-only` áp cho mọi `--config` của lần gọi.
- [ ] **Step 4:** `uv run pytest tests/evaluation tests/cli -q && uv run lint-imports && uv run pyrefly check && uv run ruff check` → PASS
- [ ] **Step 5: Commit** `feat(pharma-lab): metrics select compares gold-only reports and query variants`

### Task 4: D5, file biến thể không gọi LLM (Q0, Q1, Q6)

Chỉ làm sau khi An duyệt mục 3.7 của spec.

**Files:**
- Create: `pharma-lab/src/pharma_lab/evaluation/query_variants.py`
- Modify: `pharma-lab/src/pharma_lab/cli/commands/evaluation.py` (lệnh `evaluation variant`)
- Test: `pharma-lab/tests/evaluation/test_query_variants.py`

**Interfaces:**

```python
class Strategy(StrEnum):
    Q0 = "q0"; Q1 = "q1"; Q2 = "q2"; Q3 = "q3"; Q6 = "q6"

def conversational_rows(benchmark: Sequence[Mapping[str, object]]) -> list[dict[str, object]]
    """Các dòng eval_group == "conversational", theo thứ tự file."""

def static_query(row: Mapping[str, object], strategy: Strategy,
                 parents: Mapping[str, Mapping[str, object]]) -> str
    """Q0: turns[-1].text; Q1: mọi lượt nối bằng "\n" theo dạng "Người dùng: …"/"Trợ lý: …";
    Q6: query của dòng parents[parent_query_id]. Strategy khác: ValueError."""

def write_variant(rows: Sequence[Mapping[str, object]], queries: Mapping[str, str],
                  out: Path, *, strategy: str) -> Path
    """Ghi file evaluation chỉ thay `query`; manifest cạnh file ghi strategy, sha benchmark nguồn,
    số dòng. Thiếu query cho một query_id thì lỗi."""
```

CLI: `uv run pharma-lab evaluation variant --strategy q0|q1|q6 --out data/evaluation/gold-d5/<strategy>.jsonl`
(mặc định đọc `GOLD_EVALUATION_PATH`).

- [ ] **Step 1: Viết test** `test_q0_is_the_last_turn`, `test_q1_joins_every_turn`,
  `test_q6_is_the_parent_question`, `test_variant_keeps_ids_and_gold`, `test_missing_query_is_an_error`
- [ ] **Step 2:** FAIL
- [ ] **Step 3:** Cài đặt
- [ ] **Step 4:** `uv run pytest tests/evaluation -q && uv run lint-imports && uv run pyrefly check` → PASS
- [ ] **Step 5: Commit** `feat(pharma-lab): conversational query variants for D5`

### Task 5: D5, viết lại bằng LLM (Q2, Q3)

**Files:**
- Modify: `pharma-lab/src/pharma_lab/evaluation/query_variants.py`
- Create: `pharma-lab/src/pharma_lab/evaluation/chiq_prompts.py` (prompt CHIQ tiếng Việt)
- Modify: `pharma-lab/src/pharma_lab/cli/commands/evaluation.py` (`evaluation rewrite`)
- Test: `pharma-lab/tests/evaluation/test_query_rewrites.py`

**Interfaces:**
- Consumes: `REPHRASE_SYSTEM`, `rephrase_messages(original_query, context)` của
  `pharma_agent.domain.agent.prompts`; `LlmPort` của backend dựng từ `--backend-env-file`.
- Produces:

```python
@dataclass(frozen=True)
class Rewrite:
    query_id: str; query: str; status: Literal["ok", "error"]; error: str | None
    llm_calls: int; input_tokens: int; output_tokens: int; seconds: float

async def rewrite_rows(rows: Sequence[Mapping[str, object]], strategy: Strategy, llm: LlmPort,
                       log: Path, *, concurrency: int = 4) -> list[Rewrite]
    """Q2: một lời gọi rephrase_messages với lịch sử là turns[:-1]; Q3: chuỗi CHIQ rồi viết lại.
    Ghi nối thêm vào `log` (jsonl, khoá query_id); dòng đã `ok` trong log thì bỏ qua."""
```

CLI: `uv run pharma-lab evaluation rewrite --strategy q2|q3 --model <tên> --out data/evaluation/gold-d5/<tên>.jsonl`;
log ở `<out>.rewrites.jsonl`; chỉ ghi file biến thể khi mọi dòng `ok`; in tổng lượt gọi, token, giây.

- [ ] **Step 1: Viết test** (LLM giả): `test_q2_uses_the_backend_rephrase_prompt`,
  `test_q3_makes_the_chiq_calls_then_rewrites`, `test_failed_rewrite_blocks_the_variant_file`,
  `test_rewrites_resume_by_query_id`, `test_usage_is_recorded_per_row`
- [ ] **Step 2:** FAIL
- [ ] **Step 3:** Cài đặt
- [ ] **Step 4:** `uv run pytest tests/evaluation -q && uv run lint-imports && uv run pyrefly check` → PASS
- [ ] **Step 5: Commit** `feat(pharma-lab): LLM query rewrites for D5 with usage records`

Q2-qwen cần Qwen3.5-9B trên Kaggle. Hiện kernel chỉ có stage `e2e-run`, không có stage viết lại; cách
chạy (stage mới hay dùng lại kernel e2e) thuộc spec `kaggle-runs` và cần An chốt trước khi thêm task.

### Task 6: D5, hợp ứng viên Q0 và Q2 bằng RRF (Q5)

**Files:**
- Create: `pharma-lab/src/pharma_lab/evaluation/candidate_fusion.py`
- Modify: `pharma-lab/src/pharma_lab/cli/commands/retrieve.py` (lệnh hoặc tuỳ chọn `retrieve fuse`)
- Test: `pharma-lab/tests/evaluation/test_candidate_fusion.py`

**Interfaces:**
- Consumes: `CandidateArtifactReader`, `build_candidate_artifact` (`retrieval_candidate_artifact.py`).
- Produces: `fuse_candidates(a: Path, b: Path, out_run: str, *, rrf_k: int = 2, candidate_k: int = 20) -> Path`:
  điểm RRF `1/(rrf_k + hạng)` cộng theo `chunk_id`, giữ `candidate_k` chunk; `run.json` ghi hai run nguồn
  và file evaluation của run `a`.

- [ ] **Step 1: Viết test** `test_rrf_orders_by_summed_reciprocal_rank`,
  `test_fusion_refuses_runs_over_different_queries`, `test_fused_run_records_its_sources`
- [ ] **Step 2:** FAIL
- [ ] **Step 3:** Cài đặt
- [ ] **Step 4:** `uv run pytest tests/evaluation tests/cli -q && uv run lint-imports && uv run pyrefly check` → PASS
- [ ] **Step 5: Commit** `feat(pharma-lab): fuse two candidate runs with RRF`

### Task 7: D5, chạy và bảng

- [ ] **Step 1:** Dựng file biến thể Q0, Q1, Q6 (Task 4), Q2-gemini, Q3-gemini (Task 5); với mỗi file:
  `uv run pharma-lab evaluation judgments --evaluation <file>`.
- [ ] **Step 2:** `embed queries --evaluation <file> --model qwen3-embedding:4b-q8_0` (Kaggle); `retrieve
  --evaluation <file> --run hybrid-qwen4b-v3-d5-<mã>-p50-k20-rrf2 --retriever hybrid --prefetch-k 50
  --candidate-k 20 --rrf-k 2` trên stack `vipharmind-eval`; Q5 bằng Task 6 từ run Q0 và Q2-gemini.
- [ ] **Step 3:** `rerank --backend kaggle --model qwen3-reranker:4b-q8_0` cho mọi run; `metrics --top-k 20`.
- [ ] **Step 4:** Hai họ so sánh: mọi Qi so với Q0, và mọi Qi so với Q2-gemini (`metrics select` với
  Task 3, hoặc `paired_test` + `holm` trong script bảng); Hit@5, nDCG@5, KTC, p Holm, lượt gọi, token,
  giây; bảng phụ theo `query_form`. Ghi vào `docs/research/paper-v2/08-phase-d-results.md`.
- [ ] **Step 5: Commit** `chore(pharma-lab): D5 query strategies on the conversational group`
