# Đánh giá retrieval và end-to-end: benchmark, golden, luật chọn và ablation

Ngày: 2026-11-15. Trạng thái: hiện hành, mô tả mã và dữ liệu của nhánh `v2.0.0` (commit `9732e8e`).
Riêng mục 3.7 (D5) là thiết kế chưa duyệt, chưa có mã.

Spec này gom mười bản spec và plan về đánh giá (danh sách ở mục 6) và phần hạ tầng đo của plan pha 0
paper v2. Nó trả lời ba câu: đánh giá đang dùng bộ dữ liệu nào, đo bằng công cụ nào của `pharma-lab`,
và lượt chạy nào đã có số. Việc còn dở nằm trong plan
`docs/superpowers/plans/2026-11-15-evaluation-remaining.md`.

## 1. Mục tiêu và phạm vi

- Một benchmark retrieval duy nhất, đúng 10.000 câu, chấm hoàn toàn bằng retrieval (không gọi LLM).
- Một bộ golden end-to-end 1.000 câu. Mỗi câu có đáp án là một dòng của benchmark. Mọi lời gọi LLM
  khi đánh giá (chạy agent, judge, viết lại câu hỏi) chỉ chạy trên golden.
- Độ khó được định nghĩa từ cách dựng câu và từ corpus, không bao giờ từ kết quả của một hệ thống.
- Mọi so sánh dùng chung một bộ thống kê: bootstrap, sign-flip ghép cặp, Holm.
- Cặp retrieval của agent được chọn bằng một luật viết thành mã (`metrics select`), không chọn tay.
- Mọi lượt chạy có identity (`run.json`) ghi đủ bộ dữ liệu, model và cấu hình. Đổi identity thì phải
  đặt tên run mới.

Phạm vi là `pharma-lab/` (gói `pharma_lab.evaluation`, `pharma_lab.e2e`, các lệnh `evaluation`,
`retrieve`, `rerank`, `metrics`, `e2e`), dữ liệu ở `pharma-lab/data/evaluation/`, và ba guide
`pharma-lab/docs/guides/{evaluation,e2e-evaluation,e2e-golden-authoring}.md`.

## 2. Bộ dữ liệu đang dùng

| Bộ | Phiên bản và định danh | Cỡ | Nơi lưu |
| --- | --- | --- | --- |
| Benchmark retrieval | v3, `data/evaluation/gold/section_retrieval_eval.jsonl`, sha256 `9c6e4de6…`, đóng băng 2026-10-18 | 10.000 dòng, 9.970 có gold (30 dòng `safety` không có) | archive Kaggle (`pharma-lab data pull`) |
| Relevance judgments | `section_retrieval_eval.judgments.jsonl`, `rules_version: 2` | áp cho mọi nhóm | archive; manifest ghi sha của benchmark |
| Tập chọn retrieval | benchmark trừ `conversational` và `safety` | 8.470 câu | lọc khi chạy `metrics select --exclude-group` |
| Golden e2e | v4, `data/evaluation/e2e/golden_e2e.jsonl`, sha256 `1dae2820…`, schema `e2e-golden-v3`, dựng 2026-10-26 | 1.000 câu | manifest trong git; file golden và thư mục `authoring/` chỉ có ở máy (chưa `data push`) |
| Tập giữ lại cho judge | `data/evaluation/calibration/judge_set.jsonl` | 300 câu (265 đủ bằng chứng, 35 thiếu) | git |
| Tập giữ lại cho guard | `data/evaluation/calibration/guard_set.jsonl`, `guard_review.jsonl` | 300 lượt (150 tấn công, 150 không) | git |

Phiên bản cũ không còn dùng cho số liệu mới: benchmark 10.000 câu sinh bằng luật (run `-v2-` và
`-k30`), golden v1 500 câu (sha `8bdf0bee…`, vẫn là nguồn số của paper v1 và bản camera-ready,
run `e2e-gemini`, `e2e-qwen35-9b` còn trong git), golden v2 và v3 500 câu. Xem mục 5.

## 3. Thiết kế hiện hành

### 3.1 Benchmark retrieval 10.000 câu

Dựng bằng `pharma-lab evaluation build` (sinh câu theo luật từ bundle) rồi `pharma-lab evaluation
assemble` (`pharma_lab/e2e/benchmark_extension.py`). `assemble` làm ba việc:

