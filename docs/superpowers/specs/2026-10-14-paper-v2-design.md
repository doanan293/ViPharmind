# Spec: Paper v2 — chất lượng, độ trễ và chi phí của agentic RAG cho tra cứu thuốc tiếng Việt

Ngày: 2026-10-14. Trạng thái: chờ duyệt.
Nền: release v1.0.0 (bản nộp SoICT 2026) và ghi chú nghiên cứu trong `docs/research/paper-v2/`.

## 0. Mục tiêu

Bản v2 không nhắm một venue cụ thể. Mục tiêu là bài tốt nhất có thể, với tính mới tập trung vào
**đo chất lượng, độ trễ và chi phí cùng nhau** cho agentic RAG trên model rẻ. Mọi điểm yếu mà
reviewer có thể bắt phải được giải quyết bằng thí nghiệm hoặc phân tích, không bằng cách hạ tuyên bố.
Không huấn luyện model nào. Không đổi corpus. Giữ một bài duy nhất với benchmark làm xương sống.

Thành công nghĩa là: bốn đóng góp dưới đây đều có bảng hoặc hình riêng với kiểm định ghép cặp; mọi cấu
hình trong bài đều có đủ ba trục chất lượng, giây mỗi lượt và USD mỗi 1.000 lượt; mọi câu hỏi trong
review bản v1 (xem §4.E) có một thí nghiệm trả lời; bài đọc như một benchmark paper chuẩn.

## 1. Câu chuyện và đóng góp

Khung đặt vấn đề lấy từ Fensore et al. 2025: RAG chuyên ngành chỉ giúp khi retrieval đủ tốt. Bài v1
đã cho thấy với Hit@10 97,5 % thì grounding cắt hallucination 18 đến 25 lần. Bản v2 hỏi tiếp: khi
retrieval đã tốt, giữ chất lượng đó với độ trễ và chi phí thấp nhất bằng cách nào. Bốn đóng góp:

1. **Tách quyết định khỏi sinh văn bản.** Các bước chỉ ra quyết định (guard, judge đủ bằng chứng,
   phủ theo intent) chạy trên decision model không sinh văn bản trả về xác suất đã hiệu chuẩn (Jev
   thương mại và Strands Decider 2B open weights); các bước sinh văn bản (rephrase, refine, answer) chạy
   trên LLM nhỏ. Đo cái gì được, cái gì mất, và hiệu chuẩn của decision model trên tiếng Việt.
2. **Refinement theo độ tin cậy.** Vòng retrieve-more chỉ chạy khi xác suất "đủ bằng chứng" của judge
   dưới ngưỡng τ. Quét τ cho đường Pareto chi phí, độ trễ so với truthfulness, theo giao thức báo cáo
   của Qian et al. 2026.
3. **Graph routing so với agent ReAct trên bộ model rẻ.** Cùng corpus, retriever, tool, ngân sách và
   định dạng trả lời; chỉ khác ai điều khiển. Sáu model gọi qua API: ba model mở rẻ, hai model thương
   mại rẻ và một model nặng làm trần tham chiếu. Với mỗi model, kiến trúc nào cho chất lượng cao nhất
   trên mỗi USD và mỗi giây, và model nặng hơn có đổi kết luận không.
4. **Benchmark và đánh giá.** Benchmark retrieval 10.000 câu thêm lớp hội thoại; bộ e2e 500 item mở
   rộng an toàn lên 50 item mỗi loại; mọi cấu hình báo chất lượng, giây và USD.

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
  `{state, model, questions}` mà cả Jev lẫn Strands Decider 2B cùng nói.
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
    của bài vẫn là gemini-3.1-flash-lite để so sánh được với v1.
- Giới hạn cần tôn trọng: 64k token mỗi request, 32k cho state cộng câu hỏi dài nhất; evidence 24.000
  ký tự tiếng Việt ước 7 đến 16k token. Việc đầu tiên của plan là đo `usage.input_tokens` cho một khối
  evidence 24.000 ký tự. Câu hỏi viết bằng tiếng Anh, nội dung tiếng Việt nằm trong state.
