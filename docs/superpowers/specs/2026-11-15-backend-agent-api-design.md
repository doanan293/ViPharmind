# Backend agent dược và API cho web

Ngày: 2026-11-15. Trạng thái: thiết kế hiện hành, mô tả đúng mã của nhánh `v2.0.0` (commit `9732e8e`).
Gộp và thay cho các spec, plan cũ liệt kê ở mục 9.

## 1. Mục tiêu và phạm vi

Backend `backend/` (package `pharma_agent`) là một service FastAPI trả lời câu hỏi về thuốc bằng
tiếng Việt, dựa trên corpus Dược thư Quốc gia Việt Nam, tờ hướng dẫn sử dụng và các collection do
người dùng hay tổ chức xuất bản. Spec này phủ:

- vòng lặp agent của một lượt hỏi đáp (guard, rephrase, search, judge, refine, answer) và biến thể
  ReAct dùng cho đánh giá;
- lớp LLM (vai trò, endpoint, decision model) và cách agent gọi retrieval;
- hội thoại, bộ nhớ, lưu một lượt, citation, feedback;
- API web cho chat: stream, lịch sử, phân trang, lỗi, OpenAPI; observability; CLI của agent;
- cách kiểm thử phần trên, gồm server E2E cho Playwright.

Phần sau thuộc spec khác, ở đây chỉ nhắc một câu:

- corpus, knowledge bundle, chunking, import, release, embedding và reranker:
  [corpus-data-pipeline](2026-11-15-corpus-data-pipeline-design.md);
- tài khoản, phiên đăng nhập, Google OAuth, tổ chức, collection, phân quyền, quota, triển khai:
  [product-accounts-orgs](2026-11-15-product-accounts-orgs-design.md);
- quy tắc phân tầng, import-linter, vị trí test: [architecture-rules](2026-11-15-architecture-rules-design.md);
- giao diện web: [frontend](2026-11-15-frontend-design.md);
- benchmark, golden, harness đánh giá e2e: [evaluation](2026-11-15-evaluation-design.md);
- lý do nghiên cứu của decision model, refine theo độ tin cậy và ReAct (paper v2):
  [soict-paper](2026-11-15-soict-paper-design.md).

## 2. Ràng buộc đã chốt

| Chủ đề | Quyết định |
| --- | --- |
| Người dùng | Người dân và dược sĩ, nhân viên y tế. Rephrase nhận diện `audience`; audience chỉ đổi cách diễn đạt, không bỏ dữ kiện nào có trong tài liệu |
| Giọng trả lời | Trả lời thẳng, có trích dẫn, **không** có disclaimer kiểu "hỏi ý kiến bác sĩ". `DISCLAIMER_PHRASES` trong `domain/agent/prompts.py` là danh sách cụm cấm, test prompt kiểm mọi prompt |
| Orchestration | LangGraph 1.2, graph biên dịch một lần, không checkpointer |
| Kiểu vòng lặp | Agentic RAG workflow với structured output (retrieve, judge, refine), không function calling. Biến thể ReAct chỉ dùng trong đánh giá |
| LLM | OpenAI SDK, **Chat Completions API** (không Responses API) để đổi được sang server tương thích OpenAI bất kỳ (OpenRouter, vLLM, llama.cpp, cli-proxy-api). Mỗi vai trò có endpoint riêng |
| Model | Không có model mặc định trong mã: thiếu `model` cho một vai trò thì báo lỗi ngay. Mọi bước LLM phải chạy được trên model rẻ, nhỏ |
| Guardrail | Regex rồi LLM nhỏ hoặc decision model, fail-open |
| Bộ nhớ | Tóm tắt cuốn chiếu cộng N lượt gần nhất, lưu trong bảng của chính backend |
| Stream | AI SDK UI Message Stream v1 trên SSE |
| Lỗi HTTP | RFC 9457 Problem Details, client phân biệt theo `code` |
| Observability | Langfuse 4.x, bật khi có khóa |
| Tính năng sản phẩm "Skills" | Không có. Đã gỡ hẳn ngày 2026-09-16 (mục 9) |

Stack: Python ≥ 3.12, uv, FastAPI ≥ 0.141 (SSE dùng `fastapi.sse`), LangGraph 1.2, langchain và
langchain-openai 1.x (chỉ cho ReAct và callback Langfuse), openai 3.x, typesafe-sdk (decision model),
qdrant-client 1.19, SQLAlchemy 2 async trên psycopg 3, Alembic, fastapi-users 15, starlette-csrf,
pydantic-settings, typer, langfuse 4.x; test bằng pytest, respx, testcontainers.

## 3. Bố cục

```text
backend/src/pharma_agent/
  domain/        agent/ (AgentRun, budget, actions, prompts, decisions, react, citations)
                 llm/ (ChatMessage, LlmUsage, LlmRole, LlmPort, DecisionPort)
                 guardrail/ retrieval/ conversation/ feedback/ shared/ + corpus, account, access, ...
  application/   chat/ (graph, react_graph, react_agent, nodes, routing, state, context, runner, service)
                 conversation/ (service, ui_message, citations) memory/ feedback/ progress.py
                 pagination.py tracing.py errors.py
  infrastructure/ llm/ (openai_adapter, systemone_adapter, agent_model) retrieval/ persistence/postgres/
                 observability/ (langfuse_tracing, langfuse_retrieval) composition.py container.py settings.py
  api/           app.py routers/ ui_stream.py problems.py errors.py openapi.py csrf.py schemas.py
  cli.py
backend/tests/   domain/ application/ api/ contract/ e2e/ infrastructure/ ...
```

