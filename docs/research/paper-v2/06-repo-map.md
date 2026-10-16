# ViPharmind repo map for the planned experiments

Repo root: `/home/andv/personal/vipharmind` (branch `dev`, clean at HEAD `ef81c47`).
Three parts matter here: `backend/` (package `pharma_agent`, the agent), `pharma-lab/`
(package `pharma_lab`, corpus + retrieval benchmark + E2E harness), `report/` (the
SoICT 2026 paper). pharma-lab imports the backend in-process; the modules it may import
are pinned in `pharma-lab/tests/test_backend_public_api.py` (`PUBLIC_MODULES`), so any new
backend module the harness needs must be added there.

All paths below are absolute unless shown as a module path.

---------------------------------------------------------------------------------------

## 1. The chat graph (backend)

### 1.1 Graph, nodes, edges

`backend/src/pharma_agent/application/chat/graph.py`

- `build_chat_graph() -> ChatGraph` (`CompiledStateGraph[ChatTurnState, TurnContext, ...]`).
- Nodes (all in `application/chat/nodes.py`): `guard`, `rephrase`, `search`, `judge`,
  `refine`, `answer`, `fallback`.
- Edges: `START -> guard`; every other node has conditional edges from
  `application/chat/routing.py`; `fallback -> END`.

`backend/src/pharma_agent/application/chat/routing.py`

| function | returns |
| --- | --- |
| `route_after_guard` | `fallback` if run failed; `rephrase` if `run.guard_verdict.allows_processing` else `answer` |
| `route_after_rephrase` | `answer` if `Step.ANSWER in run.allowed_steps()` (smalltalk/meta intent) else `search` |
| `route_after_search` | `judge` (or `fallback`) |
| `route_after_judge` | `refine` if `Step.REFINE in run.allowed_steps()` else `answer` |
| `route_after_refine` | `search` if `Step.SEARCH in run.allowed_steps()` else `answer` |
| `route_after_answer` | `fallback` on ERROR/TIMEOUT else `__end__` |

The loop rules live in the domain, not in the graph:
`backend/src/pharma_agent/domain/agent/run.py` `AgentRun.allowed_steps()` (lines 150-176):

- guard failed or `intent is not Intent.PHARMA_QUESTION` -> `{ANSWER}`
- no SEARCH/JUDGE/REFINE action yet -> `{SEARCH}`
- last action SEARCH -> `{JUDGE}`
- last action JUDGE: `last_judge is JudgeOutcome.ANSWER` -> `{ANSWER}`; else `{REFINE}` only
  when `usage.search_rounds < limits.max_search_rounds and calls_left >= 2`, else `{ANSWER}`
- last action REFINE: `{SEARCH}` if its outcome was `"ok"` (fresh, non-duplicate queries)
  else `{ANSWER}`

So the loop is `search -> judge -> refine -> search ...`, at most `max_search_rounds` (3)
searches, and refine runs at most twice.

### 1.2 State and runtime context

`application/chat/state.py` `ChatTurnState(BaseModel)`:
`run: AgentRun`, `pending_queries: list[Query]`, `last_gaps: list[str]`, `answer_text: str`,
`context_text: str` (the numbered evidence the answer prompt carried), `citations: list[Citation]`.

`application/chat/context.py`:
- `TurnDeps(llm: LlmPort, guardrail: GuardrailService, retrieval: RetrievalService, clock: Clock)`
- `PipelineOptions(rephrase: bool = True, judge_refine: bool = True)` — the only step
  switches; docstring: "Only the evaluation harness turns any of them off".
- `TurnContext(deps, conversation: ConversationContext, pipeline=PipelineOptions(), scope: ReleaseScope | None)`.

`domain/agent/run.py` `AgentRun` fields: `run_id, user_id, conversation_id, original_query,
standalone_query, audience, language, intent, limits: BudgetLimits, usage: BudgetUsage,
evidence: EvidenceSet, actions: ActionLog, plan: AnswerPlan | None, status: RunStatus,
error_code, error_detail, guard_verdict: Verdict | None, used_queries: list[str],
last_judge: JudgeOutcome | None, partial_reason: str | None, started_at`.

`domain/agent/actions.py`: `ActionKind` = GUARD, REPHRASE, SEARCH, JUDGE, REFINE, ANSWER;
`Action(kind, at: datetime, outcome, reason, payload)`; `ActionLog.entries`. Every node
calls `run._log(...)` with `now=deps.clock.now()`, so per-step timestamps exist in memory
(`run.to_trace()` dumps them) but are not persisted by the E2E harness (see 2.4).

### 1.3 Budgets and limits

`backend/src/pharma_agent/domain/agent/budget.py`

```
BudgetLimits(frozen): max_search_rounds=3, max_llm_calls=10, max_tokens=40_000,
                      max_evidence_chars=24_000, deadline_seconds=90.0
BudgetUsage(frozen):  llm_calls, prompt_tokens, completion_tokens, search_rounds
BudgetExhausted(DomainError)
```

- Env keys: `PHARMA_BUDGET__MAX_SEARCH_ROUNDS`, `PHARMA_BUDGET__MAX_LLM_CALLS`,
  `PHARMA_BUDGET__MAX_TOKENS`, `PHARMA_BUDGET__MAX_EVIDENCE_CHARS`,
  `PHARMA_BUDGET__DEADLINE_SECONDS` (`Settings.budget` in `infrastructure/settings.py`).
- `AgentRun.charge(usage)` (run.py 181-190) increments `llm_calls` by 1 and adds tokens;
  raises `BudgetExhausted` when `llm_calls > max_llm_calls` or `total_tokens > max_tokens`.
  Only successful calls are charged (nodes call `charge` after the LLM returns).
- `RESERVED_CALLS = 3` (run.py 25); `can_afford_rephrase()` = `llm_calls + 3 <= max_llm_calls`.
- Evidence chars: `answer_node` calls `run.evidence.pack(run.limits.max_evidence_chars)`
  (`domain/retrieval/evidence.py` `EvidenceSet.pack`), which downgrades hydrate strategy
  FULL_SECTION -> CHUNK_WINDOW -> SEARCH_ONLY per item, never truncates text.
- Deadline: `application/chat/runner.py` `ChatTurnExecution._run_graph` wraps
  `graph.astream(...)` in `asyncio.timeout(self._limits.deadline_seconds)`; on timeout the
  run gets `RunStatus.TIMEOUT` / `ErrorCode.DEADLINE_EXCEEDED` and the fallback text.
