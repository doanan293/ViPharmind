# Paper v2: thí nghiệm e2e và viết bài Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Có đủ số của ma trận e2e paper v2 (H, A1–A4, B, C, D6, E1–E5) trên golden v4 với ba trục chất lượng, giây và USD, rồi viết bản thảo paper v2 từ các file báo cáo.

**Architecture:** Phần mã của pha 0–2 đã có trên `v2.0.0` (decision model Jev, refine template, `refine_threshold`, ReAct, `e2e compare`, `--latency`, `e2e decision-probe`, `e2e decision-set`). Plan này thêm ba mảnh mã còn thiếu (preset Gemini một model, vai Jev trong kernel Kaggle, Jev làm grader), rồi chạy theo thứ tự ưu tiên của spec, mỗi nhóm run kết thúc bằng một file kết quả trong `docs/research/paper-v2/`. Viết bài là task cuối.

**Tech Stack:** Python 3.13, uv workspace (`backend`, `pharma-lab`), typer CLI `uv run pharma-lab`, pytest, Kaggle T4 qua `e2e run --backend kaggle`, `cli-proxy-api`, OpenRouter (Jev, SDK TypeSafe), LaTeX LNCS (`latexmk`).

**Spec:** `docs/superpowers/specs/2026-11-15-soict-paper-design.md` (§3.4). Dữ liệu, kiểm định và độ nhạy của từng dòng: `docs/superpowers/specs/2026-11-15-evaluation-design.md`. Cách chạy Kaggle: `docs/superpowers/specs/2026-11-15-kaggle-runs-design.md`.

**Phụ thuộc ngoài plan:** D2, D4, D5 (ablation retrieval) nằm trong plan của mảng evaluation (`2026-11-15-evaluation-remaining.md`) và không chặn các task dưới đây, vì cặp retrieval đã chốt. Lỗi gắn lại shard trên account khác (`StopIteration`) có plan sửa ở `2026-11-15-kaggle-runs-followups.md` Task 1; nghiệm thu Opus qua proxy trong kernel ở Task 2 của plan đó, nên làm trước Task 6 dưới đây.

## Global Constraints

- Golden e2e v4: `pharma-lab/data/evaluation/e2e/golden_e2e.jsonl`, sha256 `1dae2820631fe1e3b965c77e4fdb642d57de8f97fb26b5f0391e53e8640ba309`. Mọi run dùng cùng golden; ngưỡng không bao giờ chỉnh trên golden.
- Cặp retrieval của agent: hybrid RRF k=2, prefetch 50, giữ 20, `qwen3-embedding:4b-q8_0`, rerank `qwen3-reranker:4b-q8_0`, giữ 5; `max_evidence_chars = 60_000` trừ khi Task 1 hạ xuống.
- Model: `qwen3.5:9b-q8_0` (thinking tắt), `gemini-3.8-flash-high` (thinking low), `claude-opus-5-5` (`reasoning_effort=minimal`), Jev `~typesafe/jev-latest` qua `https://openrouter.ai/api`. Judge đánh giá `gemini-3.1-flash-lite`, reasoning `none`.
- Giá niêm yết USD mỗi 1M token vào/ra (2026-10-14): Qwen3.5-9B 0,10/0,15; Gemini 3.8 Flash 0,75/3,75; Opus 5.5 4/20; gemini-3.1-flash-lite 0,25/1,50; Jev 0,042/0. Không có mô hình giờ GPU.
- Độ trễ chỉ lấy từ run `--latency` (concurrency 1, một kernel, ghi vào `<run>-c1`) trên 200 câu `--limit 200`; chỉ so độ trễ giữa kiến trúc trên cùng một model.
- Mỗi run chạy thử `--limit 20` trước khi chạy đủ.
- Thứ tự quota: H và A1, A2 trước; rồi A3, A4; rồi B; rồi C; sau cùng D6 và E. Opus xếp sau hai model rẻ.
- Jev: mỗi run ghi phiên bản model trả về và dừng khi phiên bản đổi; khoá OpenRouter chỉ nằm trong `backend/.env` và `pharma-lab/.env` (git ignore), không bao giờ vào git, `data/`, `jobs.json`, log hay archive `data push`.
- Thống kê: Wilson cho tỉ lệ, bootstrap percentile 10.000 lần, sign-flip ghép cặp với Holm trong mỗi họ (một bảng một họ); A là không thua kém với biên 4 điểm truthfulness và 3 điểm nugget recall.
- `AGENTS.md`: test trong `tests/` theo cây gương của `src/`; không `# noqa`, `# type: ignore`, `ignore_imports`; ruff, pyrefly, `uv run lint-imports`, pytest xanh trong project bị sửa.
- Số vào bài chỉ lấy từ file báo cáo sinh bằng lệnh có sẵn; mỗi run commit `run.json`, `judge.json`, `reports/`; answers và judgments vào archive `vipharmind-data-v2` sau khi An đồng ý.
- Job dài chạy trong tmux; log ở `pharma-lab/data/work/logs-v2/`.