Chiều phụ thuộc `api → infrastructure → application → domain`, domain không import framework.
Luật này do import-linter cưỡng chế (khai báo trong `backend/pyproject.toml`), chi tiết ở
[architecture-rules](2026-11-15-architecture-rules-design.md). Node của graph là hàm mỏng: đọc
`AgentRun` từ state, gọi domain, phát sự kiện tiến độ.

`infrastructure/composition.py::build_application(settings, *, tracer, database, llm, embedder,
decision, agent_model)` là composition root của agent. Các tham số tùy chọn cho phép tiêm adapter
giả (server E2E, harness đánh giá); đó là dependency injection, không phải cờ "chế độ giả".
`infrastructure/container.py` dựng `Container` cho API: chỉ bật chat khi LLM đã cấu hình hoặc có
`llm` được tiêm.

## 4. Agent

### 4.1 `AgentRun` (`domain/agent/run.py`)

Aggregate cho một lượt. Giữ câu hỏi gốc, `standalone_query`, `audience`, `intent`, `subjects`,
`asked_intents`, `limits: BudgetLimits`, `usage: BudgetUsage`, `evidence: EvidenceSet`,
`actions: ActionLog`, `guard_verdict`, `plan`, `status`, `error_code`, `partial_reason`, và
`react: ReactStats | None` cho lượt ReAct.

`BudgetLimits` mặc định (`domain/agent/budget.py`, đổi qua `PHARMA_BUDGET__*`):

| Trường | Giá trị |
| --- | --- |
| `max_search_rounds` | 3 |
| `max_llm_calls` | 10 |
| `max_tokens` | 40.000 |
| `max_evidence_chars` | 60.000 |
| `deadline_seconds` | 90 |

Máy trạng thái `allowed_steps()`:

- run đã kết thúc: rỗng; guard chặn hoặc ngoài phạm vi, hay intent không phải `pharma_question`:
  chỉ `ANSWER`;
- chưa search: `SEARCH`; sau `SEARCH`: `JUDGE`;
- sau `JUDGE = answer`: `ANSWER`; sau `JUDGE = search_more`: `REFINE` nếu
  `search_rounds < max_search_rounds` và còn ít nhất 2 lời gọi LLM, ngược lại `ANSWER`;
- sau `REFINE`: `SEARCH` nếu có query mới (outcome `ok`), ngược lại `ANSWER`.

Quy tắc khác:

- `can_afford_rephrase()`: chỉ rephrase khi `llm_calls + 3 ≤ max_llm_calls` (`RESERVED_CALLS = 3`:
  judge, answer và một dự phòng).
- `charge(usage)` cộng lời gọi và token; vượt ngân sách thì raise `BudgetExhausted`, node bắt lỗi
  và ép sang trả lời.
- `record_refine` bỏ query trùng (chuẩn hóa) với query đã dùng; không còn query mới thì
  `partial_reason = refine_duplicate`.
- `decide_answer()` trả `AnswerPlan(mode, partial)`, `mode ∈ {grounded, no_retrieval, abstain,
  blocked, redirect}`; `partial = True` khi judge chưa nói `answer` hoặc có `partial_reason`
  (judge lỗi, refine lỗi hay trùng, hết ngân sách).
- `submit_plan` với `grounded` mà không có evidence thì raise `EvidenceRequired`.
- `RunStatus`: `running, completed, partial, abstained, blocked, redirected, error, timeout`.
- `ErrorCode`: `REPHRASE_FAILED, SEARCH_FAILED, JUDGE_FAILED, REFINE_FAILED, ANSWER_FAILED,
  BUDGET_EXHAUSTED, DEADLINE_EXCEEDED, EVIDENCE_REQUIRED, INTERNAL`.

### 4.2 Graph workflow (`application/chat/graph.py`), dùng cho sản phẩm

```text
START → guard ─(chặn / ngoài phạm vi)─────────────► answer[blocked | redirect] → END
          ▼ (cho qua)
       rephrase ─(smalltalk | meta)───────────────► answer[no_retrieval] → END
          ▼ (pharma_question)
        search → judge ─(answer)──────────────────► answer[grounded] → END
          ▲         │ (search_more, còn vòng và lời gọi)
          └─ refine ◄┘        hết vòng, hết ngân sách, refine trùng → answer[grounded partial | abstain]
   node nào làm run chuyển sang error/timeout ─────► fallback → END
```

Routing (`routing.py`) là hàm thuần đọc `run.status` và `run.allowed_steps()`. State
`ChatTurnState(run, pending_queries, last_gaps, answer_text, context_text, citations, react)`.
Phụ thuộc của lượt đi qua runtime context `TurnContext(deps: TurnDeps, conversation, pipeline:
PipelineOptions, scope: ReleaseScope | None)`, không nằm trong state.

