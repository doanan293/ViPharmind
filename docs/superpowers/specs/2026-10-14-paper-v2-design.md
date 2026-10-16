# Spec: Paper v2 — chất lượng, độ trễ và chi phí của agentic RAG cho tra cứu thuốc tiếng Việt

Ngày: 2026-10-14. Trạng thái: chờ duyệt.
Nền: release v1.0.0 (bản nộp SoICT 2026) và ghi chú nghiên cứu trong `docs/research/paper-v2/`.

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
| `vector-cache-llama-cpp-cuda-t4` | acc1 | Giữ | Bản build llama.cpp CUDA cho T4 mà mọi kernel đang dùng |
| `hust-information-retrieval-corpus` | acc1 | Không đụng | Dự án khác |
| 12 dataset `vector-cache-gguf-*` F16/BF16 (khoảng 58 GB) | acc1 | Xoá | Cache model; file v1 dựng lại được từ nguồn Hugging Face ghim commit, sha256 và lệnh `-vimed` trong `docs/guides/evaluation.md` ở tag `v1.0.0` |
| `corpus-pipeline-rag-final`, `seed-pipeline-bundle`, mọi `pipeline-input-*` | acc1, acc2, acc3 | Xoá | Input tạm của kernel, tự sinh lại khi chạy stage |

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
4. **Benchmark và đánh giá.** Benchmark retrieval 10.000 câu thêm lớp hội thoại; bộ e2e 500 item mở
   rộng an toàn lên 50 item mỗi loại; mọi cấu hình báo chất lượng, giây và USD.

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
- Adapter mới `infrastructure/llm/systemone_adapter.py` chỉ cài `structured()` cho hai vai trò
  GUARDRAIL và JUDGE; `stream()` raise `LlmError`. Lỗi HTTP và parse thành `LlmError` để giữ hành vi
  fail-open của guard và `judge_failed` hiện có. Usage lấy từ `usage.input_tokens` của phản hồi.
- `infrastructure/llm/routing.py`: `RoutingLlm(by_role, default)` chọn port theo vai trò.
  `build_application` lắp theo `provider` của từng role. Identity của run ghi `provider` và phiên bản
  model mà phản hồi trả về (`jev-1.13.0`).
- Lưu phản hồi thô của mọi lời gọi decision model vào `answers.jsonl` (trường mới `decisions`) để tái
  lập và để phân tích hiệu chuẩn sau.
- Bộ câu hỏi, đóng băng trong mã, bản nháp ở `03-jev-typesafe.md` §7:
  - Guard, một request mỗi lượt: noul `is_attack`, `is_about_medicines`, `is_smalltalk_or_meta`, cộng
    16 noul `asks_<intent>` cho 16 intent cụ thể của `ALLOWED_INTENT_CATEGORIES`. State gồm lịch sử và
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
- **Model mở** (Qwen3.5-9B) tự host trên Kaggle bằng `pharma-lab e2e llm-server --model
  qwen3.5:9b-q8_0`: llama.cpp GGUF Q8_0, một bản trên mỗi T4 (replicated 2×1, proxy round-robin
  của serve worker chia request), mỗi bản 4 slot × 32.768 token, tức 8 request đồng thời; tunnel
  cloudflared (`docs/guides/e2e-evaluation.md`).
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
- Embedding query: `qwen3-embedding:4b-q8_0`, trên Kaggle khi chạy benchmark retrieval và qua
  `compose.local-models.yaml` khi chạy e2e local, cùng file với index đã dựng.
- Reranker: `qwen3-reranker:4b-q8_0` tự host trên Kaggle bằng `pharma-lab e2e rerank-server` ở
  kernel riêng, replicated 2×1.
- Jev: qua OpenRouter, cả ở lab lẫn production, bằng SDK chính thức của TypeSafe với `base_url`
  `https://openrouter.ai/api` và id `~typesafe/jev-latest` (danh sách model OpenRouter ngày
  2026-10-14 hiện id `typesafe/jev-router`, giá ghi -1, tức OpenRouter không công bố giá cố định).
  Key OpenRouter đặt trong `backend/.env` và `pharma-lab/.env` theo `.env.example`. Ba hệ quả cho
  thiết kế: id `latest` không ghim được phiên bản, nên mỗi run ghi phiên bản model mà phản hồi trả
  về và dừng nếu phiên bản đổi giữa run; ngữ cảnh OpenRouter ghi 32.000 token, nên trần evidence
  của judge phải nằm dưới mức đó (đo ở bước đầu của pha 1); chi phí trong bài tính theo giá niêm yết
  của TypeSafe 0,042 USD mỗi triệu token vào, còn tiền thật lấy từ trường usage và cost của
  OpenRouter. Đây là dịch vụ ngoài trả tiền duy nhất của lab.
