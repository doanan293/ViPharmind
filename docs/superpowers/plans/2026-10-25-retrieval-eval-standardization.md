# Chuẩn hóa đánh giá retrieval và luật chọn cặp cho agent

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Trạng thái:** chưa bắt đầu (viết 2026-10-25).

**Goal:** Mọi so sánh retrieval của bài đi qua một luật chọn duy nhất, một bộ nhãn và một golden, tính bằng công cụ của `pharma-lab`; xoá mọi run không dựng trên golden đã chốt.

**Architecture:** `statistics.py` chuyển từ `e2e` xuống `evaluation` để retrieval và e2e dùng chung bootstrap, sign-flip và Holm. Judgments chấp nhận chunk leaflet cùng hoạt chất cho mọi nhóm. Lệnh mới `pharma-lab metrics select` thay `metrics compare`: nhận danh sách cấu hình xếp từ rẻ tới đắt, áp luật §3.4 viết lại, loại nhóm theo tham số. Sau đó dựng lại judgments, tính lại metric mọi run `9c6e…` và ghi kết quả chọn vào spec.

**Tech Stack:** Python 3.13, typer, numpy, pytest, import-linter (`uv run lint-imports`), pyrefly, ruff.

**Spec:** `docs/superpowers/specs/2026-10-14-paper-v2-design.md` (§3.4, §5, Phụ lục A §5, bảng tiến độ).

## Global Constraints

- Quy tắc repo trong `AGENTS.md`: không `# noqa`, không `# type: ignore`, không `ignore_imports`; test trong `pharma-lab/tests/` theo cây gương của `src/pharma_lab/`; contract import-linter phải xanh.
- Thống kê (spec §5): trung bình bằng bootstrap percentile 10.000 lần; so sánh bằng sign-flip ghép cặp; Holm trong một họ so sánh; seed 0.
- Golden retrieval duy nhất: `data/evaluation/gold/section_retrieval_eval.jsonl`, sha256 `9c6e4de6…`.
- Lệnh chạy trong `pharma-lab/`: `uv run pytest`, `uv run ruff check`, `uv run pyrefly check`, `uv run lint-imports`.
- Commit kết thúc bằng `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Hai báo cáo chấm bằng judgments khác nhau hoặc golden khác nhau thì `metrics select` phải từ chối, không so lặng lẽ. Test: `test_select_refuses_reports_with_different_judgments` (Task 3).
2. Tên nhóm trong `--exclude-group` không có trong golden (gõ sai `conversation`) phải báo lỗi, không lặng lẽ giữ nguyên tập câu. Test: `test_unknown_excluded_group_is_an_error` (Task 3).
3. Bootstrap trên 8.470 câu không được cấp phát ma trận 10.000 × n một lần (khoảng 700 MB); kết quả phải giống hệt bản tính một khối. Test: `test_blocked_resampling_matches_one_block` (Task 1).
4. Hai cấu hình có trung bình bằng nhau tuyệt đối: người dẫn đầu là cấu hình đứng trước (rẻ hơn) trong danh sách, không phụ thuộc thứ tự dict. Test: `test_equal_means_lead_with_the_cheaper_config` (Task 3).
5. Báo cáo tính trước khi đổi judgments (manifest ghi `judgments_sha256` cũ) phải bị `metrics select` từ chối, kèm gợi ý chạy `pharma-lab metrics --force`. Test: `test_select_refuses_reports_with_stale_judgments` (Task 3).

---

### Task 1: Thống kê dùng chung ở tầng `evaluation`

**Files:**
- Move: `pharma-lab/src/pharma_lab/e2e/statistics.py` → `pharma-lab/src/pharma_lab/evaluation/statistics.py`
- Move: `pharma-lab/tests/e2e/test_statistics.py` → `pharma-lab/tests/evaluation/test_statistics.py`
- Modify: `pharma-lab/src/pharma_lab/e2e/compare.py`, `e2e/calibration.py`, `e2e/report.py` (import từ `pharma_lab.evaluation.statistics`)

**Interfaces:**
- Produces: `pharma_lab.evaluation.statistics` với `bootstrap_mean(values, *, seed=SEED) -> Summary`, `paired_test(differences, *, seed=SEED) -> PairedTest`, `holm(p_values) -> list[float]`, `Summary(n, mean, ci_low, ci_high)`, `PairedTest(summary, p_value)`, hằng `RESAMPLES = 10_000`, `SEED = 0`. Chữ ký giữ nguyên.

- [ ] **Step 1: Ghi số tham chiếu trước khi sửa**

Chạy với code hiện tại và chép hai số vào test:
`uv run python -c "from pharma_lab.e2e.statistics import bootstrap_mean, paired_test; v=[(i*37%11-5)/5 for i in range(3000)]; print(bootstrap_mean(v)); print(paired_test(v))"`

- [ ] **Step 2: `git mv` hai file, sửa import ở ba module e2e và trong test**

- [ ] **Step 3: Viết test `test_blocked_resampling_matches_one_block`**

```python
def test_blocked_resampling_matches_one_block() -> None:
    values = [(i * 37 % 11 - 5) / 5 for i in range(3000)]
    assert bootstrap_mean(values) == Summary(3000, ..., ..., ...)  # số ở Step 1
    assert paired_test(values) == PairedTest(..., ...)  # số ở Step 1
