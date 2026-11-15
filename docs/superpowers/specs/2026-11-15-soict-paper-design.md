# Spec: Bài báo SoICT 2026 (paper v1, camera-ready, paper v2) và bài thuyết trình

Ngày: 2026-11-15. Nguồn sự thật: nhánh `v2.0.0` (`9732e8e`, sau khi gộp `camera-ready`). File này thay
cho mười spec và plan cũ của mảng bài báo (xem §6). Mọi `sha:path` ở §6 đọc lại được bằng
`git show <sha>:<path>`.

## 1. Mục tiêu và phạm vi

Một chỗ duy nhất trả lời ba câu hỏi: bài nào đang ở trạng thái nào, nguồn của mỗi bài nằm ở đâu, và
paper v2 còn phải làm gì. Phạm vi gồm:

- **Paper v1**: bài nộp SoICT 2026, paper 1360, *Agentic Retrieval-Augmented Generation for
  Vietnamese Pharmaceutical Documents* (Van-An Doan, Tuan Quoc Nguyen), được nhận trình bày oral.
- **Camera-ready** của paper v1 (tag `v1.1.0`).
- **Bài thuyết trình** 15 phút tại SoICT 2026 (4–5/12/2026, TP Hồ Chí Minh).
- **Paper v2**: bản mở rộng về chất lượng, độ trễ và chi phí của agentic RAG trên model rẻ, phát
  triển trên nhánh `v2.0.0`.
- Mã phục vụ bài: `docs/report/`, `docs/presentation/`, và phần agent, harness của paper v2 trong
  `backend/` và `pharma-lab/`, chỉ ở mức nó phục vụ bài.

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
| Paper v2 | Đang phát triển, tạm dừng từ 2026-10-26 | `1b73f5b` là commit v2 cuối trước khi gộp camera-ready | Mã pha 0–2 xong; dữ liệu và cặp retrieval đã chốt; chưa có run e2e v2 nào; chưa viết bài. Phần còn lại ở plan [`2026-11-15-paper-v2-experiments-and-writing.md`](../plans/2026-11-15-paper-v2-experiments-and-writing.md) |

Từ 2026-10-26 đến 2026-11-15 nhánh `v2.0.0` không có commit nào của paper v2; mọi commit là của
camera-ready và thuyết trình, gộp vào bằng `9732e8e`.

## 3. Thiết kế hiện hành

### 3.1 Nguồn bài và cách build (`docs/report/`)

- `docs/report/` là nguồn duy nhất của bài đang có trong repo, hiện là **bản camera-ready của paper
  v1** cộng một bản nháp v2 chưa được `\input` (`drafts/methods-v2.tex`). Không giữ bản sao nguồn
  nào khác.
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

### 3.4 Paper v2

#### 3.4.1 Mục tiêu và đóng góp

Paper v2 không nhắm một venue cụ thể. Câu hỏi: khi retrieval đã tốt (v1: Hit@10 97,5 %, grounding
cắt hallucination 18 đến 25 lần), giữ chất lượng đó với độ trễ và chi phí thấp nhất bằng cách nào.
Bốn đóng góp, mỗi cái cần bảng hoặc hình riêng có kiểm định ghép cặp:

1. **Tách quyết định khỏi sinh văn bản.** Guard và judge đủ bằng chứng chạy trên decision model Jev
   (TypeSafe, trả xác suất, không sinh văn bản); rephrase, refine, answer chạy trên LLM.
2. **Refinement theo độ tin cậy.** Vòng retrieve-more chỉ chạy khi xác suất "đủ bằng chứng" dưới
   ngưỡng τ; quét τ cho đường Pareto chất lượng so với USD và giây.
3. **Graph routing so với ReAct trên model rẻ**, cùng tool, retriever, ngân sách và định dạng trả
   lời; chỉ khác ai điều khiển.
4. **Benchmark và đánh giá**: benchmark retrieval 10.000 câu có lớp hội thoại, golden e2e 1.000 câu;
   mọi cấu hình báo đủ ba trục chất lượng, giây mỗi lượt (p50, p95) và USD mỗi 1.000 lượt.

Nguyên tắc: v2 chỉ tối ưu hiệu quả, không giữ thiết kế hay dữ liệu nào chỉ để so được với v1; bài
không có phần "so với v1". Không huấn luyện model nào. Điểm yếu reviewer có thể bắt được trả lời bằng
thí nghiệm, không bằng cách hạ tuyên bố.

#### 3.4.2 Model và đường gọi