- Strands Decider 2B là đối chứng open weights **tùy chọn**, chỉ làm ở pha 4 nếu còn thời gian, vì
  không có API hosted nên phải tự host trên Kaggle T4 qua `strands-decider serve` (cùng endpoint).
  Bài v2 chạy được trọn vẹn chỉ với Jev.

### 2.1b Mọi LLM gọi qua API: model mở qua OpenRouter, model thương mại qua cli-proxy-api

- Không tự host LLM nữa, kể cả Qwen3.5-9B; run v1 tự host được giữ làm tham chiếu lịch sử và bài
  ghi rõ khác biệt. Mỗi vai trò có `BASE_URL`, `API_KEY` và `MODEL` riêng như hiện nay, nên hai
  đường dưới đây trộn được trong một run.
- **Model mở** (Qwen3.5-9B, Qwen3.8-27B, DeepSeek V4.1 Flash) qua `https://openrouter.ai/api/v1`
  với id OpenRouter. `extra_body` mang `provider: {order: [<slug>], allow_fallbacks: false,
  require_parameters: true}` để một model luôn đi một provider, một precision; Qwen3.5-9B ghim
  DeepInfra bf16. Response của OpenRouter ghi provider thực tế, lưu vào `answers.jsonl`. Dự án chưa
  có key OpenRouter; đặt vào `backend/.env` và `pharma-lab/.env` theo `.env.example`.
- **Model thương mại** (Gemini 3.8 Flash, gemini-3.1-flash-lite, GPT-6 Luna, Claude Opus 5.5) qua
  service `cli-proxy-api` của compose (image `eceasy/cli-proxy-api:v8.0.28`, bản cũ v7.3.0 giả lập
  Claude Code quá cũ để gọi Opus 5.5), endpoint `http://127.0.0.1:8317/v1`, key `proxypal-local`,
  như v1 đã dùng cho Gemini. Credential OAuth lấy từ ProxyPal trên Windows và
  chép vào volume `vipharmind_cli_proxy_auth` (README, mục CLIProxyAPI); đã đồng bộ ngày 2026-10-14
  với ba credential Antigravity, Claude và Codex. Đã gọi thử structured output thành công với
  `gemini-3.8-flash-high`, `gemini-3.1-flash-lite`, `gpt-6-luna`, `gpt-6-sol`, `gpt-6-astra`,
  `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`; `gpt-6.1-sol` bị tài khoản ChatGPT từ
  chối. Quota ChatGPT hạn chế nên GPT chỉ giữ Luna, model nặng của bài là Claude Opus 5.5.
- **Reasoning tắt hoặc thấp nhất có thể ở mọi model**, ghi rõ trong bài: GPT-6 Luna
  `reasoning_effort: none` (0 token reasoning); Gemini 3.8 Flash qua Antigravity chỉ có id
  `gemini-3.8-flash-high` và override payload trong `config.yaml` đặt `thinkingLevel: low`, mức thấp
  nhất model nhận (`minimal` bị từ chối), đo được 0 token reasoning; gemini-3.1-flash-lite không
  thinking; Claude Opus 5.5 không cho tắt thinking, dùng adaptive với `reasoning_effort: minimal`;
  Qwen3.5-9B và Qwen3.8-27B `chat_template_kwargs.enable_thinking: false`; DeepSeek V4.1 Flash
  `reasoning: {enabled: false}` trên OpenRouter. Khác với v1, nơi Gemini chạy thinking high, nên
  A1 chạy lại ở mức low và bài giữ số v1 làm tham chiếu lịch sử.
- Chi phí trong bài luôn tính theo giá niêm yết nhân token, kể cả với model thương mại đi qua
  proxy thuê bao, và bài nói rõ điều đó. Tiền thật phải trả chỉ phát sinh ở OpenRouter cho ba model
  mở và ở Jev.
- Embedding query: OpenRouter có `qwen/qwen3-embedding-4b`; trước khi dùng phải chạy kiểm tra tương
  đương trên 1.000 câu benchmark (Hit@10 và MRR@10 so với cache embedding llama.cpp fp16 của v1,
  chấp nhận chênh dưới 0,3 điểm). Không đạt thì embedding ở DeepInfra như production hiện nay.