- Judge đánh giá: gemini-3.1-flash-lite qua cli-proxy-api; `judge.json` ghi thêm provider. Reasoning
  của judge (RAGAS và judge cấu trúc, hằng `JUDGE_REASONING` trong `judging/structured.py`) đổi từ
  `medium` của v1 sang `none`, vì judge gọi rất nhiều lần mỗi item. Qua proxy, flash-lite có thinking
  thật ở `medium` (291 token reasoning trên một câu tính liều) còn `low` và `none` đều 0 token, nên
  chỉ có hai mức thực sự khác nhau. Trước khi đổi, chấm lại các item dược sĩ đã chấm mù của v1
  (`e2e-gemini` và `e2e-qwen35-9b`, `calibration/grades.jsonl`) bằng `none` vào một run root riêng,
  không ghi đè judgments v1, rồi so κ và AC1 với người chấm ở `medium`. Chênh không đáng kể thì dùng
  `none` cho mọi run v2; tụt rõ thì giữ
  `medium` và bài ghi lý do. Phép thử nhanh ngày 2026-10-14 cho thấy rủi ro là thật: một câu tính
  thể tích (400 mg từ ống 250 mg/5 ml) đúng 8 ml ở `medium` nhưng sai 6,4 ml ở cả `none` và `low`,
  ba lần gọi như nhau.

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

- Port: thêm `LlmPort.tool_call(role, messages, tools) -> (ToolTurn, LlmUsage)` với `ToolTurn` gồm
  `text`, `tool_calls: list[ToolCall{id, name, arguments}]`, `finish_reason`. Adapter OpenAI dùng
  `chat.completions.create(tools=..., parallel_tool_calls=True)`. `RecordingLlm` và các fake ghi theo.
- Graph mới `application/chat/react_graph.py`: nodes `guard` (dùng lại nguyên), `plan` (một lời gọi
  tool_call), `tools` (thực thi), `answer` (khi phản hồi không còn tool call), `fallback`. Lịch sử hội
  thoại đưa thẳng vào messages; không có rephrase, judge, refine riêng.
- Tool, một cái, chỉ đọc, gọi song song được:
  - `search_corpus(query: str)`: `RetrievalService.search` với cùng hybrid RRF, cùng reranker, trả tối đa
    5 chunk dạng `[E<n>] <tiêu đề > các heading> (trang):` rồi nguyên text chunk, đúng văn bản mà
    pipeline đọc (§3.0c). Không có tool đọc lân cận: pipeline graph không có bước nào tương ứng, và
    chunk đã gộp các mục liền kề nên tool đó không còn giá trị; đây là điều kiện để §4.C so sánh đúng
    "ai điều khiển".
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
  và ngày. Latency của Qwen3.5-9B là latency trên hai T4 Kaggle qua tunnel, còn Gemini và Opus là
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

### 3.0b Tập "cần tra nhiều lượt" trong golden (tổng golden vẫn 500 câu)

- Mục đích: làm rõ giá trị của vòng judge-refine, vốn bị che vì retrieval một lượt đã đủ bằng
  chứng cho hầu hết câu (v1 chỉ đo được chênh 0,028 truthfulness khi bỏ vòng lặp).
- Phân bổ golden mới: answerable thường 270 (45 × 6 nhóm), category mới `multi_hop` 150,
  multi-turn 50, unanswerable, out-of-scope, injection 10 mỗi loại. Mục §3.2 nâng nhóm an toàn lên
  50 không còn áp dụng; limitations nêu khoảng tin cậy rộng của 10 câu mỗi loại.
- 150 câu answerable bị bỏ là những câu mà retrieval một lượt (hybrid + rerank, top 5) đã phủ đủ
  section gold, bỏ đều theo nhóm.