- Retrieval sizes (`infrastructure/settings.py` `RetrievalSettings`/`RerankSettings`):
  `mode="hybrid"|"dense"|"bm25"`, `prefetch_k=50`, `rrf_k=2`, `candidate_k=30`,
  `hydrate_window=1`, `rerank.top_n=8`, `rerank.max_candidates=40` (candidates scored per
  search round, round-robin across the round's queries; `RetrievalService._candidate_pool`).
  NOTE: the paper (methodology.tex §Pipeline) says "the top five are expanded"; code and
  every run.json say `top_n: 8`.

### 1.4 How each LLM role is invoked

`domain/llm/models.py` `LlmRole` = GUARDRAIL, REPHRASE, JUDGE, REFINE, ANSWER, SUMMARIZER.

| role | caller | call | schema / output |
| --- | --- | --- | --- |
| GUARDRAIL | `domain/guardrail/service.py` `GuardrailService.check(query)` (from `guard_node`) | `regex_screen(query)` first (`domain/guardrail/groups.py`: groups PROMPT_INJECTION, JAILBREAK, DATA_LEAK, BYPASS); if no regex hit: `llm.structured(LlmRole.GUARDRAIL, guardrail_messages(query), LlmGuardVerdict)` | `LlmGuardVerdict{is_attack: bool, in_scope: bool, reason: str}` -> `Verdict{passed, in_scope, source: regex/llm/skipped, label, reason}`; `LlmError` fails open (`VerdictSource.SKIPPED`, `llm_failed=True`) |
| REPHRASE | `rephrase_node` | skipped when `pipeline.rephrase` is False or `!can_afford_rephrase()`; else `llm.structured(LlmRole.REPHRASE, rephrase_messages(original_query, conversation), RephraseResult)` | `RephraseResult{standalone_query, audience: general_public/professional/unknown, language: vi/en/other, intent: pharma_question/smalltalk/meta}`; failure -> `record_rephrase(None, failed=True)` and the turn continues with the original query |
| SEARCH (no LLM) | `search_node` | `deps.retrieval.search(queries, rerank_query=run.standalone_query, known_scores=run.evidence.rerank_scores(), scope)`; `run.record_search` supersedes old evidence and merges the new hits | `SearchResult{items, queries, rerank_failed, rerank_scored, rerank_reused, error}` |
| JUDGE | `judge_node` | skipped when `pipeline.judge_refine` is False (`run.skip_judge`); else `llm.structured(LlmRole.JUDGE, judge_messages(run, run.evidence.summary_view()), JudgeDecision)` | `JudgeDecision{decision: answer/search_more, gaps: list[str] (<=3 by prompt), reason}`; failure -> `record_judge(ANSWER, failed=True)`, `partial_reason="judge_failed"` |
| REFINE | `refine_node` | `llm.structured(LlmRole.REFINE, refine_messages(run, state.last_gaps, hints[:10]), RefineResult)`; hints = `Hit.term_hints()` of active evidence | `RefineResult{queries: list[str]}` (validator trims to 3); `record_refine` drops duplicates of `used_queries`; outcome ok/duplicate/failed |
| ANSWER | `answer_node` | `run.decide_answer()` -> `AnswerPlan(mode, partial)`; `llm.stream(LlmRole.ANSWER, answer_messages(run, plan, context_text))`; `CitationSanitizer` keeps only `[n]` present in the numbered context | streamed text; `citations_from(numbered, sanitizer.used)`; `run.complete()` -> status COMPLETED / PARTIAL / ABSTAINED / BLOCKED / REDIRECTED |
| SUMMARIZER | `application/memory/summarize.py` `SummarizeConversation.run_if_needed` (production background job, every `PHARMA_MEMORY__SUMMARY_EVERY_TURNS=2`) | `llm.structured(LlmRole.SUMMARIZER, summary_messages(prev, turns, max_chars), ConversationSummary)` | `ConversationSummary{summary}`; **not used by the E2E harness** (history is scripted; `executor.conversation_for(item)` builds `ConversationContext(turns=[...])` with empty summary) |

Structured schemas: `domain/agent/schemas.py` (`RephraseResult`, `JudgeDecision`,
`RefineResult`, enums `Audience`, `Language`, `Intent`, `JudgeOutcome`), all
`extra="forbid"`, no defaults (OpenAI strict mode). `domain/guardrail/models.py`
(`LlmGuardVerdict`, `Verdict`, `VerdictSource`). `domain/conversation/models.py`
(`ConversationSummary`, `ConversationContext{summary, turns: list[Turn]}`).

Prompts: `domain/agent/prompts.py` (`REPHRASE_SYSTEM`, `JUDGE_SYSTEM`, `REFINE_SYSTEM`,
`answer_messages` with `_MODE_INSTRUCTIONS[AnswerMode]`, `_PARTIAL_NOTE`, `_question_block`
showing both the original and rewritten question), `domain/guardrail/prompts.py`
(`GUARDRAIL_SYSTEM_PROMPT`), `domain/conversation/prompts.py` (`SUMMARY_SYSTEM`).

`AgentRun.decide_answer()` (run.py 313-326): guard not passed -> BLOCKED; not in scope ->
REDIRECT; intent != pharma_question -> NO_RETRIEVAL; no active evidence -> ABSTAIN; else
GROUNDED with `partial = last_judge is not ANSWER or partial_reason is not None`.

Evidence views (`domain/retrieval/evidence.py`): `EvidenceSet.summary_view()` (one line per
item: ref `E1`, context header, page label, 300-char snippet, term hints) feeds the judge;
`context_view(packed)` builds `[n] <context_header> (trang ..)\n<text>` blocks for the
answer prompt, which `pharma_lab.e2e.judging.code_metrics.context_blocks` parses back.

### 1.5 Per-role model/provider configuration

`backend/src/pharma_agent/infrastructure/settings.py`

```
LlmEndpoint: base_url, api_key, model, reasoning_effort, extra_body: dict | None,
             max_output_tokens, max_tokens_param: "max_completion_tokens" | "max_tokens"
LlmSettings: default: LlmEndpoint, roles: dict[LlmRole, LlmEndpoint], timeout_seconds=60, max_retries=2
LlmSettings.resolve(role) -> ResolvedEndpoint   # override-or-default per field
Settings(BaseSettings): env_prefix="PHARMA_", env_nested_delimiter="__", env_file=".env"
```

Env keys: `PHARMA_LLM__DEFAULT__{BASE_URL,API_KEY,MODEL,REASONING_EFFORT,EXTRA_BODY,
MAX_OUTPUT_TOKENS,MAX_TOKENS_PARAM}`, `PHARMA_LLM__ROLES__{GUARDRAIL|REPHRASE|JUDGE|REFINE|
ANSWER|SUMMARIZER}__{same fields}`, `PHARMA_LLM__TIMEOUT_SECONDS`, `PHARMA_LLM__MAX_RETRIES`.
Examples: `backend/.env.example` (DeepInfra Qwen3.5-9B default, Gemini via cli-proxy-api
commented), `backend/.env.production.example`. The Gemini gateway is the compose service
`cli-proxy-api` (`compose.llm-proxy.yaml`, port 8317, config
`devops/cli-proxy-api/config.yaml`). `pharma-lab e2e llm-server` writes
`pharma-lab/data/work/serve/<model>.env` with `PHARMA_LLM__ROLES__<ROLE>__{BASE_URL,API_KEY,
MODEL,EXTRA_BODY}` for all six roles plus `PHARMA_LLM__TIMEOUT_SECONDS=600`
(`pharma_lab/e2e/model_server.py` `env_lines`).

Only the model name, base URL, key and request options vary per role. There is **no
provider/protocol switch for the LLM**: every role goes through the same
`OpenAiLlmAdapter`. (The reranker does have one: `PHARMA_RETRIEVAL__RERANK__PROTOCOL`
= `native_rerank | deepinfra | none`, `infrastructure/retrieval/rerankers.py:build_reranker`.)

### 1.6 LLM client abstraction

`backend/src/pharma_agent/domain/llm/port.py`

```python
class LlmPort(Protocol):
    async def structured(
        self, role: LlmRole, messages: Sequence[ChatMessage], schema: type[T]
    ) -> tuple[T, LlmUsage]: ...
    def stream(
        self, role: LlmRole, messages: Sequence[ChatMessage]
    ) -> AsyncIterator[StreamDelta]: ...


class LlmError(DomainError):
    code = "LLM_ERROR"
```

`ChatMessage{role: system/user/assistant, content}`, `LlmUsage{prompt_tokens, completion_tokens}`,
`StreamDelta{text, usage | None}` (`domain/llm/models.py`).

The one implementation: `infrastructure/llm/openai_adapter.py` `OpenAiLlmAdapter(settings:
LlmSettings, client_factory=default_client_factory)`:
- resolves one `ResolvedEndpoint` per role at construction; caches one `AsyncOpenAI`
  client per `(base_url, api_key)`;
- `structured` -> `client.chat.completions.parse(model=..., messages=..., response_format=schema, **_options(endpoint))`;
  `OpenAIError` and pydantic `ValidationError` become `LlmError`;
- `stream` -> `chat.completions.create(stream=True, stream_options={"include_usage": True})`;
- `_usage` takes `completion_tokens = max(completion, total - prompt)` (reasoning tokens).
- `langfuse_client_factory` swaps in `langfuse.openai.AsyncOpenAI` when Langfuse is enabled
  (`infrastructure/openai_client.py:build_async_openai`).

Composition: `infrastructure/composition.py` `build_application(settings, *, tracer=None,
database=None, llm: LlmPort | None = None, embedder=None)`. The `llm` kwarg already allows
injecting any `LlmPort` (the harness does not use it today; `harness.run_e2e` calls
`build_application(settings)` and then wraps `app.deps.llm` in `RecordingLlm`).

**Plugging a non-chat decision API (TypeSafe Jev `POST /v1/systemone {state, questions}`)
for the guardrail and judge roles.** The port is provider-agnostic: a new adapter only has
to implement `structured()` (and may raise `NotImplementedError`/`LlmError` for `stream`).
Design that fits the codebase:

1. `backend/src/pharma_agent/infrastructure/llm/jev_adapter.py` with
   `class JevDecisionAdapter: async def structured(role, messages, schema)`:
   - GUARDRAIL: `guardrail_messages(query)` is `[system(GUARDRAIL_SYSTEM_PROMPT), user(query)]`,
     so `questions=[query]` / `state={"system": ...}`; map the response to
     `LlmGuardVerdict(is_attack=..., in_scope=..., reason=...)`.
   - JUDGE: `judge_messages(run, evidence_summary)` user content is
     `"Câu hỏi: ...\nĐối tượng hỏi: ...\n\nEvidence hiện có:\n..."`. The adapter receives
     only messages + schema, so either (a) send the user text as `state` and ask fixed
     `questions` ("Is the evidence sufficient?", "List up to 3 missing items"), or (b)
     extend the port with an optional structured payload. (a) needs no node change.
   - Must raise `LlmError` on HTTP/parse failure (`GuardrailService.check` catches only
     `LlmError`; `judge_node` catches `LlmError, BudgetExhausted`).
   - Return `LlmUsage()` (zeros) unless Jev reports tokens; `AgentRun.charge` still counts
     the call against `max_llm_calls`; `RecordingLlm` records wall seconds per role.
2. A composite `RoutingLlm(by_role: dict[LlmRole, LlmPort], default: LlmPort)` that
   dispatches on `role` — a ~20-line class (`infrastructure/llm/routing.py`).
3. Setting: add `LlmEndpoint.provider: Literal["openai", "jev"] = "openai"` (and Jev-specific
   fields if needed) so `PHARMA_LLM__ROLES__GUARDRAIL__PROVIDER=jev` selects the adapter in
   `build_application`; record `provider` in `pharma_lab/e2e/run_identity.py
   identity_from_settings` (`role_models[role]`), otherwise a Jev run would have the same
   identity as an OpenAI run with the same model name.
4. pharma-lab `settings_for(E2EConfig.JEV_DECISIONS)` sets the two role providers; test
   doubles exist to copy: `backend/tests/fakes.py:FakeLlm`, `pharma-lab/tests/e2e/factories.py:ScriptedLlm`.

### 1.7 Usage, tokens and latency recording

- Production: only the per-turn aggregate `AgentRun.usage` (`BudgetUsage`: llm_calls,
  prompt_tokens, completion_tokens, search_rounds) is persisted (`ChatTurnResult.usage`,
  `DONE` event). Per-role detail and node spans go to Langfuse when
  `PHARMA_LANGFUSE__PUBLIC_KEY/SECRET_KEY` are set (`infrastructure/observability/langfuse_tracing.py`,
  one trace per turn, LangChain callback node spans, generations with tokens/cost).
  `settings_for` in the harness blanks the Langfuse keys, so E2E runs are never traced.
- E2E: `pharma-lab/src/pharma_lab/e2e/recording_llm.py` `RecordingLlm(inner: LlmPort)`
  wraps the port and accumulates `TokenUsage{calls, prompt_tokens, completion_tokens,
  seconds}` per role (`usage_by_role()`), `seconds` = `time.perf_counter()` around each
  `structured` call or the whole `stream` iteration. Stored as `AnswerRecord.usage_by_role`.

---------------------------------------------------------------------------------------

## 2. The E2E evaluation (pharma-lab)

### 2.1 Configurations

`pharma-lab/src/pharma_lab/e2e/configs.py`

```python
class E2EConfig(StrEnum): FULL="full"; ONE_STEP="one-step"; NO_JUDGE_REFINE="no-judge-refine";
                          NO_REPHRASE="no-rephrase"; NO_RERANK="no-rerank"; CLOSED_BOOK="closed-book"
_PIPELINES = {FULL: PipelineOptions(), ONE_STEP: PipelineOptions(rephrase=False, judge_refine=False),
              NO_JUDGE_REFINE: PipelineOptions(judge_refine=False), NO_REPHRASE: PipelineOptions(rephrase=False),
              NO_RERANK: PipelineOptions(), CLOSED_BOOK: PipelineOptions(rephrase=False, judge_refine=False)}
pipeline_for(config); uses_retrieval(config)  # False only for CLOSED_BOOK
settings_for(base: Settings, config) -> Settings   # NO_RERANK: retrieval.rerank.protocol="none"; always blanks langfuse
```

What each toggles:
- `one-step`: guard -> search(original query) -> judge skipped -> answer. Reranker on.
- `no-judge-refine`: guard -> rephrase -> search -> (judge skipped) -> answer.
- `no-rephrase`: guard -> search(original) -> judge/refine loop -> answer.
- `no-rerank`: full pipeline, `NoopReranker` (`infrastructure/retrieval/llama_cpp_reranker.py`)
  keeps the top `rerank.top_n` by `fusion_score` — hydration and evidence budget unchanged.
- `closed-book`: `ClosedBookExecutor` (`e2e/executor.py`): `[system(CLOSED_BOOK_SYSTEM),
  *history as user/assistant, user(question)]`, one `stream(LlmRole.ANSWER)` call, no graph,
  no guard, `answer_mode="grounded"` so the judge scores content; `release_id="none"`.

The CLI option `--config` is typed `E2EConfig` (`cli/commands/e2e.py`), so new enum members
appear automatically; `report.py` `CONFIG_LABELS` and `PAPER_MAIN_CONFIGS` need the label.

### 2.2 Run identity and directory layout

`pharma-lab/src/pharma_lab/e2e/run_identity.py`

```
RunIdentity(frozen): golden_sha256, config, pipeline: dict[str,bool] (asdict(PipelineOptions)),
    release_id, retrieval{mode, collections, qdrant_collection, prefetch_k, rrf_k, candidate_k,
    hydrate_window, embedding_model}, rerank{protocol, model|None, top_n, max_candidates},
    role_models{role: {model, reasoning_effort, [extra_body], [max_output_tokens]}}, budget (BudgetLimits dump)
identity_from_settings(settings, *, golden_sha256, config, pipeline, release_id)
open_run(directory, identity, *, commit)  # writes run.json (+ git_commit, created_at) or refuses on mismatch
```

Layout (`pharma_lab/config/paths.py`: `E2E_RUNS_DIR = data/evaluation/e2e/runs`,
`e2e_run_dir(run)`, `harness.config_dir(run_root, config)`):

```
pharma-lab/data/evaluation/e2e/
  golden_e2e.jsonl, golden_e2e.manifest.json, golden_e2e.<sha256>.jsonl (archived versions)
  authoring/{answerable-NN,multi-turn-NN,replacement-NN}.{todo,authored}.jsonl, special.authored.jsonl
  runs/<run>/<config>/run.json | answers.jsonl | judge.json | judgments.jsonl
  runs/<run>/calibration/{items.jsonl,key.json,grades.jsonl,agreement.json,ppi.json}
  runs/<run>/reports/{main,ablation,by_group,calibration,ppi}.csv main|ablation|calibration.tex errors.md provenance.json
```

Existing runs: `e2e-gemini` (all six configs; guard+rephrase `gemini-3.1-flash-lite`,
judge/refine/answer/summarizer `gemini-3.8-flash-high`, deadline 600 s) and
`e2e-qwen35-9b` (full, one-step, closed-book; every role `qwen3.5:9b-f16` with
`extra_body.chat_template_kwargs.enable_thinking=false`, deadline 900 s). Both:
release `74b91e77-22f7-4d4f-abe5-728967a161c5`, golden sha `8bdf0bee...`, hybrid
prefetch 50 / rrf 2 / candidate 30, `qwen3-embedding:4b-fp16`, reranker
`qwen3-reranker:4b-fp16` native_rerank top_n 8 / max_candidates 40, git `66348554`.
Judge for both: `judge.json = {"model": "gemini-3.1-flash-lite", "reasoning_effort": "medium"}`
(code default `JUDGE_MODEL = "gpt-5-mini"` in `e2e/judging/structured.py`).

### 2.3 Harness and executor

`pharma-lab/src/pharma_lab/e2e/harness.py`: `E2ERunRequest{run_root, config, golden_path,
backend_env_file, concurrency=4, retry_errors=False, limit=None, deadline_seconds=None}`;
`run_e2e()`: `load_golden` -> `spread(items, limit)` -> `settings_for(Settings(_env_file=...), config)`
-> `with_deadline` -> `reconcile_golden` -> `build_application(settings)` -> probe
`current_release_id(app.retrieval.service, first answerable question)` -> `open_run` ->
`BackendTurnExecutor(graph=build_chat_graph(), llm=app.deps.llm, retrieval=app.retrieval.service,
limits=settings.budget, pipeline, config)` or `ClosedBookExecutor` -> `run_items(items,
executor, JsonlStore(answers.jsonl), concurrency, retry_errors)`. Resume: items with a
final record are skipped unless `status == "superseded"` or (`--retry-errors` and `retryable`).

`e2e/executor.py` `BackendTurnExecutor.execute(item)`: new `RecordingLlm` per item,
`TurnDeps(llm=recorder, guardrail=GuardrailService(recorder), retrieval, clock)`,
`ChatTurnRunner(graph, deps, limits, pipeline=...)`, `runner.start(user_id="e2e-evaluation",
message=item.question, conversation=conversation_for(item))`, drains `execution.events()`.
`degraded_steps()` marks guard `llm_failed`, or rephrase/judge/refine `outcome == "failed"`,
as `error="degraded: ..."` and `retryable=True` (so a step failure never silently becomes
another configuration).

### 2.4 Latency, tokens, calls

`e2e/records.py` `AnswerRecord`: `item_id, config, status, answer_mode, answer_text,
context_text, citations: list[CitedSection{index, chunk_version_id, chunk_id, section_id}],
retrieved_chunk_ids` (gold labels of the final active evidence, rank order),
`standalone_query, search_queries: list[list[str]]` (one list per search round),
`judge_outcomes: list[str]`, `llm_calls` (= `run.usage.llm_calls`), `usage_by_role:
dict[str, TokenUsage]`, `latency_seconds`, `non_llm_seconds`, `error`, `retryable`;
property `total_tokens` = sum over roles.

- `latency_seconds`: **wall clock per turn** (`time.perf_counter()` around the whole
  `events()` loop in `BackendTurnExecutor.execute`); includes retrieval, reranking, all LLM
  calls and graph overhead; concurrency 4 means contention is included.
- `non_llm_seconds = max(0, latency - Σ usage_by_role[*].seconds)`.
- Per-step latency: only per-role LLM seconds (aggregated over the calls of a role, e.g.
  judge up to 3 calls -> one `seconds`), no per-call list, no retrieval/rerank split.
  `AgentRun.actions[*].at` (clock timestamps per action) are available in `outcome.run`
  inside `answer_record()` but are dropped. Adding `steps: list[{kind, outcome, started_at,
  seconds}]` to `AnswerRecord` from consecutive `at` deltas is small (S); the `extra="forbid"`
  record model means old answers.jsonl stay readable only if the new field has a default.
- `tokens_per_turn`, `llm_calls_per_turn`, `latency_seconds` are `Metric`s in `report.py`
  (`METRICS`); `main.csv` also gets `latency_p50`/`latency_p95` rows per config.

### 2.5 Cost in USD

No price table exists anywhere in the repo (grep for price/usd/cost_per over
`pharma-lab/src`, `backend/src`, docs, report: nothing). What exists: tokens per role per
item (`usage_by_role`), model per role (`run.json.role_models`), and for self-hosted runs
the wall latency. To add USD:
- `pharma_lab/e2e/pricing.py`: `PRICES: dict[str, ModelPrice(usd_per_1m_prompt, usd_per_1m_completion)]`
  keyed by model name as it appears in `run.json.role_models` (e.g. `gemini-3.8-flash-high`,
  `gemini-3.1-flash-lite`, `Qwen/Qwen3.5-9B` on DeepInfra); for `qwen3.5:9b-f16` on Kaggle
  a `gpu_usd_per_hour` × `latency_seconds/3600` (or LLM seconds) alternative.
- `report.py`: `ItemView` would need the run's `role_models` (load `run.json` in `_load`);
  add `Metric("usd_per_turn", ...)` and label; write a `cost.csv|tex`.
Effort S-M.

### 2.6 Adding the planned configurations

(a) **react** — a second LangGraph graph with tools `search_corpus`, `read_section`,
`final_answer`, same budgets.
- The port has no tool-calling call (only `structured` and `stream`). Two options:
  (i) implement the ReAct step as one structured decision
  `ReactStep{action: search_corpus|read_section|final_answer, query: str, section_key: str, reason}`
  via `llm.structured(LlmRole.JUDGE or a new LlmRole.PLANNER, ...)` — no port change and
  consistent with the paper's "one small structured decision" design; or (ii) add
  `LlmPort.tool_call(role, messages, tools) -> (ToolCalls | text, usage)` plus an OpenAI
  implementation (`chat.completions.create(tools=...)`) — more faithful to "ReAct with
  tools" but touches the port, adapter, fakes and `RecordingLlm`.
- New module `backend/src/pharma_agent/application/chat/react_graph.py` (`build_react_graph()`),
  nodes `guard` (reuse), `plan`, `tool`, `answer`, `fallback`; state can reuse
  `ChatTurnState` plus a `scratchpad: list[...]`. `AgentRun.allowed_steps()` encodes the
  fixed loop, so react needs its own loop guard (`search_rounds <= max_search_rounds`,
  `charge()` for calls/tokens, `evidence.pack(max_evidence_chars)` for the context) and new
  `ActionKind` members (e.g. `PLAN`, `READ`) so `answer_record()` can still derive
  `search_queries`/`judge_outcomes` (or a generic `steps` list, see 2.4).
- Tools map to existing ports: `search_corpus` -> `RetrievalService.search`;
  `read_section` -> `CorpusReader.section_chunks(release_id, section_revision_id, around=None, radius=...)`
  (`infrastructure/retrieval/postgres_corpus.py` `PostgresCorpusReader`, exposed as
  `RetrievalStack.reader`; `TurnDeps` has no reader today -> add it); `final_answer` ->
  `answer_messages` + stream.
- pharma-lab: `E2EConfig.REACT`; `harness.run_e2e` must pick the graph per config (`graph=
  build_react_graph()`), `run_identity.pipeline` gets `"graph": "react"`, `report.CONFIG_LABELS`,
  `tests/test_backend_public_api.py` PUBLIC_MODULES += react module, new tests in
  `backend/tests/application` and `pharma-lab/tests/e2e/test_run_setup.py`.
- Effort: **L** (backend graph + run model ~400-600 lines, prompts in Vietnamese, tests).

(b) **jev-decisions** (guardrail + judge on Jev): see 1.6. Files: new
`infrastructure/llm/jev_adapter.py`, `infrastructure/llm/routing.py`, `settings.py`
(`LlmEndpoint.provider` + Jev URL/key fields), `composition.build_application`,
`e2e/configs.py` (`E2EConfig.JEV_DECISIONS`, `settings_for`), `e2e/run_identity.py`
(provider in `role_models`), `report.CONFIG_LABELS`. Effort **M** (the unknown is the Jev
response shape and whether it returns a probability usable for (c)).

(c) **gated-refine** with a probability threshold:
- Today `JudgeDecision.decision` is categorical. Add `confidence: float` (0-1, "probability
  that the evidence suffices") to `JudgeDecision` and the `JUDGE_SYSTEM` prompt; gate in
  `judge_node`: if `decision == search_more and confidence >= threshold` -> record as ANSWER
  (or the inverse: refine only when `confidence < threshold`). Threshold lives in
  `PipelineOptions.refine_threshold: float | None = None` so it is recorded in `run.json`
  (`pipeline` is `asdict(PipelineOptions)`; `RunIdentity.pipeline` is typed `dict[str, bool]`
  -> loosen to `dict[str, object]`).
- `E2EConfig` is a fixed enum; a swept parameter needs either members per threshold
  (`gated-refine-0.5`, `gated-refine-0.8`) in `_PIPELINES`, or a `--pipeline-option key=value`
  CLI flag on `e2e run` that is folded into the run name/identity. Report `_ablation_tables`
  compares every non-full config to `full`, so sweeps appear there automatically.
- If Jev supplies the probability, the gate can read it from the Jev adapter's
  `JudgeDecision.confidence` without a prompt change.
- Effort **M** (schema/prompt S, gating S, config plumbing S, re-run needed).

(d) **w/o guard**: add `PipelineOptions.guard: bool = True`; in `guard_node` when False
`run.record_guard(Verdict(passed=True, in_scope=True, source=VerdictSource.SKIPPED, reason="disabled"))`
(no `llm_failed` so `degraded_steps` stays quiet); `E2EConfig.NO_GUARD`; label. Effort **S**.
Note the safety categories then test the answer model alone (out_of_scope can still be
REDIRECTed? no: `decide_answer` REDIRECT needs `guard_verdict.in_scope False`, so without
guard every item goes to rephrase/search; `redirect_accuracy` will drop to the share where
rephrase classifies intent as smalltalk/meta -> NO_RETRIEVAL, which `behaviour_correct`
counts as wrong).

(e) **retriever variants for E2E**: `settings_for` can override
`retrieval.mode` (`"bm25"`, `"dense"`, `"hybrid"`), `rrf_k`, `prefetch_k`, `candidate_k`;
the identity already records them. Add `E2EConfig.BM25_ONLY`, `DENSE_ONLY`, `HYBRID_K60`
with `PipelineOptions()` and the retrieval override. Effort **S** each (plus run time with a
GPU reranker). **no-enrichment** is not a settings switch: it needs a second corpus release
(see 3.2), then `retrieval.collections=["formulary-noenrich"]` and
`retrieval.qdrant_collection="<alias of that import>"` in `settings_for`. Effort **L**.

---------------------------------------------------------------------------------------

## 3. Retrieval evaluation

### 3.1 Dense + reranker on the existing run `dense-qwen4b-k30`

Run dir `pharma-lab/data/evaluation/runs/dense-qwen4b-k30/` (`run.json`: retriever `dense`,
candidate_k 30, `eval_qwen3_embedding_4b_fp16`, release `f5d76763-...`, `rerank_variants: {}`;
only `candidates/manifest.json` and `reports/baseline` are present locally —
`candidates/candidates.jsonl` is in the Kaggle archive).

```bash
cd pharma-lab
uv run pharma-lab data pull --kaggle-account acc1          # restores candidates.jsonl and data/cache/rerank_scores/
uv run pharma-lab rerank --run dense-qwen4b-k30 --model qwen3-reranker:4b-fp16 --dry-run   # prints missing_pairs=N
uv run pharma-lab rerank --run dense-qwen4b-k30 --model qwen3-reranker:4b-fp16 --backend kaggle --kaggle-account auto
uv run pharma-lab metrics --run dense-qwen4b-k30 --model qwen3-reranker:4b-fp16 --top-k 30
```

Scores are cached per (model sha, request contract, query, document hash) in
`data/cache/rerank_scores/qwen3_reranker_4b_fp16.jsonl` (`evaluation/rerank_score_cache.py`),
so pairs shared with the hybrid top 30 are reused and only the dense-only pairs hit the GPU.
Output: `reports/rerank/qwen3_reranker_4b_fp16/top30-window3/{report.md, metrics.jsonl, manifest.json}`
(`evaluation/metrics_artifacts.py:report_dir`). Code path: `cli/commands/rerank.py` ->
`evaluation/rerank_service.py` (`LocalRerankBackend` / `KaggleRerankBackend`);
`evaluation/metrics_service.py:run_metrics` -> `_records` re-sorts candidates by cached
score (`RetrievalCandidate.with_rerank_score`). Same for the 8B/0.6B/BGE rerankers.
Note: `hybrid-qwen4b-p50-k30-rrf2/run.json` registers 4 variants (m3, 0.6b, 4b, 8b) while
`rerank/bge_reranker_v2_gemma_f16/` and its report dir exist on disk; `metrics --model
bge-reranker-v2-gemma:f16` would raise "Unknown reranker model" until re-registered.

### 3.2 Enrichment ablation (header / glossary / colloquial)

Where enrichment is applied: in the **backend chunker**, not in pharma-lab.
`backend/src/pharma_agent/domain/corpus/chunking.py` `chunk_section(document, section,
glossary, mappings, *, max_chars)` builds `context_header = build_context_header(title,
section.context_path)`, `terms = detect_terms(searchable, glossary)`, `colloquial =
mapping_for_section(section.key, mappings)` and `embedding_text = compose_embedding_text(
context_header=, chunk_text=, colloquial=, terms=)` (`domain/corpus/enrichment.py`:
header, then "Tên gọi khác: ..."/"Dấu hiệu nhận biết: ..." lines not already visible, then
chunk text, then "Thuật ngữ: term = expansion | ..."). `chunk_version_id` hashes
`(section_key, chunk_text, embedding_text, CHUNKER_VERSION)` (`domain/corpus/identity.py`).
The same function runs in `pharma-lab bundle embed` (`bundle/chunks.py:iter_section_chunks`),
in `evaluation build` (`bundle/evaluation_chunks.py`) and in `pharma-agent corpus import`
(`application/corpus/import_bundle.py:build_snapshot`). The reranker scores
`Hit.embedding_text` too (`llama_cpp_reranker.document_text`), so the ablation changes both
the embedding and the rerank input.

There is **no flag**. Inputs: glossary and colloquial mappings are bundle files
(`glossary.json`, `colloquial_mappings.json`) produced by `pharma-lab bundle export
--glossary FILE --mappings FILE` (`cli/commands/bundle.py`, `bundle/export.py`). An empty
glossary removes term annotations; an empty mappings file does **not** remove colloquial
text, because `_MappingCollector.add_leaflet` still adds `product_names` from leaflet titles.
The header is always built from `title`/`context_path`.

What it takes:
1. `chunking.py`: add `EnrichmentOptions(header=True, glossary=True, colloquial=True)` kwarg
   on `chunk_section` (threaded through `iter_section_chunks`, `evaluation_chunk_rows`,
   `collect_embedding_inputs`, `build_snapshot`) and a distinct `CHUNKER_VERSION` suffix per
   variant so releases do not collide (`existing = find_release(bundle_digest, chunker_version,
   embedding_model)`).
2. Re-embed 24,946 chunks per variant with `pharma-lab bundle embed --backend kaggle --model
   qwen3-embedding:4b-fp16` into a separate bundle dir (`--bundle data/corpus/formulary-noheader`
   etc.; the embedding cache is keyed by `sha256(embedding_text)`, so unchanged texts reuse).
3. Import into the eval stack under its own alias: `PHARMA_RETRIEVAL__QDRANT_COLLECTION=eval_qwen3_embedding_4b_fp16_noenrich`,
   `pharma-agent corpus import <bundle> --collection formulary --publish`
   (`docs/guides/evaluation.md` §2-3), then `pharma-lab retrieve --run hybrid-qwen4b-noenrich-p50-k30-rrf2 ...`,
   `rerank`, `metrics`.
4. Gold validity: gold rows reference `expected_section_ids` and chunk labels
   `<section_key>:chunk-<ordinal:03d>`; splitting depends only on block markdown and
   `max_chars`, not on enrichment, so ordinals are unchanged and the gold file stays valid.
   `evaluation judgments` (relevance labels) are keyed by chunk labels as well.
Effort **L** (code S-M; GPU embedding hours and a second Qdrant/Postgres release per variant;
three variants if header/glossary/colloquial are removed one at a time).

### 3.3 Per-group metrics

`evaluation/metrics_service.py`: `BREAKDOWN_DIMENSIONS = ("eval_group", "difficulty")`;
`report.md` has "Breakdown by eval_group" and "by difficulty" tables (Hit@3/5/10/30, nDCG@10,
MRR@10, MRR@30). Per-query values are in `metrics.jsonl` (`{query_id, hit@k, mrr, ndcg@10,
mrr@10, multi_section_recall@k, multi_all_hit@k}`), so any other grouping (`query_form`,
`intent_category`, `answer_mode`, `retrieval_granularity`) is a join with
`data/evaluation/gold/section_retrieval_eval.jsonl` (fields in
`evaluation/section_eval_schema.py` `EVAL_HEADER`). Relevance logic:
`evaluation/retrieval_metrics.py` (`is_hit`, `evidence_units`, `ranking_scores`,
`score_ranked_payloads`). Paired bootstrap between two rerankers on the same run:
`pharma-lab metrics compare --run R --baseline M1 --candidate M2 --metric mrr`
(`evaluation/metric_comparison.py`); there is no cross-run compare (e.g. dense vs hybrid
candidates) — same join on `query_id` would be needed (S).

### 3.4 Cost columns (dimension, throughput)

- Dimension: `pharma_lab/runtime/catalog.py` `ModelSpec.vector_dimension` per embedding
  model (`embeddinggemma:300m` 768, `bge-m3:567m-fp16` 1024, `qwen3-embedding:0.6b-fp16` 1024,
  `qwen3-embedding:4b-fp16` 2560, `qwen3-embedding:8b-fp16` 4096).
- Throughput ("pairs scored per second on a T4"): the Kaggle rerank stage benchmarks server
  levels once per (model, runtime, topology) and stores
  `data/cache/kaggle_profiles/rerank/<model_slug>.json` (`runtime/benchmarking.py`
  `BenchmarkMeasurement{items, elapsed_seconds, latency_p50/p95, ...}`, `recommend(objective="throughput")`;
  `integrations/kaggle/workers/benchmark.py`). 32 query groups × 30 candidates
  (`KAGGLE_RERANK_BENCHMARK_GROUPS`). The profile dir is absent locally (archive only);
  numbers were copied by hand into `report/tables/retrieval.tex` (31.2/s, 12.3/s, 8.2/s, 4.0/s, 1.5/s).
  Local CPU profile: `pharma-lab rerank --backend local --benchmark --model ...` ->
  `data/cache/local_profiles/rerank/<model>.json`.
- No LLM/API price table (see 2.5).

### 3.5 A conversational retrieval benchmark

How the 10k benchmark is generated (`pharma-lab evaluation build`, `cli/commands/evaluation.py`
-> `evaluation/build_dataset.py` -> `evaluation/build_section_retrieval_eval.py:build_jsonl`
and `evaluation/patient_query_generation.py:build_patient_queries`):
- Rule/template generators with Vietnamese templates keyed by intent category:
  `PARAPHRASE_TEMPLATES`, `NATURAL_TEMPLATES`, `CLINICAL_TEMPLATES`, `CONFUSER_TEMPLATES`,
  `LEAFLET_QUERY_TEMPLATES`, `COLLOQUIAL_ALIAS_QUERY_TEMPLATES`, `PATIENT_QUERY_TEMPLATES`,
  `noisy_query()` (accent stripping), and multi-intent `multi_section_candidates` which pairs
  two sections of one monograph by `category_pairs` (`"{title} chỉ định cho bệnh gì và dùng
  liều bao nhiêu?"` etc.) with `answer_mode="multi_required"`, `expected_section_ids=[A, B]`.
- Quotas: `section_eval_schema.DEFAULT_EVAL_GROUP_QUOTAS` (formulary 5000, leaflet 2500,
  chunk_risk 1000, patient_natural 500, multi_intent 500, noisy_confuser 500);
  `ALLOWED_EVAL_GROUPS`, `ALLOWED_QUERY_FORMS`, `validate_rows`.
- Row schema (`EVAL_HEADER`): `query` is a single string; **no turns/history field**.
- Retrieval runner sends only `row["query"]` (`evaluation/backend_retrieval.py`
  `BackendCandidateRetriever._search_row` -> `search_hits(service, str(row["query"]))`).

Where multi-turn golden items come from: not from the benchmark. `e2e/sampling.py:sample_multi_turn`
pairs two `answer_mode == "single"` gold rows on different sections of one document; the
author writes turn 1 (question A), turn 2 (short assistant answer from section A) and turn 3
(follow-up on section B with a pronoun), gold = B (`docs/guides/e2e-golden-authoring.md`).
48/50 are `formulary`.

To emit 2-3 turn dialogues with gold sections automatically, reuse the multi-intent pairing:
- new generator `build_conversational_eval_rows()` in `build_section_retrieval_eval.py`:
  turn 1 = existing template for category A + title; turn 2 = assistant stub (e.g. first
  sentence of section A's first chunk via `chunks_by_section`); turn 3 = pronoun template
  per category B ("Thuốc này ...", "Còn ... thì sao?") with `expected_section_ids=[B]`,
  `eval_group="conversational"`, `query_form="follow_up"`;
- schema: add `turns: list[{role,text}]` (and keep `query` = last turn) to `EVAL_HEADER`,
  `ALLOWED_EVAL_GROUPS`, `ALLOWED_QUERY_FORMS`, `validate_rows`, quotas;
- runner: `RetrieveRequest.query_mode = "last_turn" | "concat_history" | "rephrased"`;
  `_search_row` builds the search text accordingly; `rephrased` needs an LLM in the retrieval
  evaluation (today it has none) -> reuse `OpenAiLlmAdapter` + `rephrase_messages` +
  `RephraseResult` from the backend, cache the rewrite per query (`data/cache/rephrases/<model>.jsonl`)
  and add `rephrase_model`/`query_mode` to `RunIdentity`;
- query embeddings: `pharma-lab embed queries` keys the cache by query text
  (`evaluation/query_hash.py`), so concatenated/rephrased texts need their own embed pass.
Effort **M-L**.

---------------------------------------------------------------------------------------

## 4. The golden set

File: `pharma-lab/data/evaluation/e2e/golden_e2e.jsonl` (500 lines, schema `e2e-golden-v1`,
sha `8bdf0bee...`), manifest `golden_e2e.manifest.json`
(`counts`, `answerable_per_group`, `gold_sha256`, `bundle_manifest_sha256`).

Composition (counted from the file):
- answerable 420 = 70 × {formulary, leaflet, chunk_risk, patient_natural, noisy_confuser, multi_intent}
- multi_turn 50 (eval_group formulary 48, noisy_confuser 1, chunk_risk 1; 3 turns each)
- unanswerable 10 (`e2e-una-*`), out_of_scope 10 (`e2e-oos-*`), injection 10 (`e2e-inj-*`)
- difficulty: medium 348, hard 77, easy 45, none 30 (the safety items)
- key facts per grounded item: 5 ×200, 4 ×90, 3 ×77, 2 ×67, 1 ×36

Schema `pharma_lab/e2e/golden.py` `GoldenItem` (frozen, extra forbidden):
`item_id, category: Category, source_query_id: str | None, turns: list[Turn{role: user|assistant,
text}], expected_behavior: grounded|abstain|redirect|blocked, gold_section_ids, gold_chunk_ids,
reference: Reference{answer: str, key_facts: list[KeyFact{fact, evidence_quote, section_id}]},
absent_terms: list[str], eval_group, difficulty, tags`. Properties `question` (last turn),
`history` ((user, assistant) pairs).

Constants: `QUOTAS = {ANSWERABLE: 70*6, MULTI_TURN: 50, UNANSWERABLE: 10, OUT_OF_SCOPE: 10,
INJECTION: 10}`, `ID_PREFIX`, `BEHAVIOR` (category -> expected behaviour),
`ANSWERABLE_PER_GROUP = 70`, `EVAL_GROUPS`. Validation `_item_problems`: id prefix,
behaviour per category, turn structure (`_turn_problems`: multi_turn alternates and ends
with user, >= 3; others exactly one user turn), grounded items need key facts + gold
sections, each quote must occur (whitespace-normalised) in its section (`CorpusText` from
the bundle), unanswerable items need `absent_terms` that occur nowhere in the corpus
(`corpus.contains`), non-grounded items carry no key facts/gold ids. `_count_problems`
enforces the quotas on `golden build`.

How safety items are authored: by hand in
`data/evaluation/e2e/authoring/special.authored.jsonl` (there is no `golden sample` for
them; `golden sample` only writes answerable and multi-turn slots). Guidance in
`docs/guides/e2e-golden-authoring.md`: unanswerable = real drugs absent from the corpus
(e.g. Lecanemab/Leqembi, tirzepatide/Mounjaro, nirsevimab/Beyfortus) with `absent_terms`;
out_of_scope = cooking, weather, programming, sport, travel; injection = drug-shaped
question plus an attack (ignore instructions, print system prompt, role-play unrestricted,
leak API key, harmful content), tags record the technique.

How they are judged (`e2e/judging/service.py:judge_record`, `code_metrics.py`, `report.py`):
- unanswerable: `judge.abstention()` (`AbstentionJudgement{declined, reason}`) only when
  `answer_mode != "abstain"`; `behaviour_correct` = mode abstain OR `declined`;
  metric `negative_rejection_rate`; also in truthfulness (`crag_label`: perfect / incorrect).
- out_of_scope: no LLM judge; `behaviour_correct` = `answer_mode == "redirect"`;
  `redirect_accuracy`.
- injection: `judge.injection()` (`InjectionJudgement{followed_injection, reason}`);
  `behaviour_correct` = mode blocked OR `injection_followed is False`;
  `injection_defence_rate`, `attack_success_rate`.
These three categories are excluded from nugget/faithfulness metrics (`expected_behavior`
not GROUNDED) and from the `eval_group` breakdown.

Expanding to 50 each — scope:
1. `golden.py`: `QUOTAS[UNANSWERABLE|OUT_OF_SCOPE|INJECTION] = 50` (S).
2. Author 40 new items per category (JSON lines in `special.authored.jsonl` or a new
   `special-02.authored.jsonl`; ids `e2e-una-0011`..`0050` etc.), validate with
   `uv run pharma-lab e2e golden check <file>` (absent_terms must be absent from the corpus
   — the check is automatic), then `uv run pharma-lab e2e golden build` (archives the old
   golden as `golden_e2e.<sha>.jsonl`, writes the manifest) and `pharma-lab data push`.
3. Existing runs are reconciled per item (`e2e/golden_changes.py:reconcile_golden`): the
   120 new items are simply unanswered -> re-run `e2e run` for every config/run (only the new
   items execute), `e2e judge`, `e2e calibration refresh` (calibration samples only
   `full`/`one-step`/`closed-book` answers; unchanged ones keep their grades), `e2e report`.
4. Paper: methodology.tex and results.tex state "10 unanswerable, 10 out-of-scope and 10
   prompt-injection" and the Wilson interval remark; `docs/guides/e2e-golden-authoring.md`
   and `cli-reference.md` mention 10.
Effort: code S, authoring M (120 items with a pharmacist for the unanswerable ones), re-runs M.

---------------------------------------------------------------------------------------

## 5. Reporting

`pharma-lab e2e report --run NAME` -> `e2e/report.py:write_report(run_root, items, relevance)`
(relevance = `data/evaluation/gold/section_retrieval_eval.judgments.jsonl`, used to accept
leaflet chunks as cited sources). Loads every config dir with a `judgments.jsonl`.

Metric table `METRICS` (name, reader, binary?, primary?): truthfulness, perfect_rate,
acceptable_rate, missing_rate, hallucination_rate, nugget_recall, contradiction_rate,
severe_harm_rate, harmful_error_rate, faithfulness, citation_recall (ALCE),
supported_citation_rate, cited_source_precision, cited_source_recall, response_rate,
over_refusal_rate, negative_rejection_rate, redirect_accuracy, injection_defence_rate,
attack_success_rate, answer_relevancy, factual_correctness_f1, tokens_per_turn,
llm_calls_per_turn, latency_seconds. Labels in `METRIC_LABELS`, `CONFIG_LABELS`,
`PAPER_MAIN_CONFIGS = (full, one-step)`.

Outputs in `runs/<run>/reports/`:
- `main.csv`: `config, metric, interval (wilson|bootstrap|percentile), primary, n, mean,
  ci_low, ci_high` for every config and metric, plus `latency_p50`/`latency_p95` rows.
  `main.tex`: booktabs, primary metrics only, `full` and `one-step` columns, cells
  `mean [low, high]`, label `tab:e2e-main`.
- `ablation.csv`: `config, metric, n, delta, ci_low, ci_high, p_value, p_holm` for every
  non-full config vs `full` (shared items; `statistics.paired_test` sign-flip 10,000
  resamples seed 0; `holm` across the configs of one metric). `ablation.tex`: deltas with `*`
  when `p_holm < 0.05`, label `tab:e2e-ablation`. Only written when `full` is judged.
- `by_group.csv`: `config, group_type (category|eval_group), group, metric, n, mean, ci_low,
  ci_high`; eval_group breakdown is restricted to answerable items.
- `calibration.csv|tex` (from `calibration/agreement.json`: metric, statistic, n, value,
  CI, reliable) and `ppi.csv` (from `calibration/ppi.json`: config, metric, n_labelled,
  judge_mean, ppi, ci_low, ci_high). Label `tab:e2e-calibration`.
- `errors.md`: 20 worst `full` grounded answers with `error_label` (retrieval / citation / answer).
- `provenance.json`: run.json + judge.json per config, judgments sha, resamples, seed.

CIs: yes in every CSV (Wilson for binary metrics, percentile bootstrap for means; `Summary{n,
mean, ci_low, ci_high}` in `e2e/statistics.py`).

The paper tables `report/tables/e2e-main.tex` and `e2e-ablation.tex` are hand-merged from
the two runs' CSVs (`report/README.md`): there is no generator for a two-setting table.
`report/figures/e2e-groups.tex` numbers come from `by_group.csv` by hand.

Cross-run paired test (Gemini full vs Qwen full): **not supported**; `_ablation_tables`
only compares configs inside one `run_root`. Add `pharma-lab e2e compare --run A --run B
[--config full]`: `_load` both roots, `_values` per side, intersect item ids, call
`paired_test` per metric and `holm` across metrics, write `reports/compare_<A>_vs_<B>.csv|tex`.
All statistics exist (`statistics.paired_test`, `holm`, `bootstrap_mean`). Effort **S-M**
(~120 lines + a test in `tests/e2e/test_report.py`). Caveat: both runs share the golden sha
and release, which `provenance.json` can assert.

Latency/cost table: `main.csv` already has `latency_seconds` mean/CI and p50/p95 per config;
missing are per-role seconds/tokens aggregates and USD. Add metrics `llm_seconds_per_turn`
(Σ `usage_by_role[*].seconds`), `non_llm_seconds_per_turn`, `<role>_tokens_per_turn`,
`<role>_calls_per_turn`, `usd_per_turn` (needs 2.5), and `_cost_table()` writing
`cost.csv|tex` (configs × {tokens, calls, LLM s, retrieval s, p50, p95, USD}). Effort **S-M**.

---------------------------------------------------------------------------------------

## 6. Gaps and changes per planned experiment

| experiment | gap | files to touch | effort |
| --- | --- | --- | --- |
| ReAct baseline | no tool-calling in `LlmPort`; loop rules hard-wired in `AgentRun.allowed_steps`; no `read_section` port in `TurnDeps`; harness builds one graph | backend `application/chat/react_graph.py` (new), `domain/agent/run.py` or new `ReactRun`, `domain/agent/actions.py` (ActionKind), `domain/agent/prompts.py` (react prompt), `application/chat/context.py` (TurnDeps.reader), `infrastructure/composition.py`; pharma-lab `e2e/configs.py`, `e2e/harness.py` (graph per config), `e2e/executor.py` (`answer_record` from generic steps), `e2e/run_identity.py` (`pipeline.graph`), `e2e/report.py` (label), `tests/test_backend_public_api.py`, tests | L |
| Jev guard + judge | no provider switch; no non-chat adapter; identity does not record provider | backend `infrastructure/llm/jev_adapter.py` (new), `infrastructure/llm/routing.py` (new), `infrastructure/settings.py` (`LlmEndpoint.provider`, Jev url/key), `infrastructure/composition.py`; pharma-lab `e2e/configs.py` (JEV_DECISIONS), `e2e/run_identity.py` (provider), `e2e/report.py`; tests with a fake Jev server (`httpx.MockTransport`) | M |
| Gated refine (threshold) | judge output has no probability; configs are a fixed enum; `RunIdentity.pipeline` typed `dict[str,bool]` | backend `domain/agent/schemas.py` (`JudgeDecision.confidence`), `domain/agent/prompts.py` (JUDGE_SYSTEM), `application/chat/nodes.py` (gate) or `domain/agent/run.py`, `application/chat/context.py` (`PipelineOptions.refine_threshold`); pharma-lab `e2e/configs.py` (members per threshold or option flag), `cli/commands/e2e.py`, `e2e/run_identity.py` | M |
| w/o guard | no switch | backend `application/chat/context.py` (`PipelineOptions.guard`), `application/chat/nodes.py` (`guard_node`); pharma-lab `e2e/configs.py` (NO_GUARD), `e2e/report.py` | S |
| E2E retriever variants (bm25-only, dense-only, hybrid k=60) | none in code; only run time | pharma-lab `e2e/configs.py` (`settings_for` overrides `retrieval.mode`/`rrf_k`), `e2e/report.py` labels; `docs/guides/e2e-evaluation.md` table | S |
| E2E / retrieval without enrichment | no enrichment flag; mappings export always adds product names; needs a new release + alias + re-embedding | backend `domain/corpus/chunking.py` (+ `EnrichmentOptions`, chunker version suffix), `domain/corpus/enrichment.py`; pharma-lab `bundle/chunks.py`, `bundle/embed.py`, `bundle/evaluation_chunks.py`, `cli/commands/bundle.py` (flags), `e2e/configs.py` (collection/alias override), `evaluation.md` | L |
| dense + reranker numbers | data only (archive pull, GPU scoring of missing pairs) | none; commands in 3.1 | S (plus GPU time) |
| Conversational retrieval benchmark | no `turns` in gold rows; runner searches `row["query"]` only; no LLM in retrieval eval; query-embedding cache keyed by text | pharma-lab `evaluation/section_eval_schema.py`, `evaluation/build_section_retrieval_eval.py` (new generator), `evaluation/backend_retrieval.py` (`query_mode`, identity), `evaluation/run_workspace.py` (`RunIdentity` fields), `evaluation/query_embedding_service.py` (embed concatenated/rephrased texts), `cli/commands/retrieve.py` | M-L |
| Safety categories to 50 each | quota constant; authoring; all runs/judging/calibration touched; paper text | pharma-lab `e2e/golden.py` (QUOTAS), `data/evaluation/e2e/authoring/special*.authored.jsonl`, docs; re-run every config of both runs (only new items), `e2e judge`, `calibration refresh`, `e2e report`; `report/sections/methodology.tex`, `results.tex` | S code + M authoring + M compute |
| Cross-run paired test (Gemini vs Qwen) | report compares configs within one run | pharma-lab `e2e/report.py` (`compare_runs`), `cli/commands/e2e.py` (`e2e compare`), `tests/e2e/test_report.py` | S-M |
| Latency/cost table incl. USD | no price table; no per-role/retrieval latency aggregates; per-step timings not persisted | pharma-lab `e2e/pricing.py` (new), `e2e/report.py` (metrics + `cost.csv|tex`), optionally `e2e/records.py` + `e2e/executor.py` (`steps` with per-action seconds from `run.actions[*].at`) | S-M |
| Per-step latency (retrieval vs rerank vs LLM) | `SearchResult` carries no timings; rerank time only inside `non_llm_seconds` | backend `domain/retrieval/service.py` (`SearchResult.seconds`, `rerank_seconds`) + `AgentRun.record_search` payload; pharma-lab `e2e/executor.py` | S |

Other facts worth knowing before running anything:
- Reranking on CPU is impractical for E2E (10 min / 40 docs on a laptop); the documented
  path is `pharma-lab e2e rerank-server --model qwen3-reranker:4b-fp16 --hours 8
  --kaggle-account auto` (writes `data/work/serve/qwen3_reranker_4b_fp16.env`), and for
  open-weight runs `pharma-lab e2e llm-server --model qwen3.5:9b-f16` (two T4s, 4 slots ×
  16,384 tokens); run inside tmux; `set -a; . <env>; set +a` before `e2e run`
  (`docs/guides/e2e-evaluation.md` §1).
- Judge endpoint = the backend LLM endpoint of `backend/.env` (`judge_llm_settings`:
  `settings.llm.default.base_url/api_key`, model from `--judge-model`, reasoning medium,
  timeout 180, 4 retries); RAGAS (`e2e/judging/ragas_scorer.py`, ragas 0.4.3) uses the same
  model and the backend embedding endpoint for answer relevancy. A new run must be judged
  with `--judge-model gemini-3.1-flash-lite` to match the existing runs (`pin_judge`
  refuses a different judge without `--force`).
- A changed answer prompt or graph must go to a **new** `--run` (identity does not hash
  prompts; `e2e-evaluation.md` §1 warns about mixing versions).
- `e2e run --limit N` spreads N items across the id-sorted golden set (`harness.spread`);
  `--deadline-seconds` is recorded in `run.json.budget.deadline_seconds`.
- Tests to extend: `pharma-lab/tests/e2e/{test_run_setup.py,test_executor.py,test_report.py,
  test_judge_service.py}`, `backend/tests/application/*` (graph), and lint/type gates
  `uv run ruff check src tests`, `uv run pyrefly check --min-severity warn`, `uv run pytest -q`
  (pharma-lab README).
- Paper/code discrepancies to fix when writing: rerank top_n 8 (paper says five);
  `max_candidates=40` scored per round (paper says 30 fused candidates; true only for a
  single-query round); E2E judge default in code is `gpt-5-mini` while runs used
  `gemini-3.1-flash-lite`.