1. **Sửa câu sinh bằng luật** (`benchmark_repair.py`, `repair_rows`): bỏ câu dán đoạn văn và câu lộ
   tên mục; trỏ câu chung chung ("X là thuốc gì") về `thong-tin-chung`, câu tác dụng phụ về
   `tac-dung-khong-mong-muon-adr`, bỏ câu khi tài liệu không có mục đích; câu hỏi cả thai kỳ và cho
   con bú nhận cả hai mục và `answer_mode = multi_required`; tên sản phẩm bị cắt giữa chừng được thay
   bằng `brand_name`. Câu không đổi giữ `query_id` để cache embedding và điểm rerank dùng lại.
2. **Thêm các nhóm sinh riêng** (`golden_generate.py`, `conversational.py`): `colloquial` (alias dân
   dã; alias trỏ nhiều sản phẩm thành `any_acceptable`), `glossary` (cụm lời thường cho thuật ngữ
   viết tắt, mỗi thuật ngữ tối đa 25% nhóm), `conversational` (1.500 câu, tám hiện tượng, đặt tên
   `conv-<hiện tượng>-<câu cha>`, có `turns` và `parent_query_id`), `multi_hop` (300 câu, ba loại
   `two_drug`, `brand_to_ingredient`, `three_intent`), `safety` (30 lượt không có gold).
3. **Ghi lát cắt** (`benchmark_slices.py`, `SliceIndex`) trên từng dòng sau khi sửa:
   `header_dependent`, `name_variant`, `rare_term`, `sibling_products`, `multi_chunk`. Định nghĩa
   trong docstring của module; mỗi lát là thuộc tính của câu và corpus.

Cỡ nhóm có gold trên benchmark `9c6e4de6…`: formulary 3.444, leaflet 1.721, conversational 1.500,
structured 828, leaflet_short 495, multi_intent 493, noisy 492, glossary 354, colloquial 343,
multi_hop 300.

Benchmark chỉ được đóng băng sau khi audit lấy mẫu 25 câu mỗi nhóm có tỉ lệ lỗi dưới 5%. Bản
`9c6e4de6…` qua bốn vòng audit đầy đủ và hai vòng riêng cho leaflet (sổ audit ở Phụ lục A §6.1 của
spec paper v2).

### 3.2 Chấm retrieval

- **Nhãn.** Gold là `expected_section_ids`. Relevance judgments (`relevance_judgments.py`, luật phiên
  bản 2) chấp nhận thêm chunk tờ hướng dẫn có đúng các hoạt chất của chuyên luận và nằm ở mục trả lời
  cùng ý hỏi, cho mọi câu có gold là mục Dược thư, ở mọi nhóm. Đổi luật thì chạy `evaluation
  judgments` rồi `metrics --force`; candidates và cache giữ nguyên.
- **Chỉ số** (`retrieval_metrics.py`): Hit@k với k trong {3, 5, 10} cộng độ sâu của run; nDCG@k và
  MRR@k với k = 5 (số đoạn agent đọc mỗi vòng) và 10; với câu `multi_required`, Recall@k và
  Complete-evidence rate@k. Gain nhị phân; mỗi đơn vị bằng chứng (một section của câu
  `multi_required`, hoặc một đơn vị "answer") chỉ được tính một lần, tại chunk đầu tiên thoả nó; một
  chunk chứa nhiều section gold thoả nhiều đơn vị.
- **Báo cáo** (`metrics_service.py`, `metrics_artifacts.py`): `reports/baseline/top<k>/` và
  `reports/rerank/<model>/top<k>/`, mỗi report có bảng theo `eval_group` và theo lát (trong lát và
  `<lát>:outside`). `--gold-only` bỏ judgments, ghi vào `top<k>-gold/`; dùng cho so sánh mà
  judgments không áp được (D7).
- **Môi trường.** Stack riêng `docker compose -p vipharmind-eval` (Postgres 5434, Qdrant 6335). Mỗi
  collection Qdrant của stack này chỉ chứa corpus `formulary`; biến thể corpus (D2, D7) chạy trên stack
  tạm riêng. Lý do ở mục 5 (sự cố 2026-10-26).
- **Tên run**: `<retriever>-<embedding>-v3-[<biến thể>-]p50-k20-rrf<k>`, hoặc `dense-<embedding>-v3-k20`,
  `bm25-v3-k20`.

### 3.3 Thống kê dùng chung

