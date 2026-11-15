# Spec: Bài báo SoICT 2026 (paper v1, camera-ready) và bài thuyết trình

Ngày: 2026-11-15. Nguồn sự thật: nhánh `v2.0.0` (`9732e8e`, sau khi gộp `camera-ready`). File này thay
cho mười spec và plan cũ của mảng bài báo (xem §6). Mọi `sha:path` ở §6 đọc lại được bằng
`git show <sha>:<path>`.

## 1. Mục tiêu và phạm vi

Một chỗ duy nhất trả lời hai câu hỏi: bài nào đang ở trạng thái nào, và nguồn của mỗi bài nằm ở đâu.
Bài báo của repo này dừng ở bản camera-ready (quyết định 2026-11-15); paper v2 không làm tiếp ở đây.
Phạm vi gồm:

- **Paper v1**: bài nộp SoICT 2026, paper 1360, *Agentic Retrieval-Augmented Generation for
  Vietnamese Pharmaceutical Documents* (Van-An Doan, Tuan Quoc Nguyen), được nhận trình bày oral.
- **Camera-ready** của paper v1 (tag `v1.1.0`).
- **Bài thuyết trình** 15 phút tại SoICT 2026 (4–5/12/2026, TP Hồ Chí Minh).
- **Paper v2** chỉ ở mức lịch sử (§3.4): đã dừng, phần mã đã làm vẫn còn trong repo.
- Mã phục vụ bài: `docs/report/`, `docs/presentation/`.

Thiết kế agent (graph, decision model, ReAct) thuộc spec
[`backend-agent-api`](2026-11-15-backend-agent-api-design.md). Benchmark, golden, luật chọn
retrieval, thống kê và các ablation retrieval thuộc spec
[`evaluation`](2026-11-15-evaluation-design.md). Cách chạy trên Kaggle thuộc spec
[`kaggle-runs`](2026-11-15-kaggle-runs-design.md). Chunker và corpus thuộc spec
[`corpus-data-pipeline`](2026-11-15-corpus-data-pipeline-design.md).

## 2. Trạng thái (2026-11-15)

| Sản phẩm | Trạng thái | Mốc git | Còn lại |
| --- | --- | --- | --- |
| Paper v1 (bản nộp) | Đã nộp, được nhận oral | tag `v1.0.0` (`93c5863`, 2026-10-13, đóng băng sau khi nộp) | Không |
| Camera-ready | Đã nộp trước hạn 30/10/2026 | tag `v1.1.0` (commit `a9954db`, 2026-10-22) | Không về nội dung. Nguồn ở `docs/report/` đã đổi sau tag (§3.1), xem câu hỏi mở 1 |
| Thuyết trình | Deck xong, chưa trình bày | `dcca0d1` (2026-11-08) | Tập dượt, trình bày 4–5/12, đính deck vào GitHub Release, rồi dọn nhánh `camera-ready` |
| Paper v2 | Dừng, không làm tiếp trong repo này (2026-11-15) | `1b73f5b` là commit v2 cuối | Không. Mã pha 0–2 còn trong repo (§3.4) |

Từ 2026-10-26 đến 2026-11-15 nhánh `v2.0.0` không có commit nào của paper v2; mọi commit là của
camera-ready và thuyết trình, gộp vào bằng `9732e8e`.

## 3. Thiết kế hiện hành

### 3.1 Nguồn bài và cách build (`docs/report/`)

- `docs/report/` là nguồn duy nhất của bài trong repo: **bản camera-ready của paper v1**. Bản nháp
  `drafts/methods-v2.tex` của paper v2 chưa từng được `\input` và đã lỗi thời (§3.4). Không giữ bản
  sao nguồn nào khác.
- File chính `SoICT2026_Agentic_RAG_Vietnamese_Pharmaceutical_Documents.tex`, các mục trong
  `sections/{abstract,introduction,related-work,methodology,results,conclusion}.tex`, bảng trong
  `tables/{corpus,retrieval,e2e-main,e2e-ablation,e2e-layers}.tex`, hình TikZ trong
  `figures/{pipeline,retrieval-cost,e2e-groups}.tex`, `references.bib`, `llncs.cls` và
  `splncs04.bst` (CTAN `llncs` v2.26).