- Reranker: OpenRouter không có endpoint rerank, nên Qwen3-Reranker-4B gọi DeepInfra qua
  `PHARMA_RETRIEVAL__RERANK__PROTOCOL=deepinfra` đã có.
- Jev: gọi thẳng `api.typesafe.ai` bằng SDK chính thức, vì bản qua OpenRouter chưa công bố giá.
- Judge đánh giá: gemini-3.1-flash-lite cũng qua OpenRouter; `judge.json` ghi thêm provider.

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
- Tool, hai cái, chỉ đọc, chạy song song được:
  - `search_corpus(query: str)`: `RetrievalService.search` với cùng hybrid RRF, cùng reranker, trả tối đa
    5 hit dạng `[E<n>] <tiêu đề > đường dẫn mục> (trang): <đoạn trích>`; cùng mức mở rộng ngữ cảnh.
  - `read_section(section_id: str)`: `CorpusReader.section_chunks`, trả nguyên mục, cắt theo đầu và đuôi
    với dấu `(Đã lược N ký tự ...)` ở trần 2.000 token.
- Quy tắc dừng và ngân sách: dừng khi phản hồi không có tool call; tối đa 6 vòng tool; hết vòng thì một
  lời gọi cuối không tool với ghi chú "đã hết lượt tra cứu, trả lời từ những gì đã có"; cùng
  `max_llm_calls`, `max_tokens`, `max_evidence_chars` và deadline với pipeline; gọi trùng (tool, args)
  trả lại kết quả cũ kèm một dòng nhắc; lỗi tool trả về dạng text `Error: ...` chứ không ném.
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
  2026-10-14, ghi nguồn và ngày, USD mỗi triệu token vào/ra: Qwen3.5-9B 0,10/0,15 (DeepInfra bf16);
  Qwen3.8-27B 0,04/2,30; DeepSeek V4.1 Flash 0,021/0,89; Gemini 3.8 Flash 0,75/3,75; GPT-6 Luna
  0,10/0,50; Claude Opus 5.5 4/20 (claude.com/pricing, prompt dưới 100k token); gemini-3.1-flash-lite
  0,25/1,50; Jev 0,042/0; Qwen3-Reranker-4B và
  embedding theo giá DeepInfra hoặc OpenRouter tại ngày chạy. Mọi chi phí là giá niêm yết, không có
  mô hình giờ GPU vì không tự host.
- Metric mới: `usd_per_turn`, `usd_per_1000_turns`, `llm_seconds_per_turn`, `retrieval_seconds_per_turn`,
  `decision_seconds_per_turn`, `cost_of_pass` (USD chia tỷ lệ perfect, theo Erol et al.). Bảng
  `cost.csv|tex`.
- Giao thức đo: run đo latency chạy với concurrency 1 trên cùng máy và cùng endpoint, ghi vùng địa lý
  và ngày; run lấy chất lượng có thể chạy concurrency 4 nhưng latency lấy từ run concurrency 1. Báo
  p50 và p95. Mỗi lời gọi decision model đo client-side.

### 2.6 Công tắc và biến thể khác

- `PipelineOptions.guard: bool` cho ablation không guard.
- `settings_for` cho các biến thể retriever e2e: `bm25`, `dense`, `hybrid k=60`.
- `EnrichmentOptions(header, glossary, colloquial)` trong `chunk_section`, một biến thể tắt cả ba,
  hậu tố `CHUNKER_VERSION` riêng, re-embed và import thành release riêng với alias Qdrant riêng. Bỏ
  colloquial cần sửa `_MappingCollector.add_leaflet` để không tự thêm product names.
- Sửa mã cho khớp bài hoặc sửa bài cho khớp mã: `rerank.top_n` 8 và `max_candidates` 40. Quyết định:
  giữ mã, sửa bài, vì mọi run v1 đã dùng giá trị này.

## 3. Dữ liệu và benchmark

### 3.0 Sửa dữ liệu trước mọi run mới (theo `docs/research/paper-v2/07-dataset-review.md`)