| Vai | Model | Giá USD mỗi 1M token vào/ra (2026-10-14) | Đường gọi |
| --- | --- | --- | --- |
| Model mở, rẻ | Qwen3.5-9B Q8_0 | 0,10 / 0,15 (giá OpenRouter DeepInfra) | tự host trong kernel Kaggle |
| Model thương mại, rẻ | Gemini 3.8 Flash (`gemini-3.8-flash-high`, thinking low) | 0,75 / 3,75 | `cli-proxy-api` |
| Trần tham chiếu | Claude Opus 5.5 (`claude-opus-5-5`, effort minimal) | 4 / 20 | `cli-proxy-api` |
| Decision model | Jev (`~typesafe/jev-latest`) | 0,042 / 0 | OpenRouter, dịch vụ trả tiền thật duy nhất |
| Judge đánh giá | gemini-3.1-flash-lite, reasoning `none` | 0,25 / 1,50 | `cli-proxy-api` |

- Chỉ ba LLM: đóng góp nằm ở kiến trúc, không ở xếp hạng model. Mỗi phát hiện về kiến trúc được
  kiểm trên một model mở và một model thương mại; Opus trả lời câu "lợi thế còn không khi generator
  đã mạnh".
- Reasoning tắt hoặc thấp nhất ở mọi model; bài báo số token reasoning thực tế (Opus không tắt được
  thinking).
- Chi phí luôn là giá niêm yết nhân token, kể cả model tự host và model đi qua proxy thuê bao; không
  có mô hình giờ GPU. Bảng giá ở `pharma-lab/src/pharma_lab/e2e/pricing.py`; giá embedding và
  reranker hiện là cận trên (giá vào của Qwen3.5-9B) vì OpenRouter chưa công bố.
- Độ trễ lấy từ run concurrency 1 riêng (`e2e run --latency`, ghi vào run `<run>-c1`); chỉ so độ
  trễ giữa kiến trúc trên cùng một model, không xếp hạng độ trễ giữa model.
- Mọi model tự host chạy trong kernel Kaggle (cách chạy: spec `kaggle-runs`); chỉ Jev đi qua OpenRouter (quyết định 2026-10-26). Kernel hiện từ chối vai `systemone` (`check_no_decision_roles` trong `pharma-lab/src/pharma_lab/e2e/kaggle_shards.py`), nên A3, A4, B với Qwen cần thêm đường đưa khoá Jev vào kernel (plan Task 2).
- Cặp retrieval của agent, chọn theo luật của spec `evaluation`: hybrid RRF k=2, prefetch 50, giữ
  20, Qwen3-Embedding-4B; rerank Qwen3-Reranker-4B, giữ 5. Chunk là đơn vị đọc (khoảng 1.024
  token), tối đa 3 vòng tìm, `max_evidence_chars = 60_000`.

#### 3.4.3 Ma trận thí nghiệm e2e của bài

Mọi run e2e dùng golden v4 (1.000 câu, sha `1dae2820…`) và cùng judge. Bộ dữ liệu, kiểm định, độ
nhạy và họ so sánh của từng dòng nằm ở spec `evaluation`; bảng dưới chỉ nói bài cần gì và trạng thái.

| Mã | Câu hỏi của bài | Cấu hình | Mã | Run |
| --- | --- | --- | --- | --- |
| A1 | Mốc v1 trên dữ liệu v2 | Gemini chia vai như v1 (guard, rephrase trên 3.1-flash-lite; judge, refine, answer trên 3.8-flash) | Có | Chưa |
| A2 | Mọi vai trên một LLM | `full`, `one-step`, `closed-book` cho mỗi model trong ba model | Có | Chưa |
| A3 | Jev thay LLM ở guard và judge | Jev + refine template + τ đã chọn, mỗi model | Có | Chưa; Qwen cần Jev gọi được từ kernel |
| A4 | Tác dụng của refine template | Jev + Qwen + refine LLM | Có | Chưa |
| B | Refinement theo τ | τ ∈ {0; 0,3; 0,5; 0,7; 0,9; 1} trên A3 Qwen và A3 Gemini; cùng dải với độ tin cậy nói ra trên A2 Qwen; không quét trên Opus | Có | Chưa |
| C | Graph routing so với ReAct | cấu hình `react` so với `full` của A2, mỗi model | Có (smoke `e2e-smoke-react`) | Chưa |
| D6 | Retrieval tốt hơn có thành e2e tốt hơn | 5 retriever × {one-step, full} trên 720 câu tự nhiên và multi_hop | Có | Chưa |
| E1–E4 | Ablation rephrase, judge-refine, rerank, guard | trên A3 Qwen (E4 trên A2 và A3) | Có | Chưa |
| E5 | Jev làm judge đánh giá | Jev per-key-fact so với gemini-3.1-flash-lite trên 450 item có nhãn dược sĩ | Một phần | Chưa |
| H | Hiệu chuẩn Jev | AUROC, ECE, Brier, tỉ lệ lật khi gọi 3 lần, xoay thứ tự, trên tập giữ lại 300 câu judge và 300 lượt guard | Có (`e2e decision-set`) | Chưa (cần khoá OpenRouter) |