| Node | Vai trò LLM | Việc | Khi lỗi |
| --- | --- | --- | --- |
| guard | `guardrail` hoặc decision model | Regex trước (prompt injection, jailbreak, lộ dữ liệu, bypass); trúng thì chặn. Sau đó LLM trả `LlmGuardVerdict(is_attack, in_scope, reason)`, hoặc decision model trả xác suất cho `is_attack`, `is_about_medicines`, `is_smalltalk_or_meta` và 17 câu `asks_<intent>` | Fail-open: cho qua, ghi `llm_failed` |
| rephrase | `rephrase` | Từ tóm tắt, tối đa 4 lượt gần nhất (≤ 4.000 ký tự) và câu hỏi, sinh `RephraseResult` (standalone query, audience, language, intent, subjects) | Lỗi hoặc không đủ ngân sách: giữ câu gốc, intent `pharma_question` |
| search | không | Vòng đầu tìm `standalone_query`, các vòng sau tìm `pending_queries` của refine. Gọi `RetrievalService.search` (4.4) rồi `run.record_search` | Lỗi: ghi action lỗi, judge với evidence đang có |
| judge | `judge` hoặc decision model | LLM: `JudgeDecision(decision, gaps, reason, confidence)` từ `EvidenceSet.summary_view()`. Decision model: `covers_<intent>` cho mỗi intent đã hỏi, `sufficient_overall`, `evidence_conflict`, `wrong_drug` trên evidence đã pack, ánh xạ về `JudgeDecision` với ngưỡng τ | Lỗi hoặc hết ngân sách: ghi `answer` kèm `failed`, lượt thành partial |
| refine | `refine` hoặc không | `llm`: LLM sinh 1–3 query từ gaps và term hints. `template`: `"<subject> <cụm intent>"` cho mỗi intent chưa phủ, không gọi LLM | Lỗi hoặc toàn query trùng: sang answer, partial |
| answer | `answer` (stream) | Prompt theo mode; câu hỏi gốc của người dùng luôn có mặt, kèm bản rephrase khi khác; evidence đánh số `[n]` từ `EvidenceSet.pack(max_evidence_chars)`; `CitationSanitizer` lọc marker trên luồng delta | Ngoại lệ: run `error`, đi fallback |
| fallback | không | Text tiếng Việt cố định theo status (`error` hoặc `timeout`), không gọi LLM | Không thể lỗi |

Mỗi node bọc decorator `guarded(code)`: ngoại lệ không lường trước làm run `fail(code)` để routing
đưa sang fallback.

`PipelineOptions` (`context.py`) bật tắt các bước: `rephrase`, `judge_refine`, `guard`,
`history_query` (vòng đầu tìm cả các câu hỏi trước), `refine_threshold: float | None` (τ; `None`
giữ quyết định phân loại của judge, τ ≥ 1 luôn refine tới hết vòng), `refine_mode: "llm" |
"template"`. Chỉ mã mới truyền được `PipelineOptions`; API luôn chạy đủ mặc định. Harness đánh giá
dùng chúng cho ablation.

Decision model chỉ phục vụ vai `guardrail` và `judge`, bật khi endpoint của vai đó có
`provider = "systemone"` (4.3). Bộ câu hỏi đóng băng, 17 intent và bảng cụm intent cho template
refine nằm trong `domain/agent/decisions.py`. Nếu guard không hỏi intent bằng decision model, judge
tự hỏi một lần ở vòng đầu.

### 4.3 Graph ReAct (`application/chat/react_graph.py`), chỉ cho đánh giá

`guard → agent → finalize`, dùng lại node `answer` cho lượt bị chặn và `fallback` cho lỗi. Node
`agent` dựng mỗi lượt một `langchain.agents.create_agent` trên `TurnDeps.agent_model` (ChatOpenAI
của vai `agent`) với đúng một tool chỉ đọc `search_corpus(query)` trả tối đa 5 chunk. Middleware
`ReactBudget` giữ luật miền: tối đa `MAX_TOOL_ROUNDS = 6` vòng tool, cùng `max_llm_calls`,
`max_tokens`, `max_evidence_chars` và deadline như workflow; hết vòng hay hết ngân sách thì gọi
lần cuối với `tool_choice="none"`; tool call sai định dạng nhận `Error: ...`; query trùng trả lại
kết quả cũ. Các tool call của một phản hồi gộp thành một vòng search. `finalize` đánh số và lọc
citation như workflow. Cả hai graph chạy với `recursion_limit = 64` làm lưới an toàn.

`build_application` luôn dựng runner với graph workflow; chỉ harness của `pharma-lab` gọi
`build_react_graph()`.

### 4.4 Retrieval nhìn từ agent

Agent chỉ biết port của domain. `RetrievalService.search(queries, *, rerank_query, known_scores,
scope) -> SearchResult`: tìm mọi query (hybrid dense + BM25 qua RRF trên Qdrant), gom ứng viên xoay
vòng theo thứ hạng tới `rerank.max_candidates`, dùng lại điểm rerank đã có trong lượt
(`known_scores`), rerank theo `rerank_query`, giữ `rerank.top_n` chunk. Rerank lỗi thì giữ thứ tự RRF.
`SearchResult` mang thời gian retrieval và rerank. Chunk là đúng văn bản LLM đọc, không còn bước
hydrate.