## Review Focus

1. Một run Kaggle có vai Jev mà không bật cờ đưa khoá phải bị từ chối trước khi đẩy kernel nào, như hiện nay. Test: `test_decision_roles_need_the_key_flag` (Task 3).
2. Khoá OpenRouter không được xuất hiện trong `jobs.json`, log của lệnh, `run.json` hay dataset công khai; dataset chứa khoá bị xoá khi lệnh kết thúc, kể cả khi Ctrl-C. Test: `test_decision_key_never_reaches_logs_or_identity`, `test_decision_key_dataset_is_private_and_deleted` (Task 3).
3. Gộp shard chạy dưới hai phiên bản Jev khác nhau vào cùng một cấu hình phải bị từ chối. Test: `test_merge_refuses_a_second_decision_model_version` (Task 3).
4. Preset Gemini một model phải đặt cả bảy vai (kể cả `AGENT`) vào `gemini-3.8-flash-high`, để A2 và ReAct dùng đúng một LLM. Test: `test_gemini_all_preset_puts_every_role_on_flash` (Task 3).
5. Grader Jev gặp item thiếu key fact hoặc phản hồi lỗi phải ghi item đó là lỗi, không tính là `missing`. Test: `test_decision_grade_error_is_not_a_missing_fact` (Task 8).

---

### Task 1: Đo token Jev của một khối evidence 60.000 ký tự

Mã đã có (`pharma-lab/src/pharma_lab/e2e/decision_probe.py`, lệnh `e2e decision-probe`, test `tests/e2e/test_decision_probe.py`); chưa chạy vì chưa có khoá OpenRouter.

**Files:**
- Create: `docs/research/paper-v2/10-phase-1-results.md` (mục "Token probe")
- Modify (chỉ khi phải hạ): `backend/src/pharma_agent/domain/agent/budget.py` (`BudgetLimits.max_evidence_chars`), spec `2026-11-15-soict-paper-design.md` §3.4.2, spec `2026-11-15-backend-agent-api-design.md` (bảng ngân sách)

- [ ] **Step 1:** Đặt vai `JUDGE` của `backend/.env` sang Jev (`PHARMA_LLM__ROLES__JUDGE__PROVIDER=systemone`, `..._BASE_URL=https://openrouter.ai/api`, `..._MODEL=~typesafe/jev-latest`, `..._API_KEY=<khoá>`).
- [ ] **Step 2:** `cd pharma-lab && uv run pharma-lab e2e decision-probe --chars 60000` ba lần; lấy lần hai và ba. Expected: in `input_tokens`, `chars_per_token`, `seconds`, `model` và `recommended max_evidence_chars`.
- [ ] **Step 3:** Luật: `input_tokens <= 24_000` thì giữ 60.000; ngược lại đặt `max_evidence_chars` bằng số khuyến nghị (làm tròn xuống nghìn), cho mọi cấu hình cùng lúc, và sửa hai spec. Ghi số đo, phiên bản model, ngày vào `10-phase-1-results.md`.
- [ ] **Step 4:** Nếu có sửa `budget.py`: `cd backend && uv run pytest -q && uv run ruff check . && uv run pyrefly check && uv run lint-imports` → PASS.
- [ ] **Step 5:** Commit `docs: Jev tokens of a full evidence budget` (kèm `budget.py` nếu đổi).

