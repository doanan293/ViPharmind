# Camera-ready SoICT 2026 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bản camera-ready của paper 1360 trả lời bốn review bằng ba thí nghiệm (E1 baseline hội thoại, E2 dev/test, E3 citation recall) và các chỉnh sửa câu chữ, trên đúng code, data và model F16 của `v1.0.0`.

**Architecture:** Khôi phục trạng thái chạy của v1 (data từ archive Kaggle, Postgres/Qdrant riêng, model F16 dựng lại) mà không đụng data v2. Thêm một cờ pipeline ở backend và một config e2e, hai module phân tích chạy trên artifact v1 có sẵn. Bài sửa trong `report/` và build bằng `latexmk`.

**Tech Stack:** backend `pharma_agent` (LangGraph), pharma-lab (typer, pydantic), llama.cpp, Kaggle T4, LaTeX LNCS.

**Spec:** `docs/superpowers/specs/2026-10-19-camera-ready-design.md`

## Global Constraints

- Branch `camera-ready` (base `v1.0.0`, `ef81c47`); merge về `dev` rồi `main` khi xong.
- Hạn 30/10/2026; xong thí nghiệm trước 25/10.
- 12 đến 15 trang LNCS tính cả references.
- Model F16 đúng như v1; không thay bằng Q8 khi chưa được tác giả đồng ý.
- Run v1 không được chạy lại hay sửa; identity trong `run.json` của run v1 không đổi.
- `AGENTS.md`: test trong `tests/` theo cây gương; không `# noqa`, `# type: ignore`, `ignore_imports`; ruff, pyrefly, `uv run lint-imports`, pytest pass trong project bị sửa.
- Data v2 nằm ở `pharma-lab/data.v2` suốt quá trình và được đổi tên lại ở Task 12.
- Commit theo từng task, message kết thúc bằng dòng `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- Câu multi-turn có lịch sử chứa lượt bị chặn: harness luôn đưa `status="completed"` nên `query_with_history` nối mọi lượt; test ở Task 4 dùng đúng `conversation_for` của harness.
- Lần search thứ hai (refine) khi `history_query` bật cùng `judge_refine`: chỉ query đầu được nối; test ở Task 4.
- Resume một run v1 sau khi thêm field vào `PipelineOptions`: identity phải giống từng byte; test ở Task 5 so với `run.json` của `e2e-gemini/full` trong git.
- Nhóm benchmark có số câu lẻ hoặc chỉ một câu: chia dev/test vẫn tất định và mỗi câu thuộc đúng một nửa; test ở Task 6.
- Câu trả lời có trích dẫn tới số đoạn không có trong context: tính là trích dẫn hỏng, không phải "có trích dẫn"; test ở Task 7.

---

### Task 1: `--dataset` cho `data pull` và `data push`

**Files:**
- Modify: `pharma-lab/src/pharma_lab/data_archive/service.py` (`push_data`, `pull_data`)
- Modify: `pharma-lab/src/pharma_lab/cli/commands/data.py`
- Modify: `pharma-lab/docs/guides/cli-reference.md`
- Test: `pharma-lab/tests/data_archive/test_service.py`

**Interfaces:**
- Produces: `pull_data(*, project_root, dataset, force, slug: str = DATASET_SLUG)`, `push_data(..., slug: str = DATASET_SLUG)`; CLI `--dataset SLUG` trên cả hai lệnh, mặc định `seed-pipeline-data`.

- [ ] **Step 1: Test** `test_pull_reads_the_named_dataset` và `test_push_writes_the_named_dataset`: với fake `DatasetService` sẵn có trong file test, `slug="vipharmind-data"` làm mọi lời gọi tới `owner/vipharmind-data`; không truyền `slug` thì vẫn là `owner/seed-pipeline-data`.
- [ ] **Step 2:** `cd pharma-lab && uv run pytest tests/data_archive/test_service.py -q` → FAIL (unexpected keyword `slug`).
- [ ] **Step 3:** Thêm tham số `slug` như Interfaces; CLI truyền `--dataset`.
- [ ] **Step 4:** Chạy lại test → PASS; `uv run ruff check . && uv run pyrefly check --min-severity warn && uv run lint-imports`.
- [ ] **Step 5:** Commit `feat(pharma-lab): data pull and push take the dataset slug`.

### Task 2: Khôi phục data v1 và kiểm archive

**Files:** không sửa code. Thao tác trong `pharma-lab/`.

- [ ] **Step 1:** `mv data data.v2 && git checkout -- data`. Kiểm: `git status --short data` rỗng, `du -sh data.v2` khoảng 37G.
- [ ] **Step 2:** `uv run pharma-lab data pull --dataset vipharmind-data --kaggle-account acc1`. Kiểm `sha256sum data/corpus/rag-final/sections.jsonl` bằng `files."sections.jsonl".sha256` trong `data/corpus/rag-final/manifest.json`, và `sha256sum data/evaluation/e2e/golden_e2e.jsonl` bằng `sha256` trong `golden_e2e.manifest.json` (`8bdf0bee…`).
- [ ] **Step 3:** `uv run pharma-lab e2e report --run e2e-gemini && uv run pharma-lab e2e report --run e2e-qwen35-9b`, rồi `git diff --stat -- data/evaluation/e2e/runs/`. Pass khi không có dòng nào đổi trong `main.csv`, `ablation.csv`, `calibration.csv`. Có lệch thì dừng và báo tác giả (spec §6).
- [ ] **Step 4:** `uv run pharma-lab metrics compare --run hybrid-qwen4b-p50-k30-rrf2-sample1000 --baseline qwen3-reranker:0.6b-fp16 --candidate qwen3-reranker:0.6b-fp16-vimed --metric mrr --top-k 30 --resamples 10000 --seed 0` cho mean difference 0,045 như bài (kiểm metrics report retrieval có trong archive). Nếu lệnh từ chối model `0.6b-fp16-vimed` vì đã bỏ khỏi catalog, so trực tiếp hai file `metrics.jsonl` trong `reports/rerank/*/top30-window3/` theo cột `mrr`.
- [ ] **Step 5:** Không commit (data gitignored). Ghi kết quả kiểm vào mô tả task.

### Task 3: Dựng lại model F16 (chạy nền)

**Files:** không sửa code. Thao tác ở gốc repo, file vào `ai-models/`.

- [ ] **Step 1:** Qwen3.5-9B: làm đúng khối lệnh "Chuẩn bị file GGUF F16" trong `pharma-lab/docs/guides/e2e-evaluation.md`. Pass: `sha256sum -c` của `qwen3.5-9b-f16.gguf` OK (`863a67e2…`).
- [ ] **Step 2:** Qwen3-Reranker-4B `-vimed`: tải `qwen3-reranker-4b-f16.gguf` từ `Voodisss/Qwen3-Reranker-4B-GGUF-llama_cpp`, kiểm `c4de2e3e…`, rồi làm khối lệnh gắn chat template trong `pharma-lab/docs/guides/evaluation.md` (dòng 111–146) với `SIZE=4b`. Pass: `4b428e98…`.
- [ ] **Step 3:** Qwen3-Embedding-4B F16 (`qwen3-embedding-4b-fp16.gguf`, `e8b4e85c…`, 8.049.889.824 byte theo `runtime/catalog.py`). Nguồn Hugging Face chưa ghi trong guide: tìm repo GGUF F16 chính thức của Qwen cho model này, tải, kiểm sha256. Không khớp thì dừng và báo; không dùng file khác.
- [ ] **Step 4:** Đặt file theo `canonical_filename` của catalog trong `ai-models/gguf/`; `uv run pharma-lab doctor --backend local` không báo thiếu model.
- [ ] **Step 5:** Bổ sung nguồn của embedding 4B vào `pharma-lab/docs/guides/evaluation.md` cạnh bảng nguồn reranker. Commit `docs(pharma-lab): source of the Qwen3-Embedding-4B F16 file`.

### Task 4: Cờ `history_query` ở backend

**Files:**
- Modify: `backend/src/pharma_agent/domain/conversation/context.py`
- Modify: `backend/src/pharma_agent/application/chat/context.py`
- Modify: `backend/src/pharma_agent/application/chat/nodes.py` (`search_node`)
- Modify: `backend/tests/fakes.py` (`FakeReranker.queries: list[str]`)
- Test: `backend/tests/domain/test_conversation_context.py`, `backend/tests/application/test_chat_graph.py`

Bản nháp nằm ở `stash@{0}` ("camera-ready WIP 2026-10-19"); được phép `git stash apply stash@{0}` rồi kiểm lại theo các step dưới.

**Interfaces:**
- Produces: `query_with_history(question: str, context: ConversationContext) -> str` (user text đã strip của mọi lượt, rồi câu hiện tại, nối bằng một dấu cách); `PipelineOptions.history_query: bool = False`.

- [ ] **Step 1: Test**
  - `test_query_with_history_puts_earlier_questions_before_the_turn`: hai lượt `" Panadol là thuốc gì? "`, `"Có dùng cho trẻ em không?"`, câu `"Liều bao nhiêu? "` → `"Panadol là thuốc gì? Có dùng cho trẻ em không? Liều bao nhiêu?"`; context rỗng → câu đã strip.
  - `test_history_query_searches_earlier_questions_with_the_turn`: `PipelineOptions(rephrase=False, judge_refine=False, history_query=True)`, một lượt `"Panadol là thuốc gì?"` → `retriever.calls[0][0].text == reranker.queries[0] == f"Panadol là thuốc gì? {QUESTION}"`, `outcome.run.standalone_query == QUESTION`, không gọi `LlmRole.REPHRASE`.
  - `test_history_query_leaves_refine_queries_unchanged`: `PipelineOptions(rephrase=False, history_query=True)`, judge trả `search_more`, refine trả `["liều paracetamol trẻ em"]` → `retriever.calls[1][0].text == "liều paracetamol trẻ em"`.
  - `run_turn` nhận thêm `conversation: ConversationContext | None = None` và truyền vào `runner.start`.
- [ ] **Step 2:** `cd backend && uv run pytest tests/domain/test_conversation_context.py tests/application/test_chat_graph.py -q` → FAIL (ImportError `query_with_history`).
- [ ] **Step 3:** Cài đặt. `search_node` tính `search_query` một lần: `query_with_history(run.original_query, runtime.context.conversation)` khi cờ bật, ngược lại `run.standalone_query`; dùng cho query `INITIAL` và cho `rerank_query`.
- [ ] **Step 4:** Toàn bộ test backend, ruff, pyrefly, lint-imports → PASS.
- [ ] **Step 5:** Commit `feat(backend): a pipeline flag that searches the earlier questions with the turn`.

### Task 5: Config `one-step-history` và `--category`

**Files:**
- Modify: `pharma-lab/src/pharma_lab/e2e/configs.py`, `report.py` (`CONFIG_LABELS`), `harness.py`, `sampling.py`
- Modify: `pharma-lab/src/pharma_lab/cli/commands/e2e.py` (`run`)
- Modify: `pharma-lab/docs/guides/e2e-evaluation.md` (bảng `--config`, mô tả `--category`)
- Test: `pharma-lab/tests/e2e/test_run_setup.py`, `test_report.py`, `test_sampling.py` (tạo nếu chưa có)

**Interfaces:**
- Consumes: `PipelineOptions.history_query` (Task 4).
- Produces: `E2EConfig.ONE_STEP_HISTORY = "one-step-history"` với `PipelineOptions(rephrase=False, judge_refine=False, history_query=True)`; `pipeline_record(options: PipelineOptions) -> dict[str, bool]` trong `configs.py` (là `asdict` bỏ `history_query` khi `False`); `E2ERunRequest.category: Category | None = None`; `select_items(golden, *, limit, category) -> list[GoldenItem]` trong `sampling.py` (lọc theo category trước rồi `spread`); nhãn `"One-step + history"`.

- [ ] **Step 1: Test**
  - `pipeline_for(E2EConfig.ONE_STEP_HISTORY) == PipelineOptions(rephrase=False, judge_refine=False, history_query=True)`.
  - `pipeline_record(pipeline_for(E2EConfig.FULL)) == {"rephrase": True, "judge_refine": True}` và bằng `["identity"]["pipeline"]` của `PROJECT_ROOT / "data/evaluation/e2e/runs/e2e-gemini/full/run.json"` (file run v1 đang được track; đọc file, không gọi git).
  - `pipeline_record(pipeline_for(E2EConfig.ONE_STEP_HISTORY))["history_query"] is True`.
  - `select_items` với golden fixture có 3 `multi_turn` và 2 `answerable`, `category=MULTI_TURN, limit=None` → đúng 3 id multi_turn theo thứ tự golden; `limit=2` → 2 item, đều multi_turn.
  - Test nhãn sẵn có (`{c.value for c in E2EConfig} == set(CONFIG_LABELS)`) phải pass sau khi thêm nhãn.
- [ ] **Step 2:** `uv run pytest tests/e2e -q` → FAIL.
- [ ] **Step 3:** Cài đặt; `harness.run_e2e` dùng `select_items` và `pipeline_record`; CLI `--category` kiểu `Category | None`.
- [ ] **Step 4:** `uv run pytest -q`, ruff, pyrefly, lint-imports, `tests/test_docs.py` → PASS.
- [ ] **Step 5:** Commit `feat(pharma-lab): one-step-history configuration and a category filter for e2e run`.

### Task 6: E2, chọn trên dev, báo trên test

**Files:**
- Create: `pharma-lab/src/pharma_lab/evaluation/dev_test_split.py`
- Modify: `pharma-lab/src/pharma_lab/cli/commands/evaluation.py` (lệnh `dev-test`)
- Modify: `pharma-lab/docs/guides/evaluation.md` (mục ngắn về lệnh)
- Test: `pharma-lab/tests/evaluation/test_dev_test_split.py`

**Interfaces:**
- Consumes: `load_query_metric(report: Path, metric: str)` (`metric_comparison.py`), `report_dir(run_root, *, top_k, window_size, model)` (`metrics_artifacts.py`); trường nhóm của row là `eval_group`.
- Produces:
  - `split_queries(groups: Mapping[str, str], *, seed: int) -> dict[str, Literal["dev", "test"]]`: trong mỗi nhóm, id sắp xếp rồi trộn bằng `random.Random(f"{seed}:{group}")`; nửa đầu (làm tròn xuống) là dev.
  - `choose(options: Mapping[str, Mapping[str, float]], ids: Collection[str]) -> str`: option có trung bình cao nhất trên `ids`; bằng nhau thì lấy option đứng trước.
  - CLI `pharma-lab evaluation dev-test --seed 0` ghi `data/evaluation/dev-test/report.json` và `report.md`.

Đầu vào cố định của lệnh:

| Quyết định | Option | Report | Metric chọn |
| --- | --- | --- | --- |
| k | `rrf2`, `rrf60` | baseline top30-window3 của `hybrid-qwen4b-p50-k30-rrf2` và `-rrf60` | `hit@10` trên dev |
| instruction | không, có | rerank `qwen3_reranker_0_6b_fp16` và `_vimed` của `hybrid-qwen4b-p50-k30-rrf2-sample1000` | `mrr` trên pilot ∩ dev |

Trên test, report ghi cho cả hai option của từng quyết định: `hit@10`, `mrr@10`, `ndcg@10`, số câu; với k thêm dòng sau rerank Qwen3-Reranker-4B của run `rrf2`. `report.json` ghi seed, số câu dev/test theo nhóm, option được chọn và option của v1.

- [ ] **Step 1: Test**
  - `test_split_is_stratified_and_deterministic`: nhóm a có 5 id, b có 1 id → a: 2 dev 3 test, b: 0 dev 1 test; gọi lại cùng seed cho kết quả bằng nhau; seed khác đổi ít nhất một id của nhóm a.
  - `test_every_query_is_in_one_half`: key của kết quả bằng key đầu vào.
  - `test_choose_takes_the_highest_mean_on_the_given_ids_and_the_first_on_ties`.
- [ ] **Step 2:** `uv run pytest tests/evaluation/test_dev_test_split.py -q` → FAIL.
- [ ] **Step 3:** Cài đặt module và lệnh.
- [ ] **Step 4:** Test, ruff, pyrefly, lint-imports → PASS; chạy `uv run pharma-lab evaluation dev-test --seed 0` trên data v1, kiểm `report.md` có dev chọn `rrf2` và có instruction (nếu khác, ghi nhận để Task 10 sửa bài theo đúng kết quả).
- [ ] **Step 5:** Commit code cùng `data/evaluation/dev-test/report.{json,md}` (gỡ ignore nếu cần theo `tests/test_repository_data_policy.py`). Message `feat(pharma-lab): dev/test check of the fusion constant and the rerank instruction`.

### Task 7: E3, phân tích citation recall

**Files:**
- Create: `pharma-lab/src/pharma_lab/e2e/citation_analysis.py`
- Modify: `pharma-lab/src/pharma_lab/cli/commands/e2e.py` (lệnh `citations` và `citations-summary`)
- Modify: `pharma-lab/docs/guides/e2e-evaluation.md`
- Modify: `docs/superpowers/specs/2026-10-19-camera-ready-design.md` §2 E3 (xem Step 3)
- Test: `pharma-lab/tests/e2e/test_citation_analysis.py`

**Interfaces:**
- Consumes: `content_sentences`, `cited_sentences`, `context_blocks`, `alce_citation_recall` (`e2e/judging/code_metrics.py`); `AnswerRecord`, `Judgement` (`records.py`).
- Produces:
  - `CitationBreakdown(total: int, uncited: int, dangling: int, unsupported: int, supported: int)` (frozen dataclass), `breakdown(answer_text, context_text, supported_share: float | None) -> CitationBreakdown | None` (`None` khi không có câu nội dung). `dangling` là câu có số trích dẫn nhưng không số nào có trong context. `supported` được tính đúng như `alce_citation_recall`.
  - `LABELS = ("connective", "missing_citation", "wrong_passage", "unsupported_content", "judge_error")`: câu dẫn dắt hoặc tổng hợp không cần trích; nội dung có trong evidence nhưng không trích; nội dung có trong evidence nhưng trích sai đoạn; nội dung không có trong evidence; judge sai (thực ra được hỗ trợ).
  - `sample_sentences(answers, judgments, *, size: int, seed: int) -> list[dict]`: từ item có `citation_recall < 1`, rút câu không trích dẫn hoặc câu có trích dẫn trong item có `citation_support < 1`; mỗi dòng có `item_id`, `sentence`, `citations`, `passages` (text các đoạn được trích), `evidence` (`context_text`), `label: ""`.
  - `summarise_labels(path: Path) -> dict[str, int]`: lỗi nếu có nhãn rỗng hoặc ngoài `LABELS`.
  - CLI `pharma-lab e2e citations --run R --config full --sample 20 --seed 0` ghi `runs/R/reports/citations.json` (tổng câu và tỉ lệ từng loại, cộng trung bình theo item của `supported/total`) và `runs/R/reports/citation-sample.jsonl` (không ghi đè nếu file đã có); `pharma-lab e2e citations-summary --run R` ghi `citation-labels.json`.

- [ ] **Step 1: Test**
  - `test_breakdown_matches_alce_recall`: câu trả lời 4 câu nội dung, 2 câu trích `[1]`, 1 câu trích `[9]` không có trong context, 1 câu không trích, `supported_share=0.5` → `CitationBreakdown(total=4, uncited=1, dangling=1, unsupported=1, supported=1)` và `supported / total == alce_citation_recall(...)`.
  - `test_breakdown_is_none_without_content_sentences`.
  - `test_sample_is_seeded_and_skips_fully_supported_items`.
  - `test_summary_rejects_empty_and_unknown_labels`.
- [ ] **Step 2:** `uv run pytest tests/e2e/test_citation_analysis.py -q` → FAIL.
- [ ] **Step 3:** Cài đặt. Sửa spec E3: judge v1 chỉ lưu tỉ lệ hỗ trợ của từng item, không lưu nhãn từng câu, nên phần tách tự động là bốn loại trên, còn câu nào trong số câu có trích dẫn là không được hỗ trợ được xác định ở mẫu tay; phân biệt "trích sai đoạn" và "ngoài evidence" chuyển vào bảng nhãn.
- [ ] **Step 4:** Test, ruff, pyrefly, lint-imports → PASS; chạy `e2e citations` cho `e2e-gemini` và `e2e-qwen35-9b` (`--sample 20` mỗi run, tổng 40). Kiểm trung bình `supported/total` theo item bằng citation recall trong `main.csv` (0,724 và 0,695) trong sai số làm tròn.
- [ ] **Step 5:** Commit code, spec, `citations.json` và hai file mẫu. Message `feat(pharma-lab): where citation recall is lost, with a sample for hand labels`. Báo tác giả gán nhãn hai file mẫu; Task 10 chạy `citations-summary` sau khi có nhãn.

### Task 8: Stack Postgres/Qdrant cho v1

**Files:** không sửa code.

- [ ] **Step 1:** `docker stop vipharmind-eval-postgres-1 vipharmind-eval-qdrant-1` (không `rm`, không xoá volume).
- [ ] **Step 2:** Ở gốc repo: `docker compose -p vipharmind-v1 up -d postgres qdrant` với port đặt theo `backend/.env` (`POSTGRES_PORT`, `QDRANT_HTTP_PORT`). Kiểm hai container `healthy`.
- [ ] **Step 3:** `cd backend && uv run pharma-agent migrate && uv run pharma-agent corpus import ../pharma-lab/data/corpus/formulary --collection formulary --publish`. Kiểm alias `chunks_current` trỏ vào collection của `qwen3-embedding:4b-fp16` (`curl localhost:$QDRANT_HTTP_PORT/aliases`).
- [ ] **Step 4:** Embedding local: `docker compose -f compose.yaml -f compose.local-models.yaml -p vipharmind-v1 up -d` cho service embedding 4B F16; `uv run pharma-lab doctor --backend local` pass.
- [ ] **Step 5:** Smoke: `uv run pharma-lab e2e run --run e2e-smoke-v1 --config one-step --limit 5` chạy hết không lỗi; xoá `data/evaluation/e2e/runs/e2e-smoke-v1` sau khi kiểm.

### Task 9: Chạy E1

**Files:** kết quả trong `pharma-lab/data/evaluation/e2e/runs/{e2e-gemini,e2e-qwen35-9b}/one-step-history/`.

- [ ] **Step 1:** Reranker: `uv run pharma-lab e2e rerank-server --model qwen3-reranker:4b-fp16 --hours 8 --kaggle-account auto`; nạp env vào tmux session của run.
- [ ] **Step 2:** Gemini: `e2e run --run e2e-gemini --config one-step-history --category multi_turn`; lỗi thì chạy lại với `--retry-errors`. Kiểm `run.json` có model theo role, retrieval và budget bằng `e2e-gemini/one-step/run.json` (chỉ khác `config` và `pipeline`).
- [ ] **Step 3:** Judge với model trong `e2e-gemini/full/judge.json`: `e2e judge --run e2e-gemini --config one-step-history --judge-model <model đó>`.
- [ ] **Step 4:** Qwen: `e2e llm-server --model qwen3.5:9b-f16 --hours 10 --kaggle-account auto`; chạy Step 2–3 với `--run e2e-qwen35-9b`, judge model lấy từ `e2e-qwen35-9b/full/judge.json`.
- [ ] **Step 5:** `e2e report` cho hai run. Từ `by_group.csv` và các file report, lấy cho nhóm `multi_turn`: truthfulness, response rate, nugget recall, hallucination, lời gọi và token mỗi lượt của `full`, `one-step`, `one-step-history`, kèm paired test so với `full`. Nếu report chưa xuất paired test theo nhóm, thêm một hàm vào `report.py` với test trong `tests/e2e/test_report.py` (theo mẫu `paired_delta`, Holm trên hai so sánh) thay vì tính tay.
- [ ] **Step 6:** Commit các file nhỏ của run (`run.json`, `judge.json`, `reports/`) như run v1. Message `chore(pharma-lab): one-step-history runs on the multi-turn items`.

### Task 10: Sửa bài, phần kết quả

**Files:** `report/sections/{methodology,results}.tex`, `report/tables/e2e-multiturn.tex` (mới), `report/SoICT2026_…tex` (nếu cần `\input`).

- [ ] **Step 1:** Methodology: một câu mô tả `one-step-history` cạnh mô tả one-step; câu về pilot nói rõ pilot lấy từ benchmark và được kiểm lại bằng chia dev/test.
- [ ] **Step 2:** Bảng `tab:e2e-multiturn`: hàng `Full agent`, `One-step RAG`, `One-step + history`; cột truthfulness, response rate, LLM calls cho Gemini và Qwen3.5-9B; dấu * khi p Holm < 0,05 so với full. Số lấy từ Task 9 Step 5.
- [ ] **Step 3:** Results/retrieval: kết quả E2 trong một đến hai câu từ `dev-test/report.md`.
- [ ] **Step 4:** Results/e2e: đoạn E3 từ `citations.json` và `citation-labels.json`; câu safety viết lại thành số x/10 kèm Wilson CI [0,722; 1,000], bỏ "resist all".
- [ ] **Step 5:** `cd report && latexmk` không warning. Commit `docs(report): conversational baseline, dev/test check and citation analysis`.

### Task 11: Sửa bài, định vị và giới hạn

**Files:** `report/sections/{abstract,introduction,results,conclusion}.tex`

- [ ] **Step 1:** Abstract và cuối Introduction: đóng góp là corpus và benchmark, thiết kế tái lập được cho LLM rẻ, đánh giá đầy đủ; một câu nói rõ các thành phần là kỹ thuật đã có. Bỏ câu hàm ý kiến trúc mới.
- [ ] **Step 2:** Discussion: rephrase đóng góp phần lớn khoảng cách với one-step trên câu follow-up; `one-step-history` lấy lại được bao nhiêu và tốn bao nhiêu (Task 9); judge–refine lợi ít so với tăng token và lời gọi (số từ `main.csv`, `ablation.csv`), refine có điều kiện là lựa chọn triển khai; bỏ reranker không đổi metric e2e dù tăng retrieval.
- [ ] **Step 3:** Limitations (đoạn riêng): câu hỏi benchmark và 420 câu golden single-turn sinh từ template trên cùng corpus đã enrich bằng cùng mapping nên Hit@30 99,2% có thể cao hơn câu hỏi thật; golden do tác giả đầu cùng một dược sĩ soạn, chấm mù chỉ một dược sĩ; safety 10 câu mỗi loại chỉ là kiểm tra tối thiểu. Xoá câu "remains untested" về nối lịch sử.
- [ ] **Step 4:** Kiểm: `grep -n "resist all\|remains untested" report/sections/*.tex` rỗng; mọi số mới trong bài có trong file report tương ứng.
- [ ] **Step 5:** `latexmk` sạch. Commit `docs(report): contribution framed as resource and evaluation, limitations stated`.

### Task 12: Ngân sách trang, hồ sơ nộp, trả data

**Files:** `report/` (các section), `report/REVISION-NOTES.md` (mới), `report/README.md`.

- [ ] **Step 1:** Cắt theo thứ tự spec §4 (Methodology, Related Work, bảng corpus, Discussion) tới khi `pdfinfo report/SoICT2026_…pdf | grep Pages` ≤ 15; không bỏ trích dẫn, không cắt bảng retrieval.
- [ ] **Step 2:** Corresponding author có ký hiệu phong bì; kiểm hướng dẫn CCIS về permission statement và thêm nếu yêu cầu. Cập nhật câu "tối đa 12 trang không tính references" trong `report/README.md` thành giới hạn camera-ready.
- [ ] **Step 3:** `REVISION-NOTES.md`: bảng điểm review → chỗ sửa (section, bảng, câu).
- [ ] **Step 4:** Tạo ZIP `Source` theo lệnh trong `report/README.md` mục Overleaf, cộng file text corresponding author; form copyright do tác giả ký tay và thêm vào.
- [ ] **Step 5:** Lưu data của run mới: `uv run pharma-lab data push --dataset vipharmind-camera-ready-data --message "camera-ready runs"` (dataset riêng tư mới, không thêm version vào `vipharmind-data`).
- [ ] **Step 6:** Trả môi trường: `docker compose -p vipharmind-v1 stop`; `mv pharma-lab/data pharma-lab/data.v1 && mv pharma-lab/data.v2 pharma-lab/data` chỉ khi tác giả chuyển lại sang `v2.0.0`; `docker start vipharmind-eval-postgres-1 vipharmind-eval-qdrant-1` cùng lúc.
- [ ] **Step 7:** Commit, merge `camera-ready` vào `dev` rồi `main` sau khi tác giả duyệt PDF.