`pharma_lab/evaluation/statistics.py` phục vụ cả retrieval lẫn e2e: `bootstrap_mean` (percentile,
10.000 lần, seed 0, chia khối 500 hàng để không cấp phát một ma trận lớn), `paired_test` (sign-flip
ghép cặp kèm KTC), `holm`, `weighted_bootstrap_mean`. Tỉ lệ dùng KTC Wilson. Mỗi bảng của bài là một
họ Holm.

### 3.4 Luật chọn cặp retrieval của agent

Mã: `pharma_lab/evaluation/config_selection.py`, lệnh `pharma-lab metrics select --config
LABEL=RUN[@MODEL] ...` (liệt kê từ rẻ tới đắt).

- Giai đoạn 1 (chưa rerank): chính Hit@20, phụ Hit@5. Giai đoạn 2 (rerank, chỉ trên cấu hình thắng
  giai đoạn 1): chính Hit@5, phụ MRR@10.
- Cấu hình dẫn đầu thắng rõ một cấu hình khác khi KTC 95% bootstrap ghép cặp của chênh lệch nằm trên 0
  **và** p sign-flip sau Holm dưới 0,05. Cấu hình không bị thắng rõ thì hoà; còn hoà thì xét chỉ số
  phụ trên các cấu hình hoà; vẫn hoà thì chọn cấu hình rẻ nhất.
- Tập câu là 8.470 câu của tập chọn. Agent luôn viết lại câu hỏi trước khi tìm, nên câu hội thoại để
  nguyên lượt cuối không phản ánh truy vấn agent gửi; nhóm đó đo riêng ở D5.
- Lệnh từ chối report chấm trên file evaluation khác, report chấm bằng judgments cũ (gợi ý `metrics
  --force`), tên nhóm loại trừ không có trong benchmark, và tập `query_id` lệch nhau.
- Thứ tự chi phí: BM25; dense theo số tham số embedding (gemma-300m, bge-m3, qwen 0,6B, 4B, 8B);
  hybrid ngay sau dense cùng embedding; reranker bge-v2-m3, qwen 0,6B, 4B, 8B.

Kết quả ngày 2026-10-26: giai đoạn 1 chọn hybrid Qwen3-Embedding-4B (hoà hybrid 8B ở cả hai chỉ số,
chọn bản rẻ hơn); giai đoạn 2 chọn Qwen3-Reranker-4B (hoà 8B ở cả hai chỉ số, thắng rõ 0,6B và bge).
**Cặp retrieval của agent:** hybrid RRF k=2, prefetch 50, giữ 20, Qwen3-Embedding-4B, rerank
Qwen3-Reranker-4B giữ 5. Bảng số đầy đủ: spec paper v2 §3.4 và
`docs/research/paper-v2/08-phase-d-results.md`.

### 3.5 Ablation retrieval và lượt đã chạy

Mọi ablation so với cấu hình đã chọn ở 3.4, không so với một model định sẵn: bảng retrieval trả lời
"mỗi lớp của cấu hình agent đóng góp bao nhiêu". Các run dưới đây có trong
`pharma-lab/data/evaluation/runs/` trên `v2.0.0`, tất cả trên benchmark `9c6e4de6…`, judgments phiên
bản 2.

| Mã | Câu hỏi | Run | Trạng thái |
| --- | --- | --- | --- |
| S1 | Chọn retriever | `bm25-v3-k20`, `dense-{gemma300m,bge-m3,qwen06b,qwen4b,qwen8b}-v3-k20`, `hybrid-qwen{4b,8b}-v3-p50-k20-rrf2` | xong |
| S2 | Chọn reranker | bốn reranker trên `hybrid-qwen4b-v3-p50-k20-rrf2` và trên `hybrid-qwen8b-v3-p50-k20-rrf2` | xong |
| D1 | Sao phải hybrid | `dense-qwen4b-v3-k20` + rerank 4B so với hybrid + rerank 4B | xong |
| D2 | Enrichment giúp gì | `hybrid-qwen4b-v3-plain-p50-k20-rrf2` (bundle `formulary-plain`) | có baseline; **chưa có rerank 4B** trong repo |
| rrf60 | RRF k=60 so với k=2 | `hybrid-qwen4b-v3-p50-k20-rrf60`, `hybrid-qwen8b-v3-p50-k20-rrf60` | xong (mức retrieval; D6 e2e thuộc ma trận paper) |
| D7 | Vì sao chunk khoảng 1.024 token | `hybrid-qwen4b-v3-sections-p50-k20-rrf2` + rerank 4B, chấm `--gold-only` | xong |
| D4 | Chi phí encode embedding trên T4 | không có | chưa thiết kế đo |
| D5 | Viết lại câu hỏi hội thoại | không có | thiết kế nháp (mục 3.7), chưa có mã |