```

- [ ] **Step 4: Chạy test, phải PASS ngay trên bản chưa chia khối** (chốt số tham chiếu)

Run: `uv run pytest tests/evaluation/test_statistics.py -v`

- [ ] **Step 5: Chia khối trong `bootstrap_mean` và `paired_test`**

Sinh lần lượt các khối `RESAMPLE_BLOCK = 500` hàng bằng cùng một `np.random.default_rng(seed)` (`rng.integers(0, n, (block, n))`, `rng.choice((-1.0, 1.0), size=(block, n))`) rồi nối kết quả. Luồng số ngẫu nhiên giữ nguyên thứ tự nên kết quả trùng bản một khối; test Step 3 khẳng định điều đó.

- [ ] **Step 6: Chạy toàn bộ test, lint-imports, pyrefly**

Run: `uv run pytest tests/evaluation tests/e2e -q && uv run lint-imports && uv run pyrefly check`
Expected: tất cả PASS, contract "pharma_lab layers" KEPT.

- [ ] **Step 7: Commit** `refactor(pharma-lab): retrieval and e2e share one statistics module`

### Task 2: Judgments áp cho mọi nhóm

**Files:**
- Modify: `pharma-lab/src/pharma_lab/evaluation/relevance_judgments.py:35` (xoá `JUDGED_EVAL_GROUPS` và điều kiện ở `build_judgments`), `RULES_VERSION = 2`
- Modify: docstring module: luật áp cho mọi câu có gold là mục formulary, ở bất kỳ nhóm nào
- Test: `pharma-lab/tests/evaluation/test_relevance_judgments.py`

- [ ] **Step 1: Viết test**

```python
@pytest.mark.parametrize(
    "group", ["noisy", "glossary", "conversational", "multi_hop", "structured"]
)
def test_every_group_is_judged_by_the_same_rule(group: str) -> None:
    rows = [
        {
            "query_id": "q",
            "eval_group": group,
            "answer_mode": "single",
            "expected_section_id": "drug:acarbose:lieu-luong-va-cach-dung",
        }
    ]
    assert build_judgments(rows, ACARBOSE_CHUNKS) == [JUDGMENT | {"query_id": "q"}]
```

`ACARBOSE_CHUNKS` là danh sách `chunks` hiện có trong `test_judgments_accept_same_ingredient_leaflet_chunks_of_the_asked_intent`, tách thành hằng module dùng chung. Thêm `assert manifest["rules_version"] == 2` vào `test_judgments_live_next_to_the_gold_file_and_round_trip`.

- [ ] **Step 2: Chạy, FAIL** (`build_judgments` trả `[]` cho nhóm noisy)
- [ ] **Step 3: Sửa code** như mục Files
- [ ] **Step 4: Chạy `uv run pytest tests/evaluation/test_relevance_judgments.py tests/e2e -q`, PASS**
- [ ] **Step 5: Commit** `feat(pharma-lab): relevance judgments apply to every benchmark group`

### Task 3: `pharma-lab metrics select` thay `metrics compare`

**Files:**
- Create: `pharma-lab/src/pharma_lab/evaluation/config_selection.py`
- Delete: `pharma-lab/src/pharma_lab/evaluation/metric_comparison.py`, `pharma-lab/tests/evaluation/test_metric_comparison.py`
- Modify: `pharma-lab/src/pharma_lab/cli/commands/metrics.py` (bỏ `compare`, thêm `select`)
- Modify: `pharma-lab/src/pharma_lab/evaluation/retrieval_slices.py:29`, `evaluation/dev_test_split.py:19` (import `load_query_metric` từ `config_selection`)
- Modify: `pharma-lab/docs/guides/cli-reference.md`, `pharma-lab/docs/guides/evaluation.md` (mọi chỗ nhắc `metrics compare`)
- Test: `pharma-lab/tests/evaluation/test_config_selection.py`, `pharma-lab/tests/cli/test_metrics_command.py` (thay test `compare` bằng một test `select` đọc `chosen` từ output JSON)

**Interfaces:**
- Consumes: `paired_test`, `holm` (Task 1); `report_dir(run_root, *, top_k, model)` trong `metrics_artifacts.py`; `load_bundle(..., expected_type="metrics_report", require_complete=True)`; `resolve_evaluation_reference`, `load_run_record` trong `run_workspace.py`.
- Produces (giữ `load_query_metric(report: Path, metric: str) -> tuple[dict[str, Any], dict[str, float]]`, chuyển nguyên từ `metric_comparison.py`):

```python
@dataclass(frozen=True)
class ConfigReport:
    label: str          # tên hiển thị, ví dụ "hybrid-qwen8b"
    run_root: Path
    model: str | None   # None = báo cáo baseline (chưa rerank)