`EvidenceSet` (`domain/retrieval/evidence.py`) gộp hit theo chunk, giữ điểm rerank cao nhất,
`pack(max_chars)` xếp theo điểm rerank xuyên vòng và bỏ nguyên chunk điểm thấp nhất khi vượt ngân
sách, không bao giờ cắt giữa chunk. `summary_view()` (snippet 300 ký tự) cho judge LLM,
`context_view()` cho answer.

Tham số mặc định của agent (`RetrievalSettings`): `mode = hybrid`, `prefetch_k = 50`, `rrf_k = 2`,
`candidate_k = 20`, `rerank.top_n = 5`, `rerank.max_candidates = 40`, `max_concurrent_searches = 3`.

`scope`: lượt chat qua API chỉ tìm trong collection mà người dùng được xem, thu hẹp theo
`collection_ids` của hội thoại (`ScopeResolver`, quy tắc thấy collection thuộc
[product-accounts-orgs](2026-11-15-product-accounts-orgs-design.md)). Lượt không có người dùng (CLI,
harness) dùng `retrieval.collections` (mặc định `["formulary"]`). Embedding, reranker, payload Qdrant
và chunker: [corpus-data-pipeline](2026-11-15-corpus-data-pipeline-design.md).

### 4.5 Chạy một lượt (`application/chat/runner.py`)

`ChatTurnRunner.start(...)` trả `ChatTurnExecution`. Graph chạy trong task riêng dưới
`asyncio.timeout(deadline_seconds)` và đẩy `ProgressEvent` vào queue; consumer (SSE) ngắt kết nối
thì task bị hủy và lượt không được lưu. Timeout chuyển run sang `timeout`, ngoại lệ chuyển sang
`error` với `INTERNAL`; cả hai phát text fallback rồi `done`.

Sự kiện công khai (`application/progress.py`), không lộ tên node, prompt hay suy luận:
`conversation`, `phase` (`guarding, understanding, searching (kèm round), reading, answering`),
`evidence`, `token`, `citations`, `done`.

Chi phí điển hình của lượt grounded một vòng: guard 1, rephrase 1, judge 1, answer 1 lời gọi LLM.
Với decision model ở judge và refine `template`, vòng judge-refine không tốn lời gọi LLM nào.

## 5. Lớp LLM

- Port: `LlmPort.structured(role, messages, schema) -> (T, LlmUsage)` và
  `LlmPort.stream(role, messages) -> AsyncIterator[StreamDelta]`; `DecisionPort.decide(role, state,
  questions) -> Decision` (xác suất trong [0, 1], giữ phản hồi thô và request id).
- `LlmRole`: `guardrail, rephrase, judge, refine, answer, summarizer, agent`.
- `OpenAiLlmAdapter`: `chat.completions.parse(response_format=schema)` cho structured,
  `chat.completions.create(stream=True)` có usage cho stream. Mọi lỗi model, gồm JSON sai shape,
  phản hồi không có `choices`, timeout, đều thành `LlmError` để các bước fail-open hoạt động.
  `LlmUsage` đếm cả reasoning token khi server báo.
- `SystemOneAdapter`: decision model qua SDK TypeSafe (`POST /v1/systemone`, đi qua OpenRouter),
  timeout riêng 10 giây mỗi request và 30 giây cả retry, xa dưới deadline 90 giây để guard và judge
  còn fail-open được.
- `agent_chat_model`: `ChatOpenAI` cho vai `agent`, cùng timeout, retry và trường endpoint.

Settings (`PHARMA_` prefix, `__` lồng nhau, đọc `.env`):

```text
llm.default / llm.roles.<role>: provider (openai | systemone), base_url, api_key, model,
    reasoning_effort, extra_body, max_output_tokens, max_tokens_param   # role thiếu trường thì lấy default
llm.timeout_seconds=60, llm.max_retries=2, llm.decision_timeout_seconds=10, llm.decision_total_seconds=30
retrieval.*, qdrant.*, budget.*, memory.*, langfuse.*, postgres.dsn, api.*, auth.* (spec tài khoản)
```

`reasoning_effort`, `extra_body` và `max_output_tokens` chỉ gửi khi được đặt, vì nhiều server tương
thích OpenAI từ chối các trường lạ. Thiếu khóa LLM thì chat tắt (`/chat*` trả 503
`AGENT_UNAVAILABLE`), các API khác vẫn chạy.

## 6. Hội thoại, bộ nhớ, lưu trữ

### 6.1 Một lượt trong hội thoại (`application/chat/service.py`)

`ChatService.open_turn(user_id, message, conversation_id, collection_ids)`:

1. Không có `conversation_id`: tạo hội thoại mới, tiêu đề lấy từ tin nhắn đầu, lưu
   `collection_ids` nếu có. Có `conversation_id`: nạp hội thoại của chính người dùng (không thấy
   thì 404), đặt tiêu đề từ tin nhắn đầu nếu tiêu đề vẫn là mặc định, dựng context từ tóm tắt và
   `memory.context_turns = 4` lượt gần nhất trong `memory.context_chars = 4.000` ký tự; lượt
   `blocked`, `error`, `timeout` bị loại.