### Task 2: Hiệu chuẩn Jev trên tập giữ lại (H) và chọn τ, ngưỡng guard

Tập đã dựng: `pharma-lab/data/evaluation/calibration/judge_set.jsonl` (300 câu, 35 thiếu bằng chứng) và `guard_set.jsonl` (300 lượt). Mã: `decision_calibration.py`, `decision_metrics.py`, lệnh `e2e decision-set score`.

**Files:**
- Create: `pharma-lab/data/evaluation/calibration/jev.json`
- Modify: `docs/research/paper-v2/10-phase-1-results.md` (mục "Calibration")

- [ ] **Step 1:** Nếu An quyết định lấy thêm câu thiếu bằng chứng (câu hỏi mở 4 của spec), dựng lại bằng `uv run pharma-lab e2e decision-set build --run hybrid-qwen4b-v3-p50-k20-rrf2 --model qwen3-reranker:4b-q8_0 --size <n> --seed 0` trước bước sau.
- [ ] **Step 2:** Vai `GUARDRAIL` và `JUDGE` của `backend/.env` trỏ Jev; `uv run pharma-lab e2e decision-set score --repeats 3`. Expected: `jev.json` có AUROC, ECE, Brier, độ chính xác ở 0,5 và ở `tau`, tỉ lệ lật khi xoay thứ tự và khi gọi lặp, recall tấn công ở 0,35/0,50/0,70, `tau`, `block`, `review`, phiên bản model, ngày.
- [ ] **Step 3:** Ghi mọi số vào `10-phase-1-results.md` kèm khoảng tin cậy bootstrap của AUROC. Luật: AUROC judge dưới 0,70 thì A2 (LLM judge) là điểm so sánh chính và kết quả vẫn được báo; run vẫn chạy.
- [ ] **Step 4:** Commit `data: Jev calibration on the held-out set` (`jev.json`, file kết quả).

### Task 3: Preset Gemini một model và vai Jev trong kernel Kaggle

Hiện kernel từ chối mọi vai `systemone` (`check_no_decision_roles`), và preset `gemini` là cấu hình chia vai của A1 (guard, rephrase trên flash-lite). A2 Gemini, ReAct Gemini, A3 Qwen, A4 và B đều cần mảnh này.

**Files:**
- Modify: `pharma-lab/src/pharma_lab/e2e/llm_presets.py`, `pharma-lab/src/pharma_lab/e2e/kernel_env.py`, `pharma-lab/src/pharma_lab/e2e/kaggle_shards.py`, `pharma-lab/src/pharma_lab/e2e/proxy_credentials.py` (hoặc module mới `decision_key.py` cùng tầng), `pharma-lab/src/pharma_lab/cli/commands/e2e.py`, `pharma-lab/docs/guides/e2e-evaluation.md`
- Test: `pharma-lab/tests/e2e/test_kernel_env.py`, `pharma-lab/tests/e2e/test_kaggle_shards.py`, `pharma-lab/tests/e2e/test_proxy_credentials.py`