@dataclass(frozen=True)
class PairRow:
    leader: str; other: str; mean_difference: float
    ci_low: float; ci_high: float; p_value: float; p_holm: float; beaten: bool

@dataclass(frozen=True)
class StageResult:
    metric: str; leader: str; means: dict[str, float]
    rows: tuple[PairRow, ...]; tied: tuple[str, ...]   # tied giữ thứ tự đầu vào

@dataclass(frozen=True)
class Selection:
    chosen: str
    reason: Literal["primary", "secondary", "cheapest_of_tie"]
    primary: StageResult; secondary: StageResult | None
    query_count: int; excluded_groups: tuple[str, ...]

def select_config(
    configs: Sequence[ConfigReport], *, primary: str, secondary: str,
    top_k: int, exclude_groups: Sequence[str] = (),
) -> Selection
```

Luật (đúng §3.4 viết lại ở Task 4), viết thành code:

```
stage(metric, pool):
    leader = cấu hình có trung bình cao nhất; bằng nhau thì cấu hình đứng trước
    với mỗi cấu hình khác o: d = leader - o theo từng câu; paired_test(d)
    p_holm = holm(các p của họ này)
    beaten(o) = ci_low > 0 và p_holm < 0,05
    tied = [leader] + các o không bị beaten, theo thứ tự đầu vào
chọn:
    s1 = stage(primary, mọi cấu hình); tied chỉ còn leader -> chosen, "primary"
    s2 = stage(secondary, s1.tied);    tied chỉ còn leader -> chosen, "secondary"
    ngược lại -> tied đầu tiên của s2 theo thứ tự đầu vào, "cheapest_of_tie"
```

Kiểm tra trước khi tính: mọi báo cáo cùng `evaluation_sha256` và cùng `judgments_sha256`, và `judgments_sha256` bằng sha của file judgments hiện tại cạnh golden (khác thì báo "chạy `pharma-lab metrics --run <run> --force`"); cùng tập `query_id` sau khi loại nhóm; mỗi tên trong `exclude_groups` phải là một `eval_group` có trong golden; `primary` và `secondary` phải có trong mọi dòng `metrics.jsonl`; ít nhất hai cấu hình, nhãn không trùng. Nhóm của câu đọc từ golden của run (`load_run_record(run_root).identity.evaluation_path` qua `resolve_evaluation_reference(..., DATA_DIR)`).

CLI:

```
uv run pharma-lab metrics select --top-k 20 --metric hit@20 --secondary hit@5 \
  --exclude-group conversational \
  --config bm25=bm25-v3-k20 --config dense-qwen8b=dense-qwen8b-v3-k20 \
  --config hybrid-qwen8b+4b=hybrid-qwen8b-v3-p50-k20-rrf2@qwen3-reranker:4b-q8_0