- **Corpus:** tách mỗi tờ hướng dẫn theo heading markdown có sẵn thành section con (p50 16 heading
  mỗi tờ), chuẩn hóa tên heading về bộ intent bằng bảng ánh xạ trong `relevance_judgments.py`,
  header context `<sản phẩm> > <heading>`. Re-embed trên Kaggle như v1 (bundle embed chỉ có backend
  local và Kaggle; cache theo sha của text nên chỉ chunk leaflet mới tốn GPU), release mới sinh từ
  digest bundle, `CHUNKER_VERSION` giữ nguyên. Giữ `MAX_CHUNK_CHARS = 3000`; không ablation kích
  thước chunk, bài biện minh bằng thống kê token (p50 657 token, 78 % section một chunk).
- **Benchmark retrieval:** sinh lại từ release mới. Bỏ mọi hậu tố "(phần ...)" và đáp án trong
  ngoặc; chunk_coverage hỏi theo intent của heading chứa chunk; leaflet dùng tên sản phẩm chuẩn hóa
  (thương hiệu, hàm lượng, dạng) thay tiêu đề marketing; patient_natural đổi tên thành
  leaflet_short và mô tả đúng là template ngắn; bỏ nhóm confuser, 200 câu chuyển cho noisy dưới
  dạng lỗi gõ sinh tự động bên cạnh 300 câu bỏ dấu; bỏ trường difficulty; tách general_info thành
  intent cụ thể (overdose, storage, pharmacology, general_info); mở rộng any_acceptable cho sản
  phẩm có chunk trùng văn bản. Giữ 10.000 câu và sáu nhóm.
- **Golden e2e:** giữ nguyên nội dung, chỉ viết lại 50 item có hậu tố "(phần ...)"; gold section
  của item leaflet ánh xạ sang section con mới; chạy `golden check`.
- **Hệ quả:** mọi số retrieval v1 vô hiệu; chạy lại bảng retrieval với năm embedding tự host và
  bốn reranker trên Kaggle (bỏ BGE-reranker-v2-gemma; bỏ OpenAI text-embedding-3-large vì run v1 là
  run nhập từ pipeline cũ, không tái lập được); bài có đoạn "so với v1" nói rõ v1 có gợi ý trong
  câu hỏi.

### 3.1 Lớp hội thoại của benchmark retrieval

- Sinh bằng luật từ benchmark 10.000 câu, kế thừa gold section của câu cha, không cần gắn nhãn mới.
  Kích thước 1.500 item, lấy từ cả sáu nhóm và 16 intent, phân tầng theo độ khó.
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
- Bộ golden 500 item hiện tại giữ nguyên nội dung các item cũ để so sánh với v1.

### 3.3 Tập giữ lại cho ngưỡng và hiệu chuẩn

- Ngưỡng guard và judge không được chỉnh trên bộ golden. Dùng một tập hiệu chuẩn riêng lấy từ benchmark
  retrieval: 300 câu có gold section, với evidence do pipeline lấy về, nhãn "đủ bằng chứng" tính từ gold
  (top-k có chứa gold section hay không, và với đa intent là có đủ mọi section không); cộng 100 câu tấn
  công và ngoài phạm vi sinh thêm cho guard. Báo AUROC, ECE, và độ chính xác tại ngưỡng chọn, cho Jev
  và Decider 2B, kèm kiểm tra xoay thứ tự lựa chọn và tỷ lệ lật quyết định khi gọi lặp 3 lần.
- Hiệu chuẩn judge đánh giá bằng dược sĩ chấm mù giữ giao thức v1, mở rộng mẫu cho các cấu hình mới
  (50 item mỗi cấu hình chính) và báo tương quan lỗi giữa judge và người chấm theo Rao và Callison-Burch.

## 4. Ma trận thí nghiệm

Ký hiệu vai trò: G guard, J judge, R refine, P rephrase, A answer. Mọi cấu hình chạy trên cùng bộ
golden và cùng judge đánh giá.

### A. Phân vai theo loại model (đóng góp 1)

Bộ sáu model dùng xuyên suốt bài (giá USD mỗi triệu token vào/ra, OpenRouter 2026-10-14):