**Interfaces:**
- Produces:
  - Preset `"gemini-all"` trong `PRESETS`: mọi vai của `LLM_ROLES` là `RoleEndpoint("gemini-3.8-flash-high", PROXY_API_KEY, base_url=PROXY_BASE_URL)`, `needs_proxy=True`, `providers={"antigravity"}`, `max_in_flight=4`. `--llm` nhận `gemini-all`.
  - `RoleEndpoint.provider: str = "openai"`; `_endpoint_env` ghi `<prefix>PROVIDER` khi khác `"openai"`.
  - `with_decision_roles(preset: LlmPreset, *, api_key_file: str, thresholds: Mapping[str, float]) -> LlmPreset`: thay `GUARDRAIL` và `JUDGE` bằng `RoleEndpoint("~typesafe/jev-latest", <đọc từ file trong kernel>, base_url="https://openrouter.ai/api", provider="systemone")`; `GUARDRAIL` mang `extra_body={"thresholds": {"block": b, "review": r}}` lấy từ `jev.json`.
  - Cờ `e2e run --decision jev` (mặc định tắt) cộng `--with-decision-key`: đọc `OPENROUTER_API_KEY` từ `pharma-lab/.env`, đưa lên một dataset riêng tư theo run trên account chạy shard, xoá khi lệnh kết thúc (cùng vòng đời và cách quét dataset sót như `CredentialDataset`). Thiếu `--with-decision-key` khi có `--decision jev` thì từ chối trước khi đẩy kernel.
  - Gộp shard (`kaggle_shards`) so phiên bản Jev trong `run.json` như đang so sha256 model.

- [ ] **Step 1: Test** `test_gemini_all_preset_puts_every_role_on_flash` (bảy vai, đúng model, `needs_proxy`); `test_decision_roles_need_the_key_flag` (`--decision jev` không có `--with-decision-key` → lỗi, không kernel nào được đẩy); `test_kernel_env_writes_the_decision_provider` (env có `PHARMA_LLM__ROLES__JUDGE__PROVIDER=systemone` và `..._BASE_URL=https://openrouter.ai/api`, không chứa giá trị khoá); `test_decision_key_never_reaches_logs_or_identity`; `test_decision_key_dataset_is_private_and_deleted` (`public=False`, xoá cả khi ngắt); `test_merge_refuses_a_second_decision_model_version`.
- [ ] **Step 2:** `cd pharma-lab && uv run pytest tests/e2e -q` → FAIL ở các test mới.
- [ ] **Step 3:** Cài đặt theo Interfaces. Kernel đọc khoá từ file trong dataset vào biến môi trường của tiến trình backend, không ghi ra đĩa output.
- [ ] **Step 4:** `uv run pytest -q && uv run ruff check . && uv run pyrefly check --min-severity warn && uv run lint-imports` → PASS; cập nhật guide (lệnh, cờ, quy tắc khoá).
- [ ] **Step 5:** Nghiệm thu thật: `uv run pharma-lab e2e run --backend kaggle --run e2e-v4-smoke-jev --config full --limit 10 --decision jev --with-decision-key --pipeline-option refine_mode=template --pipeline-option refine_threshold=<tau>`. Expected: 10 câu, mỗi dòng `answers.jsonl` có `decisions` của guard và judge, cùng một phiên bản Jev; dataset khoá đã bị xoá.
- [ ] **Step 6:** Commit `feat(pharma-lab): Jev decision roles and a one-model Gemini preset in Kaggle runs`.

### Task 4: Giá của embedding và reranker của agent

**Files:**
- Modify: `pharma-lab/src/pharma_lab/e2e/pricing.py`, `pharma-lab/tests/e2e/test_pricing.py`

- [ ] **Step 1:** Đọc giá OpenRouter của Qwen3-Embedding-4B và Qwen3-Reranker-4B ngày chạy. Có giá: thay dòng cận trên của `qwen3-embedding:4b-q8_0` và `qwen3-reranker:4b-q8_0` bằng `ModelPrice(<vào>, 0.0, <url>, <ngày>)` và sửa test giá tương ứng. Không có giá: giữ cận trên và ghi câu "giá retrieval là cận trên" vào `09-phase-0-results.md` để bài nêu.
- [ ] **Step 2:** `uv run pytest tests/e2e/test_pricing.py -q` → PASS; commit `chore(pharma-lab): list prices of the agent's retrieval pair` (nếu đổi).