Các ablation retrieval của bài (D1, D2, D3, D4, D5, D7) do spec `evaluation` giữ. Ngày 2026-10-26
đã có số D1 (hybrid hơn dense +1,58 điểm Hit@5), D6 mức retrieval (k=2 hơn k=60 +1,83), D7 (chunk gộp
hơn chunk theo mục +2,19); D2 đang rerank; D4 và D5 chưa làm (`docs/research/paper-v2/08-phase-d-results.md`).

Nhãn dược sĩ: 50 item mỗi cấu hình chính (A2, A3, ReAct × 3 model), chấm mù theo giao thức v1, dùng
cho PPI và κ của judge. Đây là nguồn hiệu chuẩn duy nhất từ người. Golden v4 do model soạn và duyệt
hai vòng, dược sĩ chỉ xem lướt; bài phải ghi đúng như vậy.

#### 3.4.4 Bài viết

- Cấu trúc IMRaD tạp chí: Introduction, Related Work, Materials and Methods, Results, Discussion
  (principal findings, comparison with prior work, implications, limitations), Conclusion. Tiêu đề
  chốt khi có kết quả.
- Related Work thêm: workflow so với agent (Anthropic 2024, Ferrazzi et al. 2026, Kumar et al.
  2026); dừng vòng lặp và gating (TASR, HALT, Stop-RAG, Tiny-Critic RAG); decision model (REFLEX,
  Ibrahim và Zaki 2026, Rao và Callison-Burch 2026); viết lại và RAG hội thoại (Ma et al. 2023, CHIQ,
  MTRAG, CORAL); tiếng Việt (ViRE, ViMedAQA). Danh sách đầy đủ ở `docs/research/paper-v2/05-literature-survey.md` §I.
  Mỗi mục trong `references.bib` kiểm từ DOI, arXiv hoặc DBLP.
- Limitations: Jev closed weights và early access, giá có thể được trợ, hiệu chuẩn do vendor tự khai,
  tấn công kênh lựa chọn và chèn ngữ cảnh (Azizi et al., Xu et al. 2026), decision model không bao
  giờ là cổng an toàn duy nhất (regex screen chạy trước), độ trễ đo từ datacenter Kaggle, kết quả
  kiến trúc chỉ trên ba model, Opus chạy ở mức thinking thấp nhất, golden do model duyệt.
- Bản nháp Methods v2 (`docs/report/drafts/methods-v2.tex`) viết ngày 2026-10-16 đến 18 và đã lỗi
  thời ở mục golden (500 câu, năm loại multi-hop) và tập guard (100 lượt); khi viết phải theo golden v4
  (1.000 câu, ba loại multi-hop) và tập guard 300 lượt.
- Bản công khai dữ liệu của v2 là một dataset Kaggle công khai mới, link riêng, để link của bài SoICT
  luôn trỏ đúng dữ liệu đã nộp.
- Tiêu chí mỗi pha: lint, type, test xanh; mỗi run có `run.json` đủ identity; bảng sinh bằng lệnh có
  sẵn; số vào bài chỉ từ file báo cáo; build sạch warning.

#### 3.4.5 Rủi ro còn hiệu lực

- `~typesafe/jev-latest` không ghim được phiên bản: mỗi run ghi phiên bản trả về và dừng khi phiên bản
  đổi; lưu phản hồi thô trong `answers.jsonl` (`decisions`).
- Jev tiếng Việt chưa có số công bố: tập hiệu chuẩn là bằng chứng trong bài. Nếu AUROC của judge dưới
  0,70 thì LLM judge (A2) là đối chứng và kết quả vẫn được báo.