- Build bằng pdfLaTeX qua `latexmk`; mọi thiết lập nằm trong `.latexmkrc`. Build thất bại khi còn
  citation, reference chưa định nghĩa hay bất kỳ warning nào. Hook `report-build` của
  `.pre-commit-config.yaml` chạy `latexmk` mỗi khi commit chạm `docs/report/`.
- `package.sh overleaf` nén nguồn để tải lên Overleaf; `package.sh camera-ready [--final]` dựng ZIP
  File B (thư mục `Source/`, `Corresponding_Author.txt`, bản scan Licence to Publish có tên chứa
  `signed`). `submission/`, `instruction.md`, PDF và ZIP nằm ngoài git.
- Bảng e2e dựng từ `pharma-lab e2e report` của hai run `e2e-gemini`, `e2e-qwen35-9b` rồi chỉnh tay;
  số gốc ở `pharma-lab/data/evaluation/e2e/runs/<run>/reports/`. Số trong bài chỉ lấy từ file kết
  quả, không viết số nào không có trong file.
- Sau tag `v1.1.0` nguồn bài còn đổi hai lần: `package.sh` (`3f0a46d`, 2026-10-22) và đồng bộ với
  bản PDF thầy hướng dẫn sửa (`105fce4`, 2026-11-04: tên tác giả thứ hai, rút gọn đoạn mở Related
  Work và bỏ bốn trích dẫn, sửa Limitations và thêm hướng tiếp theo trong Conclusion, trích VN-MTEB
  bản EACL 2026). Vì vậy PDF build từ `v2.0.0` khác PDF của tag.
- `README.md` của `docs/report/` còn ghi `cd report` ở vài lệnh; đường đúng là `docs/report`.

### 3.2 Paper v1 và camera-ready

**Nội dung.** Ba đóng góp, sau camera-ready được định vị là tài nguyên và đánh giá, không phải
kiến trúc mới: (1) corpus thuốc tiếng Việt từ Dược thư quốc gia và 2.406 tờ hướng dẫn sử dụng, cùng
benchmark retrieval 10.000 câu; (2) benchmark retrieval có chi phí (BM25, dense, hybrid RRF,
reranker); (3) agentic RAG trên LLM rẻ (guard, rephrase, hybrid search và rerank, judge–refine,
answer có trích dẫn), đánh giá trên golden 500 câu với ablation, kiểm tra an toàn và hiệu chỉnh
judge bằng một dược sĩ chấm mù. Hai setting: Gemini 3.8 Flash qua proxy và Qwen3.5-9B tự host F16.
Không đặt tên hệ thống trong bài.

**Định dạng.** Springer CCIS, LNCS, single-blind. Bản nộp tối đa 12 trang không tính references;
camera-ready 12–15 trang tính cả references.

**Camera-ready trả lời bốn review** mà không đổi corpus, benchmark, golden, model hay kết quả cũ:

| Điểm review | Cách trả lời trong bài |
| --- | --- |
| Baseline one-step yếu trên câu nhiều lượt | E1: cấu hình `one-step-history` (trong bài gọi là Concat RAG) nối các câu hỏi trước vào query, không gọi LLM; chạy trên 50 câu multi-turn cho cả hai setting |
| k = 2 của RRF chọn trên chính benchmark | E2: chia benchmark dev/test 50/50, chọn trên dev, báo trên test; không chạy lại model |
| Citation recall 0,70–0,72 chưa phân tích | E3: sửa bộ đọc trích dẫn bỏ sót dạng `[1, 2]`, chấm lại `citation_support`, tách câu không trích dẫn và trích sai |
| Lớp nào giúp ở đâu; bỏ reranker không đổi e2e | E4: lát `rare_term` (BM25 ×2,2) và `sibling_products` (reranker ×1,4), tính trên metric từng câu có sẵn |
| Judge–refine lợi ít, tốn khoảng 40 % token | E5: chia item theo quyết định đầu của judge (295 nhận ngay, 185 tìm thêm) |
| Novelty hạn chế | Viết lại đóng góp thành tài nguyên và đánh giá |
| Safety 10 câu mỗi loại; benchmark template; một dược sĩ | Hạ tuyên bố, báo x/10 kèm Wilson CI, Limitations nêu rõ |