### Task 5: A1 và A2 (Qwen, Gemini, Opus)

**Files:**
- Create: `docs/research/paper-v2/09-phase-0-results.md`
- Create (run): `pharma-lab/data/evaluation/e2e/runs/e2e-v4-{gemini-split,qwen9b,gemini,opus}{,-c1}/`

- [ ] **Step 1: Chạy thử** mỗi run `--limit 20`: `uv run pharma-lab e2e run --backend kaggle --run e2e-v4-qwen9b --config full --config one-step --config closed-book --limit 20`; tương tự `--run e2e-v4-gemini-split --llm gemini --with-proxy-credentials` (A1) và `--run e2e-v4-gemini --llm gemini-all --with-proxy-credentials` (A2). Expected: `run.json` ghi đúng model từng vai; `reasoning_tokens == 0` với Qwen và Gemini.
- [ ] **Step 2: Chạy đủ** cùng lệnh không `--limit`; chạy lại đúng lệnh khi tạm dừng vì quota (exit 10). Rồi `--latency --limit 200 --config full --config one-step` cho mỗi run.
- [ ] **Step 3: Opus** (sau nghiệm thu Opus của plan kaggle-runs): `--run e2e-v4-opus --llm opus --with-proxy-credentials`, ba cấu hình, rồi run `--latency`. Ghi trung bình `reasoning_tokens` của Opus.
- [ ] **Step 4: Chấm và báo cáo:** với mỗi run và cấu hình `uv run pharma-lab e2e judge --run <R> --config <C> --judge-model gemini-3.1-flash-lite`; `uv run pharma-lab e2e report --run <R> --latency-run <R>-c1`; `uv run pharma-lab e2e compare --run-a e2e-v4-gemini --run-b e2e-v4-qwen9b --config full`. Expected: `reports/{main,ablation,cost}.csv|tex`, `provenance.json` có `latency_run`.
- [ ] **Step 5:** `09-phase-0-results.md`: bảng A1, A2 (truthfulness, nugget recall, hallucination, severe harm, faithfulness, citation recall, an toàn, giây p50/p95, USD mỗi 1.000 lượt, cost of pass), tách thời gian theo bước, kết quả compare, kiểm tra không lượt nào chạm trần ngữ cảnh 32.768 của Qwen. Commit `data: A1 and A2 on golden v4 with seconds and USD`.

### Task 6: A3 (ba model) và A4

**Files:**
- Modify: `docs/research/paper-v2/10-phase-1-results.md` (mục "A")

- [ ] **Step 1:** Với `M ∈ {qwen9b (--llm qwen), gemini (--llm gemini-all), opus (--llm opus)}`: `uv run pharma-lab e2e run --backend kaggle --run e2e-v4-$M-jev --config full --decision jev --with-decision-key --pipeline-option refine_mode=template --pipeline-option refine_threshold=$TAU` (thêm `--with-proxy-credentials` cho Gemini, Opus), chạy thử 20 câu trước; rồi `--latency --limit 200`.
- [ ] **Step 2: A4:** cùng lệnh với Qwen nhưng `refine_mode=llm`, vào run `e2e-v4-qwen9b-jev`.
- [ ] **Step 3:** Chấm, `report --latency-run`, và `e2e compare --run-a e2e-v4-$M --run-b e2e-v4-$M-jev --config full --config-b "full+refine_mode=template+refine_threshold=$TAU"` cho mỗi model. Expected: `usage_by_role.refine` vắng ở cấu hình template; mọi `decisions` cùng một phiên bản Jev.
- [ ] **Step 4:** Bảng A đầy đủ (A1, A2 ×3, A3 ×3, A4) với kiểm định không thua kém (biên 4 và 3 điểm) vào `10-phase-1-results.md`; commit `data: decision-model runs A3 and A4`.