`metrics select` chưa đọc được report `--gold-only`, nên kiểm định D7 hiện tính bằng script
`docs/research/paper-v2/08-phase-d-tables.py`.

### 3.6 Golden e2e v4 (1.000 câu)

Hạn ngạch ở `pharma_lab/e2e/golden.py`; tổng các hạn ngạch là 1.000.

| Tầng | Cỡ | Nguồn |
| --- | --- | --- |
| Tự nhiên (`answerable`) | 520 | dòng benchmark các nhóm luật theo tỉ lệ nhóm, tối thiểu 30: formulary 212, leaflet 106, structured 51, leaflet_short 31, multi_intent 30, noisy 30, glossary 30, colloquial 30 |
| Lát (`answerable`, tag lát) | 90 | 30 mỗi lát `header_dependent`, `name_variant`, `sibling_products`, ngẫu nhiên trong lát; câu giữ nhóm nguồn |
| `multi_hop` | 200 | nhóm `multi_hop` của benchmark: two_drug 70, brand_to_ingredient 65, three_intent 65 |
| `multi_turn` | 160 | nhóm `conversational`, 20 mỗi hiện tượng |
| safety | 30 | `unanswerable`, `out_of_scope`, `injection` mỗi loại 10 |

- **Item.** `GoldenItem` gồm `turns`, `expected_behavior` (`grounded`, `abstain`, `redirect`,
  `blocked`), `gold_section_ids`, `reference.answer`, `reference.key_facts` (mỗi fact có
  `evidence_quote` và `section_id`), `absent_terms` (chỉ `unanswerable`), `source_query_id`,
  `eval_group`, `tags`.
- **Ràng buộc** (`golden check`, `golden build`): `evidence_quote` là chuỗi con của text section sau khi
  chuẩn hoá khoảng trắng; `section_id` thuộc `gold_section_ids`; đủ hạn ngạch; mọi item answerable,
  multi_hop, multi_turn có `source_query_id` là một dòng của benchmark, và item multi_hop phải trỏ vào
  dòng nhóm `multi_hop` cùng loại.
- **Luồng soạn**: `golden {answerable,multi-hop,multi-turn}-candidates` → `golden draft --family ...`
  (nháp bằng `gemini-3.1-flash-lite`) → model khác hãng audit từng lô theo rubric, sửa, lưu
  `.authored.jsonl` → `golden check` → `golden build`. Build giữ bản cũ thành
  `golden_e2e.<sha256>.jsonl`; `e2e run`/`e2e judge` so hai bản theo item và chỉ chạy lại hoặc chấm
  lại item đã đổi.
- **Vòng duyệt của golden v4** (đúng như bài phải ghi): Claude Sonnet audit từng lô nháp, rồi Claude
  Opus duyệt lại cả 1.000 câu (908 giữ, 92 sửa, 0 loại; tỉ lệ sửa natural 7,5%, slice 3,3%, multi_hop
  11,5%, multi_turn 16,9%, safety 0%); dược sĩ chỉ xem lướt. Không gọi đây là "dược sĩ duyệt".
  Lệnh `golden pharmacist-pack` và `golden pharmacist-score` (`golden_audit.py`) có sẵn cho vòng duyệt
  dược sĩ đầy đủ nhưng chưa dùng.

### 3.7 D5: chiến lược truy vấn cho câu hội thoại (thiết kế nháp, chưa duyệt)

Trên 1.500 câu `conversational`, tìm bằng câu cuối để nguyên chỉ đạt khoảng 22% Hit@5 với cặp agent.
D5 đo viết lại câu hỏi giúp bao nhiêu và tốn bao nhiêu. Giả thuyết (An đồng ý 2026-10-26, số đo quyết
định): một lượt viết lại bằng LLM rẻ, đúng bước rephrase của backend, kéo Hit@5 lên sát mức oracle;
cách đắt kiểu CHIQ không hơn đáng kể.