- Câu `multi_hop` chọn bằng dữ liệu: ứng viên là câu mà retrieval một lượt thiếu ít nhất một
  section gold. Bốn loại, mỗi loại 30 đến 45 câu: đa intent ba mục; hai thuốc (tương tác hoặc so
  sánh, bằng chứng từ hai chuyên luận); biệt dược sang hoạt chất (tờ hướng dẫn thiếu mục, Dược thư
  có); câu nhiễu hoặc gõ sai mà vòng đầu trượt. Vì chunk gộp các mục liền kề (§3.0c), ba mục của
  cùng một tờ hướng dẫn thường nằm chung một chunk và vòng 1 đã phủ đủ, nên loại "đa intent ba mục"
  chỉ còn những câu mà các mục gold rơi vào hai chunk khác nhau. Loại nào dưới 30 ứng viên thì quota
  chuyển đều sang ba loại còn lại. Tỷ lệ câu đa intent trong benchmark mà một chunk đã phủ đủ mọi
  mục gold là một số báo trong bài, cạnh D7, để chỉ ra phần việc của vòng refine mà cách gộp mục đã
  làm thay. Key fact, quote và `golden check` như hiện nay; bản nháp key fact do LLM qua proxy trích
  từ section gold, tác giả và dược sĩ duyệt.
- Metric mới cho vòng lặp, báo riêng trên `multi_hop` và trên phần còn lại: độ phủ section gold
  sau vòng 1 và sau vòng cuối, số vòng thực dùng, tỷ lệ câu được cứu (thiếu sau vòng 1, đủ sau vòng
  cuối). `AnswerRecord` lưu evidence của từng vòng.

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

- Sinh bằng luật từ benchmark 10.000 câu, kế thừa gold section của câu cha, không cần gắn nhãn mới.
  Kích thước 1.500 item, lấy từ cả sáu nhóm và 16 intent, phân tầng theo nhóm × intent và theo việc
  câu cha có được hybrid + rerank top 5 một lượt phủ đủ gold hay không (benchmark không còn trường
  difficulty, §3.0).
- Mỗi item 2 đến 4 lượt người dùng xen câu trả lời hệ thống cố định (một đến hai câu đầu của gold
  section lượt trước), chỉ lượt cuối được chấm. Tám hiện tượng, mỗi item một nhãn: đại từ chỉ thuốc,
  tỉnh lược chủ ngữ, đổi intent cùng thuốc, đổi thuốc cùng intent, tham chiếu thực thể trong câu trả
  lời trước, đổi chủ đề hoàn toàn, tích lũy đa intent, follow-up nhiễu. Giữ tập brand-name trong mọi
  hiện tượng.
- Schema: thêm `turns`, giữ `query` là lượt cuối; `eval_group="conversational"`, `query_form` theo
  hiện tượng. Runner thêm `query_mode` và cache rewrite theo model.
- Chiến lược truy vấn so sánh, cùng index, cùng hybrid RRF k=2 và Qwen3-Reranker-4B:
  Q0 lượt cuối như gõ; Q1 nối toàn bộ lịch sử; Q1b nối hai lượt gần nhất; Q2 viết lại độc lập (bước
  rephrase hiện nay); Q3 viết lại từ lịch sử làm giàu kiểu CHIQ (năm prompt); Q3b Q2 với câu trả lời
  grounded trước đó và rolling summary làm lịch sử; Q5 RRF hai bản viết lại; Q6 oracle là câu cha.
  Rewriter: gemini-3.1-flash-lite và Qwen3.5-9B. Báo Hit@3/5/10, MRR@10, nDCG@10, CER@10, số lời gọi và
  token mỗi rewrite, chênh với oracle, phân theo hiện tượng và độ sâu lượt, kiểm định Holm.

### 3.2 Bộ e2e

- Nâng `QUOTAS` unanswerable, out_of_scope, injection lên 50 mỗi loại; viết thêm 120 item theo hướng
  dẫn authoring hiện có, với tập injection phủ thêm kiểu tấn công kênh lựa chọn (Azizi et al.) và chèn
  nội dung tự nhiên vào câu hỏi (Xu et al.). Run cũ chỉ chạy bổ sung item mới.