### Task 7: B, quét τ

- [ ] **Step 1:** Với `τ ∈ {0, 0.3, 0.5, 0.7, 0.9, 1}`: A3 Qwen và A3 Gemini (`--decision jev ... refine_threshold=τ`), cùng A2 Qwen với `--pipeline-option refine_threshold=τ` (độ tin cậy nói ra của LLM judge). Không quét Opus; τ đã chọn áp nguyên cho Gemini và Opus.
- [ ] **Step 2:** Chấm và `report`; `ablation.csv` của mỗi run giữ các điểm τ so với điểm τ đã chọn. So sánh khai báo trước: τ=0 so với τ\*, τ\* so với τ=1, Jev so với độ tin cậy nói ra (Holm).
- [ ] **Step 3:** `10-phase-1-results.md` mục "B": đường chất lượng so với USD và so với giây, tỉ lệ refine thực tế, chi phí bước judge, tỉ lệ gây hại khi τ=0, phân tích "judge nói đủ nhưng thiếu key fact" theo nhóm. Commit `data: refinement threshold sweep`.

### Task 8: C (graph routing so với ReAct), D6 và E1–E5

**Files:**
- Create: `pharma-lab/src/pharma_lab/e2e/judging/decision_grader.py`, `docs/research/paper-v2/11-phase-2-results.md`, `docs/research/paper-v2/12-e2e-ablations.md`
- Modify: `pharma-lab/src/pharma_lab/cli/commands/e2e.py` (lệnh `e2e decision-grade`)
- Test: `pharma-lab/tests/e2e/judging/test_decision_grader.py`

**Interfaces:**
- Produces: `grade_questions(item: GoldenItem) -> dict[str, ChoiceQuestion]` (mỗi key fact một câu chọn `supported`/`missing`/`contradicted`, cộng `harm`, `abstention`, `injection`); `async grade_answer(decision: DecisionPort, item, answer) -> DecisionGrade`; lệnh `uv run pharma-lab e2e decision-grade --run <R> --config <C>` ghi `decision_grades.jsonl` cạnh `judgments.jsonl` và `agreement` với nhãn dược sĩ khi có `calibration/grades.jsonl`.

- [ ] **Step 1: C.** Với mỗi model `uv run pharma-lab e2e run --backend kaggle --run e2e-v4-$M --config react ...` (preset như Task 5), rồi `--latency`; chấm; `e2e compare --run-a e2e-v4-$M --run-b e2e-v4-$M --config full --config-b react`. `11-phase-2-results.md`: mỗi model hai điểm, chênh ghép cặp, bảng thất bại ReAct theo loại (chạm trần vòng, tool call sai định dạng, gọi trùng, không trích dẫn), lát multi_hop, multi_turn và injection.
- [ ] **Step 2: D6.** Trên Qwen A2, chạy `--category answerable --category multi_hop` (810 câu; golden không có category riêng cho tầng tự nhiên) và báo trên tầng `natural_and_multi_hop` (720 câu) của report: cấu hình `bm25`, `dense`, `hybrid-k60`, `no-rerank`, `full`, mỗi cái ở hai chế độ (`one-step` là `--pipeline-option rephrase=false --pipeline-option judge_refine=false`). Vẽ truthfulness theo Hit@5 và nDCG@5 của retriever tương ứng (số từ spec `evaluation`).
- [ ] **Step 3: E1–E4** trên A3 Qwen: `--pipeline-option rephrase=false`, `judge_refine=false`, cấu hình `one-step`, `no-rerank`; E4 `no-guard` trên A2 và A3, đo trên `guard_set.jsonl` và tỉ lệ từ chối nhầm trên golden.
- [ ] **Step 4: E5, test:** `test_grade_questions_one_choice_per_key_fact`, `test_decision_grade_error_is_not_a_missing_fact`; chạy → FAIL; cài đặt; chạy lại → PASS; ruff, pyrefly, lint-imports xanh.
- [ ] **Step 5: Nhãn dược sĩ:** `uv run pharma-lab e2e calibration export --run <R> --config <C>` 50 item cho mỗi cấu hình chính (A2, A3, ReAct × 3 model); dược sĩ chấm vào `grades.jsonl`; `e2e calibration score --run <R>`. Rồi `e2e decision-grade` trên 450 item đó, báo AC1, κ có KTC, USD và giây so với gemini-3.1-flash-lite.
- [ ] **Step 6:** `12-e2e-ablations.md` (D6, E1–E5, taxonomy lỗi của full agent, phân tích citation recall). Commit theo từng nhóm run: `data: graph routing versus ReAct`, `data: e2e ablations D6 and E`, `feat(pharma-lab): Jev as a per-key-fact grader`.