| Nhóm | Model | Giá | Vai trò trong bài |
| --- | --- | --- | --- |
| Mở, rẻ | Qwen3.5-9B | 0,10 / 0,15 | nối với v1 |
| Mở, rẻ | Qwen3.8-27B | 0,04 / 2,30 | Qwen dense mới nhất |
| Mở, rẻ | DeepSeek V4.1 Flash | 0,021 / 0,89 | họ mở ngoài Qwen |
| Thương mại, rẻ | Gemini 3.8 Flash | 0,75 / 3,75 | nối với v1 |
| Thương mại, rẻ | GPT-6 Luna | 0,10 / 0,50 | model rẻ nhất của OpenAI; model GPT duy nhất vì quota ChatGPT hạn chế |
| Nặng, trần tham chiếu | Claude Opus 5.5 | 4 / 20 | giới hạn trên của chất lượng |

| Cấu hình | G, J | R | P, A | Ghi chú |
| --- | --- | --- | --- | --- |
| A1 gemini (v1) | gemini-3.1-flash-lite, 3.8-flash | LLM | 3.1-flash-lite, 3.8-flash | đã có, chạy lại qua OpenRouter |
| A2 llm-only, mỗi model | cùng model | LLM | cùng model | sáu run, mọi vai trò trên một LLM |
| A3 jev + mỗi model | Jev | template | cùng model | sáu run, cấu hình chính của bài |
| A4 jev + qwen9b, refine LLM | Jev | LLM | Qwen3.5-9B | tách tác dụng của refine template |
| A5 decider2b + qwen9b | Decider 2B | template | Qwen3.5-9B | tùy chọn, cần tự host |

Kết quả: bảng chính v2 với truthfulness, nugget recall, hallucination, severe harm, faithfulness,
citation recall, các metric an toàn, giây mỗi lượt p50 và p95, USD mỗi 1.000 lượt; hình teaser
truthfulness theo giây và theo USD, mỗi cấu hình một điểm; hình tách thời gian mỗi lượt theo bước.

### B. Refinement theo độ tin cậy (đóng góp 2)

- Trên A3 với Qwen3.5-9B và với Gemini 3.8 Flash: τ ∈ {0, 0,3, 0,5, 0,7, 0,9, 1}. Trên A2 Qwen3.5-9B: cùng
  dải với độ tin cậy nói ra của LLM judge.
- Báo theo Qian et al. 2026: đường biên chất lượng so với chi phí và so với độ trễ, tỷ lệ refine thực
  tế, chi phí của chính bước judge, độ ổn định của τ khi chuyển model (τ chọn trên Qwen3.5-9B áp sang
  các model còn lại của A3), tỷ lệ gây hại khi bỏ refine.
- Phân tích tương quan lỗi: judge nói "đủ" nhưng câu trả lời thiếu key fact, theo nhóm câu hỏi.

### C. Graph routing so với ReAct trên bộ sáu model (đóng góp 3)

Hai nhánh dùng cùng một LLM cho mọi vai trò, để khác biệt chỉ còn là ai điều khiển. Nhánh graph
routing là A2 của model đó; nhánh ReAct là một run mới cùng model. Các cấu hình có decision model
(A3) không thuộc so sánh này mà được vẽ thêm như điểm tham chiếu. Câu hỏi của bài không còn là "cỡ
nào thì ReAct bắt kịp" mà là "với mỗi model rẻ và với model nặng, kiến trúc nào cho chất lượng cao
nhất trên mỗi USD và mỗi giây", cộng một nhận xét về xu hướng theo sức mạnh model.

- Giữ cố định: tool, retriever, reranker, mức bằng chứng, định dạng trả lời, reasoning effort, nhiệt độ,
  judge đánh giá. Giao diện gọi được nêu rõ: structured output cho pipeline, native tool calling cho
  ReAct (Patel et al. 2026 chỉ ra giao diện là một nhiễu).