2. Giải `scope` từ quyền của người dùng và `collection_ids` của hội thoại.
3. Sinh sẵn `user_message_id` và `assistant_message_id`, rồi khởi chạy runner.

`ChatSession.events()` phát `conversation` trước, chuyển tiếp sự kiện của runner, và khi gặp
`done` thì lưu lượt: `append_turn` ghi tin nhắn người dùng, tin nhắn trợ lý và citation trong một
transaction. Lưu lỗi thì log và `done` mang `persisted = false` (không có sự kiện lỗi sau `done`).

### 6.2 Tóm tắt cuốn chiếu (`application/memory/summarize.py`)

Sau mỗi lượt, API thêm background task `summarize_quietly`. Khi số lượt chưa tóm tắt đạt
`memory.summary_every_turns = 2`, vai `summarizer` nhận tóm tắt cũ cộng các lượt mới (bỏ lượt
blocked, error, timeout) và trả tóm tắt tối đa `memory.summary_max_chars = 1.500` ký tự. Lỗi chỉ được
log.

### 6.3 Bảng Postgres của phần này

| Bảng | Cột chính |
| --- | --- |
| `conversations` | `id, user_id, title (≤ 80), summary, turn_count, summarized_turns, collection_ids uuid[] NULL, created_at, updated_at`; index `(user_id, updated_at, id)` |
| `messages` | `id, conversation_id, role (user \| assistant), content, status, usage jsonb, run_id, created_at`; index `(conversation_id, created_at, id)` |
| `message_citations` | PK `(message_id, index)`, `chunk_version_id` FK `corpus.chunk_versions` RESTRICT, `release_id` FK `corpus.releases` RESTRICT |
| `feedback` | `feedback_id, user_id, message_id, rating (up \| down), note, created_at`; duy nhất `(user_id, message_id)` |

Citation trỏ vào chunk version bất biến của corpus nên không chép text. Không có bảng checkpoint
LangGraph, bảng audit retrieval hay cột `messages.phases`, `messages.citations`: chúng đã bị bỏ vì
chỉ ghi mà không ai đọc (mục 9). Migration Alembic nằm trong
`infrastructure/persistence/postgres/migrations/versions/` (hiện tới `0021`).

## 7. API cho web

Tất cả dưới `/api/v1`, yêu cầu phiên đăng nhập trừ `/health` và `/maintenance/daily`. Trình duyệt
dùng cookie HttpOnly `pharma_session` cùng origin, mọi request không an toàn mang cookie đó phải có
header `x-csrftoken` (starlette-csrf); chi tiết ở
[product-accounts-orgs](2026-11-15-product-accounts-orgs-design.md). Truy cập tài nguyên của người
khác trả 404.

| Method, path | Body, query | Trả về |
| --- | --- | --- |
| `POST /chat/stream` | `ChatRequest {message (1–4000), conversation_id?, collection_ids?}` | UI Message Stream v1 (7.1) |
| `POST /chat` | như trên | `ChatTurnResult {conversation_id, message_id, run_id, status, content, citations, phases, usage, created_at, persisted}` |
| `POST /conversations` | | 201 `ConversationView`, tiêu đề mặc định |
| `GET /conversations` | `?limit=20 (≤ 100)&cursor` | `{items, next_cursor}`, sắp `(updated_at desc, id desc)`, bỏ hội thoại chưa có lượt nào |
| `GET /conversations/{id}` | | `ConversationView` |
| `PATCH /conversations/{id}` | `{title?, collection_ids?}` (`null` là mọi nguồn) | `ConversationView` |
| `DELETE /conversations/{id}` | | 204 |
| `GET /conversations/{id}/messages` | `?limit=30 (≤ 100)&cursor` | `{items: UIMessage[], next_cursor}`; trang đầu là tin mới nhất, trong trang xếp cũ → mới |
| `GET /messages/{id}/citations/{index}` | | `CitationDetail {index, source, document_title, section, start_page, end_page, is_current, text}`; không có hoặc không có quyền: 404 `CITATION_NOT_FOUND` |
| `POST /messages/{id}/feedback` | `{rating: up \| down, note ≤ 2000}` | 201 `FeedbackView`, đồng thời ghi score Langfuse |
| `GET /health` | | `{status, agent, checks, reasons, phone_sign_in_enabled, google_sign_in_enabled}`; 503 khi có check hỏng (ví dụ `corpus: CORPUS_NOT_READY`) |

Các route tài khoản, tổ chức, collection, tài liệu, job, admin và maintenance thuộc spec
[product-accounts-orgs](2026-11-15-product-accounts-orgs-design.md).

### 7.1 Stream

`POST /chat/stream` mở lượt trước khi stream bắt đầu, nên lỗi lúc mở (401, 404, 422, 503) vẫn là
problem+json. Response `text/event-stream`, header `x-vercel-ai-ui-message-stream: v1`, mỗi chunk
một dòng `data: {json}`, kết thúc `data: [DONE]`. Encoder thuần `api/ui_stream.py`
(`UIMessageStreamEncoder`) chuyển `ProgressEvent` thành chunk; domain không biết AI SDK.