| Mã | Truy vấn đưa vào retriever | Lượt gọi LLM |
| --- | --- | --- |
| Q0 | câu cuối để nguyên | 0 |
| Q1 | ghép cả lịch sử hội thoại | 0 |
| Q2-gemini | viết lại bằng `gemini-3.1-flash-lite` với `REPHRASE_SYSTEM` và `rephrase_messages` của backend | 1 |
| Q2-qwen | như Q2 bằng Qwen3.5-9B, chạy trên Kaggle | 1 |
| Q3-gemini | CHIQ đầy đủ rồi viết lại; prompt tiếng Việt mới trong pharma-lab | 5–6 |
| Q5 | hợp ứng viên Q0 và Q2-gemini bằng RRF trước rerank | 1 |
| Q6 | oracle: câu cha một lượt (`parent_query_id`) | 0 |

Cách dựng đề xuất: mỗi chiến lược sinh một file evaluation biến thể (giữ 1.500 dòng, `query_id` và
gold; chỉ thay `query`), dựng judgments cho file đó, rồi chạy chuỗi có sẵn `embed queries` → `retrieve`
→ `rerank` 4B → `metrics`. Q5 cần bước mới hợp hai artifact candidates. `metrics select` cần nhận các
file evaluation chỉ khác nhau ở `query`. Ghi lượt gọi, token và giây mỗi lần viết lại. Cột báo cáo:
Hit@5, nDCG@5, KTC, p sign-flip sau Holm (họ "so với Q0" và họ "so với Q2-gemini"), chi phí; bảng phụ
theo tám hiện tượng. Ngoài phạm vi: đo e2e các chiến lược (đã có `no-rephrase` trên golden), huấn
luyện rewriter.

### 3.8 Harness end-to-end

Gói `pharma_lab.e2e` gọi backend trong cùng tiến trình, không qua HTTP, không ghi Postgres của app.

- **Cấu hình** (`configs.py`, `E2EConfig`): `full`, `one-step`, `one-step-history`, `no-judge-refine`,
  `no-rephrase`, `no-rerank`, `no-guard`, `no-guard-no-rerank`, `bm25`, `dense`, `hybrid-k60`,
  `closed-book`, `react`. Công tắc pipeline đi qua `PipelineOptions` của backend (rephrase,
  judge_refine, guard, history_query, refine_mode, refine_threshold); production luôn chạy mặc định,
  không có biến môi trường nào bật công tắc. Biến thể retriever và "không rerank" đổi settings trong bộ
  nhớ của harness. `--pipeline-option key=value` từ chối khoá lạ trước khi chạy item nào.
- **Lệnh**: `e2e run` (local hoặc `--backend kaggle`), `e2e judge`, `e2e calibration
  {export,refresh,score}`, `e2e report [--latency-run <run>-c1]`, `e2e compare`, `e2e citations`,
  `e2e rejudge-citations`, `e2e status`. Chạy trên Kaggle (shard, nối lại, proxy trong kernel) thuộc
  spec `kaggle-runs`.
- **Dữ liệu một run**: `data/evaluation/e2e/runs/<run>/<config>/` gồm `run.json` (identity: sha golden,
  release, model và reasoning theo role, pipeline, retrieval, concurrency, git commit), `answers.jsonl`
  (câu trả lời, `context_text`, trích dẫn quy về `section_id`, token và reasoning token theo role, giây
  theo bước `steps`, `retrieval_seconds`, `rerank_seconds`), `judgments.jsonl`, `judge.json`. File
  jsonl chỉ ghi nối thêm, khoá theo `item_id`; chạy lại cùng lệnh thì nối tiếp; `--retry-errors` chỉ
  chạy lại câu lỗi.
- **Chấm**: judge có output cấu trúc (`judging/structured.py`) cộng RAGAS (`judging/ragas_scorer.py`)
  cộng chỉ số tính bằng mã (`judging/code_metrics.py`). Metric chính: truthfulness và các lớp
  perfect/acceptable/missing/incorrect (CRAG), nugget recall, severe harm rate, faithfulness, citation
  recall (ALCE), response rate, negative rejection, redirect accuracy, injection defence; phụ: answer
  relevancy, factual correctness. Mặc định trong mã: `JUDGE_MODEL = "gpt-5-mini"`,
  `DEFAULT_JUDGE_REASONING = "none"`; các run dùng `--judge-model gemini-3.1-flash-lite`. Đổi judge
  hoặc reasoning cần `--force`.