```

`--config LABEL=RUN[@MODEL]`, lặp lại, thứ tự là thứ tự chi phí tăng dần. Đầu ra `CommandResult` gồm `chosen`, `reason`, `query_count`, `excluded_groups` và với mỗi giai đoạn: `metric`, `means`, các dòng `PairRow`, `tied`.

- [ ] **Step 1: Viết test** trong `test_config_selection.py`, dựng báo cáo bằng `publish_metrics_artifact` như helper `_publish` của test cũ, golden giả có cột `eval_group`:
  - `test_a_clear_primary_winner_is_chosen`: A thắng B, C ở mọi câu → `chosen == "A"`, `reason == "primary"`, mọi `PairRow.beaten`.
  - `test_a_primary_tie_goes_to_the_secondary_metric`: A, B bằng nhau ở `hit@20`, A hơn rõ ở `hit@5` → `reason == "secondary"`, `chosen == "A"`.
  - `test_a_full_tie_takes_the_cheapest`: A, B bằng nhau ở cả hai → `chosen` là cấu hình đứng trước, `reason == "cheapest_of_tie"`.
  - `test_equal_means_lead_with_the_cheaper_config`.
  - `test_holm_uses_the_family_size`: ba cấu hình; `p_holm` của dòng p nhỏ nhất bằng `min(1, 2 * p)`.
  - `test_excluded_groups_drop_their_queries`: câu nhóm `conversational` bị loại, `query_count` giảm đúng số đó, và chênh lệch chỉ ở các câu đó không làm ai thắng.
  - `test_unknown_excluded_group_is_an_error`.
  - `test_select_refuses_reports_with_different_judgments`.
  - `test_select_refuses_reports_with_stale_judgments`.
  - `test_reports_over_different_queries_are_refused`.
- [ ] **Step 2: Chạy, FAIL** (module chưa có)
- [ ] **Step 3: Viết `config_selection.py`, xoá `metric_comparison.py` và test cũ, sửa CLI và hai guide**
- [ ] **Step 4: Chạy `uv run pytest tests/evaluation tests/cli -q && uv run lint-imports && uv run pyrefly check && uv run ruff check`, PASS**
- [ ] **Step 5: Commit** `feat(pharma-lab): metrics select applies the agent's retrieval selection rule`

### Task 4: Spec §3.4 viết lại trước khi tính số mới

**Files:**
- Modify: `docs/superpowers/specs/2026-10-14-paper-v2-design.md` §3.4, Phụ lục A §5 (gạch "Reranker: chọn theo Hit@5 và Hit@1 ... ngang 8B"), §5 (không đổi nội dung, chỉ dẫn chiếu tới §3.4)

- [ ] **Step 1: Viết lại §3.4** với nội dung sau (giữ tiêu đề, đổi dòng ngày):
  - Giai đoạn 1 (chưa rerank): mọi cấu hình tìm; chính Hit@20, phụ Hit@5.
  - Giai đoạn 2 (chỉ trên cấu hình thắng giai đoạn 1): Qwen3-Reranker-0.6B, 4B, 8B, bge-reranker-v2-m3; chính Hit@5, phụ MRR@10.
  - Thắng rõ: khoảng tin cậy 95% bootstrap ghép cặp 10.000 lần của chênh lệch nằm trên 0 **và** p sign-flip sau Holm trong họ (mỗi giai đoạn, mỗi chỉ số là một họ) dưới 0,05. Thủ tục chính xác như `pharma_lab/evaluation/config_selection.py`.
  - Tập câu: benchmark 10.000 câu trừ nhóm `conversational` và 30 câu safety (8.470 câu). Lý do: agent luôn viết lại câu hỏi trước khi tìm; nhóm hội thoại được đo ở D5.
  - Nhãn: golden `9c6e4de6…` cùng judgments rules_version 2 (mọi nhóm).
  - Thứ tự chi phí dùng khi hòa: BM25; dense theo số tham số embedding (gemma-300m, bge-m3, qwen 0,6B, 4B, 8B); hybrid ngay sau dense cùng embedding; reranker theo số tham số (bge-v2-m3, 0,6B, 4B, 8B).
  - Ghi chú lịch sử: luật bản 2026-10-18 có thêm vế "không tụt quá 1 điểm ở lát hay nhóm nào" và chấm trên cả nhóm hội thoại; hai thay đổi này và judgments cho mọi nhóm quyết định ngày 2026-10-25, sau khi đã thấy số `-v3-` giai đoạn 1. Bảng retrieval báo đủ theo nhóm và lát, kể cả nhóm cấu hình thắng bị tụt.
- [ ] **Step 2: Commit** `docs(spec): the retrieval selection rule, written as the code applies it`

### Task 5: Xoá run retrieval không dựng trên golden đã chốt

**Files:**
- Delete: mọi `pharma-lab/data/evaluation/runs/<run>/` có `evaluation_sha256` khác `9c6e4de6…` (danh sách lấy bằng lệnh ở Step 1; ngày 2026-10-25 là 26 trên 34 run, còn lại 8 run `-v3-`: mọi `-v2-`, mọi `-k30`, `dense-text-embedding-3-large-k30`, `hybrid-qwen4b-v3-p50-k20-rrf60`, `hybrid-qwen4b-v3-plain-p50-k20-rrf2`)
- Delete: `pharma-lab/data/evaluation/gold-conversational/`, `pharma-lab/data/evaluation/gold-enrichment/` nếu Step 1 cho thấy không run nào còn trỏ tới
- Modify: `pharma-lab/data/README.md` nếu có nhắc các run này

