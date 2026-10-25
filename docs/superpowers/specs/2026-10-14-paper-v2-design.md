# Spec: Paper v2 — chất lượng, độ trễ và chi phí của agentic RAG cho tra cứu thuốc tiếng Việt

Đây là spec duy nhất của v2. Ngày tạo 2026-10-14, gộp các spec nhánh ngày 2026-10-24 (xem
"Lịch sử gộp" cuối bảng tiến độ). Nhánh: `v2.0.0`. Nền: release v1.0.0 (bản nộp SoICT 2026),
tag `v1.1.0` (camera-ready) và ghi chú nghiên cứu trong `docs/research/paper-v2/`.

## Bảng tiến độ (cập nhật 2026-10-25)

Mỗi pha có một plan trong `docs/superpowers/plans/`. Plan chỉ tồn tại khi pha đã được triển khai;
pha chưa tới thì chưa có plan, tới lúc đó mới viết (brainstorm, viết plan, làm). "Mã" là code đã
merge vào `v2.0.0` kèm test; "chạy" là thí nghiệm đã có số trong `pharma-lab/data/`.

| Pha | Mã | Chạy và số liệu | Plan | Còn lại |
| --- | --- | --- | --- | --- |
| Nền: quy tắc kiến trúc (`AGENTS.md`, import-linter, vị trí test) | Xong | Không áp dụng | `2026-10-16-architecture-rules.md` | Không |
| Nền: bản camera-ready SoICT (tag `v1.1.0`) | Xong | Xong | `2026-10-19-camera-ready.md` | Dọn nhánh `camera-ready` giữ đến sau buổi trình bày |
| Nền: chuẩn hoá đánh giá (Phụ lục C: luật chọn, judgments mọi nhóm, golden 1.000 câu, tập giữ lại) | Đang làm | Golden v4 chờ soạn và dược sĩ duyệt | `2026-10-25-retrieval-eval-standardization.md`, `2026-10-25-golden-e2e-v4.md` | Xem hai plan |
| Nền: Kaggle chạy trọn trong kernel, bỏ tunnel | Xong | Xong, hai vòng nghiệm thu trên Kaggle thật (Phụ lục B) | `2026-10-20-kaggle-batch-e2e.md`, `2026-10-23-kaggle-resumable-runs.md` | Không |
| Pha D: dữ liệu (tách leaflet, chunk là đơn vị đọc, benchmark 10.000 câu, golden v3) | Xong | Giai đoạn 1 của §3.4 xong trên golden `9c6e…` (chọn hybrid-qwen8b); giai đoạn 2 tạm (chưa có reranker 8B) | `2026-10-14-paper-v2-phase-d-data.md`, `2026-10-15-chunk-reading-unit.md`, `2026-10-18-unified-benchmark.md`, `2026-10-18-eval-data-v3.md`, `2026-10-25-retrieval-eval-standardization.md` | Rerank 8B trên hybrid-qwen8b rồi chốt S2; các run Kaggle của Phụ lục C (D1, D2, D5, D7, rrf60); viết `08-phase-d-results.md` |
| Pha 0: hạ tầng đo (reasoning token, giây, USD, `compare`, `--latency-run`) | Xong (Task 1–9) | Chưa: chọn xong cặp retrieval của agent; A1 Gemini, A2 Qwen và run latency chưa chạy | `2026-10-16-paper-v2-phase-0-measurement.md` | Task 10 (judge `none` so với nhãn dược sĩ v1), Task 11 (các run A1, A2), viết `09-phase-0-results.md` |
| Pha 1: decision model (Jev) và refinement theo độ tin cậy | Xong (Task 1–10) | Chưa: chưa có kết quả đo token Jev, tập hiệu chuẩn, ngưỡng τ | `2026-10-16-paper-v2-phase-1-decision-model.md` | Task 4 (đo token), Task 10 (chạy hiệu chuẩn), Task 11 (run A2, A3, A4, quét τ), `10-phase-1-results.md`; cần API key Jev |
| Pha 2: agent ReAct | Xong (Task 1–6) | Chưa | `2026-10-16-paper-v2-phase-2-react.md` | Task 7 (ma trận C), `11-phase-2-results.md`; chờ run của pha 1 |
| Pha 3: retrieval (§3.1, D1–D7, enrichment) | Một phần: công tắc enrichment đã có (§2.6) | Chưa | Chưa viết | Brainstorm, viết plan, làm |
| Pha 4: e2e bổ sung (§3.2, mục E, hiệu chuẩn dược sĩ mở rộng) | Chưa | Chưa | Chưa viết | Như trên |
| Pha 5: viết bài (§6) | Một phần: bản nháp Methods v2 trong `report/` | Chưa | Chưa viết | Như trên |

### Đang chạy được gì

Tất cả bước dùng GPU chạy qua `uv run pharma-lab e2e run --backend kaggle` (và `rerank`, `embed`
với `--backend kaggle`): chia shard qua nhiều tài khoản, ghi kết quả về local, chạy lại cùng lệnh để
nối tiếp (exit 10 là tạm dừng do quota, 11 là có cặp bị kẹt). Xem tiến độ bằng `e2e status` và
`kaggle status`. Chi tiết lệnh: `pharma-lab/docs/guides/e2e-evaluation.md` và `cli-reference.md`.
Model thương mại (Gemini, Opus) chạy qua `cli-proxy-api` trong kernel với `--with-proxy-credentials`.
Judge, `report`, `compare`, `calibration`, `decision-set` và `decision-probe` chạy local.

### Việc đang mở

1. **Golden retrieval chốt `9c6e4de6…`; judgments rules_version 2** (1.704 câu, mọi nhóm). Chỉ còn 8
   run `-v3-` trên golden này; 26 run cũ chuyển sang `pharma-lab/data/work/retired-runs/`. Kết quả
   luật §3.4 ghi ở §3.4. Còn: rerank Qwen3-Reranker-8B trên `hybrid-qwen8b-v3-p50-k20-rrf2` để chốt
   S2, rồi các run Kaggle của Phụ lục C.4 (D1 dense + reranker S2, D2 `plain`, `rrf60` cho D6, D5
   Q0–Q6, D7, D4 đo encode) trên golden này.
2. **Mọi run e2e trước đây bị bỏ** (`e2e-v2-qwen9b`, `e2e-v2-qwen9b-c1-c1`, `e2e-v2-gemini`): chạy trước
   khi cặp retrieval được chọn bằng luật và trên golden e2e cũ. Golden e2e dựng lại 1.000 câu theo
   `2026-10-25-golden-e2e-v4.md`; run e2e bắt đầu sau S2 và golden v4.
3. **Bất thường cần kiểm:** dense Qwen3-Embedding-4B (Hit@20 91,1) kém cả 0,6B (95,9) trên tập chọn,
   trong khi hybrid 4B vẫn 98,5; cần kiểm cache vector query và collection của 4B trước khi đưa vào
   bảng D.
4. **Chờ quyết định:** đẩy nhánh `v2.0.0`; xoá dataset đầu vào còn sót trên Kaggle (`pipeline-static-*`,
   `pipeline-input-*`); dọn Postgres local; chạy lại Opus khi Claude hết giới hạn tốc độ.

### Lịch sử gộp

Ngày 2026-10-24 các spec sau được gộp vào file này và xoá khỏi thư mục: `2026-10-18-eval-data-v3-design`
(nay là Phụ lục A), `2026-10-23-kaggle-resumable-runs-design` (Phụ lục B), `2026-10-20-kaggle-batch-e2e-design`
(bị Phụ lục B thay), `2026-10-16-architecture-rules-design` (quy tắc sống ở `AGENTS.md` của repo) và
`2026-10-19-camera-ready-design` (đã nộp, tag `v1.1.0`). Nội dung cũ vẫn nằm trong lịch sử git.

## 0. Mục tiêu

**Nguyên tắc áp dụng cho mọi phần của spec này:** v2 chỉ tối ưu hiệu quả. Không giữ bất kỳ thiết kế,
dạng dữ liệu, cấu hình hay đoạn mã nào chỉ để số v2 so sánh được với v1. v1 đã đóng băng ở release
v1.0.0 và Kaggle `vipharmind-data` version 1; mọi nhánh tương thích ngược, công cụ chuyển đổi một
lần và dữ liệu v1 cục bộ đều bị gỡ. Bài trình bày kết quả v2 như kết quả cuối, không có phần "so với
v1". Chỗ nào bên dưới còn nhắc "như v1" chỉ mô tả cách làm cũ đang được dùng lại vì nó tốt, không
phải ràng buộc.

**Dữ liệu trên Kaggle (kiểm kê ngày 2026-10-15).** Chỉ giữ thứ làm minh chứng cho bài SoICT v1 và
thứ v2 đang dùng; mọi thứ khác xoá.

| Dataset | Tài khoản | Xử lý | Lý do |
| --- | --- | --- | --- |
| `vipharma-rag` (công khai, version 2, 8,2 GB) | acc1 | Giữ, đóng băng | Bài SoICT dẫn link này; không thêm version, không đổi mô tả |
| `vipharmind-data` version 1 (riêng tư, 4,9 GB) | acc1 | Giữ | Toàn bộ dữ liệu làm việc của v1, ghép với tag `v1.0.0`; v2 thêm version 2 |
| `vector-cache-llama-cpp-cuda-t4` (công khai) | acc1 | Giữ | Bản build llama.cpp CUDA cho T4 mà mọi tài khoản mount |
| `vector-cache-gguf-*-q8_0*` (công khai) | acc1 | Giữ | Model Q8_0 open-weight mà mọi tài khoản mount; stage đầu tiên tự tạo |
| `hust-information-retrieval-corpus` | acc1 | Không đụng | Dự án khác |
| 12 dataset `vector-cache-gguf-*` F16/BF16 (khoảng 58 GB) | acc1 | Xoá | Cache model; file v1 dựng lại được từ nguồn Hugging Face ghim commit, sha256 và lệnh `-vimed` trong `docs/guides/evaluation.md` ở tag `v1.0.0` |
| `corpus-pipeline-rag-final`, `seed-pipeline-bundle`, `vipharmind-bundle`, mọi `pipeline-input-*` công khai | acc1, acc2, acc3 | Xoá | Input tạm của kernel; từ 2026-10-16 input là `pipeline-input-<hash>` riêng tư của tài khoản chạy kernel, tự sinh lại khi chạy stage |

Bản công khai của v2 là một dataset công khai mới, link riêng trong bài v2, để link của bài SoICT
luôn trỏ đúng dữ liệu đã nộp. Cache model Q8_0 (`vector-cache-gguf-*-q8_0*`) do stage đầu tiên tự
tạo. Ở máy local, `data/work/archive-v1-root`, `data/work/bundle-v1`, file GGUF F16 cùng cache
embedding, rerank và profile F16 bị xoá; run v1 trong git vẫn còn ở tag `v1.0.0`.


Bản v2 không nhắm một venue cụ thể. Mục tiêu là bài tốt nhất có thể, với tính mới tập trung vào
**đo chất lượng, độ trễ và chi phí cùng nhau** cho agentic RAG trên model rẻ. Mọi điểm yếu mà
reviewer có thể bắt phải được giải quyết bằng thí nghiệm hoặc phân tích, không bằng cách hạ tuyên bố.
Không huấn luyện model nào. Corpus được làm lại khi cách chia tốt hơn. Giữ một bài duy nhất với benchmark làm xương sống.

Thành công nghĩa là: bốn đóng góp dưới đây đều có bảng hoặc hình riêng với kiểm định ghép cặp; mọi cấu
hình trong bài đều có đủ ba trục chất lượng, giây mỗi lượt và USD mỗi 1.000 lượt; mọi câu hỏi trong
review bản v1 (xem §4.E) có một thí nghiệm trả lời; bài đọc như một benchmark paper chuẩn.

## 1. Câu chuyện và đóng góp

Khung đặt vấn đề lấy từ Fensore et al. 2025: RAG chuyên ngành chỉ giúp khi retrieval đủ tốt. Bài v1
đã cho thấy với Hit@10 97,5 % thì grounding cắt hallucination 18 đến 25 lần. Bản v2 hỏi tiếp: khi
retrieval đã tốt, giữ chất lượng đó với độ trễ và chi phí thấp nhất bằng cách nào. Bốn đóng góp:

1. **Tách quyết định khỏi sinh văn bản.** Các bước chỉ ra quyết định (guard, judge đủ bằng chứng,
   phủ theo intent) chạy trên decision model Jev, không sinh văn bản mà trả về xác suất đã hiệu
   chuẩn; các bước sinh văn bản (rephrase, refine, answer) chạy trên LLM nhỏ. Đo cái gì được, cái gì mất, và hiệu chuẩn của decision model trên tiếng Việt.
2. **Refinement theo độ tin cậy.** Vòng retrieve-more chỉ chạy khi xác suất "đủ bằng chứng" của judge
   dưới ngưỡng τ. Quét τ cho đường Pareto chi phí, độ trễ so với truthfulness, theo giao thức báo cáo
   của Qian et al. 2026.
3. **Graph routing so với agent ReAct trên model rẻ.** Cùng corpus, retriever, tool, ngân sách và
   định dạng trả lời; chỉ khác ai điều khiển. Với mỗi model, kiến trúc nào cho chất lượng cao nhất
   trên mỗi USD và mỗi giây, và model nặng có đổi kết luận không.
4. **Benchmark và đánh giá.** Benchmark retrieval 10.000 câu thêm lớp hội thoại; bộ e2e 1.000 item
   (Phụ lục C.2) có 200 câu cần tra nhiều lượt theo cấu tạo, dược sĩ duyệt toàn bộ; mọi cấu hình báo
   chất lượng, giây và USD.

Bài cố ý chỉ dùng ba LLM: cặp của v1 gồm một model mở rẻ (Qwen3.5-9B) và một model thương mại rẻ
(Gemini 3.8 Flash), cộng một model nặng (Claude Opus 5.5) làm trần tham chiếu. Đóng góp của bài nằm ở
kiến trúc (decision model, refinement theo ngưỡng, graph routing so với ReAct), không ở việc xếp hạng
model; so sánh model đã có nhiều bài làm và không mang tính mới. Mỗi phát hiện về kiến trúc được kiểm trên cả một model mở lẫn một model thương mại.
Opus 5.5 trả lời câu hỏi mà reviewer chắc chắn đặt ra: lợi thế của kiến trúc trên model rẻ có còn
khi generator đã mạnh, và model rẻ cộng Jev cách trần bao xa với chi phí bao nhiêu.

Định vị bắt buộc trong Related Work: Anthropic 2024 (định nghĩa workflow và agent); Ferrazzi et al.
2026 và Kumar et al. 2026 (workflow so với agent, phải đối chiếu rõ khác biệt: cùng tool và giao diện,
decision model, USD, tiếng Việt, nhiều lượt); TASR, HALT, Stop-RAG, Tiny-Critic RAG (dừng vòng lặp);
REFLEX, Ibrahim và Zaki 2026, Rao và Callison-Burch 2026 (decision model); Azizi et al. 2026 và Xu et
al. 2026 (tấn công decision model, vào limitations); Ma et al. 2023, CHIQ, MTRAG, CORAL (viết lại và
RAG hội thoại); ViRE và ViMedAQA (tiếng Việt). Danh sách đầy đủ ở `05-literature-survey.md` §I.

## 2. Thay đổi hệ thống (backend)

### 2.1 Provider decision model cho vai trò quyết định

- Thêm `LlmEndpoint.provider: Literal["openai", "systemone"] = "openai"` trong settings, cùng
  `base_url`, `api_key`, `model` dùng chung. `systemone` là giao thức `POST /v1/systemone`
  `{state, model, questions}` của Jev.
- Port riêng `DecisionPort.decide(role, state, questions) -> Decision` (domain `llm/decision.py`),
  cài bằng `infrastructure/llm/systemone_adapter.py` (`AsyncTypeSafeClient.system_one`) cho hai vai
  trò GUARDRAIL và JUDGE, tiêm vào `TurnDeps.decisions`. Lỗi SDK, HTTP và parse thành `LlmError` để
  giữ hành vi fail-open của guard và `judge_failed`. Usage lấy từ `usage.input_tokens`; `Decision`
  giữ phản hồi thô và `request_id`. Client có timeout riêng cho decision model (10 giây mỗi request,
  30 giây cả retry, theo mặc định của SDK), xa dưới hạn 90 giây của lượt, và được đóng khi tắt app.
  Identity của run ghi phiên bản model mà phản hồi trả về; qua OpenRouter đó là id OpenRouter, ví
  dụ `typesafe/jev-1.13-20260917`, và bài báo ghi đúng id này.
- Lưu phản hồi thô của mọi lời gọi decision model vào `answers.jsonl` (trường mới `decisions`) để tái
  lập và để phân tích hiệu chuẩn sau.