- Tập judge chỉ có 35 mẫu "thiếu bằng chứng" trên 300, nên khoảng tin cậy của AUROC rộng.
- Quota GPU Kaggle (30 giờ mỗi tuần mỗi tài khoản) và hạn mức thuê bao Claude: chạy theo thứ tự ưu
  tiên A1, A2 rồi A3, A4 rồi B rồi C, sau cùng D6, E; Opus xếp sau hai model rẻ. Ước tính Qwen trên
  1.000 câu: full khoảng 14 GPU-giờ, one-step khoảng 7, closed-book khoảng 4; Gemini full khoảng 9.
- Model rẻ gọi tool kém trong ReAct là kết quả, nhưng phải tách lỗi harness khỏi lỗi model bằng bảng
  thất bại theo loại.
- Điều khoản của Jev về công bố benchmark: kiểm Master Customer Agreement trước khi công bố.

## 4. Ngoài phạm vi

Huấn luyện hoặc fine-tune model; corpus mới hay câu hỏi người dùng thật; kiến trúc đa agent;
benchmark decision model ngoài miền thuốc; decision model thứ hai (kể cả open weights); sửa nội dung
khoa học của paper v1 hay dữ liệu đã đóng băng của nó.

## 5. Câu hỏi mở cho An

1. Bản PDF thầy sửa (`105fce4`, 2026-11-04) có được gửi lại cho ban tổ chức không? Nếu có, nên gắn
   tag (ví dụ `v1.1.1`) để mốc của bản in khớp nguồn; nếu không, `docs/report/` đang khác bản đã nộp.
2. Paper v2 viết ở đâu: thay dần nội dung `docs/report/` (bản v1 vẫn còn ở tag `v1.1.0`) hay một thư
   mục mới? Plan mặc định giữ `docs/report/` nguyên đến sau buổi trình bày 4–5/12 và viết v2 ở
   `docs/report-v2/`.
3. Khoá OpenRouter cho Jev đã có chưa, và có đồng ý đưa khoá lên Kaggle bằng dataset riêng tư xoá sau
   lượt chạy (như credential của proxy) để A3, A4, B chạy được với Qwen trong kernel?
4. Có lấy thêm câu "thiếu bằng chứng" cho tập judge trước khi hiệu chuẩn không (hiện 35 trên 300)?
5. Paper v2 vẫn tiếp tục theo ma trận trên, hay thu hẹp (ví dụ bỏ Opus, bỏ D6) vì đã tạm dừng ba tuần?

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
| 2026-11-15 | Gộp mười spec và plan của mảng bài báo vào spec này và một plan còn việc | Spec paper v1, spec v2 1.383 dòng, spec camera-ready, spec thuyết trình, plan pha D, pha 0, 1, 2, plan v1, plan camera-ready | Ít file, không mâu thuẫn | file này |

Plan đã chạy xong và bị bỏ (kết quả nằm trong mã): plan paper v1, plan camera-ready, plan pha D
(`414e317:docs/superpowers/plans/2026-10-14-paper-v2-phase-d-data.md`, Task 1–7b xong; Task 8 được
thay bằng `08-phase-d-results.md`), phần mã của plan pha 0 (Task 1–9), pha 1 (Task 1–10) và pha 2
(Task 1–6) (`414e317:docs/superpowers/plans/2026-10-16-paper-v2-phase-{0-measurement,1-decision-model,2-react}.md`).
Các bước chạy còn lại của ba plan này được viết lại trong plan mới, với lệnh `e2e run --backend
kaggle` thay cho `e2e llm-server`, `rerank-server`, `embed-server` đã gỡ.

## 7. Liên kết

- [`backend-agent-api`](2026-11-15-backend-agent-api-design.md): graph pipeline, decision model Jev
  (`DecisionPort`, `SystemOneAdapter`), refine template, `refine_threshold`, agent ReAct.
- [`evaluation`](2026-11-15-evaluation-design.md): benchmark 10.000 câu, golden v4, tập giữ lại, luật
  chọn retrieval, thống kê, ablation retrieval D1–D7, harness e2e, giá và độ trễ.
- [`kaggle-runs`](2026-11-15-kaggle-runs-design.md): `e2e run --backend kaggle`, shard, nối lại,
  proxy trong kernel.
- [`corpus-data-pipeline`](2026-11-15-corpus-data-pipeline-design.md): chunk là đơn vị đọc, corpus.
- [`architecture-rules`](2026-11-15-architecture-rules-design.md): quy tắc `AGENTS.md`.
- Ghi chú nghiên cứu nền: `docs/research/paper-v2/` (`README.md` liệt kê).
- Plan còn việc: [`2026-11-15-paper-v2-experiments-and-writing.md`](../plans/2026-11-15-paper-v2-experiments-and-writing.md).