| Sự kiện | Chunk |
| --- | --- |
| `conversation` | `start {messageId}` rồi `data-conversation {id, title}` (transient) |
| `phase` | `data-phase` với `id = "phase"` (client cập nhật tại chỗ), `data {phase, round?}` |
| `evidence` | `data-evidence` với `id = "evidence"`, `items: [EvidenceItem {index, source, title, section, startPage, endPage, snippet}]` |
| `token` | `text-start` ở token đầu, rồi `text-delta` |
| `citations` | `text-end` rồi mỗi citation một `source-document` (`sourceId = chunk_version_id`, `providerMetadata.pharma {index, source, title, section, startPage, endPage, snippet, isCurrent}`) |
| `done` | `finish {finishReason, messageMetadata {status, createdAt, errorCode, usage, runId, persisted}}`; `finishReason = "error"` khi status là `error` hoặc `timeout`, còn lại `"stop"` |

Bảo đảm có test: mỗi `[n]` trong text có đúng một `source-document` cùng index; mỗi
`source-document` được nhắc ít nhất một lần; marker không bị cắt giữa hai `text-delta`.

### 7.2 Lịch sử dạng `UIMessage`

`application/conversation/ui_message.py` giữ model camelCase dùng chung cho stream và lịch sử, và
một hàm dựng `source-document` duy nhất. Tin nhắn người dùng chỉ có part `text`; tin nhắn trợ lý có
`text` và các `source-document`. `metadata = {status, createdAt, feedback?}`; `isCurrent = false`
khi release của citation không còn hiện hành. Phase và evidence không có trong lịch sử.

### 7.3 Phân trang, lỗi, OpenAPI

- Cursor là base64url không padding của JSON `{"t": <ISO timestamp UTC>, "id": <id>}`, keyset theo
  `(timestamp, id)`. Cursor hỏng trả 422 `INVALID_CURSOR`.
- Mọi lỗi là `application/problem+json`: `{type: "urn:pharma-agent:problem:<slug>", title, status,
  detail, code, errors?}`; `errors` chỉ có ở 422 (`VALIDATION_ERROR`). Lỗi application dùng `code`
  của nó (`CONVERSATION_NOT_FOUND`, `MESSAGE_NOT_FOUND`, `CITATION_NOT_FOUND`, `INVALID_CURSOR`,
  `AGENT_UNAVAILABLE`...), lỗi fastapi-users đưa mã chuỗi vào `code`, CSRF là `CSRF_FAILED`, 401 là
  `UNAUTHORIZED`.
- `operationId` là tên route (`generate_unique_id_function`), có test bảo đảm duy nhất. Lệnh
  `pharma-agent export-openapi --output <path>` ghi schema không cần chạy server; frontend commit
  `frontend/openapi.json` và sinh client bằng orval. Model stream (`PharmaDataParts`, `UIMessage`,
  `MessageMetadata`, `EvidenceItem`, `CitationDetail`, `Problem`) nằm trong `components`.

## 8. Observability, CLI, kiểm thử

**Langfuse** (`infrastructure/observability/`): mỗi lượt là một trace (session là hội thoại, kèm
`user_id`, `run_id`), span cho node qua `CallbackHandler` của LangChain truyền vào config của
graph, generation của OpenAI tự động qua integration `langfuse.openai`, observation riêng cho
rerank. Feedback thành score trên trace của tin nhắn. Không có khóa thì dùng `NullTracing`.

**CLI** `pharma-agent` (`cli.py`), phần của agent và API: `ask "<câu hỏi>" [--json]` (chạy một
lượt, in tiến độ và trích dẫn), `check` (kiểm cấu hình và kết nối), `serve`, `migrate [revision]`,
`export-openapi`, `cleanup-sessions`. Nhóm lệnh `corpus` và `superadmin` thuộc spec corpus và spec
tài khoản.

**Kiểm thử**:

- domain: `AgentRun` (máy trạng thái, dự trữ lời gọi, `EvidenceRequired`, ngân sách),
  `EvidenceSet.pack`, `CitationSanitizer` (marker bị cắt giữa delta, index sai, marker gộp "[1, 2]" thành
  "[1], [2]"), `make_preview` (đoạn trích cho người đọc bỏ dấu markdown, giữ ">" của ngưỡng; bằng chứng của judge vẫn
  dùng `make_snippet` không đổi), prompt không chứa
  cụm disclaimer, bộ câu hỏi decision model; thuần, không mock;
- application: graph thật với port giả (`tests/fakes.py`): smalltalk, chặn, ngoài phạm vi,
  grounded một vòng, refine nhiều vòng, partial khi hết ngân sách, abstain khi search lỗi, timeout,
  lưu lỗi; graph ReAct (`test_react_graph.py`);
- api: qua `httpx.ASGITransport`, kiểm SSE, header, `[DONE]`, problem+json, phân trang khi nhiều
  tin cùng `created_at`, CSRF;
- contract: `tests/contract/fixtures/ui-stream/<kịch bản>.sse` (blocked, completed-with-citations,
  no-evidence, persist-failed, timeout) do backend ghi, frontend kiểm bằng `uiMessageChunkSchema`
  của AI SDK;