- Bộ câu hỏi, đóng băng trong mã, bản nháp ở `03-jev-typesafe.md` §7:
  - Guard, một request mỗi lượt: noul `is_attack`, `is_about_medicines`, `is_smalltalk_or_meta`, cộng
    17 noul `asks_<intent>` cho 17 intent của `INTENTS` trong `domain/agent/decisions.py`. State gồm lịch sử và
    lượt mới nhất. Regex screen hiện có vẫn chạy trước. Ngưỡng khởi điểm theo cookbook guardrail của
    vendor (0,35 review, 0,70 block) và được chỉnh trên tập giữ lại (§3.3). Lưu ý: TypeSafe không có
    model hay endpoint guardrail chuyên biệt; cookbook "Guardrails for LLMs" chỉ là một battery câu hỏi
    noul và score trên Jev tổng quát, và các đo đạc độc lập cho thấy prompt injection là task Jev yếu
    nhất (0,741 so với 0,767 của Qwen3.8-27B; Red Hat 86,35 % so với 89,01 % của DeBERTa 200M). Bài
    báo cáo recall tấn công của guard ở nhiều ngưỡng, và decision model không bao giờ là cổng an toàn
    duy nhất.
  - Judge, một request mỗi vòng tìm kiếm: noul `covers_<intent>` cho từng intent đã hỏi,
    `sufficient_overall`, `evidence_conflict`, `wrong_drug`. State gồm câu hỏi gốc, standalone query,
    danh sách intent đã hỏi, và evidence dạng mảng có id. Ánh xạ về `JudgeDecision`: `answer` khi
    `sufficient_overall ≥ τ` và mọi `covers` ≥ τ, ngược lại `search_more` với `gaps` là các intent chưa
    phủ. `JudgeDecision` thêm `confidence: float` (xác suất đủ bằng chứng).
  - Grader (đánh giá, không thuộc pipeline): per-key-fact choice supported/missing/contradicted, harm,
    abstention, injection. Đây là thí nghiệm phụ "decision model làm judge đánh giá" (§4.E), judge chính
    của bài là gemini-3.1-flash-lite.
- Giới hạn cần tôn trọng: 64k token mỗi request, 32k cho state cộng câu hỏi dài nhất (OpenRouter ghi
  ngữ cảnh 32.000, nên lấy 32k làm trần thực tế); ngân sách evidence 60.000 ký tự tiếng Việt (§3.0c)
  ước 19 đến 20k token ở 3,1 ký tự mỗi token, còn khoảng 12k token cho câu hỏi và phần còn lại của
  state. Việc đầu tiên của plan là đo `usage.input_tokens` cho một khối evidence đúng 60.000 ký tự; nếu
  vượt 24k token thì hạ `max_evidence_chars` tới mức vừa, không cắt chunk. Câu hỏi viết bằng tiếng
  Anh, nội dung tiếng Việt nằm trong state.
- Bài chỉ dùng một decision model là Jev. Không chạy decision model thứ hai, kể cả bản open weights;
  Related Work nhắc các model cùng loại và Limitations ghi Jev là closed weights.

### 2.1b Đường gọi model: lab tự host trên Kaggle hoặc qua cli-proxy-api, production qua OpenRouter

- Lab (pharma-lab, mọi run của bài) chỉ dùng OpenRouter cho Jev. Model mở tự host trên Kaggle như
  v1, model thương mại đi qua `cli-proxy-api`. Production (backend triển khai) gọi LLM qua OpenRouter;
  vì cả hai đều là endpoint tương thích OpenAI nên khác nhau chỉ ở cấu hình, không ở mã. Mỗi vai trò
  có `BASE_URL`, `API_KEY` và `MODEL` riêng như hiện nay, nên hai đường của lab trộn được trong một
  run.
- **Model mở** (Qwen3.5-9B) chạy trong kernel Kaggle của `pharma-lab e2e run --backend kaggle`:
  llama.cpp GGUF Q8_0 trên GPU0 (4 slot × 32.768 token, tức 4 request đồng thời), reranker trên GPU1,
  embedding trên CPU; không có tunnel hay cổng nào mở ra ngoài (`docs/guides/e2e-evaluation.md`).
- **Mọi model tự host đều ở Q8_0**, cả LLM, embedding và reranker. Sinh token trên GPU bị giới
  hạn bởi băng thông bộ nhớ, nên F16 lãng phí: Q8_0 giảm nửa dung lượng trọng số, chất lượng
  gần như bằng F16, tốc độ sinh mỗi request nhanh hơn rõ. Trọng số 9B Q8_0 còn 9,5 GB nên vừa một
  T4 cạnh KV cache, cho phép hai bản thay vì một bản chia đôi; 4B còn 4,3 GB, giải phóng VRAM cho
  nhiều slot và batch lớn hơn. Không tự quantize: mỗi file là bản Q8_0 đã công bố, tải theo commit
  và kiểm sha256 (Qwen3.5-9B từ `unsloth/Qwen3.5-9B-GGUF`, Qwen3-Embedding từ repo GGUF chính chủ
  của Qwen, Qwen3-Reranker-0.6B từ `ggml-org`, 4B từ `Voodisss`, 8B từ `sinjab`, bge từ `gpustack`,
  EmbeddingGemma từ `ggml-org`; commit và sha256 ghi trong `docs/guides/evaluation.md`). Reranker
  Qwen3 chỉ đổi khoá metadata `tokenizer.chat_template.rerank` sang instruction tiếng Việt y tế bằng
  `gguf-new-metadata`, tensor giữ nguyên từng byte. File F16 xoá. Bài ghi precision Q8_0 và nguồn
  file cho mọi model tự host.
- **Phục vụ lấy tốc độ làm đầu, không tiết kiệm quota:** mỗi model một kernel riêng trên một tài
  khoản Kaggle riêng, chạy song song, dùng đủ hai T4 của kernel (LLM, embedding và reranker đều
  replicated 2×1). Profile runtime (slot, ubatch, concurrency, batch) của từng model Q8_0 do cơ chế
  auto-benchmark sẵn có (`corpus-embed-benchmark`, `rerank --benchmark`) đo trên Kaggle và chọn
  nhanh nhất, với không gian tìm nới rộng vì VRAM dư; client gửi batch với concurrency bằng số slot.
- **Model thương mại** (Gemini 3.8 Flash, gemini-3.1-flash-lite, Claude Opus 5.5) qua service
  `cli-proxy-api` của compose (image `eceasy/cli-proxy-api:v8.0.28`, bản cũ v7.3.0 giả lập Claude
  Code quá cũ để gọi Opus 5.5), endpoint `http://127.0.0.1:8317/v1`, key `proxypal-local`, như v1 đã
  dùng cho Gemini. Credential OAuth Antigravity và Claude lấy từ ProxyPal trên Windows và chép vào
  volume `vipharmind_cli_proxy_auth` (README, mục CLIProxyAPI); đã đồng bộ ngày 2026-10-14. Đã gọi
  thử structured output thành công với `gemini-3.8-flash-high`, `gemini-3.1-flash-lite` và
  `claude-opus-5-5`.