- **Hiệu chuẩn judge**: `calibration export` rút 50 câu mỗi cấu hình, che danh tính, xáo bằng seed;
  người chấm mù ghi `grades.jsonl`; `calibration score` tính percent agreement, Cohen κ, Gwet AC1,
  Spearman ρ kèm KTC bootstrap (ngưỡng tin cậy 0,6) và ước lượng PPI.
- **Chi phí và độ trễ** (hạ tầng đo của pha 0): `pricing.py` ghi giá niêm yết theo triệu token kèm
  nguồn và ngày; model không có giá làm `report` dừng (`UnpricedModel`). Report có `cost.csv|tex`
  (USD mỗi lượt, mỗi 1.000 lượt, cost of pass, giây theo bước, p50/p95). Số giây trong bài lấy từ run
  concurrency 1 cùng máy và endpoint (`--latency-run`); cấu hình thiếu trong run đó thì dừng, không
  lấy số của run chất lượng. `e2e compare` so một cấu hình giữa hai run trên item chung (từ chối khi
  không có item chung, ghi cột `same_judge`).
- **Report** (`report.py`): `main`, `ablation` (Δ so với `full`, sign-flip, Holm), `by_group` và
  `group_ablation` theo `category`, `eval_group`, tầng golden (`natural`, `slice`, `multi_hop`,
  `multi_turn`, `natural_and_multi_hop`) và loại multi-hop, `reweighted.csv` (tầng tự nhiên tái trọng
  số về tỉ lệ nhóm của benchmark), `calibration`, `cost`, `errors.md`, `provenance.json`. Lệnh dừng khi
  một cấu hình chạy trên golden khác `--golden` hiện tại.
- **Tập giữ lại** (`decision-set build|guard-draft|score`): tập judge 300 câu benchmark ngoài golden,
  nhãn `sufficient` tính từ gold trên top 5 của cặp agent; tập guard 300 lượt nháp theo template rồi
  duyệt. Dùng để chỉnh ngưỡng của decision model, không bao giờ chỉnh trên golden. Cách dùng ngưỡng
  thuộc spec `backend-agent-api` và ma trận của paper.

Trên `v2.0.0` chưa có run e2e nào trên golden v4. Các run v2 trước đó (`e2e-v2-qwen9b`,
`e2e-v2-gemini`…) bị bỏ khi golden đổi và nằm ở `pharma-lab/data/work/retired-e2e-runs/` (ngoài git).

## 4. Ngoài phạm vi

- Ma trận thí nghiệm của paper v2 (A, B, C, D6 e2e, E1–E5, H), ngân sách quota và các run A1, A2
  (Task 11 của plan pha 0): spec `soict-paper`.
- Chạy trên Kaggle (shard, quota, proxy trong kernel, `e2e run --backend kaggle`): spec `kaggle-runs`.
- Corpus, bundle, chunk và rerank serving: spec `corpus-data-pipeline`.
- `PipelineOptions`, decision model Jev, graph ReAct trong backend: spec `backend-agent-api`.
- Quy tắc tầng của `pharma-lab` (import-linter, vị trí test): spec `architecture-rules`.

## 5. Lịch sử quyết định