### Task 9: Viết bản thảo paper v2

**Files:**
- Create: thư mục bài v2 (mặc định `docs/report-v2/`, theo câu trả lời của An cho câu hỏi mở 2), cùng cấu trúc với `docs/report/` (`.latexmkrc`, `llncs.cls` hoặc class của venue, `sections/`, `tables/`, `figures/`, `references.bib`)
- Modify: `.pre-commit-config.yaml` (hook build cho thư mục mới)

- [ ] **Step 1:** Dựng khung IMRaD (Introduction, Related Work, Materials and Methods, Results, Discussion, Conclusion); build `latexmk` sạch warning.
- [ ] **Step 2:** Methods từ `docs/report/drafts/methods-v2.tex`, sửa theo golden v4 (1.000 câu: tự nhiên 520, lát 90, multi_hop 200 gồm two_drug 70, brand_to_ingredient 65, three_intent 65, multi_turn 160, safety 30), tập guard 300 lượt, cách duyệt golden bằng hai vòng model và dược sĩ xem lướt; chunk là đơn vị đọc kèm thống kê token và D7; giao thức đo độ trễ và chi phí; ReAct và quy tắc công bằng.
- [ ] **Step 3:** Results và bảng sinh từ `reports/*.tex` của các run (không chép tay số); hình teaser truthfulness theo USD và theo giây; Pareto τ; mặt phẳng graph so với ReAct.
- [ ] **Step 4:** Related Work theo spec §3.4.4, mỗi mục bib kiểm từ DOI, arXiv hoặc DBLP; Limitations theo spec §3.4.4; kiểm điều khoản công bố của Jev.
- [ ] **Step 5:** Tạo dataset Kaggle công khai mới cho v2 (không đụng `vipharma-rag`) sau khi An duyệt; đặt link vào bài.
- [ ] **Step 6:** Kiểm cuối: `latexmk` sạch, không citation hay reference thiếu, mọi số truy được về file báo cáo. Commit `docs(report): paper v2 manuscript`.

## Self-review

- **Spec coverage:** §3.4.3 H (Task 2), A1–A2 (Task 5), A3–A4 (Task 6), B (Task 7), C, D6, E1–E5 và nhãn dược sĩ (Task 8); §3.4.2 giá (Task 4), độ trễ (Task 5–8 dùng `--latency`), Jev trong kernel (Task 3); token probe (Task 1); §3.4.4 bài viết và dataset công khai (Task 9). D1–D5, D7 ngoài plan (mảng evaluation).
- **Đã bỏ so với plan cũ:** pha 0 Task 10 (An bỏ ngày 2026-10-16); mọi lệnh `e2e llm-server`, `rerank-server`, `embed-server` (đã gỡ); bước chọn cặp retrieval của pha 0 Task 11 Step 0 (đã chốt theo luật mới ngày 2026-10-26).
- **Placeholder:** `$TAU`, ngưỡng `block`, `review` lấy từ `jev.json` của Task 2 trước mọi lệnh dùng chúng.