Mã của camera-ready còn trên `v2.0.0`: cờ `PipelineOptions.history_query` và cấu hình e2e
`one-step-history` (`pharma-lab/src/pharma_lab/e2e/configs.py`), `data pull/push --dataset`. Run
camera-ready (`e2e-gemini-cr`, `e2e-qwen35-9b-cr`) chỉ nằm trên nhánh `camera-ready`, không gộp vào
`v2.0.0`.

**Dữ liệu làm minh chứng, đóng băng:** dataset Kaggle công khai `vipharma-rag` version 2 (bài dẫn
link này) và dataset riêng tư `vipharmind-data-v1` (version 1 ghép với `v1.0.0`, version 2 ghép với
`v1.1.0`). `pharma-lab data push` từ chối ghi vào các dataset này (`FROZEN_DATASETS` trong
`pharma-lab/src/pharma_lab/data_archive/service.py`). Archive làm việc của v2 là `vipharmind-data-v2`.

### 3.3 Bài thuyết trình (`docs/presentation/`)

- 15 phút gồm Q&A, người trình bày Van-An Doan: nói khoảng 11 phút, khoảng 16 slide nội dung cộng
  slide cảm ơn, 8 slide dự phòng. Slide và speaker notes tiếng Anh (khoảng 1.470 từ).
- Quy tắc cao nhất: mọi con số, tên model, tên thuốc và tuyên bố phải khớp đúng bài camera-ready.
  Nguồn số theo thứ tự: `docs/report/tables/*.tex`, toạ độ trong `docs/report/figures/*.tex`, văn
  xuôi trong `docs/report/sections/*.tex`; dữ liệu thô chỉ dùng cho ví dụ, không cho metric. Không
  nêu chênh lệch giữa run và bài ở bất cứ đâu.
- Quy tắc biên tập của tác giả: không chi tiết hạ tầng (T4, llama.cpp, thinking tắt), không chú thích
  thừa, không dòng credit, nhãn mục theo cấu trúc bài (Introduction · Resources · Method · Results ·
  Conclusion · Backup), câu hỏi tiếng Việt có dấu kèm bản dịch tiếng Anh, QR code chỉ ở slide cảm ơn
  (GitHub tag `v1.1.0` và Kaggle `vipharma-rag`).
- Build: `docs/presentation/build/make.sh` dựng lại workspace ppt-master từ `template.pptx`, sinh SVG
  slide và notes (`build_deck.py`, `notes.py`), chạy bộ kiểm chất lượng và xuất PPTX;
  `render_pdf.py` xuất PDF dự phòng. Chạy Python bằng `/usr/bin/python3`. `template.pptx`,
  `assets-src/`, `fonts/`, `projects/` và file PPTX, PDF đầu ra nằm ngoài git (chỉ ở máy tác giả);
  deck cuối đính vào GitHub Release. `rehearsal.md` giữ thời lượng từng slide.
- Thiết kế chi tiết từng slide và 20 insight đã duyệt: `dcca0d1:docs/superpowers/specs/2026-11-04-soict-presentation-design.md`.

### 3.4 Paper v2 (đã dừng)

Paper v2 được mở ngày 2026-10-14 trên nhánh `v2.0.0`: giữ chất lượng của v1 với độ trễ và chi phí
thấp nhất, bằng bốn đóng góp (tách quyết định khỏi sinh văn bản qua decision model Jev, refinement
theo ngưỡng tin cậy τ, so graph routing với ReAct trên model rẻ, benchmark và golden v4 báo ba trục
chất lượng, giây, USD). Công việc tạm dừng từ 2026-10-26 và ngày 2026-11-15 An quyết định không làm
tiếp trong repo này.

Đã làm và còn trong repo: mã pha D (dữ liệu, benchmark v3, golden v4), pha 0 (đo đạc, giá, độ trễ),
pha 1 (decision model, `refine_threshold`) và pha 2 (agent ReAct); cặp retrieval của agent đã chốt
(spec `evaluation`). Chưa có run e2e v2 nào và chưa viết bài. Thiết kế đầy đủ, ma trận thí nghiệm
(A1–A4, B, C, D6, E1–E5, H), rủi ro và danh sách tài liệu đọc lại được ở
`1b73f5b:docs/superpowers/specs/2026-10-14-paper-v2-design.md`; ghi chú nghiên cứu nền ở
`docs/research/paper-v2/`. Muốn mở lại thì viết spec mới từ hai nguồn đó.

## 4. Ngoài phạm vi