| Ngày | Quyết định | Thay cho | Lý do | Nguồn |
| --- | --- | --- | --- | --- |
| 2026-09-15 | Đề xuất metric theo facet (Intent Recall@K, All Intents Covered@K) cho câu `multi_intent` | `Multi-all-hit@K` theo đúng section Dược thư | Chunk tờ hướng dẫn phủ đủ ý vẫn bị tính sai. Không được cài: hôm sau thay bằng relevance judgments (`37e671e`), đơn giản hơn và áp được cho mọi nhóm | `f9fc933:docs/superpowers/specs/2026-09-15-facet-aware-retrieval-evaluation-design.md` |
| 2026-09-16 | Relevance judgments chấp nhận chunk leaflet cùng hoạt chất, cùng ý hỏi (chỉ nhóm formulary và multi_intent) | Chỉ section gold | Cùng lý do trên | `37e671e` |
| 2026-09-16 | Golden e2e v1: 500 câu (420 answerable, 50 multi_turn, 30 safety), năm cấu hình, RAGAS + judge cấu trúc `gpt-5-mini` reasoning medium, hiệu chuẩn mù 100 câu | Chưa có đánh giá e2e | Paper v1 cần phần e2e; harness trong `pharma_lab.e2e`, backend chỉ thêm `PipelineOptions` | `f9fc933:docs/superpowers/specs/2026-09-16-e2e-golden-evaluation-design.md`, `f9fc933:docs/superpowers/plans/2026-09-16-e2e-golden-evaluation.md` |
| 2026-09-22 | Rà soát golden v1, sửa 57 item theo tiêu chí cố định | Bản golden v1 đầu | Câu không nêu đối tượng, slug lọt vào câu hỏi, ý chính ngoài đoạn trích | `9732e8e:pharma-lab/docs/guides/e2e-evaluation.md` (mục 2) |
| 2026-10-15 | Golden v2: thêm nhóm `multi_hop` 150 câu, 270 answerable gồm probe rerank, lexical, semantic | Golden v1 | Paper v2 cần tập "cần tra nhiều lượt". Bị thay vì probe và câu "trượt vòng 1" được chọn theo kết quả hệ thống, nên thắng theo định nghĩa | `29a4c54` |
| 2026-10-16 | Judge v2 chấm ở reasoning `none`; bỏ phép thử `none` trên nhãn dược sĩ v1 (Task 10 pha 0) | Reasoning `medium` | Hiệu chuẩn dược sĩ trên chính run v2 đo độ khớp; chấm lại ở `medium` nếu độ khớp kém | `9732e8e:docs/superpowers/plans/2026-10-16-paper-v2-phase-0-measurement.md` (Task 10) |
| 2026-10-16 | Hạ tầng đo pha 0: reasoning token, giây theo bước, bảng giá, `cost`, `e2e compare`, `--latency-run`, công tắc `guard` và biến thể retriever từ harness | Chỉ có token và tổng latency | Paper v2 báo chất lượng cùng giây và USD mỗi lượt. Task 8b (embed-server qua tunnel) bị thay bởi `e2e run --backend kaggle` | cùng plan, Task 1–9 |
| 2026-10-18 | Benchmark v3: đúng 10.000 câu, sửa luật sinh câu, nhóm sinh riêng, lát cắt theo cách dựng, golden chỉ là các dòng của benchmark; LLM chỉ chạy trên golden | Benchmark 10.000 câu sinh bằng luật (run `-v2-`), trong đó hàng trăm câu sai do luật sinh (bảng chẩn đoán §1.1 của bản thiết kế) | Câu sai làm nhiễu mọi cấu hình như nhau và che chênh lệch giữa các tầng; "một benchmark xuyên suốt" (quyết định của An) | `f582acc:docs/superpowers/specs/2026-10-18-eval-data-v3-design.md`, `9732e8e:docs/superpowers/plans/2026-10-18-eval-data-v3.md`, `9732e8e:docs/superpowers/plans/2026-10-18-unified-benchmark.md` |
| 2026-10-18 | Lát `name_variant` | `low_overlap` (trùng từ với mục gold dưới 35%) | Mọi ngưỡng trùng từ tách lớp dense dưới 2 lần; tên thuốc tách 3,3 lần | `f582acc:docs/superpowers/specs/2026-10-18-eval-data-v3-design.md` §3.4 |
| 2026-10-19 | Golden v3 (sha `9e2769ca…`, 500 câu): tầng lát cắt thay probe, multi-turn lấy từ nhóm conversational | Golden v2 | Bỏ chọn theo kết quả; mọi item là dòng benchmark | `9732e8e:docs/superpowers/plans/2026-10-18-eval-data-v3.md` (Task 5) |
| 2026-10-25 | Luật chọn retrieval viết lại: bootstrap 10.000 lần + sign-flip Holm, bỏ vế "không tụt quá 1 điểm ở nhóm hay lát nào", loại nhóm `conversational`, judgments cho mọi nhóm (luật phiên bản 2) | Luật 2026-10-18 (bootstrap 1.000 lần, không kiểm định, chấm cả nhóm hội thoại, judgments hai nhóm) | Vế 1 điểm không xét cỡ mẫu; judgments hai nhóm chấm cùng một câu đúng khác nhau theo nhóm. Đổi sau khi đã thấy số giai đoạn 1, bài nêu cả hai bản | `9732e8e:docs/superpowers/plans/2026-10-25-retrieval-eval-standardization.md`, `41b8958`, `2a5820d` |
| 2026-10-25 | `statistics.py` chuyển từ `e2e` xuống `evaluation`; xoá 26 run chấm trên gold đã thay | Hai bộ thống kê; run `-v2-`, `-k30` | Retrieval và e2e dùng chung một thống kê; chỉ giữ run trên benchmark đã chốt | `a477569`, `cc4ee4d` |
| 2026-10-25 | Golden v4: 1.000 câu theo Phụ lục C.2; multi_hop lấy từ nhóm `multi_hop` của benchmark; report theo tầng và tái trọng số | Golden v3 500 câu, tầng `retrieval_miss` và `noisy_retry` | Phụ lục C chốt cỡ theo độ nhạy (C.3); bỏ hẳn câu chọn theo lỗi của hybrid + rerank | `9732e8e:docs/superpowers/plans/2026-10-25-golden-e2e-v4.md`, `1998e3a`, `c91cc20`, `dbbb8ca` |
| 2026-10-26 | Golden v4 duyệt bằng hai vòng model (Sonnet audit, Opus duyệt lại toàn bộ), dược sĩ xem lướt | Dược sĩ duyệt toàn bộ 1.000 câu (quyết định 2026-10-25, Task 5 Step 6 của plan golden v4) | Nguồn không ghi lý do (xem câu hỏi mở trong ghi chú); bài báo phải ghi đúng cách duyệt | `fe70723`, `1a95de9`; spec paper v2 Phụ lục C.2 |
| 2026-10-26 | Giai đoạn 1 chạy lại trên Qdrant sạch chọn hybrid Qwen3-Embedding-4B; giai đoạn 2 chọn Qwen3-Reranker-4B; mọi ablation so với cặp này | Kết quả 2026-10-25 chọn hybrid Qwen3-Embedding-8B | Collection 4B còn 51.000 point của hai corpus thử nghiệm: HNSW có lọc mất recall, IDF BM25 sai. Từ đó mỗi collection chỉ chứa `formulary` | `e9d214f`, `c18334e`, `9732e8e:docs/superpowers/plans/2026-10-26-retrieval-ablation-runs.md` |
| 2026-10-26 | Bỏ các run e2e v2 (`e2e-v2-qwen9b`, `e2e-v2-qwen9b-c1-c1`, `e2e-v2-gemini`) | Run e2e trên golden v3 | Golden đổi; run e2e chỉ bắt đầu khi S1, S2 chốt và golden v4 build xong | `730b9e4` |
| 2026-10-26 | Thiết kế nháp D5 (Q0, Q1, Q2-gemini, Q2-qwen, Q3-gemini, Q5, Q6); rewriter Qwen chạy trên Kaggle, OpenRouter chỉ cho Jev | Q1b, Q3a, Q3b, Q4 bị bỏ | Biến thể không thêm kết luận | `9732e8e:docs/superpowers/specs/2026-10-26-d5-conversational-rewrite-design.md`, `1b73f5b` |