- **Reasoning tắt hoặc thấp nhất có thể ở mọi model**, ghi rõ trong bài: Claude Opus 5.5 không cho
  tắt thinking (`reasoning_effort: none` bị từ chối với "thinking.type.disabled is not supported for
  this model", kiểm lại ngày 2026-10-14), nên dùng adaptive với `reasoning_effort: minimal`, đo được
  0 token reasoning trên câu ngắn; bài báo số token reasoning thực tế của Opus. Gemini 3.8 Flash qua
  Antigravity chỉ có id `gemini-3.8-flash-high` và override payload trong `config.yaml` đặt
  `thinkingLevel: low`, mức thấp nhất model nhận (`minimal` bị từ chối), đo được 0 token reasoning;
  Qwen3.5-9B `chat_template_kwargs.enable_thinking: false`.
- Chi phí trong bài luôn tính theo giá niêm yết nhân token, kể cả với model thương mại đi qua
  proxy thuê bao, kể cả Opus 5.5, và kể cả Qwen3.5-9B tự host: Qwen tính theo giá niêm yết trên
  OpenRouter (DeepInfra bf16), tức đúng giá production sẽ trả, không theo giờ GPU Kaggle. Bài nói
  rõ điều đó. Tiền thật phải trả chỉ phát sinh ở Jev qua OpenRouter.
- Embedding query và reranker của tầng agent: chọn từ bảng retrieval v2 (§4.D) sau khi pha D
  xong, theo quy tắc ghi trong plan pha 0 (nDCG@5 sau rerank cao nhất; chênh dưới một điểm thì
  lấy model nhỏ hơn), không cố định trước (quyết định ngày 2026-10-16). Cả hai chạy trong cùng
  kernel với LLM của lượt chạy (reranker GPU1, embedding CPU), không còn kernel riêng phục vụ qua
  mạng; shard chạy song song trên nhiều tài khoản. Embedding phải cùng file với index đã dựng; CPU
  qua `compose.local-models.yaml` chỉ để demo.
- Jev: qua OpenRouter, cả ở lab lẫn production, bằng SDK chính thức của TypeSafe với `base_url`
  `https://openrouter.ai/api` và id `~typesafe/jev-latest` (danh sách model OpenRouter ngày
  2026-10-14 hiện id `typesafe/jev-router`, giá ghi -1, tức OpenRouter không công bố giá cố định).
  Key OpenRouter đặt trong `backend/.env` và `pharma-lab/.env` theo `.env.example`. Ba hệ quả cho
  thiết kế: id `latest` không ghim được phiên bản, nên mỗi run ghi phiên bản model mà phản hồi trả
  về và dừng nếu phiên bản đổi giữa run; ngữ cảnh OpenRouter ghi 32.000 token, nên trần evidence
  của judge phải nằm dưới mức đó (đo ở bước đầu của pha 1); chi phí trong bài tính theo giá niêm yết
  của TypeSafe 0,042 USD mỗi triệu token vào (`pricing.py`). Model `Usage` của SDK bỏ trường `cost`
  của OpenRouter, nên tiền thật chỉ còn trong phản hồi thô (`Decision.raw`); bài chỉ báo chi phí theo
  giá niêm yết. Đây là dịch vụ ngoài trả tiền duy nhất của lab.
- Judge đánh giá: gemini-3.1-flash-lite qua cli-proxy-api; `judge.json` ghi thêm provider. Reasoning
  của judge (RAGAS và judge cấu trúc, hằng `JUDGE_REASONING` trong `judging/structured.py`) đổi từ
  `medium` của v1 sang `none`, vì judge gọi rất nhiều lần mỗi item. Qua proxy, flash-lite có thinking
  thật ở `medium` (291 token reasoning trên một câu tính liều) còn `low` và `none` đều 0 token, nên
  chỉ có hai mức thực sự khác nhau. Mọi run v2 chấm ở `none` (quyết định ngày 2026-10-16, không
  chấm lại nhãn v1): hiệu chuẩn dược sĩ trên chính các run v2 (§3.3) đo độ khớp của judge; nếu độ
  khớp kém thì chấm lại ở `medium`. Rủi ro đã biết: một câu tính thể tích (400 mg từ ống 250 mg/5
  ml) đúng 8 ml ở `medium` nhưng sai 6,4 ml ở `none` và `low` (thử ngày 2026-10-14), nên bài báo
  cáo độ khớp với dược sĩ của chính judge này.

### 2.2 Judge-refine kiểu quyết định

- Rephrase (LLM) thêm trường `subjects: list[str]`, tên thuốc hoặc hoạt chất mà lượt này hỏi, lấy
  từ standalone query. Không đổi hành vi khác.
- Refine có hai chế độ, chọn bằng `PipelineOptions.refine_mode: "llm" | "template"`:
  - `llm`: như hiện nay, một lời gọi LLM sinh 1 đến 3 query từ `gaps`.
  - `template`: query = `"<subject> <cụm intent>"` cho mỗi intent chưa phủ, bảng 16 cụm tiếng Việt cố
    định trong mã (ví dụ dosage → "liều dùng và cách dùng", storage → "bảo quản"). Không gọi LLM.
    Trùng với `used_queries` thì bỏ như hiện nay.
- Với decision model ở judge và `template` ở refine, vòng judge-refine không tốn lời gọi LLM nào.

### 2.3 Refinement theo độ tin cậy

- `PipelineOptions.refine_threshold: float | None`. `None` giữ hành vi nhị phân cũ. Khi có giá trị,
  judge quyết định `search_more` chỉ khi `confidence < τ`; τ = 0 là "không bao giờ refine", τ = 1 là
  "luôn refine đến hết vòng".
- Nguồn `confidence` theo cấu hình: xác suất noul của decision model, hoặc, cho thí nghiệm đối chứng,
  độ tin cậy nói ra bằng lời của LLM judge (trường `confidence` thêm vào prompt `JUDGE_SYSTEM`).
  Thí nghiệm này kiểm tra phát hiện của TASR rằng độ tin cậy nói ra của model RLHF gần như vô dụng.
- `RunIdentity.pipeline` nới kiểu thành `dict[str, object]` để ghi τ và `refine_mode`. CLI `e2e run`
  nhận `--pipeline-option key=value`, tên run gộp giá trị để các điểm quét nằm cùng một run root và
  bảng ablation tự so với `full`.

### 2.4 Agent ReAct

Thiết kế rút từ dsh, Codex và Claude Agent SDK (`01-*.md` §8, `02-*.md` Part 4), cố ý tối thiểu và
công bằng:

- Agent dựng sẵn của LangChain 1.x: `langchain.agents.create_agent` (chạy trên LangGraph) với một
  `BaseChatModel` riêng cho vai `agent`. `infrastructure/llm/agent_model.py` dựng `ChatOpenAI` từ
  `LlmSettings.resolve(LlmRole.AGENT)` (base_url, khoá, model, reasoning_effort, extra_body,
  max_output_tokens; endpoint muốn `max_tokens` thì nhận trường đó trong extra_body), cùng timeout
  và số lần thử lại với các vai khác, Chat Completions, `stream_usage`. `build_application` gắn nó
  vào `TurnDeps.agent_model` khi LLM đã cấu hình; harness lấy lại từ đó. `LlmPort` không có lời gọi
  tool nào.
- Graph `application/chat/react_graph.py`: `guard` (dùng lại nguyên) → `agent` → `finalize`, cùng
  `answer` cho lượt bị chặn hoặc ngoài phạm vi và `fallback` cho lỗi. Node `agent` dựng mỗi lượt một
  `create_agent(model, tools=[search_corpus], system_prompt=REACT_SYSTEM, middleware=[ReactBudget])`
  (`application/chat/react_agent.py`) rồi `ainvoke` với lịch sử hội thoại và câu hỏi, truyền config
  của graph cha để callback (Langfuse) nối vào trace của lượt. Tin nhắn AI cuối là câu trả lời đưa
  sang `finalize`; thiếu model, lỗi model hay câu trả lời rỗng làm lượt thất bại và đi `fallback`.
  Không có rephrase, judge, refine riêng. Agent dùng cùng retriever, ngân sách và luật evidence với
  pipeline graph; vòng model ⇄ tool là của LangChain, luật miền nằm ở middleware. Cả hai graph chạy
  với `recursion_limit` 64 làm lưới an toàn dưới ngân sách miền.
- Middleware `ReactBudget` (`AgentMiddleware`, điểm mở rộng chính thức) giữ ngân sách miền:
  `awrap_model_call` thêm ghi chú hết lượt và gọi với `tool_choice="none"` (tool vẫn khai báo, vì
  lịch sử có tool call) khi đã đủ 6 vòng, khi còn dưới hai lời gọi LLM, hoặc khi lời gọi trước làm
  cạn ngân sách; sau mỗi lời gọi nó đọc `usage_metadata`, tính vào `AgentRun` (lời gọi, token), ghi
  một action `agent` và cộng usage, số giây vào `ReactStats` để harness tính giá và độ trễ dưới vai
  `agent`. Phản hồi xin tool khi đã cạn ngân sách thì bỏ các tool call đó và gọi thêm đúng một lần
  không tool. `awrap_tool_call` trả `Error: ...` cho tool call sai định dạng (tên lạ, thiếu `query`,
  đối số không phải JSON) mà không chạy tool.
- Tool, một cái, chỉ đọc, gọi song song được:
  - `search_corpus(query: str)`: `RetrievalService.search` với cùng hybrid RRF, cùng reranker, trả tối đa
    5 chunk dạng `[E<n>] <tiêu đề > các heading> (trang):` rồi nguyên text chunk, đúng văn bản mà
    pipeline đọc (§3.0c). Không có tool đọc lân cận: pipeline graph không có bước nào tương ứng, và
    chunk đã gộp các mục liền kề nên tool đó không còn giá trị; đây là điều kiện để §4.C so sánh đúng
    "ai điều khiển".
  - Tool là `StructuredTool` của LangChain với schema pydantic `SearchArgs` (một `query` bắt buộc,
    không rỗng). Các tool call của một phản hồi chạy đồng thời trong ToolNode nhưng gộp thành một
    vòng tìm: mỗi query mới (đã chuẩn hoá) tìm đúng một lần, tất cả cùng lúc, kết quả đánh số theo
    thứ tự gọi và ghi thành một action `search`.
- Quy tắc dừng và ngân sách: dừng khi phản hồi không có tool call; tối đa 6 vòng tool; hết vòng thì một
  lời gọi cuối không tool với ghi chú "đã hết lượt tra cứu, trả lời từ những gì đã có"; cùng
  `max_llm_calls`, `max_tokens`, `max_evidence_chars` và deadline với pipeline. Ngân sách evidence
  tính trên tổng text chunk đã đưa vào messages: chunk đã hiện ở lượt trước không hiện lại (chỉ trả
  id), kết quả làm tràn ngân sách bị thay bằng dòng "hết ngân sách bằng chứng, trả lời từ những gì đã
  có", và harness ghi số lần chạm trần này. Gọi trùng (tool, args) trả lại kết quả cũ kèm một dòng
  nhắc; lỗi tool trả về dạng text `Error: ...` chứ không ném.
- Prompt hệ thống ngắn, tiếng Việt, theo mẫu codex: vai dược sĩ, quy tắc trích dẫn `[E<n>]` giống
  pipeline, "dùng tool để tìm đúng mục trước khi trả lời, không đoán", "phần lớn câu chỉ cần một đến
  hai lần tìm", "đi rộng rồi thu hẹp". Không plan tool, không compaction, không subagent.
- Hậu xử lý câu trả lời dùng lại `CitationSanitizer` và nhãn grounded/partial/abstain như pipeline.
- Ghi lại mỗi lượt: số vòng, số tool call, có chạm trần không, có tool call sai định dạng không, số
  lần gọi trùng, để báo cáo thất bại theo loại như Kapoor et al. và Kumar et al.
- Không chạy được trên decision model, đó là điểm đối chiếu: ReAct buộc mọi bước là LLM.

### 2.5 Đo độ trễ và chi phí

- `AnswerRecord.steps: list[{kind, outcome, started_at, seconds}]` từ `AgentRun.actions[*].at`;
  `SearchResult` thêm `retrieval_seconds` và `rerank_seconds`.
- `pharma_lab/e2e/pricing.py`: bảng giá theo id model và provider, đọc từ OpenRouter ngày
  2026-10-14, ghi nguồn và ngày, USD mỗi triệu token vào/ra: Qwen3.5-9B 0,10/0,15 (giá DeepInfra bf16
  trên OpenRouter, dùng cho run tự host);
  Gemini 3.8 Flash 0,75/3,75; Claude Opus 5.5 4/20 (claude.com/pricing, prompt dưới 100k token);
  gemini-3.1-flash-lite 0,25/1,50; Jev 0,042/0; Qwen3-Reranker-4B và
  embedding theo giá OpenRouter tại ngày chạy (production gọi OpenRouter, không còn DeepInfra). Mọi chi phí là giá niêm yết, không có mô hình giờ
  GPU, kể cả cho thành phần tự host trên Kaggle.
- Metric mới: `usd_per_turn`, `usd_per_1000_turns`, `llm_seconds_per_turn`, `retrieval_seconds_per_turn`,
  `decision_seconds_per_turn`, `cost_of_pass` (USD chia tỷ lệ perfect, theo Erol et al.). Bảng
  `cost.csv|tex`.
- Giao thức đo: run đo latency chạy với concurrency 1 trên cùng máy và cùng endpoint, ghi vùng địa lý
  và ngày. Latency của Qwen3.5-9B là latency trên hai T4 trong kernel Kaggle, còn Gemini và Opus là
  latency API qua proxy, nên bài chỉ so latency giữa các kiến trúc trên cùng một model (A2 so với
  A3, graph so với ReAct), không xếp hạng latency giữa các model; run lấy chất lượng có thể chạy concurrency 4 nhưng latency lấy từ run concurrency 1. Báo
  p50 và p95. Mỗi lời gọi decision model đo client-side.

### 2.6 Công tắc và biến thể khác

- `PipelineOptions.guard: bool` cho ablation không guard.
- `settings_for` cho các biến thể retriever e2e: `bm25`, `dense`, `hybrid k=60`.
- `EnrichmentOptions(header, glossary, colloquial)` trong `chunk_document`, một biến thể tắt cả ba,
  hậu tố `CHUNKER_VERSION` riêng, re-embed và import thành release riêng với alias Qdrant riêng. Bỏ
  colloquial cần sửa `_MappingCollector.add_leaflet` để không tự thêm product names.
- `rerank.max_candidates` giữ 40; `rerank.top_n` là 5 theo §3.0c. Bài ghi đúng hai số này.

## 3. Dữ liệu và benchmark

### 3.0 Sửa dữ liệu trước mọi run mới (theo `docs/research/paper-v2/07-dataset-review.md`)

- **Corpus:** tách mỗi tờ hướng dẫn theo heading markdown có sẵn thành section con (p50 16 heading
  mỗi tờ), chuẩn hóa tên heading về bộ intent bằng bảng ánh xạ trong `relevance_judgments.py`,
  header context theo dạng `<tiêu đề> > <heading 1>; <heading 2>; ...` của §3.0c. Re-embed trên Kaggle như v1 (bundle embed chỉ có backend
  local và Kaggle; cache theo sha của text nên chỉ chunk leaflet mới tốn GPU), release mới sinh từ
  digest bundle. Kích thước chunk và cách gộp mục theo §3.0c; không ablation kích thước chunk, bài
  biện minh bằng thống kê token của §3.0c.
- **Benchmark retrieval:** sinh lại từ release mới. Bỏ mọi hậu tố "(phần ...)" và đáp án trong
  ngoặc; query_form `chunk_coverage` đổi tên `section_coverage` và hỏi theo intent của mục gold (chunk
  không còn là đơn vị hỏi, §3.0c); leaflet dùng tên sản phẩm chuẩn hóa
  (thương hiệu, hàm lượng, dạng) thay tiêu đề marketing; patient_natural đổi tên thành
  leaflet_short và mô tả đúng là template ngắn; bỏ nhóm confuser, 200 câu chuyển cho noisy dưới
  dạng lỗi gõ sinh tự động bên cạnh 300 câu bỏ dấu; bỏ trường difficulty; tách general_info thành
  intent cụ thể (overdose, storage, pharmacology, general_info); mở rộng any_acceptable cho sản
  phẩm có chunk trùng văn bản. Giữ 10.000 câu và sáu nhóm.
- **Golden e2e:** giữ nguyên nội dung, chỉ viết lại 50 item có hậu tố "(phần ...)"; gold section
  của item leaflet ánh xạ sang section con mới; chạy `golden check`.
- **Hệ quả:** mọi số retrieval v1 vô hiệu; chạy lại bảng retrieval với năm embedding tự host và
  bốn reranker trên Kaggle, tất cả ở Q8_0 (§2.1b) (bỏ BGE-reranker-v2-gemma; bỏ OpenAI text-embedding-3-large vì run v1 là
  run nhập từ pipeline cũ, không tái lập được); bài chỉ trình bày số trên benchmark mới.

### 3.0b Tập "cần tra nhiều lượt" trong golden

Thay hoàn toàn bằng Phụ lục C.2: 200 câu multi_hop (two_drug 70, brand_to_ingredient 65, three_intent 65)
là dòng nhóm `multi_hop` của benchmark, do generator cố định tạo; không câu nào chọn theo lỗi của hệ thống.

### 3.0c Chunk là đơn vị đọc: gộp mục tới khoảng 1.024 token, bỏ hydrate, 5 chunk mỗi lượt

Quyết định ngày 2026-10-15, plan riêng `docs/superpowers/plans/2026-10-15-chunk-reading-unit.md`,
chạy trước Task 7 của plan pha D.

- **Vấn đề:** sau khi tách tờ hướng dẫn theo heading, mỗi chunk đúng bằng một mục nên ngắn: 42.567
  chunk, trung bình 372 token, trung vị 224, 5,5 % dưới 64 token (đo bằng tokenizer Qwen3 trên text
  embedding). Backend bù bằng hydrate: với mỗi chunk trúng, truy vấn thêm cả mục hoặc hai chunk cạnh;
  91 % mục chỉ có một chunk nên bước này tốn một truy vấn mà không thêm thông tin.
- **Chunk là đơn vị đọc.** Chunk vừa là đơn vị embed, rerank, vừa là đúng văn bản LLM đọc; không
  còn hydrate. Chunker mới `chunk_document` gộp các mục liền kề của cùng một tài liệu theo thứ tự
  trong tài liệu: thêm mục kế tiếp chừng nào tổng còn dưới `TARGET_CHUNK_CHARS = 4200`; mục dài hơn
  `MAX_CHUNK_CHARS = 5600` được cắt bằng bộ cắt đoạn hiện có, rồi các mảnh được gói lại theo thứ tự
  tới `MAX_CHUNK_CHARS` thành nhiều chunk của riêng mục đó, để câu dẫn đi cùng bảng nó giới thiệu. Đo
  ở target 3.200 cho trung bình chỉ 781 token, vì nhiều tài liệu ngắn hơn target nên chunk cuối của
  tài liệu luôn non; target 4.200 cho 13.412 chunk, trung bình 1.001 token, trung vị 1.054, p99
  2.224, max 3.098 (`docs/research/paper-v2/07-dataset-review.md`). Không gộp qua tài liệu khác.
  Text chunk giữ heading của từng mục dưới dạng `## <heading>`; header context là
  `<tiêu đề> > <heading 1>; <heading 2>; ...`.
  Embedding text là header, tên colloquial chưa xuất hiện, chunk text, rồi phần mở rộng thuật ngữ
  (`compose_embedding_text`), không cắt phần nào. Riêng chunk text của bảng dài đã tới khoảng 3.100
  token (embedding text tới khoảng 3.200), nên slot embed và ubatch của embedding nâng từ 2.048 lên
  **4.096 token** (catalog Kaggle và compose local); một test giữ điều kiện chunk dài nhất vừa slot.
- **Định danh:** chunk thuộc tài liệu, nhãn gold `<document_key>:chunk-NNN`, mang `section_keys` và
  `headings` theo thứ tự. Mục (section) vẫn là đơn vị nguồn gốc: benchmark và golden giữ gold theo
  section id; một chunk trúng khi bất kỳ mục nào của nó là gold (hoặc nhãn relevance chấp nhận chunk
  đó). Câu nhiều mục: một chunk có thể thoả nhiều đơn vị bằng chứng cùng lúc.
  Id của chunk version băm từ `document_id` (đã gắn collection), danh sách `section_keys`, chunk text,
  embedding text và phiên bản chunker: cùng một tờ hướng dẫn ở hai collection, hoặc đoạn lặp lại
  trong một tờ, luôn là hai dòng riêng. `corpus gc` xoá cả point Qdrant của collection mà không release
  sống nào nhắc tới (ví dụ point còn lại sau migration 0021).
- **Bỏ hẳn hydrate ở backend:** `HydrateStrategy`, `Hydrator`, `PostgresHydrator`, `section_chunks`,
  `hydrate_window`, cột `hydrate_strategy` và bảng `section_revisions`; chunk version trỏ thẳng tài
  liệu; Qdrant payload còn `collection_id`, `document_id`, `release_ids`. Citation lưu một chunk và
  hiện đúng text đó (bỏ `strategy`, `block_chunk_version_ids`); API `CitationDetail` trả `text` thay
  danh sách chunk; frontend hiện một khối. Migration 0021, không giữ đường cũ (DB production xuất
  phát trống).
- **Ngân sách đọc:** reranker trả 5 chunk mỗi lượt (`rerank.top_n = 5`, trước là 8), vì chunk dài gấp
  ba; evidence gói theo nguyên chunk, không cắt. Vòng judge-refine lấy thêm 5 chunk mỗi vòng, tối đa
  `max_search_rounds = 3` vòng, nên evidence tích luỹ tới 15 chunk, trung bình khoảng 48.000 ký tự.
  `max_evidence_chars = 60000` (khoảng 19k token) để ngân sách không che mất vòng refine mà đóng góp
  2 đo; `pack` xếp chunk theo điểm rerank xuyên mọi vòng và bỏ nguyên chunk điểm thấp nhất khi vượt.
  `AnswerRecord.rounds` ghi số chunk và số token evidence sau mỗi vòng, bài báo cáo evidence token
  mỗi lượt theo cấu hình. Mọi chỗ nói "top 8" đổi thành 5, gồm `golden hard-candidates`, `golden trim`
  và §3.0b.
- **Benchmark:** bỏ mọi nhãn mức chunk (`expected_chunk_id`, `expected_chunk_index`,
  `expected_chunk_role`, `retrieval_granularity`, `chunk_window`, `chunk_exact`), chỉ còn gold theo
  section và `answer_mode`. Nhóm `chunk_risk` (1.000 câu) đổi thành `structured`: câu mà mục gold chứa
  bảng hoặc danh sách, vì rủi ro cắt chunk không còn, còn đọc bảng vẫn khó. Golden bỏ
  `gold_chunk_ids`, nhóm `chunk_risk` đổi tên tương ứng; schema `e2e-golden-v3`. Evidence từng vòng
  (`AnswerRecord.rounds`) ghi section key, và độ phủ gold tính trên section.
- **Pipeline corpus (pharma-lab):** rag-final chỉ còn `sections.jsonl` và `blocks.jsonl`; bỏ
  `chunks.jsonl`, `hydrate_strategy`, `section_char_count` và các bước validate đi kèm, vì backend là
  chunker duy nhất. Chế độ `RetrievalMode.INDEX_ONLY` của bundle (chỉ dùng để tắt hydrate cho bảng
  tra cứu biệt dược) bỏ theo. `PIPELINE_VERSION` lên 0.4.0.
- **Đánh đổi ghi trong bài:** chunk dài hơn nên LLM đọc khoảng 5.000 token evidence mỗi vòng thay vì
  khoảng 3.000, đổi lại bớt 5 đến 8 truy vấn DB mỗi vòng, bớt mảnh vụn và câu nhiều ý thường nằm
  trọn một chunk. Reranker chấm trên chunk dài hơn (tối đa khoảng 3.100 token, dưới ubatch 4.096), nên
  `rerank_seconds` mỗi lượt tăng và được báo riêng (§2.5). Đơn vị trích dẫn là chunk; citation recall
  vẫn chấm theo section gold nằm trong chunk nhờ `section_keys`, và text giữ `## <heading>` nên người
  đọc định vị được mục. Lý do chọn cỡ 1.024 token được kiểm bằng D7 (§4.D), không chỉ bằng thống kê.

### 3.1 Lớp hội thoại của benchmark retrieval

Thay hoàn toàn bằng Phụ lục A §3 (nhóm `conversational` 1.500 câu, mỗi dòng đặt tên theo hiện tượng và câu cha; sinh bằng luật, kế thừa gold section của câu cha).

### 3.2 Bộ e2e

- Nhóm an toàn của golden giữ 10 câu mỗi loại (§3.0b); không nâng lên 50. Kiểu tấn công kênh lựa
  chọn (Azizi et al.) và chèn nội dung tự nhiên vào câu hỏi (Xu et al.) được đo trên tập giữ lại của
  guard (§3.3, 300 lượt tấn công và ngoài phạm vi), không thêm vào golden.

### 3.3 Tập giữ lại cho ngưỡng và hiệu chuẩn

- Ngưỡng guard và judge không được chỉnh trên bộ golden. Dùng một tập hiệu chuẩn riêng lấy từ benchmark
  retrieval: 300 câu có gold section, với evidence do pipeline lấy về, nhãn "đủ bằng chứng" tính từ gold
  (top-k có chứa gold section hay không, và với đa intent là có đủ mọi section không); cộng 300 lượt tấn
  công và ngoài phạm vi sinh thêm cho guard. Báo AUROC, ECE, và độ chính xác tại ngưỡng chọn của Jev,
  kèm kiểm tra xoay thứ tự lựa chọn và tỷ lệ lật quyết định khi gọi lặp 3 lần.
- Hiệu chuẩn judge đánh giá bằng dược sĩ chấm mù giữ giao thức v1, mở rộng mẫu cho các cấu hình mới
  (50 item mỗi cấu hình chính) và báo tương quan lỗi giữa judge và người chấm theo Rao và Callison-Burch.

### 3.4 Luật chọn retrieval và reranker cho agent (bản 2026-10-25, viết trước khi tính lại số)

Không thiên vị cấu hình nào, kể cả model lớn hơn. Chọn theo hai giai đoạn, để reranker chỉ chạy trên
cấu hình đã thắng ở bước tìm. Thủ tục chính xác là mã `pharma_lab/evaluation/config_selection.py`,
chạy bằng `pharma-lab metrics select`.

1. Giai đoạn 1, tìm (chưa rerank): BM25, dense với từng embedding, hybrid RRF k=2 prefetch 50 giữ 20
   với Qwen3-Embedding-4B và 8B. Chỉ số chính Hit@20, tức gold nằm trong 20 ứng viên reranker nhận;
   chỉ số phụ Hit@5.
2. Giai đoạn 2, rerank, chỉ trên cấu hình thắng giai đoạn 1: Qwen3-Reranker-0.6B, 4B, 8B, và
   bge-reranker-v2-m3 làm đối chứng ngoài họ Qwen. Chỉ số chính Hit@5 (agent đọc 5 đoạn đầu), phụ
   MRR@10.
3. Thắng rõ: cấu hình dẫn đầu (trung bình chỉ số cao nhất) thắng một cấu hình khác khi khoảng tin
   cậy 95% bootstrap ghép cặp theo câu hỏi (10.000 lần) của chênh lệch nằm trên 0 **và** p của kiểm
   định sign-flip ghép cặp, hiệu chỉnh Holm trong họ, dưới 0,05. Mỗi giai đoạn với mỗi chỉ số là một
   họ. Cấu hình không bị thắng rõ thì hòa với cấu hình dẫn đầu; còn hòa thì xét chỉ số phụ trên các
   cấu hình hòa theo cùng luật; vẫn hòa thì chọn cấu hình rẻ nhất.
4. Tập câu: benchmark 10.000 câu trừ nhóm `conversational` (1.500) và 30 câu safety, tức 8.470 câu.
   Agent luôn viết lại câu hỏi trước khi tìm, nên câu hội thoại để nguyên lượt cuối không phản ánh
   truy vấn agent gửi; nhóm này được đo ở D5.
5. Nhãn: golden `9c6e4de6…` cùng judgments rules_version 2, chấp nhận chunk leaflet cùng hoạt chất
   cho mọi câu có gold là mục formulary, ở mọi nhóm.
6. Thứ tự chi phí khi hòa: BM25; dense theo số tham số embedding (gemma-300m, bge-m3, qwen 0,6B, 4B,
   8B); hybrid đứng ngay sau dense cùng embedding; reranker theo số tham số (bge-v2-m3, 0,6B, 4B, 8B).
7. Bảng retrieval của bài báo cáo mọi cấu hình đã chạy, theo nhóm và theo lát, kể cả cấu hình không
   được chọn và nhóm mà cấu hình thắng bị tụt.

Kết quả (2026-10-25, 8.470 câu, `pharma-lab metrics select`):

| Giai đoạn | Chỉ số | Trung bình (%) | Cấu hình thắng | Chênh với cấu hình gần nhất | Lý do |
| --- | --- | --- | --- | --- | --- |
| 1 | Hit@20 | hybrid-qwen8b 99,17; hybrid-qwen4b 98,51; dense bge-m3 97,17; dense qwen8b 97,06; dense qwen06b 95,89; dense gemma300m 95,02; BM25 94,34; dense qwen4b 91,11 | hybrid-qwen8b | +0,66 (KTC +0,47 đến +0,86; p Holm 0,0007) so với hybrid-qwen4b; thắng rõ cả 7 | chỉ số chính |
| 2 (tạm, chưa có 8B) | Hit@5 | qwen 4B 98,29; qwen 0,6B 97,86; bge-v2-m3 96,75 | Qwen3-Reranker-4B | +0,43 (KTC +0,18 đến +0,67; p Holm 0,0007) so với 0,6B | chỉ số chính |

Lịch sử: bản 2026-10-18 dùng bootstrap 1.000 lần không kèm kiểm định, thêm vế "không tụt quá 1 điểm ở
lát hay nhóm nào", chấm trên cả nhóm hội thoại, và judgments chỉ áp cho hai nhóm formulary và
multi_intent. Bốn điểm này đổi ngày 2026-10-25, sau khi đã thấy số `-v3-` giai đoạn 1: vế 1 điểm so
trung bình nhóm mà không xét cỡ mẫu (nhóm noisy 492 câu, 8 câu là 1,6 điểm) và chỉ xét cấu hình
thắng tụt chứ không xét cấu hình kia tụt bao nhiêu; judgments hai nhóm chấm cùng một câu trả lời đúng
khác nhau theo nhóm. Bài nêu cả hai bản luật và kết quả của bản cũ.

## 4. Ma trận thí nghiệm

Ký hiệu vai trò: G guard, J judge, R refine, P rephrase, A answer. Mọi cấu hình chạy trên cùng bộ
golden và cùng judge đánh giá.

### A. Phân vai theo loại model (đóng góp 1)

Ba model dùng xuyên suốt bài (giá USD mỗi triệu token vào/ra, ngày 2026-10-14): một model mở rẻ và một model thương mại rẻ, cộng một model nặng làm trần (lý do ở §1):

| Nhóm | Model | Giá | Đường gọi |
| --- | --- | --- | --- |
| Mở, rẻ | Qwen3.5-9B | 0,10 / 0,15 | tự host Kaggle, llama.cpp Q8_0, hai bản trên 2 T4 |
| Thương mại, rẻ | Gemini 3.8 Flash | 0,75 / 3,75 | cli-proxy-api, thinking low |
| Nặng, trần tham chiếu | Claude Opus 5.5 | 4 / 20 | cli-proxy-api, adaptive effort minimal |

| Cấu hình | G, J | R | P, A | Ghi chú |
| --- | --- | --- | --- | --- |
| A1 gemini (v1) | gemini-3.1-flash-lite, 3.8-flash | LLM | 3.1-flash-lite, 3.8-flash | đã có, chạy lại ở thinking low |
| A2 llm-only, mỗi model | cùng model | LLM | cùng model | ba run, mọi vai trò trên một LLM |
| A3 jev + mỗi model | Jev | template | cùng model | ba run, cấu hình chính của bài |
| A4 jev + qwen9b, refine LLM | Jev | LLM | Qwen3.5-9B | tách tác dụng của refine template |

Kết quả: bảng chính v2 với truthfulness, nugget recall, hallucination, severe harm, faithfulness,
citation recall, các metric an toàn, giây mỗi lượt p50 và p95, USD mỗi 1.000 lượt; hình teaser
truthfulness theo giây và theo USD, mỗi cấu hình một điểm; hình tách thời gian mỗi lượt theo bước.

### B. Refinement theo độ tin cậy (đóng góp 2)

- Trên A3 với Qwen3.5-9B và với Gemini 3.8 Flash: τ ∈ {0, 0,3, 0,5, 0,7, 0,9, 1}. Trên A2 Qwen3.5-9B: cùng
  dải với độ tin cậy nói ra của LLM judge.
- Báo theo Qian et al. 2026: đường biên chất lượng so với chi phí và so với độ trễ, tỷ lệ refine thực
  tế, chi phí của chính bước judge, độ ổn định của τ khi chuyển model (τ chọn trên Qwen3.5-9B áp sang
  Gemini 3.8 Flash và Claude Opus 5.5, chỉ ở τ đã chọn), tỷ lệ gây hại khi bỏ refine. Không quét
  τ trên Opus 5.5.
- Phân tích tương quan lỗi: judge nói "đủ" nhưng câu trả lời thiếu key fact, theo nhóm câu hỏi.

### C. Graph routing so với ReAct trên ba model (đóng góp 3)

Hai nhánh dùng cùng một LLM cho mọi vai trò, để khác biệt chỉ còn là ai điều khiển. Nhánh graph
routing là A2 của model đó; nhánh ReAct là một run mới cùng model, nên có ba run ReAct (Qwen3.5-9B,
Gemini 3.8 Flash và Claude Opus 5.5). Các cấu hình có decision model (A3) không thuộc so sánh này mà
được vẽ thêm như điểm tham chiếu. Câu hỏi của bài là "với một model rẻ, mở hay thương mại, kiến trúc
nào cho chất lượng cao nhất trên mỗi USD và mỗi giây, và kết luận có giữ khi model đủ mạnh như Opus
5.5 không", không phải "cỡ model nào thì ReAct bắt kịp".

- Giữ cố định: tool, retriever, reranker, mức bằng chứng, định dạng trả lời, reasoning effort, nhiệt độ,
  judge đánh giá. Giao diện gọi được nêu rõ: structured output cho pipeline, native tool calling cho
  ReAct (Patel et al. 2026 chỉ ra giao diện là một nhiễu).
- Báo: hình mặt phẳng chất lượng so với USD và so với giây, mỗi model hai điểm nối bằng một đoạn
  (graph routing và ReAct); bảng thất bại của ReAct theo loại (chạm trần vòng, tool call sai định
  dạng, gọi trùng, trả lời không trích dẫn); cùng kết quả trên 50 item nhiều lượt và 10 item injection
  vì ReAct không có rephrase và guard chỉ ở ngoài.
- Qwen3.5-9B tự host trên Kaggle, Gemini 3.8 Flash và Claude Opus 5.5 qua cli-proxy-api (§2.1b);
  bài ghi rõ phần cứng, precision và mức thinking.

### D. Retrieval

- D1 dense Qwen3-Emb-4B + Qwen3-Reranker-4B, so với hybrid + reranker (trả lời "sao phải hybrid").
- D2 ablation enrichment: một biến thể duy nhất không enrichment (không header, glossary, colloquial)
  trên hybrid + rerank, trên toàn benchmark chín nhóm; enrichment lộ rõ nhất ở colloquial,
  glossary, leaflet và noisy.
- D3 bảng retrieval theo nhóm câu hỏi và theo intent cho các cấu hình chính; độ khó không còn là
  trường của benchmark, trục thay thế là "một lượt top 5 đã phủ đủ gold hay chưa" tính từ cấu hình
  hybrid + rerank.
- D4 cột chi phí dense: số tham số, dung lượng Q8_0 và tốc độ encode query trên T4, thay cho chỉ có dimension.
- D5 chiến lược truy vấn hội thoại Q0 đến Q6 (§3.1).
- D6 đường cong retrieval đến e2e: chạy one-step và full với bm25, dense, hybrid k=60, hybrid k=2 không
  rerank, hybrid có rerank; vẽ truthfulness theo Hit@5 và nDCG@5 vì pipeline đọc 5 chunk mỗi vòng;
  giải thích vì sao bỏ reranker không đổi e2e ở v1 (vòng judge-refine bù).
- D7 ablation đơn vị đọc, chỉ ở mức retrieval: chunk theo từng mục (chunker trước §3.0c) so với chunk
  gộp tới 1.024 token, cùng embedding, cùng hybrid + rerank, cùng benchmark, chấm theo section gold.
  Báo Hit@5, nDCG@5, số chunk, token trung bình, và tỷ lệ câu đa intent mà một chunk phủ đủ mọi mục
  gold (§3.0b). Chỉ tốn một lượt embed và một run benchmark, không tốn LLM; trả lời câu "vì sao
  1.024 token" bằng dữ liệu.

### E. Sửa các điểm review v1

- Khoảng tin cậy trong mọi bảng e2e (CSV đã có, bảng LaTeX sinh thêm).
- Lệnh `e2e compare --run A --run B` cho kiểm định ghép cặp xuyên run (Gemini full so với Qwen full).
- Ablation rephrase và judge-refine với Qwen3.5-9B; ablation guard với cả hai setting.
- Phân loại lỗi còn lại của full agent từ `errors.md` thành bảng taxonomy.
- Phân tích citation recall: câu không trích dẫn so với trích dẫn sai chunk (chunk không chứa section
  gold), và trong các chunk đúng, phần key fact mà judge thấy có trong text chunk được trích.
- Thí nghiệm phụ "decision model làm judge đánh giá": chấm lại 450 item có nhãn dược sĩ bằng Jev per-key-fact, so với
  gemini-3.1-flash-lite và nhãn dược sĩ; báo κ, chi phí và giây.
- Sửa số liệu và câu chữ đã liệt kê trong review (Hit@5 3,7 so với 3,8; BGE-gemma có cải thiện nDCG;
  "unanswered" so với missing; header Table 3; top 5 từ 20 ứng viên mỗi câu truy vấn, tối đa 40 mỗi vòng; footnote repo).

## 5. Thống kê và báo cáo

- Tỷ lệ: Wilson; trung bình: bootstrap percentile 10.000; so sánh: sign-flip ghép cặp, Holm trong một
  họ so sánh. Họ so sánh khai báo trước: mỗi bảng là một họ.
- Judge: AUROC, ECE (10 bin), Brier cho decision model trên tập giữ lại; PPI cho metric dựa judge.
- Chi phí: USD mỗi 1.000 lượt theo bảng giá ngày ghi rõ, token mỗi lượt để người đọc tính lại; cost of
  pass. Độ trễ: p50, p95, concurrency 1, vùng địa lý.
- Mọi phản hồi decision model lưu thô; mọi run ghi `provider`, phiên bản model, ngày.

## 6. Thay đổi bài báo

- Cấu trúc IMRaD tạp chí: Introduction, Related Work, Materials and Methods, Results, Discussion
  (principal findings, comparison with prior work, implications, limitations), Conclusion.
- Tiêu đề đổi để nêu đủ benchmark, decision model và chi phí; chốt khi có kết quả.
- Related Work thêm năm đoạn: workflow so với agent; adaptive retrieval và gating; chi phí và độ trễ;
  decision model và guardrail nhỏ; RAG hội thoại và viết lại; cập nhật đoạn tiếng Việt với ViRE, ViMedAQA.
- Methods mô tả decision model như một provider, bộ câu hỏi đóng băng, ngưỡng và cách chọn, ReAct và
  quy tắc công bằng, giao thức đo độ trễ và chi phí. Methods nêu chunk là đơn vị embed, rerank, đọc
  và trích dẫn, kèm thống kê token của §3.0c và kết quả D7; citation recall chấm theo section gold
  nằm trong chunk được trích.
- Limitations viết theo `03-jev-typesafe.md` §8 và `05-literature-survey.md` §H: closed weights, early
  access, giá có thể được trợ, hiệu chuẩn vendor tự khai, tiếng Việt không có số liệu công bố, tấn công
  kênh lựa chọn và ngữ cảnh tự nhiên, decision model không phải cổng an toàn duy nhất, độ trễ đo từ
  Việt Nam đến endpoint Mỹ, kết quả kiến trúc chỉ kiểm trên ba model, Opus 5.5 không tắt được
  thinking nên chạy ở mức thấp nhất thay vì tắt hẳn.
- Table 2 gọn lại (bỏ MRR@30, bỏ Hit@30 ở khối reranker) để nhường chỗ cho hàng mới.

## 7. Thứ tự thực hiện

Mỗi pha là một plan riêng, chạy xong mới sang pha sau trừ khi ghi khác. Pha D đứng trước pha 0; hai
pha có thể gối nhau ở phần mã vì pha 0 không phụ thuộc dữ liệu, nhưng mọi run đo đều chờ pha D.

0. **Pha D, dữ liệu.** §3.0: tách leaflet theo heading, release mới, sinh lại benchmark, viết lại 50
   item golden, chạy lại bảng retrieval (năm embedding và bốn reranker trên Kaggle). Mọi pha
   sau chạy trên release và benchmark này.
1. **Pha 0, hạ tầng đo.** §2.1b (Opus 5.5 qua cli-proxy-api, kiểm tra reasoning `none` của judge
   trên nhãn dược sĩ v1), §2.5 và §2.6 (trừ enrichment), `e2e compare`, pricing, steps latency, bảng
   cost. Xác nhận bằng cách chạy lại A1 và A2 Qwen3.5-9B (tự host Kaggle) và so với bảng v1 có thêm
   cột giây và USD.
2. **Pha 1, decision model.** §2.1, §2.2, §2.3, §3.3. Đo token Vietnamese trên Jev; chạy tập hiệu
   chuẩn; chọn τ; chạy A2 và A3 cho ba model, A4, và quét B. Kết quả đóng góp 1 và 2.
3. **Pha 2, ReAct.** §2.4 và ma trận C. Có thể chạy song song pha 1 vì không chung mã, chỉ chung hạn
   mức API.
4. **Pha 3, retrieval.** §3.1, D1 đến D7, enrichment §2.6. D1, D6 và D7 làm trước vì rẻ.
5. **Pha 4, e2e bổ sung.** §3.2, các mục E còn lại, hiệu chuẩn dược sĩ mở rộng.
6. **Pha 5, viết.** §6, hình và bảng, build sạch warning.

Tiêu chí chấp nhận mỗi pha: lint, type và test của backend và pharma-lab xanh; run có `run.json` đầy đủ
identity; báo cáo sinh bằng lệnh có sẵn chứ không chép tay; số liệu vào bài chỉ từ file báo cáo.

Ngân sách tiền thật, ước với chunk mới (§3.0c): mỗi item khoảng 1 lời gọi guard nhỏ cộng 1,5 vòng
judge với evidence tới 19k token, tức khoảng 16k token Jev mỗi item và 16M token mỗi run 1.000 item,
khoảng 0,68 USD mỗi run theo giá niêm yết. Ba run A3, một run A4, 12 điểm quét τ và tập hiệu chuẩn
§3.3 cộng lại khoảng 12 đến 16 USD, cộng phí OpenRouter nếu có; đó là khoản tiền thật duy nhất. Qwen3.5-9B và reranker chạy trên quota GPU Kaggle; mọi run Qwen (A2, A3, A4, ReAct,
quét τ, ablation) phải xếp theo quota tuần của các account Kaggle.
Gemini 3.8 Flash, Claude Opus 5.5 và judge gemini-3.1-flash-lite đi qua proxy thuê bao nên không
tốn thêm; giá niêm yết của chúng (khoảng 240 USD cho ba run Opus 5.5, 40 USD cho judge, ước gấp đôi bản 500 item) chỉ xuất
hiện trong bảng chi phí của bài. Quota Claude có hạn nên các run Opus 5.5 xếp sau run của hai model
rẻ. Mỗi run chạy thử 20 item trước khi chạy đủ.

## 8. Rủi ro

- Jev early access, giới hạn và giá có thể đổi, và id `~typesafe/jev-latest` trên OpenRouter có thể
  trỏ sang phiên bản mới giữa chừng: ghi phiên bản trả về mỗi lời gọi, dừng run nếu phiên bản đổi,
  lưu phản hồi thô, chạy pha 1 sớm.
- Jev tiếng Việt: người dùng đã thử ổn, nhưng tập hiệu chuẩn §3.3 là bằng chứng trong bài. Nếu AUROC
  thấp thì LLM judge (A2) là đối chứng, và kết quả vẫn là finding.
- Nhiều noul trong một request thiên về "có": ngưỡng chỉnh trên tập giữ lại, báo AUROC thay vì chỉ độ
  chính xác tại 0,5.
- Model rẻ có thể gọi tool kém trong ReAct: đó là kết quả, nhưng phải tách lỗi harness khỏi lỗi model
  bằng bảng thất bại theo loại và biến thể có và không có chặn gọi trùng.
- Quota GPU Kaggle và giới hạn thời gian mỗi phiên kernel: mỗi run chạy được tiếp sau khi kernel
  khởi động lại vì harness đã ghi `answers.jsonl` từng item; xếp run Qwen theo quota và ưu tiên
  cấu hình chính (A2, A3, ReAct) trước quét τ và ablation.
- Rerank trên chunk dài gấp ba: mỗi câu truy vấn giữ 20 ứng viên sau RRF (`candidate_k = 20`, prefetch
  50 mỗi nhánh, trần 40 mỗi vòng), backend và benchmark như nhau. Chốt ngày 2026-10-15: hạng 21–30 chỉ
  giữ gold của khoảng 1 % câu (v1: hybrid Hit@10 95,9 %, Hit@30 99,2 %) mà tốn một phần ba chi phí
  rerank, cả trên Kaggle lẫn production; 10 thì chặn khoảng 4 % câu ngay từ đầu. Bảng retrieval chấm
  10.000 câu × 20 ứng viên × khoảng 1.000 token, tức khoảng 200 triệu token mỗi reranker; nếu không vừa
  quota tuần thì chạy tiếp sau khi Kaggle reset, harness giữ điểm từng cặp trong cache.
- Ngân sách evidence 60.000 ký tự cộng prompt và lịch sử phải vừa slot 32.768 của Qwen3.5-9B: run thử
  20 item ở pha 0 kiểm tra không có lượt nào chạm trần ngữ cảnh; nếu có thì hạ `max_evidence_chars`
  cho mọi cấu hình cùng lúc, không hạ riêng một nhánh.
- Bốn slot 32.768 token mỗi bản 9B Q8_0 trên một T4 là tính toán (KV cache 4 GiB cạnh 9,5 GB
  weights), chưa đo: lần chạy kernel đầu của `e2e run --backend kaggle` xác nhận server lên được; nếu
  hết VRAM thì giảm còn 3 slot. ReAct vẫn ghi số lượt chạm trần ngữ cảnh vào bảng thất bại.
- Credential OAuth Antigravity hoặc Claude của cli-proxy-api hết hạn, hết quota, hoặc đổi danh sách
  model được dùng: proxy trả `auth_unavailable`, khi đó chép lại credential từ ProxyPal; `pin_judge`
  và run identity vẫn ghi tên model nên run tiếp tục được sau khi khôi phục.
- Độ trễ đo từ Việt Nam tới endpoint ở xa (kernel Kaggle, gateway của proxy): số tuyệt đối gồm
  mạng, và Qwen trên T4 không cùng phần cứng với model thương mại; bài chỉ so latency giữa kiến
  trúc trên cùng một model (§2.5).
- Giấy phép và điều khoản Jev về công bố benchmark: kiểm tra Master Customer Agreement trước khi công bố.

## 9. Ngoài phạm vi

Huấn luyện hoặc fine-tune bất kỳ model nào; corpus mới hoặc câu hỏi người dùng thật; kiến trúc đa agent;
benchmark decision model tổng quát ngoài miền thuốc; thay judge đánh giá chính của bài.

## Phụ lục A. Dữ liệu eval v3: benchmark 10.000 câu (golden e2e: xem Phụ lục C)

Số trong phụ lục này đo trên các run `-v2-`; golden đã được dựng lại sau đó (xem "Việc đang mở" ở đầu). Thay §3.0b, §3.1 và phần dữ liệu của §4.

### 1. Chẩn đoán

#### 1.1 Câu sai từ luật sinh (không phải câu khó)

| Lỗi | Số câu | Nguồn |
| --- | --- | --- |
| Câu "dán nguyên đoạn văn" có gold lệch mục (chunk → section map sai) | 81 | `lexical` formulary, `section_coverage` structured |
| Câu chung chung ("X là thuốc gì", "Tìm thông tin về X", "X có tác dụng phụ gì") gắn vào mục quy chế, tương kỵ hoặc hướng dẫn xử trí ADR | 479 | formulary, structured, noisy |
| Hỏi "có thai hoặc cho con bú" nhưng gold chỉ một mục | 222 | formulary, conversational |
| Tên sản phẩm bị cắt giữa chừng ("Agirenyl 5000IU phòng và có…") | 168 | leaflet, leaflet_short |
| colloquial: một alias trỏ nhiều sản phẩm; biến thể alias lặp; gold một dòng; câu trùng khác gold | 165 / 392 / 93 / 78 | luật colloquial |
| glossary: 68% là một thuật ngữ (TKTW); 8% mục đã viết đủ cụm lời thường | 150 / 18 | luật glossary |
| conversational: lịch sử là đoạn văn dán, câu trả lời cố định lấy sai mục; câu kiểu tiêu đề mục; trùng | 103 / 44 / 35 / 71 | kế thừa lỗi câu cha |
| multi_hop: "Tôi đang dùng" với thuốc tiêm, gây mê | ~30 | luật two_drug |

Những câu này không làm benchmark khó hơn, chỉ làm nhiễu: chúng hạ số của mọi cấu hình như nhau và
che chênh lệch giữa các tầng.

#### 1.2 Hiệu ứng trần

Mỗi ablation chỉ đổi kết quả một lượt (gold trong top 5) ở một phần nhỏ số câu:

| Ablation | Tỉ lệ câu tầng đầy đủ thắng (toàn 10k) | Nhóm thắng nhiều nhất |
| --- | --- | --- |
| hybrid so với BM25 | 13,0% | noisy 33,2%, multi_intent 20,2%, structured 18,3% |
| enrichment so với không | 9,3% (không rerank); colloquial 28,9%, glossary 14,6% | leaflet 15,0%, structured 12,8%, noisy 12,2% |
| hybrid so với dense | 3,9% | leaflet_short 3,8% |
| rerank 4B so với không | 3,6% | noisy 10,2%, leaflet 5,4% |
| rerank 4B so với 0.6B / 8B | 1,0% / 0,7% (và thua 1,7% / 1,0%) | không nhóm nào |

Hệ quả cho bài: con số tổng trên benchmark sẽ nhỏ với mọi tầng trừ hybrid và enrichment. Đó là sự
thật của corpus này (retrieval đã gần trần), khớp với câu chuyện của bài, nhưng mỗi tầng cần một
**lát cắt mục tiêu** nơi hiệu quả của nó lộ rõ.

#### 1.3 Lát cắt theo cách dựng câu tách được tầng

Đo trên 10k, lát cắt định nghĩa từ câu và corpus, không từ kết quả hệ thống:

| Lát cắt (định nghĩa) | Tầng | Tầng thắng trong lát | Ngoài lát |
| --- | --- | --- | --- |
| Mục gold không chứa tên thuốc/sản phẩm (chỉ header mang tên) | enrichment | 14,3% | 6,1% |
| Trùng từ câu hỏi và mục gold thấp (< 35%) | dense trong hybrid | 7,3% | 2,8% |
| Trùng từ thấp | hybrid so với BM25 | 15,6% | 11,2% |
| Biệt dược thuộc họ ≥ 3 sản phẩm cùng tên đầu | rerank | 4,1% | 3,5% |

Lát header và trùng từ tách tốt; lát "họ sản phẩm" chưa tách được rerank, cần định nghĩa sắc hơn
(cùng hoạt chất và cùng mục, khác hàm lượng hoặc dạng bào chế).

#### 1.4 Probe chọn theo kết quả hệ thống là luẩn quẩn

`rerank_probe`, `lexical_probe`, `semantic_probe` được chọn ở chỗ tầng đó thắng, nên trên golden
chúng thắng theo định nghĩa (21/22 câu thắng ròng của rerank là probe; trên câu tự nhiên chênh gần
0). `retrieval_miss` và `noisy_retry` chọn ở chỗ hệ đầy đủ trượt, nên ở đó ablation lại thắng. Reviewer
sẽ bác cả hai.

### 2. Nguyên tắc

1. **Đúng trước, khó sau.** Mỗi câu phải: là câu người dùng thật có thể hỏi; hiểu được (kể cả qua
   lịch sử); mục gold trả lời đủ và chỉ những gì được hỏi. Đóng băng chỉ khi audit lấy mẫu mỗi nhóm
   (25 câu, người duyệt Fable) có tỉ lệ lỗi dưới 5%.
2. **Độ khó định nghĩa từ cách dựng câu, không từ kết quả hệ thống.** Mỗi tầng có một lát cắt mục
   tiêu định nghĩa bằng thuộc tính của câu và corpus; bài báo cáo số tổng và số trong lát.
3. **Một benchmark xuyên suốt.** Đúng 10.000 câu, golden e2e (1.000 câu, Phụ lục C.2) là các dòng của nó; mọi bảng
   retrieval và e2e theo cùng nhóm và cùng lát.
4. **Ngân sách.** Benchmark chỉ chấm bằng retrieval; mọi lời gọi LLM chỉ trên golden. Ngoại lệ ghi
   rõ: decision model Jev trên bộ hiệu chỉnh 300 + 100 câu (khoảng 0,2 USD, không sinh văn bản).
5. **Tách bộ hiệu chỉnh khỏi golden.** Bộ hiệu chỉnh ngưỡng không chứa câu nguồn của golden hay câu
   cha của câu multi-turn golden.

### 3. Benchmark 10.000 câu

#### 3.1 Sửa luật sinh câu (thượng nguồn, `evaluation build`)

- Bỏ dạng câu "dán đoạn văn" (`lexical` dạng trích nguyên văn, `section_coverage` fill): không phải
  câu người dùng hỏi; thay bằng câu template cùng mục.
- Câu chung chung chỉ gắn vào `thong-tin-chung` hoặc `chi-dinh` (câu "là thuốc gì"),
  `tac-dung-khong-mong-muon-adr` (câu tác dụng phụ); không bao giờ vào `thong-tin-qui-che`,
  `tuong-ky`, `huong-dan-cach-xu-tri-adr`.
- Câu hỏi gộp thai kỳ và cho con bú: gold gồm cả `thoi-ky-mang-thai` và `thoi-ky-cho-con-bu`,
  `answer_mode = multi_required`; hoặc tách thành hai câu.
- Tên sản phẩm: dùng `brand_name` (cắt dạng bào chế và công dụng đúng ranh giới), không cắt giữa từ.

#### 3.2 Nhóm và cỡ

| Nhóm | Cỡ | Tầng chứng minh | Ghi chú |
| --- | --- | --- | --- |
| formulary | ~3.100 | nền, hybrid, enrichment header | lấy mẫu theo intent và lát trùng từ |
| leaflet | ~1.550 | enrichment header, rerank (họ sản phẩm) | lấy mẫu theo lát header và họ sản phẩm |
| structured | 1.000 | chunk gộp, hybrid | sau khi bỏ câu dán đoạn |
| leaflet_short | 500 | nền | sau khi sửa tên cắt |
| noisy | 500 | hybrid (BM25 yếu), rerank, rephrase | |
| multi_intent | 500 | chunk gộp, judge đếm intent | |
| colloquial | ~400 | enrichment colloquial | sửa luật, mục 3.3 |
| glossary | ~300 | enrichment glossary | sửa luật, mục 3.3 |
| conversational | 1.500 | rephrase, D5 | sửa luật, mục 3.3 |
| multi_hop | 300 | judge + refine, graph so với ReAct | sửa luật, mục 3.3 |
| safety | 30 | guard | không có gold |

Cỡ formulary và leaflet là phần còn lại để tổng đúng 10.000.

#### 3.3 Sửa các nhóm sinh thêm

- **colloquial**: một alias một sản phẩm (alias trỏ nhiều sản phẩm thì `any_acceptable` với gold là
  mục tương ứng của mọi sản phẩm); tối đa hai biến thể alias mỗi nhóm sản phẩm (ưu tiên alias ít trùng từ với tên); gold ít nhất 40 ký tự (bỏ câu rỗng kiểu "Không có."); bỏ alias
  là tên chính thức (tên tiếng Anh in trên hộp); trải trên mọi sản phẩm có alias.
- **glossary**: thêm thuật ngữ Dược thư viết tắt (ADR, HIV, AIDS, COX-2, ACE, PPI, SSRI, NSAID, MAO,
  TKTW, ECG, GFR, HBV, COPD, INR, QT, G6PD, LDL, HbA1c…) với cụm lời thường tự nhiên; mỗi thuật ngữ tối
  đa 25% nhóm; chỉ giữ mục chưa viết cụm lời thường.
- **conversational**: câu cha chỉ là câu dạng hỏi đã qua sửa 3.1; câu trả lời cố định lấy từ chính
  mục gold của câu lịch sử; thay câu kiểu tiêu đề ("còn thông tin chung thì sao") bằng câu tự nhiên;
  khử trùng (lượt cuối, gold); `topic_switch` ghi là đối chứng (lượt cuối là câu đầy đủ).
- **multi_hop**: bỏ vai "Tôi đang dùng" cho thuốc tiêm hoặc dùng trong bệnh viện, dùng câu hỏi trung
  tính; ghi `parallel` (two_drug) và `sequential` (brand_to_ingredient); `three_intent` đổi tên
  `multi_section`.

#### 3.4 Thuộc tính lát cắt ghi trên từng dòng

Mỗi dòng có thêm trường `slices` tính khi assemble, không dùng kết quả hệ thống:

- `header_dependent`: mục gold không chứa từ đầu của tên thuốc/sản phẩm.
- `name_variant`: câu hỏi không viết nguyên văn chữ nào của tên thuốc/sản phẩm (gõ sai, không
  dấu, gọi cách khác). Thay `low_overlap`: độ trùng từ với mục gold không tách được lớp dense
  (mọi ngưỡng thử dưới 2 lần), tên thuốc thì tách được.
- `sibling_products`: sản phẩm có biến thể cùng hoạt chất và cùng mục, khác hàm lượng hoặc dạng
  (định nghĩa sắc hơn "họ sản phẩm"; cần kiểm lại tỉ lệ rerank thắng trước khi dùng).
- `multi_chunk`: các mục gold nằm ở từ hai chunk trở lên.

Báo cáo retrieval có bảng theo nhóm và bảng theo lát.

Kiểm trước trên run v2, 5.831 dòng không đổi, tỉ lệ dòng mà lớp thắng (top 5) trong và ngoài lát:

| Lát | Lớp (đủ so với bỏ) | Trong lát | Ngoài lát | Gấp |
| --- | --- | --- | --- | --- |
| header_dependent | hybrid so với plain | 14,0% | 5,6% | 2,5 |
| name_variant | dense so với BM25 | 46,2% | 14,1% | 3,3 |
| name_variant | hybrid so với BM25 | 41,0% | 12,9% | 3,2 |
| sibling_products | rerank 4B so với không rerank | 9,2% | 3,2% | 2,9 |
| multi_chunk | chunk gộp so với chunk theo mục | 34,4% | 10,1% | 3,4 |

Số chính thức đo lại trên run `-v3-` (Task 6).

### 4. Golden e2e

Thay bằng Phụ lục C.2 (golden v4, 1.000 câu, ngày 2026-10-25). Golden v3 (500 câu, sha `9e2769ca…`)
có tầng "trượt vòng 1" (retrieval_miss 25, noisy_retry 25, cùng 7 câu three_intent lấy từ câu đa intent
bị trượt) chọn từ lỗi của hybrid + rerank 4B; tầng này bỏ hẳn, 93 câu multi_hop sinh theo cấu tạo được
giữ, mọi câu còn lại của v3 giữ khi vẫn thuộc tầng mới.

### 5. Quy tắc báo cáo (bài báo)

- Mọi khẳng định retrieval lấy từ benchmark 10k, có bảng theo nhóm và theo lát.
- Ablation trên golden báo theo tầng golden (`tier` trong report); D6 và các hàng retriever, reranker ở
  e2e chỉ trên tầng `natural_and_multi_hop`; tỉ lệ cứu đo trên mọi câu mà chính run trượt ở vòng 1.
- Truthfulness báo cả số thô và số tái trọng số theo tỉ lệ nhóm benchmark.
- Khai báo trước các so sánh có kiểm định (loop: tất cả / multi_hop / cứu có điều kiện; τ: 0 so với τ*,
  τ* so với 1, Jev so với độ tin cậy nói ra) với Holm; Jev so với LLM judge là non-inferiority với biên
  4 điểm truthfulness và 3 điểm nugget recall (Phụ lục C.3).
- D7 thêm so sánh cùng ngân sách token (mục ở k ≈ 15 so với chunk gộp k = 5).
- Reranker và retriever của agent: chọn theo luật §3.4, không theo kết luận viết trước.

### 6. Kiểm chứng trước khi đóng băng

1. Audit lấy mẫu mỗi nhóm benchmark (25 câu, Fable): lỗi dưới 5%.
2. Bảng phân biệt: mỗi tầng có lát cắt mà tỉ lệ thắng trong lát ít nhất gấp đôi ngoài lát (đo trên
   run `-v3-`).
3. Golden: audit độc lập toàn bộ câu mới và mẫu 60 câu cũ.
4. `golden build` qua với kiểm tra mọi câu là dòng benchmark; câu multi_hop phải là dòng nhóm `multi_hop`
   cùng loại.

#### 6.1 Sổ audit benchmark (Fable 5.1, rubric `data/work/benchmark-audit/audit-rubric.md`)

Mỗi vòng lấy mẫu mới 25 câu mỗi nhóm (275 câu), dựng lại benchmark sau mỗi lần sửa luật.

| Vòng | Lỗi | Tỉ lệ | Nhóm còn từ 5% | Luật sửa sau vòng |
| --- | --- | --- | --- | --- |
| 1 | 22/275 | 8,0% | colloquial 20%, noisy 16%, leaflet_short 12%, multi_hop 12% | gold rỗng, thai kỳ/cho con bú theo câu hỏi, tên cắt dở, alias phải có tên riêng, B là thuốc tương tác thật, lịch sử không trùng mục gold |
| 2 | 8/275 | 2,9% | structured 12%, leaflet 8%, leaflet_short 8% | tên cắt ở mọi vị trí, mục thay thế cùng thuốc, câu liều chỉ nhận mục liều, vắc xin không hỏi điều trị |
| 3 | 10/275 | 3,6% | formulary 12%, leaflet 8%, leaflet_short 8%, structured 8% | câu hỏi tên biệt dược giữ mục tên thương mại, mục thay thế trong cùng chuyên luận, bỏ tiêu đề dán, viết lại mẫu "người có thai hoặc có chống chỉ định" |
| 4 | 6/275 | 2,2% | leaflet 8% | câu "cần lưu ý gì" chỉ nhận mục thận trọng, sản phẩm dùng ngoài không ghép chuyên luận toàn thân |
| leaflet 5 | 3/50 | 6,0% | | "phòng," một từ vẫn là tên cắt, alias leaflet phải có tên riêng |
| leaflet 6 | 2/60 | 3,3% | | mục thay thế cùng thương hiệu, từ chỉ màu không là tên riêng |

Sau luật cuối, 110 câu leaflet đã audit ở hai vòng có chủ đích còn 1 lỗi (≈1%). Benchmark đóng băng
ngày 2026-10-18 bằng `evaluation assemble` (đúng 10.000 câu).

1. Sửa luật sinh câu benchmark gốc (3.1) và chạy lại `evaluation build`; giữ id câu cũ khi câu không
   đổi để cache dùng lại.
2. Sửa ba nhóm sinh thêm (3.3), thêm `slices` (3.4), assemble.
3. Audit benchmark (6.1); lặp tới khi đạt.
4. Golden: thay câu lỗi, chọn lại colloquial và glossary, tầng lát cắt, cân lại multi_hop; Fable duyệt;
   audit (6.3).
5. Chạy ma trận retrieval `-v3-`; kiểm bảng phân biệt (6.2).
6. Cập nhật spec, plan, Methods.

## Phụ lục B. Chạy trên Kaggle: local-first, nối lại được, nhiều tài khoản

Thay phần "Đường gọi model" của §2.1b và §2.5 (không tunnel; mọi bước GPU chạy trong kernel).

### 0. Vì sao

Ngày 2026-10-19 account acc2 bị khoá vì một notebook `rerank-serve` mở tunnel cloudflared. Ngày
2026-10-22 Kaggle gỡ khoá và gọi đó là "false positive" của hệ thống tự động. Điều khoản của Kaggle
không nhắc tunnel (đã đọc Terms, Community Guidelines, Notebooks docs ngày 2026-10-23), nhưng thực thi
là tự động và theo quyết định của họ, và mỗi vi phạm chỉ kháng cáo một lần. **Quyết định của người dùng
(2026-10-23): mọi thứ chạy trong kernel, không tunnel, không mở cổng.** Test
`tests/integrations/kaggle/test_no_external_exposure.py` giữ quy tắc này.

**Phạm vi (người dùng, 2026-10-23): cơ chế áp dụng cho mọi bước dùng Kaggle**, không chỉ bước e2e cuối:
embed corpus, embed truy vấn, rerank, các lượt đo profile và e2e. Phần e2e (§4.1 đến §4.8) là bộ
chuyển đổi khó nhất vì hiện chưa có resume nào; §4.9 nêu lớp điều phối chung và cách từng bước còn lại
cắm vào.

Spec v2 gốc được viết trước đó nên vẫn giả định mỗi model là một server riêng trên một account và
một tunnel nối về máy. Cần thiết kế lại cách chạy sao cho đạt ba điều người dùng yêu cầu:

1. **Ra kết quả nhanh nhất** với quota GPU hiện có (30 giờ mỗi tuần mỗi account; ngày 2026-10-23
   còn khoảng 6 đến 8 giờ mỗi account, reset sáng 2026-10-24).
2. **Dừng và chạy tiếp dễ dàng**, bất kỳ lúc nào, kể cả khi kernel chết giữa chừng.
3. **Đổi account dễ dàng** mà không mất gì và vẫn làm tiếp.

### 1. Hiện trạng (đã đọc code)

Stage `E2E_RUN` hiện có (`integrations/kaggle/e2e_stage.py`, `e2e/kernel_worker.py`,
`e2e/kernel_harness.py`, `e2e/kaggle_run.py`) chạy cả agent trong một kernel: LLM Qwen3.5-9B Q8_0 ở
GPU0, reranker Q8_0 ở GPU1, embedding trên CPU, Postgres và Qdrant cài ngay trong kernel, harness
`run_e2e` gọi qua localhost. Điểm yếu:

- Một lệnh là **một kernel trên một account**. Worker chỉ đóng gói `e2e_output.tar` **sau khi harness
  chạy xong**; kernel chết, hết giờ hay hết quota giữa chừng thì không có gì để tải về.
- Worker **không biết hạn của phiên** (rerank dùng `worker_deadline`, e2e thì không) và không bao giờ
  ghi kết quả dở.
- Kernel mới luôn bắt đầu từ thư mục trống: không nhận lại phần đã làm.
- CLI từ chối chạy nếu thư mục đích đã có `answers.jsonl` (`check_targets`) và báo lỗi, không ghi gì,
  nếu kernel chưa xong mọi câu. Gọi `run_kaggle_stage(max_runs=1, resume_remote=False)`.
- Mỗi phiên tốn thời gian dựng môi trường (pip, apt Postgres, tải Qdrant, nạp corpus, khởi động ba
  server). Chưa có số đo; ước lượng khoảng nửa giờ.
- `kernel_harness` không nhận `--pipeline-option`, nên các cấu hình biến thể của v2 (`guard=false`,
  `refine_threshold`, `refine_mode`...) chưa chạy được trên Kaggle.

Hạ tầng đã có và dùng lại được (pipeline rerank đang dùng đúng mô hình này, xem
`evaluation/rerank_service.py`, `rerank_cache_checkpoint.py`):

- `sessions.run_account_sessions`, `reserve_session_account(_waiting)`, `QuotaExhausted`,
  `StopReason`: chọn account theo quota còn lại, khoá theo account giữa các lệnh local, tự xoay
  account, dừng khi hết quota hoặc không tiến triển. Kaggle cho mỗi account hai phiên GPU batch cùng
  lúc (`SESSION_CAPACITY_MARKER`).
- `LocalCheckpointSource` và `artifact_sink` của `run_kaggle_stage`: coi tiến độ nằm ở máy là một
  checkpoint và nhận kết quả về máy trước khi làm việc khác.
- `KernelReconciler.attach_or_recover` và `CloudArtifact.allow_partial`: nối lại kernel đang chạy,
  nhận lại output của kernel lỗi, chấp nhận artifact chưa đủ.
- `workers/runtime.worker_deadline`: hạn dừng nhận việc mới, chừa biên để xả việc đang chạy.

#### 1.1 Các bước Kaggle hiện có (đã đọc `StageName` và nơi gọi `run_kaggle_stage`)

| Bước (lệnh) | Việc còn thiếu tính ở máy | Resume | Xoay account | Song song nhiều account |
| --- | --- | --- | --- | --- |
| Embed corpus (`bundle embed --backend kaggle`) | Có: chỉ gửi văn bản chưa có trong cache (`missing_inputs.jsonl`) | Có (checkpoint) | Không: gắn một account (`hold_pinned_account`) | Không |
| Embed truy vấn (`embed queries --backend kaggle`) | Có: chỉ gửi truy vấn chưa có (`*.missing.jsonl`) | Có | Không: gắn một account | Không |
| Rerank (`rerank --backend kaggle`) | Có: cache rerank là checkpoint cục bộ | Có | **Có** (`run_account_sessions`, tuần tự) | Không |
| Đo profile (`*-benchmark`, `auto_profile`) | Không áp dụng (một lượt đo) | Không áp dụng | Có (`reserve_session_account_waiting`) | Không áp dụng |
| e2e (`e2e run --backend kaggle`) | **Không** | **Không** | Không | Không |

Ba bước nặng nhất (rerank, embed corpus, e2e) đều có thể tách theo "đơn vị việc còn thiếu", nên đều
hưởng lợi từ chia shard song song nhiều account. Các lượt đo profile là một kernel duy nhất nên giữ nguyên.

### 2. Nguyên tắc

1. **Trạng thái nằm ở máy.** Sự thật duy nhất là `data/evaluation/e2e/runs/<run>/<config>/answers.jsonl`
   (cùng `run.json`). Kaggle chỉ là chỗ tính toán tạm. Mất kernel, mất quyền vào account hay xoá
   dataset không làm mất kết quả đã tải về.
2. **Phần còn thiếu luôn tính lại từ trạng thái máy.** Không có "job" cần nhớ để chạy tiếp: chạy lại
   cùng lệnh thì tự biết còn thiếu gì. Vì vậy dừng, nối lại và đổi account là cùng một thao tác.
3. **Không cổng nào mở ra ngoài kernel.** Internet chỉ để tải về. Dataset đầu vào của một job là
   private theo account chạy, không chứa khoá API.
4. **Một lệnh duy nhất** (`e2e run --backend kaggle`) làm cả việc lên kế hoạch, chạy, thu và gộp.

### 3. Hành vi người dùng thấy

```bash
pharma-lab e2e run --backend kaggle --run e2e-v2-qwen9b \
  --config full --config one-step [--category ...] [--limit N] \
  [--pipeline-option guard=false ...] \
  [--kaggle-account auto | acc1,acc3]  [--parallel N]  [--budget-seconds S]  [--max-sessions K]
pharma-lab e2e status --run e2e-v2-qwen9b
```

- Lệnh tính phần thiếu theo từng cấu hình, chia thành các **shard**, đẩy mỗi shard lên một kernel của
  một account còn quota, chạy song song, thu kết quả về, gộp vào máy, rồi lặp cho tới khi hết việc,
  hết quota hoặc tới `--max-sessions`.
- **Dừng:** Ctrl-C hoặc tắt máy bất kỳ lúc nào. Kernel đang chạy vẫn chạy tiếp. Chạy lại cùng lệnh
  sẽ nối lại kernel đó (`attach`) hoặc thu kết quả của nó, rồi tạo shard mới cho phần còn thiếu.
- **Hết quota:** lệnh in bảng quota từng account, giờ reset, số câu còn thiếu theo cấu hình, rồi thoát
  với trạng thái "tạm dừng" (không phải lỗi). Chạy lại sau khi quota reset.
- **Đổi account:** không cần thao tác. `--kaggle-account` chỉ giới hạn tập account được phép dùng;
  `auto` là mọi account có profile. Không có trạng thái nào gắn với một account.
- `e2e status` in bảng cấu hình × (xong/tổng), các kernel đang chạy (account, shard, giờ đẩy lên),
  quota của từng account, và ước lượng số giờ GPU còn cần.

### 4. Thiết kế

#### 4.1 Gộp kết quả vào máy (nguồn sự thật)
- Mỗi cặp (cấu hình, câu) giữ **một bản ghi cuối**. Bản hoàn thành không bao giờ bị bản `error` ghi
  đè; hai bản hoàn thành thì giữ bản mới hơn. Gộp hai lần cho cùng kết quả (idempotent).
- **Tập câu của một run** là đúng kết quả `select_items(golden, limit, category)` mà harness dùng
  (lọc theo nhóm rồi `spread` theo `--limit`). Planner và `status` gọi chính hàm đó. Đổi `--limit`
  hay `--category` ở lần chạy sau chỉ đổi tập "cần có", không bao giờ xoá bản ghi đã có.
- Bản ghi cuối của một câu là **dòng cuối** của câu đó trong `answers.jsonl` (file nối thêm, đúng như
  `JsonlStore.latest()`).
- Một cặp **còn thiếu** khi: không có bản ghi; hoặc bản ghi cuối có `status = superseded` (câu golden
  đã sửa, luôn chạy lại như `run_items`); hoặc bản ghi cuối là `error` có `retryable` và **chưa quá 3 lần
  thất bại**. Số lần thất bại đếm bằng số dòng `error` của câu đó trong file, không thêm trường mới.
  Quá 3 lần thì cặp ở trạng thái `kẹt`: `status` liệt kê riêng, planner không đưa vào shard trừ khi
  người dùng thêm `--retry-stuck`. Mục đích là một câu lỗi cố định không đốt quota mãi.
- `extract_outputs` giữ luật hiện nay (chỉ nhận `<config>/answers.jsonl` và `run.json`, từ chối mọi
  thành viên khác) nhưng **gộp** thay vì từ chối thư mục đã có `answers.jsonl`.
- Trước khi gộp, kiểm danh tính: `run.json` của shard phải khớp `run.json` của cấu hình trên máy
  (golden sha256, release, settings, pipeline). Khác thì dừng với thông báo rõ. Commit khác nhau chỉ
  cảnh báo.
- **Độ chính xác khi gộp nhiều kernel:** mỗi shard ghi vào `run.json` sha256 của từng file model,
  phiên bản `llama-server` và `cli-proxy-api`, phiên bản backend và mức suy luận của từng vai. Gộp hai
  shard khác sha256 model hoặc khác bản `llama-server` bị **từ chối** (kết quả không còn so sánh được);
  khác phiên bản proxy thì cảnh báo. Mục đích là mọi cặp của một run đến từ cùng một phần mềm và cùng
  trọng số, dù chạy ở account nào.

#### 4.2 Chia shard
- Đơn vị việc là cặp (cấu hình, câu). Một shard gồm nhiều cấu hình **cùng bố cục máy chủ** trên cùng
  một lát câu hỏi, để các cấu hình dùng chung một lần dựng môi trường.
- Bố cục A (có rerank): LLM ở GPU0, reranker ở GPU1, embedding trên CPU (như hiện nay). Đây là bố
  cục duy nhất của **giai đoạn 1**.
- Bố cục B (**giai đoạn 2, chỉ làm khi job thử cho thấy LLM là điểm nghẽn**): cấu hình không rerank
  (`no-rerank`, `no-guard-no-rerank`, `closed-book`) chạy hai bản LLM, mỗi bản một T4, chia request
  bằng một proxy round-robin nhỏ **chỉ nghe trên `127.0.0.1`** trong kernel. Planner không trộn hai
  bố cục trong một shard. Bố cục được ghi vào `run.json` của cấu hình (không thuộc danh tính, vì hai
  bản Q8_0 cho cùng câu trả lời); lệnh gộp không chặn theo bố cục, nhưng phép đo độ trễ (§4.7) cố định
  bố cục.
- Kích thước shard bị chặn bởi **ngân sách thời gian**, không phải số cặp cố định:
  `(tổng giây ước lượng của các cặp ÷ độ song song hiệu dụng) + thời gian dựng môi trường + biên ≤
  budget_seconds`. Ước lượng giây mỗi lượt theo (cấu hình, nhóm câu) lấy từ trường `latency_seconds`
  trong các `answers.jsonl` đã có trên máy (các run Qwen cũ nằm ở
  `data/evaluation/e2e/runs/e2e-qwen35-9b/*/answers.jsonl`); chưa có thì dùng hằng số mặc định, sau
  mỗi shard xong ước lượng được cập nhật từ chính kết quả. Cùng đầu vào cho cùng cách chia (tất định).
  Không chia quá nhỏ vì mỗi shard trả lại chi phí dựng môi trường.
- Số shard chạy song song là `min(--parallel, tổng số phiên GPU còn trống)`. Kaggle cho **hai phiên GPU
  batch cùng lúc mỗi account** (`SESSION_CAPACITY_MARKER`), nên với ba account có tối đa sáu shard cùng
  lúc. Mặc định `--parallel` dùng đủ hai phiên mỗi account, để thời gian thực ngắn nhất; tổng giờ GPU
  không đổi và quota mỗi tuần vẫn là giới hạn thật. Trần riêng theo nhà cung cấp (§4.8) vẫn áp dụng.
  Planner không đưa việc cho account không còn đủ quota cho một shard.
- **Cân tải ở đuôi:** khi một kernel xong sớm, điều phối lập ngay shard mới từ phần chưa giao cho kernel
  nào (kể cả phần đã thu của kernel chết), nên không account nào ngồi chờ kernel chậm nhất.
- **Độ lớn shard là hàm của chi phí dựng môi trường** `S`: không tách khi việc của một shard nhỏ hơn
  `S` (chi phí dựng lấn át), và mỗi shard dài tối đa khoảng 2 giờ (mặc định, tinh chỉnh sau khi đo `S`)
  để việc dừng và chạy lại ít tốn kém.

#### 4.3 Phía kernel (`kernel_worker`, `kernel_harness`)
- `e2e_job.json` mang danh sách cặp (cấu hình, câu) của shard. Harness chỉ chạy các cặp đó (thêm bộ
  lọc theo `item_id`; `select_items` hiện chỉ lọc theo nhóm và `--limit`).
- **Hạn phiên:** dùng `worker_deadline`. Tới hạn thì ngừng nhận câu mới, chờ các câu đang chạy
  (tối đa `deadline_seconds` của lượt), đóng gói và thoát sạch.
- **Chụp định kỳ:** cứ khoảng 5 phút hoặc 25 câu, worker ghi `e2e_output.tar` và manifest (completion)
  vào thư mục output bằng ghi tạm rồi `os.replace`. Nhờ đó một kernel bị kill hay hết giờ vẫn để lại
  output gần nhất. Chu kỳ là một tham số của job (`snapshot_seconds`, mặc định 300, `0` tắt hẳn) nên
  có thể gỡ mà không phải thiết kế lại.
  *Giả định cần kiểm chứng bằng job thật:* Kaggle giữ `/kaggle/working` của kernel trạng thái ERROR.
  Code hiện có (`attach_or_recover`, `ArtifactContractError` với `KernelStatus.ERROR`) đã xử lý trường
  hợp này. Nếu giả định sai, chụp định kỳ không cứu được kernel bị kill, và chỉ còn **hạn phiên** bảo vệ:
  vì vậy mặc định giữ ngân sách phiên của e2e hiện nay (3 giờ) với biên của `worker_deadline`, không
  nới ra. Phần mã được xây và kiểm thử đơn vị trước; bước kiểm chứng bằng job thật là cổng chấp nhận
  cuối cùng (§7).
- Completion của artifact: `total` là số cặp của shard, `complete` là số cặp có bản ghi không phải
  `error`. Đã có `completed_answers`.
- Truyền `--pipeline-option` vào harness (nhãn thư mục cấu hình `full+guard=false` như chạy local);
  kernel_env đã có vai `AGENT` nên cấu hình `react` chạy được.
- Ghi mốc thời gian từng bước dựng môi trường vào log và telemetry để đo và tối ưu sau này.

#### 4.4 Điều phối phía máy
- Module mới điều phối (tên do builder đặt) thay `run_on_kaggle`: tính phần thiếu, lập shard, chạy
  thread pool; mỗi luồng: `reserve_session_account` (khoá theo account, kiểm quota) → `run_kaggle_stage`
  cho shard (`resume_remote=False`, `artifact_sink` ghi vào máy) → gộp → trả account.
- File trạng thái `data/work/e2e-kaggle/<run>/jobs.json` ghi các kernel đang chạy (account, tham chiếu
  kernel, các cặp của shard, giờ đẩy lên). Khi CLI sống lại, nó đọc file này để `attach` hoặc thu
  kết quả của từng kernel trước khi lập shard mới; nếu file mất, kernel mồ côi chỉ tốn quota, không
  làm sai dữ liệu vì mọi thứ tính lại từ trạng thái máy.
- Dùng lại `QuotaExhausted`, `KaggleSessionCapacityReached`, chờ khi account đang bị lệnh local khác
  giữ. Thêm backoff khi Kaggle trả 429 (đã gặp khi tạo dataset liên tiếp).
- **Đầu vào tĩnh dùng lại theo nội dung:** phần nặng của job (corpus khoảng 270 MB, golden, danh sách
  thư viện) tách thành một dataset private *theo nội dung* cho mỗi account, tạo một lần rồi dùng lại cho
  mọi shard; mỗi shard chỉ thêm một dataset rất nhỏ chứa `e2e_job.json` (lát của nó). Hiện mỗi job tải lại
  cả 270 MB, và đường upload ở mạng công ty chỉ khoảng 0,3 đến 11 MB/s, nên đây là phần tiết kiệm lớn.
- **Không dùng checkpoint dataset phía Kaggle cho e2e.** Trạng thái đã nằm ở máy nên không cần kế thừa
  checkpoint giữa account (`checkpoint_inheritance`), và không để lại dataset thừa trên account.
  (Quyết định của mình, dễ đổi: nếu sau này muốn resume trong lúc máy tắt, thêm sau.)

#### 4.5 Tốc độ (xếp theo tác dụng)
1. **Shard song song trên nhiều account** (chia thời gian thực cho số account).
2. **Nhiều cấu hình trong một kernel** để chia sẻ một lần dựng môi trường.
3. **Bố cục B** (hai bản LLM) cho cấu hình không cần reranker.
4. **Giảm thời gian dựng môi trường:** bước đầu tiên là *đo*. Nếu vượt 15 phút, đóng gói bánh xe
   Python, nhị phân Qdrant và gói Postgres vào một dataset "toolchain" private để kernel khỏi tải. Chỉ
   làm nếu số đo cho thấy đáng.
5. **Một hàng đợi chung trong kernel:** hiện harness chạy tuần tự từng (cấu hình, nhóm) nên cuối mỗi
   nhóm GPU nhàn rỗi chờ câu chậm nhất. Chạy các cấu hình của shard đồng thời với một semaphore toàn
   cục (tổng độ song song vẫn bằng số slot của LLM) giữ GPU luôn đầy. Làm sau khi có số đo thật cho thấy
   khoảng nhàn rỗi đáng kể.
6. **Đầu vào tĩnh dùng lại** (§4.4) và chỉ tải lên phần thay đổi.
7. **Chấm điểm gối đầu (`--judge`):** sau mỗi lần gộp, một luồng ở máy chấm các câu mới về (`e2e judge`
   đã tự nối lại theo từng câu, qua proxy cục bộ, không tốn quota GPU), nên khi shard cuối về thì phần
   lớn đã chấm xong. Báo cáo sinh bằng lệnh có sẵn.

#### 4.6 An toàn
- Giữ `test_no_external_exposure.py`. Không thêm công cụ tunnel, cổng nghe ngoài `127.0.0.1`.
- Dataset đầu vào private theo account chạy; `jobs.json` và log không chứa khoá API.

#### 4.7 Đo độ trễ
Độ trễ chỉ so giữa các kiến trúc trên cùng một model (spec v2 §2.5). Chạy riêng một **lượt đo**
(`--latency`): một shard duy nhất, `--concurrency 1`, bố cục A cố định, trên một lát câu hỏi `spread`
(kích thước do người dùng chọn, xem §9), mỗi cấu hình một lượt. Kết quả vào run `<run>-c1`, đúng chỗ mà
`e2e report --latency-run` đang đọc. Chất lượng không lấy từ lượt đo. Chạy một lượt đo nhiều shard hay
nhiều bố cục là sai thiết kế nên planner từ chối.

#### 4.8 Model thương mại: `cli-proxy-api` chạy **trong kernel**

Không hạn chế thí nghiệm: Gemini 3.8 Flash, Claude Opus 5.5 và judge `gemini-3.1-flash-lite` chạy trong
kernel cùng reranker GPU và embedding, chia shard như Qwen. Cách làm (người dùng đồng ý đưa file
credential của proxy lên Kaggle, 2026-10-23):

- **Worker dựng proxy trong kernel:** tải bản `CLIProxyAPI_8.0.28_linux_amd64.tar.gz` (đã có trên
  GitHub releases, 23 MB; kết nối đi ra) và kiểm checksum; ghi `config.yaml` từ
  `devops/cli-proxy-api/config.yaml` với `host: 127.0.0.1` và `auth-dir` trỏ vào thư mục tạm quyền
  `0700`; chép các file credential vào đó (quyền `0600`); chạy ở `127.0.0.1:8317`. Harness dùng đúng các
  biến môi trường như ở máy (`http://127.0.0.1:8317/v1`, khoá cục bộ `proxypal-local`, id model như
  `gemini-3.8-flash-high`, `claude-opus-5-5`), nên không đổi mã agent. Proxy chỉ nghe localhost và chỉ
  gọi ra nhà cung cấp.
- **Credential đi bằng một dataset private riêng cho lượt chạy**, tạo ở account chạy shard, **xoá sau
  khi thu kết quả** (và quét xoá dataset sót lại khi `status` hoặc lần chạy sau thấy). Không bao giờ
  public (có test khẳng định `public=False`). Nguồn là volume `vipharmind_cli_proxy_auth` hoặc một thư mục
  ngoài repo; file credential **không bao giờ** vào `data/`, git, archive của `data push` hay log (test
  khẳng định `list_archive_files` và log không chứa chúng; log che nội dung).
- **Chỉ đi khi người dùng bật rõ từng lần chạy:** cờ `--with-proxy-credentials` (mặc định tắt), lệnh in
  ra tên file và loại (`antigravity`, `claude`, `codex`) sẽ được tải lên và chỉ tải đúng những file cần
  cho các model của run (`--proxy-credential FILE` để chọn).
- **Giới hạn tốc độ theo nhà cung cấp:** các gói thuê bao có hạn mức, mà shard song song nhân số request.
  Có trần độ song song riêng cho từng nhà cung cấp (Claude thấp nhất) và backoff khi proxy trả
  `quota-exceeded`/`auth_unavailable`; run bị gián đoạn vẫn nối lại được vì trạng thái ở máy.
- **Làm tươi token:** kernel dùng *bản sao* credential; token làm tươi trong kernel không chép ngược về.
  Nếu nhà cung cấp xoay vòng refresh token, bản sao có thể làm bản cục bộ hết hiệu lực: kiểm bằng một job
  ngắn trước khi chạy thật, và giữ bản sao lưu volume.
- **Độ trễ** của model thương mại đo từ datacenter của Kaggle, không phải từ Việt Nam; bài ghi rõ và chỉ
  so giữa các kiến trúc trên cùng một model (spec v2 §2.5).
- **Decision model Jev** (OpenRouter) khác proxy: cần khoá API riêng, người dùng cung cấp sau. Thiết kế
  chừa chỗ: `kernel_env` nhận bản đồ vai trò → điểm cuối. Trước khi có khoá, nếu môi trường local khai
  báo vai `systemone`, lệnh dừng với thông báo rõ thay vì chạy âm thầm với model khác.
- Chạy ở máy (`--backend local`) vẫn dùng được cho model qua proxy, cùng bộ lập kế hoạch và `status`.

(Proxy round-robin của bố cục B ở §4.2 là thứ khác: chỉ nằm trong kernel, nghe `127.0.0.1`.)

#### 4.9 Lớp điều phối chung cho mọi bước Kaggle

Tách phần dùng chung ra khỏi từng bước để mọi bước có cùng hành vi: dừng và nối lại, đổi account,
chia shard song song, `status`.

- **Lớp chung** (module do builder đặt tên): lập danh sách account được phép và quota, giữ khoá theo
  account, chạy thread pool các shard, ghi `jobs.json` toàn cục, nối lại kernel đang chạy, backoff khi
  Kaggle trả 429, in bảng quota và giờ reset. Dùng lại `sessions.py`, `quota.py`, `KernelReconciler`.
- **Bộ chuyển đổi cho mỗi bước** cung cấp ba việc: (1) liệt kê đơn vị việc còn thiếu từ kho cục bộ
  (embed: văn bản hoặc truy vấn chưa có trong cache; rerank: cặp (truy vấn, đoạn) chưa có điểm; e2e: cặp
  (cấu hình, câu)); (2) dựng đầu vào cho một lát đơn vị việc; (3) gộp artifact về kho cục bộ,
  idempotent. Tất cả bước đã có (1) và (3) dưới dạng cache; phần mới là chia lát và chạy song song.
- **Lệnh nhận cùng cờ**: `--kaggle-account auto|acc1,acc3` (mặc định `auto`, không còn gắn một account),
  `--parallel N`, `--budget-seconds`, `--max-sessions`; thêm `pharma-lab kaggle status` liệt kê mọi kernel
  đang chạy và quota của mọi account, và `e2e status` / `rerank --status` cho từng bước.
- Thứ tự áp dụng theo lợi ích: rerank (tiêu nhiều giờ GPU nhất và đã có hạ tầng) và e2e (chưa có resume),
  rồi embed corpus và embed truy vấn. Lượt đo profile giữ nguyên.
- Dữ liệu và định danh cache của từng bước **không đổi**, nên không phải làm lại gì đã có.

### 5. Dọn tư duy tunnel (một lượt, cùng lần sửa)

- `2026-10-14-paper-v2-design.md`: viết lại §2.1b (đường gọi model), §2.5 (độ trễ đo trong kernel ở
  concurrency 1 trên một shard duy nhất, không còn "mạng tới tunnel"), bảng A và đoạn C nhắc "tự host
  Kaggle", pha 0 trong §7, các rủi ro §8 nhắc tunnel và `llm-server`; §3 nhắc "năm embedding tự host".
- Các plan `2026-10-16-paper-v2-phase-0/1/2`, `2026-10-20-kaggle-batch-e2e`, spec
  `2026-10-20-kaggle-batch-e2e-design.md`: cập nhật các bước còn nhắc `llm-server`, `rerank-server`,
  `embed-server`. Plan và spec của camera-ready là lịch sử, chỉ thêm ghi chú đầu trang.
- `pharma-lab/docs/guides/e2e-evaluation.md`, `cli-reference.md`, `workflow-local-kaggle.md`: mô tả
  quy trình mới (lệnh, `status`, dừng và nối lại, đổi account).
- `evaluation.md`, `workflow-local-kaggle.md` (embed corpus, embed truy vấn, rerank): cùng cờ mới và cách dừng, nối lại, đổi account.
- Memory: ghi quyết định này.

### 6. Ngoài phạm vi

Tunnel, mở cổng hay phục vụ model ra ngoài kernel; resume *bên trong* một kernel; chia một câu hỏi
giữa nhiều kernel; khoá API trực tiếp (OpenRouter cho Jev, Gemini, Anthropic): người dùng cung cấp sau, thiết kế chỉ chừa chỗ (§4.8). Credential của proxy thì **trong phạm vi**; tự động hoá judge và báo cáo; đổi hạ tầng rerank, embed hiện có;
đụng `camera-ready`, `main`, tag `v1.1.0` hay dataset của bài.

### 7. Kiểm thử và tiêu chí chấp nhận

- Đơn vị: chia shard (cân bằng, tất định, không trùng và không sót cặp); gộp (idempotent, bản `error`
  không đè bản hoàn thành, từ chối danh tính khác); worker (hạn phiên và chụp định kỳ với đồng hồ giả);
  `extract_outputs` vẫn từ chối thành viên lạ; `status`; nhận `--pipeline-option`.
- Giả lập (Kaggle giả như các test của stage hiện có): ba shard song song, giết CLI giữa chừng, chạy
  lại, hoàn tất, không cặp nào chạy thừa hơn một lần thử lại; account hết quota thì chuyển sang account
  khác.
- Thật: một job thử khoảng 20 câu × 2 cấu hình trên một account (khoảng 1 đến 1,5 giờ GPU, cần quota
  sau reset 2026-10-24) để đo thời gian dựng môi trường, VRAM của từng server, và kiểm chứng giả định ở
  §4.3 bằng cách đặt `--budget-seconds` ngắn để ép dừng theo hạn và xem output có về không.
- Mỗi bộ chuyển đổi (rerank, embed corpus, embed truy vấn, e2e) có test: liệt kê đơn vị còn thiếu, chia lát
  không trùng và không sót, gộp idempotent; lớp chung có test với account giả (hết quota thì chuyển account,
  kernel mồ côi không làm sai dữ liệu).
- ruff, pyrefly, `lint-imports` và pytest của `pharma-lab` (và `backend` nếu chạm) đều xanh; code mới
  nằm đúng tầng (`e2e` cho điều phối và worker, `integrations/kaggle` cho phần Kaggle).

### 8. Để builder quyết

Tên và vị trí module mới, định dạng `jobs.json`, thuật toán chia shard cụ thể và các hằng số
(chu kỳ chụp, biên hạn phiên, backoff), cách in `status`, cách đo mốc thời gian dựng môi trường.

### 9. Quyết định

**Của người dùng (đã chốt):** chạy trong kernel, không tunnel; ba mục tiêu: nhanh nhất, dừng và nối
lại dễ, đổi account dễ; sửa toàn bộ trong một lượt.

**Hoãn theo người dùng:** khoá API trực tiếp (Jev qua OpenRouter, Gemini/Anthropic không qua proxy).

**Đã chốt (2026-10-23):** người dùng cho phép đưa **mọi** file credential trong volume proxy lên Kaggle,
gồm cả credential của email công ty `sun-asterisk.com` (Antigravity, Claude, và Codex ghi "enterprise ...
usage-based"). Mình đã nêu rủi ro (quy định của công ty, chi phí theo mức dùng của tổ chức, lộ thì tổ
chức chịu); người dùng vẫn đồng ý. Thiết kế giữ nguyên các biện pháp ở §4.8: cờ bật theo từng lần chạy,
in danh sách file, dataset private xoá sau khi thu kết quả, trần độ song song theo nhà cung cấp.

**Mặc định (đổi được):** lượt đo độ trễ concurrency 1 dùng lát 100 câu `spread` mỗi cấu hình.

**Của mình, chọn theo tiêu chí người dùng giao (nhanh, chính xác, dừng và nối lại tốt; có thể đổi):**
- Đủ hai phiên GPU mỗi account (sáu shard cùng lúc với ba account), cân tải ở đuôi.
- Trạng thái ở máy, không dùng checkpoint dataset phía Kaggle cho e2e. Dừng nghĩa là ngừng giao shard
  mới (`--drain`) và để các shard đang chạy kết thúc theo ngân sách; Kaggle CLI không có lệnh huỷ kernel.
  Vì shard ngắn (khoảng 2 giờ) nên chờ ngắn.
- Câu lỗi quá 3 lần thì "kẹt", cần `--retry-stuck` mới chạy lại.
- Chụp định kỳ mặc định 300 giây (tắt được); ngân sách phiên mặc định khoảng 2 giờ.
- Gộp từ chối khi khác sha256 model hoặc bản `llama-server` (độ chính xác).
- Bố cục hai bản LLM và hàng đợi chung trong kernel chỉ làm sau khi có số đo thật.
- Lượt đo độ trễ concurrency 1 dùng lát 100 câu `spread` mỗi cấu hình.
- Cờ `--with-proxy-credentials` bật theo từng lần chạy; dataset credential xoá sau khi thu kết quả.
- `--judge` gối đầu là cờ tuỳ chọn.

### Kết quả nghiệm thu (2026-10-23, job Kaggle thật)

Chạy bằng acc1, acc2, acc3; mỗi kernel dùng khoảng 0,4 đến 0,6 giờ GPU.

| Bước | Kết quả |
| --- | --- |
| 1. Dựng môi trường, 40 cặp (`full`, `no-rerank`, 20 câu) | Đạt. Dựng môi trường khoảng 8 phút (venv 5 s, Postgres 47 s, Qdrant 3 s, model server 157 đến 273 s, nhập corpus 220 s), không phải nửa giờ. `e2e status` báo 20/20 mỗi cấu hình. Kernel lần đầu lỗi ở lượt chạy thứ hai của harness (`run.json` có khối `software`), nhưng vẫn để lại 20/40 câu và lệnh gộp được: giả định "kernel lỗi vẫn giữ output" đúng. |
| 2. Ép dừng theo hạn (100 câu, phiên 1 giờ) | Đạt. Kernel nhận 49 câu rồi ngừng nhận câu mới, lượt thử lại không chạy thêm, đóng gói sau 2.450 s; máy gộp 49/100 và scheduler tự lập shard mới cho đúng 51 câu còn lại. |
| 3. Dừng bằng Ctrl-C và nối lại | Đạt. Chạy lại cùng lệnh báo "already runs this job's kernel; attaching", cùng shard, không đẩy kernel mới; kết quả cuối 100 dòng, 100 câu khác nhau, không câu nào chạy thừa; gộp được kết quả của hai kernel (hai `release_id` khác nhau). |
| 4. Đổi account (acc3) với `--limit 130` | Đạt. Chỉ phần thiếu được giao cho acc3, acc3 tự upload input tĩnh của nó, mọi bản ghi cũ của acc1 còn nguyên. |
| 5. Gemini qua proxy trong kernel (`--llm gemini --with-proxy-credentials`, 10 câu, một file credential) | Đạt. `cli-proxy-api` lên sau 2,6 s, 10 câu: 7 hoàn tất, 3 một phần. Dataset credential bị xoá khi lệnh kết thúc; credential cục bộ vẫn dùng được (39 model, gọi `gemini-3.8-flash-high` bình thường), nên không bị vô hiệu do xoay vòng token. |

Lỗi chỉ lộ ra ở job thật, đã sửa kèm test: (1) lượt chạy thứ hai của harness trong cùng kernel từ chối `run.json` có khối `software`; (2) Qdrant trong kernel lắng nghe `0.0.0.0` (nay `127.0.0.1`); (3) file credential xuất từ volume Docker thuộc `root` nên chính lệnh không đọc được; (4) bản phát hành proxy đặt tên chương trình `cli-proxy-api`, không phải `CLIProxyAPI`; (5) dataset credential không bị xoá khi Ctrl-C được bấm hai lần (nay xoá bỏ qua SIGINT); (6) 8 request cùng lúc làm Gemini trả 429 `model_cooldown` cho nửa số câu, nay trần là 4 (Opus 2); (7) thư mục credential trong kernel chứa nhầm `dependency_manifest.json`; (8) `merged` đếm dòng lỗi thay vì câu xong.



#### Vòng nghiệm thu thứ hai (cùng ngày)

| Việc | Kết quả |
| --- | --- |
| Nhiều account song song (`closed-book`, 300 câu đề nghị, 3 account, `--parallel 3`) | Đạt. Cắt thành 3 shard (84, 83, 83 câu), mỗi shard một account, chạy cùng lúc; kết quả 250 câu, 250 dòng khác nhau, cả 250 `completed`. |
| `--judge` cùng kernel | Cơ chế đạt (chấm ngay khi mỗi shard về, lỗi của judge không chặn việc gộp). Chấm gần như toàn lỗi vì judge mặc định `gpt-5-mini` không có trên proxy cục bộ: thêm `--judge-model` và `--judge-reasoning` cho `e2e run`. |
| `rerank` qua scheduler (0,6B, 20 truy vấn, 177 cặp thiếu, 2 account cho phép) | Đạt. 1 shard, 400/400 cặp, biến thể được ghi, `stop=complete`, khoảng 6,5 phút. |
| Embedding truy vấn (0,6B, 40 truy vấn) | Đạt. 1 shard, 40/40. Lần đầu lỗi: `--kaggle-account acc1,acc2` bị truyền nguyên chuỗi vào bước chọn profile; đã sửa cho cả embedding corpus. |
| Embedding corpus (0,6B, 13.408 văn bản, 3 account) | Đạt. 3 shard 4.469 đến 4.470 văn bản, 13.408/13.408 vector, `stop=complete`; so với cache cũ cosine ≥ 0,9995. |
| Claude/Opus qua proxy (10 câu, một file credential) | Proxy trong kernel đọc credential Claude, nhận ra nhà cung cấp `claude` và gửi yêu cầu lên Anthropic. Anthropic trả 429 `rate_limit_error` (chờ 12 giờ 17 phút); gọi từ máy cũng bị y như vậy, nên là hạn mức của tài khoản, không phải lỗi cơ chế. Chưa có câu trả lời đầy đủ của Opus. Một lần chạy trước đó thấy 0 file credential trong kernel (mount dataset mới tạo, không lặp lại); nay kernel báo lỗi to và kể tên thư mục nó thấy. Dataset credential được xoá sạch sau cả hai lần. |

Lỗi thêm tìm ra ở vòng này (đã sửa, có test): hạn mức Gemini 8 request quá cao (nay 4, Opus 2); thư mục credential trong kernel chứa nhầm `dependency_manifest.json`; `merged` đếm dòng lỗi thay vì câu xong; file credential xuất từ volume Docker thuộc `root`; tên nhị phân proxy là `cli-proxy-api`; xoá credential bị cắt ngang khi Ctrl-C hai lần; `--judge` thiếu lựa chọn model; danh sách account bị truyền nguyên chuỗi vào bước profile runtime ở embedding.

Còn chưa thử: câu trả lời đầy đủ của Opus (chờ hạn mức Claude); `--judge` với model judge chạy được.

## Phụ lục C. Ma trận ablation: mỗi câu hỏi một bộ dữ liệu, một phép thử, một ngưỡng (chốt 2026-10-25)

Phụ lục này thay các cỡ golden ở Phụ lục A §4 và là nguồn duy nhất cho câu "ablation X đo trên gì,
thử bằng gì, nhạy tới đâu". Mọi ablation phải ra một trong hai kết luận rõ: khác biệt có ý nghĩa
(KTC 95% không chứa 0 và p sign-flip sau Holm < 0,05), hoặc tương đương trong biên (báo KTC và nói
"chênh lệch nằm trong ±X điểm"). Không bảng nào để một hàng "không ý nghĩa" mà không kèm biên.

### C.1 Bộ dữ liệu

| Bộ | Cỡ | Chọn thế nào | Dùng cho |
| --- | --- | --- | --- |
| Benchmark retrieval `9c6e4de6…` | 10.000 dòng, 9.970 có gold | luật sinh, audit 4 vòng (Phụ lục A §6) | mọi ablation retrieval |
| Tập chọn retrieval | 8.470 | benchmark trừ `conversational` và `safety` | luật chọn §3.4 |
| Golden e2e v4 | 1.000 | xem C.2; không câu nào chọn theo kết quả hệ thống | mọi ablation e2e |
| Tập giữ lại §3.3 | 300 câu judge + 300 lượt guard | judge: dòng benchmark ngoài golden, nhãn từ gold; guard: LLM nháp theo template, audit | ngưỡng guard, τ, hiệu chuẩn Jev; không bao giờ dùng golden để chỉnh |
| Nhãn dược sĩ | 50 item × 9 cấu hình chính (A2, A3, ReAct × 3 model) | ngẫu nhiên phân tầng theo tầng golden | PPI cho metric dựa judge, κ của judge |

### C.2 Golden e2e v4, 1.000 câu

| Tầng | Cỡ | Nguồn và cách chọn |
| --- | --- | --- |
| Tự nhiên | 520 | dòng benchmark các nhóm luật, chia theo tỉ lệ nhóm trong benchmark, tối thiểu 30 mỗi nhóm (formulary 212, leaflet 106, structured 51, leaflet_short 31, multi_intent 30, noisy 30, glossary 30, colloquial 30); ngẫu nhiên trong nhóm |
| Lát | 90 | 30 mỗi lát `header_dependent`, `name_variant`, `sibling_products`, ngẫu nhiên trong lát |
| multi_hop | 200 | nhóm `multi_hop` của benchmark: two_drug 70, brand_to_ingredient 65, three_intent 65 |
| multi_turn | 160 | nhóm `conversational`, 20 mỗi hiện tượng |
| safety | 30 | unanswerable, out_of_scope, injection 10 mỗi loại; chỉ báo hành vi, không dùng chỉnh ngưỡng |

Item đã soạn ở golden v3 được giữ khi dòng benchmark của nó vẫn thuộc tầng mới; tầng "trượt vòng 1"
(retrieval_miss, noisy_retry, chọn từ lỗi của hybrid + rerank 4B) bỏ hẳn. Đáp án mới: LLM soạn nháp,
máy kiểm mọi `evidence_quote` có nguyên văn trong section gold, một model khác hãng audit toàn bộ
theo rubric, rồi dược sĩ duyệt toàn bộ 1.000 câu (quyết định 2026-10-25); bài báo tỉ lệ câu
dược sĩ phải sửa ở mỗi tầng. Tầng tự nhiên có trọng số chuẩn về tỉ lệ benchmark để báo số tái trọng số cạnh số thô.

### C.3 Độ nhạy (power 80%, α sau Holm khoảng 0,005; phương sai từ ablation v1)

| Tập | n | truthfulness | nugget recall | hallucination |
| --- | --- | --- | --- | --- |
| Golden toàn bộ | 1.000 | 4,9 điểm | 3,9 | 1,9 |
| Tự nhiên + multi_hop (D6) | 720 | 5,8 | 4,6 | 2,2 |
| multi_hop | 200 | 11,0 | 8,7 | 4,2 |
| multi_turn | 160 | 12,3 | 9,7 | 4,7 |
| Benchmark, tập chọn (Hit@k) | 8.470 | khoảng 1,0 điểm | | |
| Benchmark, conversational (Hit@k) | 1.500 | khoảng 3,6 điểm | | |

Không thua kém (một phía, α 0,025): biên khả thi trên golden toàn bộ là 4 điểm truthfulness và 3
điểm nugget recall; đây là biên chốt cho A (thay biên 3 điểm ở Phụ lục A §5).

### C.4 Ma trận

Họ so sánh (Holm) = một hàng "Họ" dưới đây; mỗi họ là một bảng của bài.

| Mã | Câu hỏi | Dữ liệu | Thử | Metric chính (phụ) | Họ | Nhạy tới |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | Chọn retriever cho agent | tập chọn 8.470 | §3.4 | Hit@20 (Hit@5) | S1 | 1 điểm |
| S2 | Chọn reranker | tập chọn 8.470 trên cấu hình S1 | §3.4 | Hit@5 (MRR@10) | S2 | 1 điểm |
| D1 | Sao phải hybrid | benchmark, theo nhóm và lát | dense + rerank so với hybrid + rerank, cùng reranker S2 | Hit@5 (nDCG@5) | D | 1 điểm; nhóm nhỏ báo KTC |
| D2 | Enrichment giúp gì | benchmark | `plain` so với đủ, hybrid + rerank | Hit@5, theo colloquial, glossary, leaflet, noisy | D | 1 điểm |
| D7 | Vì sao chunk 1.024 token | benchmark, chấm theo section gold | chunk theo mục so với chunk gộp; thêm mục ở k ≈ 15 cùng ngân sách token | Hit@5, tỉ lệ phủ đủ câu đa intent | D | 1 điểm |
| D5 | Viết lại câu hỏi hội thoại | 1.500 conversational | Q1–Q6 so với Q0 | Hit@5 | D5 | 3,6 điểm |
| D3, D4 | Bảng theo nhóm, intent, lát; chi phí embedding | benchmark; đo trên T4 | mô tả, Wilson | | không | |
| D6 | Retrieval tốt hơn có thành e2e tốt hơn | golden tự nhiên + multi_hop (720) | 5 retriever × {one-step, full} so với hybrid + rerank | truthfulness (nugget recall) | D6 | 5,8 điểm |
| A | Jev thay LLM ở vai trò quyết định | golden 1.000 | A3 không thua A2, mỗi model; A4 so với A3 trên Qwen | truthfulness NI 4 điểm, nugget NI 3 điểm; giây, USD | A | biên NI |
| B | Refine theo ngưỡng | golden 1.000; τ chọn trên tập giữ lại | τ=0 so với τ\*, τ\* so với τ=1, Jev so với độ tin cậy nói ra | truthfulness, USD, giây | B | 4,9 điểm |
| C | Graph routing so với ReAct | golden 1.000; multi_hop và multi_turn báo riêng | A2 so với ReAct, mỗi model | truthfulness (nugget, USD, giây) | C | 4,9 toàn bộ; 11 multi_hop |
| E1 | Rephrase | golden 1.000; multi_turn báo riêng | `no-rephrase` so với `full` | truthfulness | E | 4,9 toàn bộ; 12,3 multi_turn |
| E2 | Judge-refine | golden 1.000; multi_hop báo riêng | `no-judge-refine`, `one-step` so với `full`; tỉ lệ cứu có điều kiện (Wilson) | truthfulness, nugget | E | 4,9 |
| E3 | Rerank ở e2e | golden 1.000 | `no-rerank` so với `full` | truthfulness | E | 4,9 |
| E4 | Guard | guard set 300 của tập giữ lại; over-refusal trên golden | `no-guard` so với `full`, cả hai setting | tỉ lệ chặn tấn công, chặn nhầm (Wilson) | E | ±5 điểm mỗi tỉ lệ |
| E5 | Decision model làm judge đánh giá | 450 item có nhãn dược sĩ | Jev per-key-fact so với gemini-3.1-flash-lite | AC1, κ có KTC; USD, giây | E5 | |
| H | Hiệu chuẩn decision model | tập giữ lại §3.3 | mô tả | AUROC, ECE, Brier, tỉ lệ lật khi gọi 3 lần, bootstrap | không | |

Các ablation e2e một model (E1–E3) chạy trên Qwen3.5-9B cấu hình A3; E4 trên A2 và A3 như §4.E.
Run e2e chỉ bắt đầu sau khi S1 và S2 chốt và golden v4 build xong; mọi run trước đó bị bỏ.