- integration (`-m integration`, cần Docker): repository Postgres, adapter Qdrant qua
  testcontainers;
- server E2E `uv run python -m tests.e2e.server --port 8001`: app thật trên Postgres và Qdrant
  thật, xóa và tạo lại database E2E (tên phải chứa `e2e`), import bundle fixture dưới alias
  `e2e_chunks_current`, tiêm `ScenarioLlm` (kịch bản theo nội dung câu hỏi) và `FakeEmbedder`; cookie
  không bật `Secure`.

Cổng trước mỗi commit, chạy trong `backend/`: `uv run ruff check src tests && uv run ruff format
--check src tests && uv run pyrefly check --min-severity warn && uv run pytest -q`. pytest chạy với
`filterwarnings = ["error"]`; không thêm `# noqa` hay `# type: ignore`.

**Ngoài phạm vi**: tạo lại, sửa hay rẽ nhánh câu trả lời; nối lại stream sau khi mất kết nối;
endpoint AG-UI; rate limit cho chat; tính năng Skills; lưu text corpus trong bảng của hội thoại.

## 9. Lịch sử quyết định

Nguồn đọc bằng `git -C <repo> show <sha>:<path>`. Viết tắt: `S0911` =
`875eab9:backend/docs/superpowers/specs/2026-09-11-pharma-agent-backend-design.md`, `SWEB` =
`875eab9:backend/docs/superpowers/specs/2026-09-13-web-client-contract-design.md`, `SV2` =
`1b73f5b:docs/superpowers/specs/2026-10-14-paper-v2-design.md`.