- Báo: hình mặt phẳng chất lượng so với USD và so với giây, mỗi model hai điểm nối bằng một đoạn
  (graph routing và ReAct); bảng thất bại của ReAct theo loại (chạm trần vòng, tool call sai định
  dạng, gọi trùng, trả lời không trích dẫn); cùng kết quả trên 50 item nhiều lượt và 50 item injection
  vì ReAct không có rephrase và guard chỉ ở ngoài.
- Mọi model qua OpenRouter với provider ghim cố định (§2.1b), ghi rõ provider và precision trong bài.

### D. Retrieval

- D1 dense Qwen3-Emb-4B + Qwen3-Reranker-4B, so với hybrid + reranker (trả lời "sao phải hybrid").
- D2 ablation enrichment: một biến thể duy nhất không enrichment (không header, glossary, colloquial)
  trên hybrid + rerank; phân theo nhóm, nhất là noisy và leaflet.
- D3 bảng retrieval theo nhóm câu hỏi và độ khó cho các cấu hình chính.
- D4 cột chi phí dense: số tham số và tốc độ encode query trên T4, thay cho chỉ có dimension.
- D5 chiến lược truy vấn hội thoại Q0 đến Q6 (§3.1).
- D6 đường cong retrieval đến e2e: chạy one-step và full với bm25, dense, hybrid k=60, hybrid k=2 không
  rerank, hybrid có rerank; vẽ truthfulness theo Hit@10 và nDCG@10; giải thích vì sao bỏ reranker không
  đổi e2e ở v1 (vòng judge-refine bù).

### E. Sửa các điểm review v1

- Khoảng tin cậy trong mọi bảng e2e (CSV đã có, bảng LaTeX sinh thêm).
- Lệnh `e2e compare --run A --run B` cho kiểm định ghép cặp xuyên run (Gemini full so với Qwen full).
- Ablation rephrase và judge-refine với Qwen3.5-9B; ablation guard với cả hai setting.
- Phân loại lỗi còn lại của full agent từ `errors.md` thành bảng taxonomy.
- Phân tích citation recall: câu không trích dẫn so với trích dẫn sai passage.
- Thí nghiệm phụ "decision model làm judge đánh giá": chấm lại 500 item bằng Jev per-key-fact, so với
  gemini-3.1-flash-lite và nhãn dược sĩ; báo κ, chi phí và giây.
- Sửa số liệu và câu chữ đã liệt kê trong review (Hit@5 3,7 so với 3,8; BGE-gemma có cải thiện nDCG;
  "unanswered" so với missing; header Table 3; top 8 và 40 ứng viên; footnote repo).

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
  quy tắc công bằng, giao thức đo độ trễ và chi phí.
- Limitations viết theo `03-jev-typesafe.md` §8 và `05-literature-survey.md` §H: closed weights, early
  access, giá có thể được trợ, hiệu chuẩn vendor tự khai, tiếng Việt không có số liệu công bố, tấn công
  kênh lựa chọn và ngữ cảnh tự nhiên, decision model không phải cổng an toàn duy nhất, độ trễ đo từ
  Việt Nam đến endpoint Mỹ.
- Table 2 gọn lại (bỏ MRR@30, bỏ Hit@30 ở khối reranker) để nhường chỗ cho hàng mới.

## 7. Thứ tự thực hiện

Mỗi pha là một plan riêng, chạy xong mới sang pha sau trừ khi ghi khác. Pha D đứng trước pha 0; hai
pha có thể gối nhau ở phần mã vì pha 0 không phụ thuộc dữ liệu, nhưng mọi run đo đều chờ pha D.

0. **Pha D, dữ liệu.** §3.0: tách leaflet theo heading, release mới, sinh lại benchmark, viết lại 50
   item golden, chạy lại bảng retrieval (sáu embedding qua API, bốn reranker trên Kaggle). Mọi pha
   sau chạy trên release và benchmark này.
1. **Pha 0, hạ tầng đo và chuyển API.** §2.1b (OpenRouter cho mọi LLM, provider ghim, kiểm tra tương
   đương embedding, reranker DeepInfra), §2.5 và §2.6 (trừ enrichment), `e2e compare`, pricing,
   steps latency, bảng cost. Xác nhận bằng cách chạy lại A1 và A2 Qwen3.5-9B qua OpenRouter và so với
   bảng v1 có thêm cột giây và USD.