## 6. Nguồn đã gom

Spec: `2026-09-15-facet-aware-retrieval-evaluation-design`, `2026-09-16-e2e-golden-evaluation-design`,
`2026-10-18-eval-data-v3-design`, `2026-10-26-d5-conversational-rewrite-design`. Plan:
`2026-09-16-e2e-golden-evaluation`, `2026-10-18-eval-data-v3`, `2026-10-18-unified-benchmark`,
`2026-10-25-golden-e2e-v4`, `2026-10-25-retrieval-eval-standardization`,
`2026-10-26-retrieval-ablation-runs`, và phần đo (Task 1–10) của `2026-10-16-paper-v2-phase-0-measurement`.
Đường dẫn và commit ở mục 5.

## 7. Liên kết

- `2026-11-15-soict-paper-design.md`: paper v1, v2, camera-ready; ma trận thí nghiệm dùng các bộ dữ liệu
  và công cụ ở đây.
- `2026-11-15-kaggle-runs-design.md`: chạy embed, rerank, e2e trên Kaggle.
- `2026-11-15-corpus-data-pipeline-design.md`: bundle `formulary`, `formulary-plain`,
  `formulary-sections`, chunk là đơn vị đọc.
- `2026-11-15-backend-agent-api-design.md`: pipeline agent, `PipelineOptions`, decision model.
- `2026-11-15-architecture-rules-design.md`: tầng của `pharma-lab`.
- Plan còn mở: `docs/superpowers/plans/2026-11-15-evaluation-remaining.md`.