Paper v2 và mọi thí nghiệm e2e mới cho bài báo; sửa nội dung khoa học của paper v1 hay dữ liệu đã
đóng băng của nó.

## 5. Câu hỏi mở cho An

1. Bản PDF thầy sửa (`105fce4`, 2026-11-04) có được gửi lại cho ban tổ chức không? Nếu có, nên gắn
   tag (ví dụ `v1.1.1`) để mốc của bản in khớp nguồn; nếu không, `docs/report/` đang khác bản đã nộp.

## 6. Lịch sử quyết định

| Ngày | Quyết định | Thay cho | Lý do | Nguồn |
| --- | --- | --- | --- | --- |
| 2026-09-17 | Paper v1 viết bằng LaTeX LNCS, ba đóng góp cân đối, placeholder `\pending{}` cho số chưa có, bảng e2e sinh từ `pharma-lab e2e report` | Chưa có | Hạn full paper 20/09; viết trong lúc E2E và rerank 8B còn chạy | `f9fc933:docs/superpowers/specs/2026-09-17-soict-paper-design.md`, plan `f9fc933:docs/superpowers/plans/2026-09-17-soict-paper.md` (đã chạy xong) |
| 2026-09-23 | Build bằng pdfLaTeX qua `latexmk` và `.latexmkrc`, hook pre-commit | LuaLaTeX + `fontspec` qua script của `latex-document-skill` | Commit không ghi lý do; kết quả là một lệnh `latexmk` build đủ, Overleaf biên dịch được bằng compiler mặc định | `9b09cf7`, `6ff700b` |
| 2026-09-24 | Bỏ macro `\pending`, gỡ spec và plan paper v1 khỏi repo | Cờ `\finaltrue` biến `\pending` sót thành lỗi | Bài đã đủ số | `6cde8ce`, `99447e5` |
| 2026-10-14 | Mở paper v2 trên nhánh `v2.0.0`: tối ưu chất lượng, độ trễ, chi phí; bốn đóng góp; ba LLM | Mở rộng v1 theo hướng xếp hạng model | So sánh model không mới; tính mới nằm ở kiến trúc | `1b73f5b:docs/superpowers/specs/2026-10-14-paper-v2-design.md` §0–§1 |
| 2026-10-15 | Chunk là đơn vị đọc (gộp mục tới khoảng 1.024 token), 5 chunk mỗi lượt, bỏ hydrate | Chunk theo từng mục cộng hydrate, top 8 | Chi tiết ở spec `corpus-data-pipeline` | cùng spec §3.0c |
| 2026-10-16 | Judge đánh giá ở reasoning `none`, không chấm lại nhãn dược sĩ v1; hiệu chuẩn dược sĩ trên run v2 đo độ khớp | Pha 0 Task 10 so `none` với nhãn v1 | Judge gọi rất nhiều lần; chỉ có hai mức thực sự khác nhau | `414e317:docs/superpowers/plans/2026-10-16-paper-v2-phase-0-measurement.md` Task 10 |
| 2026-10-16 | Cặp embedding và reranker của agent chọn từ bảng retrieval v2, không cố định trước | Cố định Qwen3-Embedding-4B và reranker 4B | Để số quyết định | spec v2 §2.1b |
| 2026-10-19 | Camera-ready: ba thí nghiệm E1–E3 rồi thêm E4, E5; định vị lại đóng góp; model F16 đúng như v1, dùng lại run v1 | Đưa hướng v2 vào bài | Bài phải vẫn là bài đã được review | `61d10db:docs/superpowers/specs/2026-10-19-camera-ready-design.md`, plan `61d10db:docs/superpowers/plans/2026-10-19-camera-ready.md` (đã chạy xong) |
| 2026-10-19 | E3 bỏ mẫu gán nhãn tay, chỉ sửa bộ đọc `[1, 2]` và chấm lại | Gán nhãn tay một mẫu trích dẫn | Quyết định của tác giả | spec camera-ready §2 E3 |
| 2026-10-22 | Camera-ready xong, tag `v1.1.0`; archive dữ liệu v1 là `vipharmind-data-v1` | Tên `vipharmind-data`/`seed-pipeline-data` | Dataset cũ không còn trên Kaggle | `a9954db`, `c9b1b9b` |
| 2026-10-23 | Mọi bước GPU chạy trong kernel Kaggle, không tunnel; cũng áp cho run của paper v2 | Server trên Kaggle nối về máy bằng tunnel (`e2e llm-server`, `rerank-server`) | Một tài khoản bị khoá vì tunnel; chi tiết ở spec `kaggle-runs` | spec v2 Phụ lục B |
| 2026-10-24 | Gộp mọi spec nhánh vào một spec v2 có bảng tiến độ | Nhiều spec rời (eval-data-v3, kaggle, architecture-rules, camera-ready) | Một nguồn tiến độ | `414e317` |
| 2026-10-25 | Ma trận ablation Phụ lục C: golden v4 1.000 câu không chọn theo kết quả hệ thống; mỗi ablation có dữ liệu, phép thử và độ nhạy | Golden v3 500 câu có tầng "trượt vòng 1" | Probe chọn theo lỗi hệ thống là luẩn quẩn; chi tiết ở spec `evaluation` | spec v2 Phụ lục C |
| 2026-10-26 | Cặp retrieval của agent: hybrid Qwen3-Embedding-4B + Qwen3-Reranker-4B | Hybrid Qwen3-Embedding-8B (kết quả ngày 2026-10-25, đo trên Qdrant bẩn) | 8B không hơn 4B có ý nghĩa; luật chọn bản rẻ hơn | spec v2 §3.4 |
| 2026-10-26 | Chỉ Jev dùng OpenRouter; rewriter của D5 và mọi model tự host chạy trên Kaggle | OpenRouter cho cả rewriter | Quyết định của An | `1b73f5b` |
| 2026-11-04 | Thiết kế bài thuyết trình; 2026-11-05 sửa theo deck đã giao; 2026-11-08 gộp slide embedding và reranker | Chưa có | Hội nghị 4–5/12 | `dcca0d1:docs/superpowers/specs/2026-11-04-soict-presentation-design.md` |
| 2026-11-10 | `report/` và `presentation/` chuyển vào `docs/` | Thư mục ở gốc repo | Gom tài liệu | `54a9be9`, `642b578` |
| 2026-11-15 | Bài báo của repo dừng ở camera-ready; không làm tiếp paper v2 | Plan thí nghiệm e2e và viết paper v2 | Quyết định của An | file này |
| 2026-11-15 | Gộp mười spec và plan của mảng bài báo vào spec này | Spec paper v1, spec v2 1.383 dòng, spec camera-ready, spec thuyết trình, plan pha D, pha 0, 1, 2, plan v1, plan camera-ready | Ít file, không mâu thuẫn | file này |