- [ ] **Step 1: Liệt kê**

Run: `cd pharma-lab && grep -L '"evaluation_sha256": "9c6e4de6' data/evaluation/runs/*/run.json`
Expected: đúng các run ở mục Files; dán danh sách vào message commit.

- [ ] **Step 2: Kiểm tra không còn code hay doc nào đọc tên các run đó**

Run: `grep -rn "<tên run>" pharma-lab/src pharma-lab/tests pharma-lab/docs docs/` cho từng tên; sửa chỗ còn trỏ.

- [ ] **Step 3: `git rm -r` các thư mục; `uv run pytest -q` (có `test_tracked_runs.py`) PASS**
- [ ] **Step 4: Commit** `chore(pharma-lab): drop retrieval runs scored on retired gold files`

### Task 6: Tính lại và chạy luật chọn trên số hiện có

**Files:**
- Modify (dữ liệu): `pharma-lab/data/evaluation/gold/section_retrieval_eval.judgments.jsonl` và manifest; `reports/` của mọi run `-v3-`
- Modify: spec, bảng tiến độ, "Việc đang mở" và một mục kết quả mới trong §3.4

- [ ] **Step 1: Dựng lại judgments**

Run: `cd pharma-lab && uv run pharma-lab evaluation judgments`
Expected: manifest `rules_version: 2`, `query_count` lớn hơn 958.

- [ ] **Step 2: Tính lại metric mọi run**

Run: `for r in $(ls data/evaluation/runs); do uv run pharma-lab metrics --run $r --top-k 20 --force || break; done`
Expected: mọi run có `reports/baseline/top20` mới, run hybrid-qwen8b có thêm ba `reports/rerank/*/top20`.

- [ ] **Step 3: Giai đoạn 1**

```
uv run pharma-lab metrics select --top-k 20 --metric hit@20 --secondary hit@5 \
  --exclude-group conversational \
  --config bm25=bm25-v3-k20 \
  --config dense-gemma300m=dense-gemma300m-v3-k20 \
  --config dense-bge-m3=dense-bge-m3-v3-k20 \
  --config dense-qwen06b=dense-qwen06b-v3-k20 \
  --config dense-qwen4b=dense-qwen4b-v3-k20 \
  --config hybrid-qwen4b=hybrid-qwen4b-v3-p50-k20-rrf2 \
  --config dense-qwen8b=dense-qwen8b-v3-k20 \
  --config hybrid-qwen8b=hybrid-qwen8b-v3-p50-k20-rrf2
```

- [ ] **Step 4: Giai đoạn 2 tạm (chưa có 8B), chỉ khi Step 3 chọn hybrid-qwen8b**

```
uv run pharma-lab metrics select --top-k 20 --metric hit@5 --secondary mrr@10 \
  --exclude-group conversational \
  --config bge-m3=hybrid-qwen8b-v3-p50-k20-rrf2@bge-reranker-v2-m3:q8_0 \
  --config qwen-0.6b=hybrid-qwen8b-v3-p50-k20-rrf2@qwen3-reranker:0.6b-q8_0 \
  --config qwen-4b=hybrid-qwen8b-v3-p50-k20-rrf2@qwen3-reranker:4b-q8_0
```

Nếu Step 3 chọn cấu hình khác: không chạy Step 4; ghi rằng giai đoạn 2 cần rerank cả bốn reranker trên cấu hình đó (plan Kaggle sau).

- [ ] **Step 5: Ghi kết quả vào spec**: bảng hai giai đoạn (means, Δ, KTC, p Holm, tied, chosen, reason), ghi rõ giai đoạn 2 là tạm cho tới khi có 8B; cập nhật bảng tiến độ và "Việc đang mở": ba run e2e (`e2e-v2-qwen9b`, `e2e-v2-qwen9b-c1-c1`, `e2e-v2-gemini`) bị bỏ, golden e2e dựng lại theo plan `2026-10-25-golden-e2e-v4.md`; danh sách run Kaggle còn thiếu: rerank 8B trên cấu hình thắng, D1, D2 `plain`, `rrf60`, D5 Q0–Q6, D7, D4.
- [ ] **Step 6: Commit dữ liệu và spec** `chore(pharma-lab): judgments for every group; retrieval reports rescored; stage results`