| Ngày | Quyết định | Thay cho | Lý do | Nguồn |
| --- | --- | --- | --- | --- |
| 2026-09-11 | Một service FastAPI, clean architecture, LangGraph, agentic RAG judge/refine với structured output | State machine tự viết; ReAct tool calling | Ưu tiên thư viện có cộng đồng; model rẻ làm tốt việc nhỏ, mỗi lời gọi một việc. Bài học từ DocMind: ngân sách có dự trữ, cổng "không evidence thì không trả lời grounded", tiến độ là contract công khai, sanitizer citation khi stream | `S0911` §1, §2, §14 |
| 2026-09-11 | Chat Completions qua OpenAI SDK, mỗi vai trò một endpoint | Responses API, LiteLLM | Tương thích server tự host và OpenRouter, đổi server chỉ đổi cấu hình | `S0911` §9, §14 |
| 2026-09-11 | Guardrail regex + LLM nhỏ, fail-open; không disclaimer y tế | Guardrail fail-closed | Lỗi guard không được chặn câu hỏi hợp lệ; giọng trả lời thẳng | `S0911` §2, §10 |
| 2026-09-11 | Kế hoạch triển khai 3 plan (core, platform, extras) | — | Đã chạy xong, kết quả nằm trong mã; plan bỏ | `875eab9:backend/docs/superpowers/plans/2026-09-11-pharma-agent-core.md`, `…/2026-09-12-pharma-agent-platform.md`, `…/2026-09-12-pharma-agent-extras.md` |
| 2026-09-12 | Skill theo Agent Skills specification | Định dạng skill tự đặt (`skill_id`, slug, mục bắt buộc) | Định dạng tự đặt sai chuẩn; sau đó cả tính năng bị gỡ (dòng 2026-09-16) | `875eab9:backend/docs/superpowers/plans/2026-09-12-pharma-agent-extras.md` (ghi chú đầu file) |
| 2026-09-13 | AI SDK UI Message Stream v1, encoder mỏng ở tầng API | Protocol SSE tự định nghĩa (`phase`, `token`, `done`, `error` sau `done`) | Frontend dùng thẳng AI SDK; AG-UI còn draft. `done` mang `persisted` thay cho sự kiện lỗi `PERSIST_FAILED` | `SWEB` §2, §3 |
| 2026-09-13 | Lịch sử là `UIMessage`, cursor keyset `{t, id}`, `POST /conversations` trước tin đầu | Danh sách thô, cursor datetime | Cursor datetime trùng hoặc sót khi nhiều tin cùng thời điểm | `SWEB` §4 |
| 2026-09-13 | Citation là hàng `message_citations` trỏ chunk version bất biến | Cột JSONB `messages.citations` chép text | Xem lại đúng văn bản mô hình đã đọc, kể cả khi release đổi (`isCurrent`) | `SWEB` §5 |
| 2026-09-13 | Cookie HttpOnly + session Postgres + CSRF cho trình duyệt, JWT bearer giữ cho CLI và test | JWT bearer trong `localStorage` | An toàn hơn cho trình duyệt; về sau bỏ cả bearer (dòng 2026-10-13) | `SWEB` §6 |
| 2026-09-13 | RFC 9457 cho mọi lỗi, operationId cố định, `export-openapi` | Ba dạng lỗi khác nhau | Frontend sinh client và type lỗi bằng orval | `SWEB` §7, §8 |
| 2026-09-13 | Server E2E trong `tests/` với LLM kịch bản, database và alias riêng | Cờ "fake mode" trong mã production | Không để đường giả trong production; không ghi đè dữ liệu dev | `SWEB` §9 |
| 2026-09-13 | Plan web P5–P7 và bảng tên chung | — | Đã chạy xong; plan bỏ | `875eab9:backend/docs/superpowers/plans/2026-09-13-{plans-overview,web-api-foundation,web-chat-stream,web-auth-e2e}.md` |
| 2026-09-15 | Reranker chỉ qua `/v1/rerank` (`native_rerank`) | Protocol `completion_logprobs` | Logprobs chấm sai bản 8B và buộc chép prompt giữa hai project | `S0911` §14 mục 5 |
| 2026-09-16 | Gỡ hẳn tính năng Skills; graph thành `guard → rephrase → search ⇄ (judge → refine) → answer` | Node `resolve_skills`, SKILL.md hệ thống và upload, bảng `skills` | Bớt một lời gọi LLM tùy chọn và một nguồn lỗi; tính năng không cần cho sản phẩm. Lúc đó chọn viết lại lịch sử migration và xóa tài liệu về Skills; spec này giữ lại dấu vết theo quy ước mới | `875eab9:docs/superpowers/specs/2026-09-16-remove-product-skills-design.md`, `875eab9:docs/superpowers/plans/2026-09-16-remove-product-skills.md` |
| 2026-09-16 | `PipelineOptions` cho ablation, chỉ mã truyền được | — | API luôn chạy đủ agent; harness tắt từng bước | commit `e9da813`, `c8d6273` |
| 2026-09-21 | Answer luôn thấy câu hỏi gốc; audience chỉ đổi cách nói | Answer chỉ thấy câu rephrase; người dân nhận câu trả lời ngắn | Phân tích e2e: rephrase làm rơi chi tiết, model nhỏ bỏ dữ kiện khi bị yêu cầu ngắn | commit `ca19494` |
| 2026-10-10 | Bỏ checkpointer LangGraph, bảng audit retrieval, `messages.phases` (migration 0010, 0011) | Checkpoint Postgres và job dọn, `retrieval_runs`/`retrieval_hits` | Chỉ ghi, không ai đọc; phân tích retrieval làm ở pharma-lab và Langfuse | commit `908287c`, `e7efa2c` |
| 2026-10-13 | Bỏ model mặc định `gpt-5-*` và đăng nhập JWT bearer | Model mặc định trong mã; bearer song song cookie | Thiếu model phải báo ngay; bearer vượt qua việc thu hồi phiên | commit `99981a0` |
| 2026-10-13 | Structured output sai shape thành `LlmError`; giới hạn output token theo endpoint | Lỗi pydantic làm hỏng cả lượt | Server không ép json_schema vẫn phải fail-open | commit `93c5863` |
| 2026-10-15 | Chunk là đơn vị đọc: bỏ hydrate, 5 chunk mỗi vòng, ngân sách evidence 60.000 ký tự, pack bỏ nguyên chunk từ đáy, citation một chunk | Hydrate theo strategy, top 8, 24.000 ký tự, citation là khối nhiều chunk | Văn bản LLM đọc trùng văn bản được đánh giá; không cắt giữa chunk. Plan đã xong (Task 1–11), bỏ | `414e317:docs/superpowers/plans/2026-10-15-chunk-reading-unit.md`, `SV2` §3.0c |
| 2026-10-15 | `candidate_k = 20` | 30 | Rerank 20 ứng viên mỗi query, như đánh giá | commit `0725481` |
| 2026-10-16 | Decision model (Jev, `provider = systemone`) cho guard và judge; refine `template`; refine theo độ tin cậy τ | Chỉ LLM cho mọi vai | Thí nghiệm paper v2: vòng judge-refine không tốn lời gọi LLM; chỉ dùng qua cấu hình | `SV2` §2.1–§2.3 |
| 2026-10-18 | ReAct chạy trên `create_agent` của LangChain với middleware ngân sách; chỉ cho đánh giá | Vòng ReAct tự viết, `LlmPort.tool_call` | Dùng agent dựng sẵn, giữ luật miền ở middleware; điều kiện công bằng khi so với workflow | `SV2` §2.4, commit `4acbadc` |
| 2026-10-18 | Timeout riêng cho decision model, `recursion_limit = 64` | Dùng timeout LLM (180 giây cả retry) | Lời gọi kẹt phải bỏ trước deadline để guard còn fail-open | commit `74ef8df` |

## 10. Liên kết

- [corpus-data-pipeline](2026-11-15-corpus-data-pipeline-design.md): corpus, chunker, release, embedding, reranker.
- [product-accounts-orgs](2026-11-15-product-accounts-orgs-design.md): tài khoản, phiên, CSRF, tổ chức, collection, triển khai.
- [architecture-rules](2026-11-15-architecture-rules-design.md): phân tầng, import-linter.
- [frontend](2026-11-15-frontend-design.md): giao diện chat dùng stream và lịch sử ở mục 7.
- [evaluation](2026-11-15-evaluation-design.md): harness e2e dùng `PipelineOptions` và graph ReAct.
- [soict-paper](2026-11-15-soict-paper-design.md): lý do nghiên cứu của decision model và ReAct.