Plan đã chạy xong và bị bỏ (kết quả nằm trong mã): plan paper v1, plan camera-ready, plan pha D
(`414e317:docs/superpowers/plans/2026-10-14-paper-v2-phase-d-data.md`, Task 1–7b xong; Task 8 được
thay bằng `08-phase-d-results.md`), phần mã của plan pha 0 (Task 1–9), pha 1 (Task 1–10) và pha 2
(Task 1–6) (`414e317:docs/superpowers/plans/2026-10-16-paper-v2-phase-{0-measurement,1-decision-model,2-react}.md`).
Các bước chạy còn lại của ba plan này (hiệu chuẩn Jev, ma trận e2e, viết bài) không làm, vì paper v2
đã dừng.

## 7. Liên kết

- [`backend-agent-api`](2026-11-15-backend-agent-api-design.md): graph pipeline, decision model Jev
  (`DecisionPort`, `SystemOneAdapter`), refine template, `refine_threshold`, agent ReAct.
- [`evaluation`](2026-11-15-evaluation-design.md): benchmark 10.000 câu, golden v4, tập giữ lại, luật
  chọn retrieval, thống kê, ablation retrieval D1–D7, harness e2e, giá và độ trễ.
- [`kaggle-runs`](2026-11-15-kaggle-runs-design.md): `e2e run --backend kaggle`, shard, nối lại,
  proxy trong kernel.
- [`corpus-data-pipeline`](2026-11-15-corpus-data-pipeline-design.md): chunk là đơn vị đọc, corpus.
- [`architecture-rules`](2026-11-15-architecture-rules-design.md): quy tắc `AGENTS.md`.
- Ghi chú nghiên cứu nền của paper v2: `docs/research/paper-v2/` (`README.md` liệt kê).