### 3.3 Tập giữ lại cho ngưỡng và hiệu chuẩn

- Ngưỡng guard và judge không được chỉnh trên bộ golden. Dùng một tập hiệu chuẩn riêng lấy từ benchmark
  retrieval: 300 câu có gold section, với evidence do pipeline lấy về, nhãn "đủ bằng chứng" tính từ gold
  (top-k có chứa gold section hay không, và với đa intent là có đủ mọi section không); cộng 100 câu tấn
  công và ngoài phạm vi sinh thêm cho guard. Báo AUROC, ECE, và độ chính xác tại ngưỡng chọn của Jev,
  kèm kiểm tra xoay thứ tự lựa chọn và tỷ lệ lật quyết định khi gọi lặp 3 lần.
- Hiệu chuẩn judge đánh giá bằng dược sĩ chấm mù giữ giao thức v1, mở rộng mẫu cho các cấu hình mới
  (50 item mỗi cấu hình chính) và báo tương quan lỗi giữa judge và người chấm theo Rao và Callison-Burch.

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
  dạng, gọi trùng, trả lời không trích dẫn); cùng kết quả trên 50 item nhiều lượt và 50 item injection
  vì ReAct không có rephrase và guard chỉ ở ngoài.
- Qwen3.5-9B tự host trên Kaggle, Gemini 3.8 Flash và Claude Opus 5.5 qua cli-proxy-api (§2.1b);
  bài ghi rõ phần cứng, precision và mức thinking.

### D. Retrieval

- D1 dense Qwen3-Emb-4B + Qwen3-Reranker-4B, so với hybrid + reranker (trả lời "sao phải hybrid").
- D2 ablation enrichment: một biến thể duy nhất không enrichment (không header, glossary, colloquial)
  trên hybrid + rerank; phân theo nhóm, nhất là noisy và leaflet.
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
- Thí nghiệm phụ "decision model làm judge đánh giá": chấm lại 500 item bằng Jev per-key-fact, so với
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
judge với evidence tới 19k token, tức khoảng 16k token Jev mỗi item và 8M token mỗi run 500 item,
khoảng 0,34 USD mỗi run theo giá niêm yết. Ba run A3, một run A4, 12 điểm quét τ và tập hiệu chuẩn
§3.3 cộng lại khoảng 6 đến 8 USD, cộng phí OpenRouter nếu có; đó là khoản tiền thật duy nhất. Qwen3.5-9B và reranker chạy trên quota GPU Kaggle; mọi run Qwen (A2, A3, A4, ReAct,
quét τ, ablation) phải xếp theo quota tuần của các account Kaggle.
Gemini 3.8 Flash, Claude Opus 5.5 và judge gemini-3.1-flash-lite đi qua proxy thuê bao nên không
tốn thêm; giá niêm yết của chúng (khoảng 120 USD cho ba run Opus 5.5, 20 USD cho judge) chỉ xuất
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
  weights), chưa đo: lần khởi động đầu của `e2e llm-server` ở pha 0 xác nhận server lên được; nếu
  hết VRAM thì giảm còn 3 slot. ReAct vẫn ghi số lượt chạm trần ngữ cảnh vào bảng thất bại.
- Credential OAuth Antigravity hoặc Claude của cli-proxy-api hết hạn, hết quota, hoặc đổi danh sách
  model được dùng: proxy trả `auth_unavailable`, khi đó chép lại credential từ ProxyPal; `pin_judge`
  và run identity vẫn ghi tên model nên run tiếp tục được sau khi khôi phục.
- Độ trễ đo từ Việt Nam tới endpoint ở xa (tunnel Kaggle, gateway của proxy): số tuyệt đối gồm
  mạng, và Qwen trên T4 không cùng phần cứng với model thương mại; bài chỉ so latency giữa kiến
  trúc trên cùng một model (§2.5).
- Giấy phép và điều khoản Jev về công bố benchmark: kiểm tra Master Customer Agreement trước khi công bố.

## 9. Ngoài phạm vi

Huấn luyện hoặc fine-tune bất kỳ model nào; corpus mới hoặc câu hỏi người dùng thật; kiến trúc đa agent;
benchmark decision model tổng quát ngoài miền thuốc; thay judge đánh giá chính của bài.