2. **Pha 1, decision model.** §2.1, §2.2, §2.3, §3.3. Đo token Vietnamese trên Jev; chạy tập hiệu
   chuẩn; chọn τ; chạy A2 và A3 cho sáu model, A4, và quét B. Kết quả đóng góp 1 và 2.
3. **Pha 2, ReAct.** §2.4 và ma trận C. Có thể chạy song song pha 1 vì không chung mã, chỉ chung hạn
   mức API.
4. **Pha 3, retrieval.** §3.1, D1 đến D6, enrichment §2.6. D1 và D6 làm trước vì rẻ.
5. **Pha 4, e2e bổ sung.** §3.2, các mục E còn lại, hiệu chuẩn dược sĩ mở rộng.
6. **Pha 5, viết.** §6, hình và bảng, build sạch warning.

Tiêu chí chấp nhận mỗi pha: lint, type và test của backend và pharma-lab xanh; run có `run.json` đầy đủ
identity; báo cáo sinh bằng lệnh có sẵn chứ không chép tay; số liệu vào bài chỉ từ file báo cáo.

Ngân sách tiền thật, ước theo 11.600 token mỗi lượt của full agent v1 và ReAct gấp đôi: ba model mở
trên OpenRouter nhân ba run (A2, A3, ReAct) cộng quét τ và ablation trên Qwen3.5-9B khoảng 15 USD;
Jev dưới 2 USD. Model thương mại, kể cả Claude Opus 5.5, và judge gemini-3.1-flash-lite đi qua proxy
thuê bao nên không tốn thêm; giá niêm yết của chúng (khoảng 120 USD cho Opus 5.5, 20 USD cho judge)
chỉ xuất hiện trong bảng chi phí của bài. Quota ChatGPT thấp nên các run GPT-6 Luna xếp sau cùng và
chạy thử 20 item trước. Mỗi run chạy thử 20 item trước khi chạy đủ.

## 8. Rủi ro

- Jev early access, giới hạn và giá có thể đổi: ghim phiên bản, lưu phản hồi thô, chạy pha 1 sớm.
- Jev tiếng Việt: người dùng đã thử ổn, nhưng tập hiệu chuẩn §3.3 là bằng chứng trong bài. Nếu AUROC
  thấp thì Decider 2B và LLM judge là đối chứng, và kết quả vẫn là finding.
- Nhiều noul trong một request thiên về "có": ngưỡng chỉnh trên tập giữ lại, báo AUROC thay vì chỉ độ
  chính xác tại 0,5.
- Model rẻ có thể gọi tool kém trong ReAct: đó là kết quả, nhưng phải tách lỗi harness khỏi lỗi model
  bằng bảng thất bại theo loại và biến thể có và không có chặn gọi trùng.
- Embedding query qua OpenRouter có thể lệch với index đã dựng bằng llama.cpp fp16: kiểm tra tương
  đương trước (§2.1b), không đạt thì giữ DeepInfra.
- Provider trên OpenRouter có thể đổi giá hoặc rút model giữa chừng: ghi provider và giá vào từng
  run, chạy mỗi cấu hình trọn trong một đợt.
- Credential OAuth của cli-proxy-api hết hạn hoặc tài khoản ChatGPT, Claude đổi danh sách model được
  dùng: proxy trả `auth_unavailable`, khi đó chép lại credential từ ProxyPal; `pin_judge` và run
  identity vẫn ghi tên model nên run tiếp tục được sau khi khôi phục.
- Độ trễ đo từ Việt Nam tới gateway Mỹ: mọi model cùng điều kiện nên so sánh được, nhưng số tuyệt đối
  gồm mạng; ghi rõ trong bài.
- Giấy phép và điều khoản Jev về công bố benchmark: kiểm tra Master Customer Agreement trước khi công bố.

## 9. Ngoài phạm vi

Huấn luyện hoặc fine-tune bất kỳ model nào; corpus mới hoặc câu hỏi người dùng thật; kiến trúc đa agent;
benchmark decision model tổng quát ngoài miền thuốc; thay judge đánh giá chính của bài.
