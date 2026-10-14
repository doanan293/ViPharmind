# 02. How production coding agents run the ReAct loop: OpenAI Codex and Anthropic guidance

Research notes for the paper comparing a code-controlled graph-routing RAG pipeline against a fully agentic tool-calling agent for Vietnamese drug-information QA on small or cheap language models.

Date of research: 2026-10-14.

Sources and provenance:

- (a) Shallow clone of `openai/codex` at commit `95273b84fbff40f9df7d71d50f1ca52c6489b25d` (committed 2026-10-14, "Keep the agent dashboard browsable during task removal (#53908)"). Local path: `/tmp/claude-1000/-home-andv-personal-vipharmind/00451d94-5a9a-4b9b-8cda-801b6c69721a/scratchpad/external/codex`. Paths below are relative to that root. Read only; nothing was built or executed.
- (b) Anthropic engineering posts and Claude Code / Agent SDK documentation, fetched 2026-10-14. The fetch tool caps each verbatim quote at about 125 characters, so long passages appear as short quoted fragments joined by paraphrase. Any quote that will go into the paper should be re-checked against the live page before submission.

Conventions: "Codex" means the Rust harness in `codex-rs/`, not the old Codex language model. "Sampling request" is Codex's term for one model call. "Turn" in Codex means one user prompt to one final assistant message, which may contain many sampling requests. The Claude Agent SDK uses "turn" for one model call plus its tool executions, so the two vocabularies differ and the paper should pick one and define it.

---

## Part 1. OpenAI Codex (codex-rs)

### 1.1 Where the loop lives

The Codex monorepo is a Rust workspace with around 150 crates (`codex-rs/`). The pieces relevant to a ReAct baseline:

| Concern | Files |
| --- | --- |
| Turn loop (outer loop over sampling requests) | `codex-rs/core/src/session/turn.rs` (3,330 lines), function `run_turn` at line 166 |
| One model call plus tool dispatch | same file, `run_sampling_request` (line 1707) and `try_run_sampling_request` (line 2618) |
| Classification of streamed output items into tool futures or messages | `codex-rs/core/src/stream_events_utils.rs`, `handle_output_item_done` (around line 330) |
| Tool router and registry | `codex-rs/core/src/tools/router.rs`, `registry.rs`, `spec_plan.rs` |
| Parallel execution gate | `codex-rs/core/src/tools/parallel.rs` |
| Tool declaration types | `codex-rs/tools/src/tool_spec.rs`, `responses_api.rs` |
| Output truncation | `codex-rs/utils/output-truncation/src/lib.rs`, `codex-rs/utils/string/src/truncate.rs`, `codex-rs/core/src/tools/context.rs`, `codex-rs/core/src/tools/mod.rs` |
| Compaction | `codex-rs/core/src/compact.rs`, `compact_token_budget.rs`, `session/context_window.rs`, `session/async_compaction.rs`, `prompts/templates/compact/prompt.md` |
| Retry | `codex-rs/core/src/responses_retry.rs`, `codex-rs/codex-client/src/retry.rs`, `codex-rs/protocol/src/error.rs` |
| Model catalog and provider abstraction | `codex-rs/protocol/src/openai_models.rs`, `codex-rs/model-provider-info/src/lib.rs`, `codex-rs/models-manager/src/model_info.rs`, `codex-rs/ollama/src/lib.rs`, `codex-rs/lmstudio/src/lib.rs` |
| System prompts | `codex-rs/core/gpt_5_2_prompt.md`, `gpt_5_1_prompt.md`, `gpt-5.2-codex_prompt.md`, `gpt_5_codex_prompt.md`, `gpt-5.1-codex-max_prompt.md`, `codex-rs/models-manager/prompt.md` (fallback), `codex-rs/prompts/templates/*` |

The user-facing configuration reference has moved out of the repo. `codex-rs/config.md` now reads "# Configuration docs moved" and `docs/config.md` points to `https://developers.openai.com/codex/config-basic`, `config-advanced`, and `config-reference`.

### 1.2 The turn loop

The doc comment on `run_turn` (`codex-rs/core/src/session/turn.rs`, lines 153-165) states the loop contract exactly:

> Takes initial turn input and runs a loop where, at each sampling request, the model replies with either:
> - requested function calls
> - an assistant message
>
> While it is possible for the model to return multiple of these items in a single sampling request, in practice, we generally one item per sampling request:
> - If the model requests a function call, we execute it and send the output back to the model in the next sampling request.
> - If the model sends only an assistant message, we record it in the conversation history and consider the turn complete.

Model calls per turn. There is exactly one model call per iteration of the `loop` in `run_turn`, made through `run_sampling_request`. The loop repeats while `needs_follow_up` is true. There is no fixed count: a turn with a direct answer is one call, a turn with N tool rounds is N+1 calls.

How `needs_follow_up` is set (`try_run_sampling_request`, lines 2685-3120):

- It starts `false` for each sampling request.
- Every `ResponseEvent::OutputItemDone` is passed to `handle_output_item_done`. If the item is a `FunctionCall`, `CustomToolCall`, or client-executed `ToolSearchCall`, the handler builds a tool future and sets `output.needs_follow_up = true` (`stream_events_utils.rs`, line 356). If the item is a message or reasoning block, it is recorded and `last_agent_message` is updated.
- If a tool call is rejected before dispatch (`FunctionCallError::RespondToModel`), the error text is recorded as a `FunctionCallOutput` and `needs_follow_up = true` (line 424), so the model sees the rejection and gets another call.
- On `ResponseEvent::Completed { end_turn, .. }`, if the server reports `end_turn == Some(false)` the harness sets `needs_follow_up = true` (line 3112). Otherwise it keeps whatever the tool calls set.
- The outer loop also folds in steering input: `let needs_follow_up = model_needs_follow_up || has_pending_input;` (line 604). A user message typed while the agent is running forces another sampling request.

Stop conditions. The turn ends when a sampling request completes with no tool calls, no pending input, and no server `end_turn == false`. At that point `run_turn_stop_hooks` runs (line 720). A `Stop` hook can `should_block` the end of turn and inject a "continuation" prompt message, which re-enters the loop with `stop_hook_active = true`, or `should_stop`. Hard aborts: `TurnAborted` (user interrupt), `Fatal` tool errors, `ContextWindowExceeded` after compaction fails, invalid image requests.

Maximum turns or steps. There is no `max_turns`, `max_steps`, or similar cap anywhere in `core`. A grep over `core/src` for `max_turns|max_steps|MAX_TURNS|max_tool_calls` returned nothing. The only ceilings are token-based: the context window (section 1.8) and the optional `RolloutBudgetConfig` (`core/src/config/mod.rs`, line 1341) with fields `limit_tokens`, `reminder_at_remaining_tokens: Vec<i64>`, `sampling_token_weight`, `prefill_token_weight`. The budget is a weighted sum of output tokens and non-cached input tokens (`core/src/rollout_budget.rs`, `record_usage`); crossing it raises `SessionBudgetExceeded` (`core/src/agent/control/budget.rs`, line 14). Reminders at the configured remaining-token thresholds are injected into history as user-role context messages. The comment in `run_turn` (line 672) states the designers' assumption: "as long as compaction works well in getting us way below the token limit, we shouldn't worry about being in an infinite loop."

Order of operations inside one iteration of `run_turn`:

1. Drain pending (steering) input and record it, run prompt hooks.
2. Record a rollout-budget reminder if due (`rollout_budget::maybe_record_reminder`).
3. Capture a `StepContext` (the tool router, model settings, environments) so that "context, advertised tools, and tool calls share one request view" (comment at line 490).
4. Record a current-time reminder if due, record world-state changes, validate required skills, record a reasoning-effort override item.
5. Build the prompt from history: `sess.clone_history().await.for_prompt(&input_modalities)`.
6. `run_sampling_request` (retry wrapper) -> `try_run_sampling_request` (stream consumer).
7. After the call: compute token status, maybe start background compaction, maybe roll over to a new context window (mid-turn compaction) when `needs_follow_up && (new_window_requested || token_limit_reached || candidate.is_some())`.
8. If `!needs_follow_up`: run stop hooks, legacy after-agent hook, optional post-turn compaction, then `break`.

How the model request is built (`build_prompt`, lines 1668-1700):

```rust
Prompt {
    input,
    tools: step_context.tool_router.model_visible_specs(),   // empty when incremental tools are used
    parallel_tool_calls: true,
    base_instructions,
    output_schema: turn_context.final_output_json_schema.clone(),
    output_schema_strict: ...,
    cyber_access_program: ...,
}
```

The whole history is resent on every call (Responses API input array). Tool definitions are resent unless the "incremental tools" window feature is on. `output_schema` is an optional JSON schema for the final message, used by `codex exec --output-schema`.

### 1.3 How tool calls are executed

Routing. `ToolRouter::build_tool_call` (`tools/router.rs`, line 262) converts a streamed `ResponseItem::FunctionCall { name, namespace, arguments, call_id }` or `CustomToolCall { name, input }` into a `ToolCall { tool_name, call_id, payload }`. Dispatch goes through `ToolRegistry::dispatch_any_with_state`, which looks up a `RegisteredTool` with a `runtime` (the handler) and an `exposure` (`Direct`, `DirectModelOnly`, `Deferred`, `DeferredModelOnly`, `CodeModeOnly`, `Hidden`). Deferred tools are only visible through a BM25 `tool_search` tool (description in `tools/handlers/tool_search_spec.rs`: "Searches over deferred tool metadata with BM25 and exposes matching tools for the next model call").

Execution and result delivery. Each tool call becomes a boxed future pushed onto `FuturesOrdered<InFlightFuture>` (`turn.rs`, line 2905). The futures start immediately while the stream is still being read, so tools run concurrently with the model finishing its response. After the stream completes, `drain_in_flight` (line 2565) awaits them in order and records each `FunctionCallOutput` into history. Results therefore always enter history in the order the model emitted the calls, regardless of completion order.

Parallelism gate (`tools/parallel.rs`, lines 206-236). A single `tokio::sync::RwLock<()>` per sampling request gates execution:

```rust
if supports_parallel {
    Either::Left(lock.read().await)
} else {
    Either::Right(lock.write().await)
}
```

Tools whose runtime reports `supports_parallel_tool_calls() == true` take a read lock and run together. Tools that do not take a write lock and therefore run alone. Which tools opt in: `view_image`, `current_time`, `get_context_remaining`, `list_agents`, MCP tools only when the server opts in (`tools/handlers/mcp.rs`, around line 887-920), `exec_command` and `write_stdin` (unified exec handlers define `supports_parallel_tool_calls`; `exec_command.rs` line 141). The registry returns `false` for hidden tools (`registry.rs`, line 606).

Tool failure semantics. `FunctionCallError` has two important variants. `RespondToModel(message)` turns into a normal `FunctionCallOutput` whose body is the error text, so the model sees it and may retry (`parallel.rs`, line 118: `Self::failure_response(error_call, other)`). `Fatal(message)` aborts the turn (`Err(CodexErr::Fatal(message))`). A cancelled tool call produces an "aborted" response with the elapsed seconds (`aborted_response`).

Approvals and sandboxing. Shell commands run under a sandbox policy and an approval policy (`core/src/safety.rs`, `exec_policy`, `sandboxing/`). The prompts reference approval modes `never`, `untrusted`, `on-request` (`prompts/templates/permissions/approval_policy/*.md`). This is a large part of the harness but is irrelevant to a read-only RAG baseline.

### 1.4 Tool declaration format

Codex declares tools in the OpenAI Responses API shape. `codex-rs/tools/src/tool_spec.rs`, lines 19-56:

```rust
/// When serialized as JSON, this produces a valid "Tool" in the OpenAI
/// Responses API.
#[derive(Debug, Clone, Serialize, PartialEq)]
#[serde(tag = "type")]
pub enum ToolSpec {
    #[serde(rename = "function")]
    Function(ResponsesApiTool),
    #[serde(rename = "namespace")]
    Namespace(ResponsesApiNamespace),
    #[serde(rename = "tool_search")]
    ToolSearch { execution: String, description: String, parameters: JsonSchema },
    #[serde(rename = "web_search")]
    WebSearch { ... },
    #[serde(rename = "custom")]
    Freeform(FreeformTool),
}
```

`codex-rs/tools/src/responses_api.rs`, lines 33-43:

```rust
pub struct ResponsesApiTool {
    pub name: String,
    pub description: String,
    /// TODO: Validation. When strict is set to true, the JSON schema,
    /// `required` and `additional_properties` must be present. All fields in
    /// `properties` must be present in `required`.
    pub strict: bool,
    pub defer_loading: Option<bool>,
    pub parameters: JsonSchema,
    #[serde(skip)]
    pub output_schema: Option<ToolOutputSchema>,
}
```

`FreeformTool { name, description, defer_loading, format: { type, syntax, definition } }` is used for `apply_patch`, whose argument is a raw patch string, not JSON. The GPT-5.2 prompt says "This is a FREEFORM tool, so do not wrap the patch in JSON." Serialized MCP tool definitions are capped at `MAX_SERIALIZED_MCP_TOOL_BYTES = 8_000` (`responses_api.rs`, line 14).

A concrete built-in declaration, `exec_command` (`core/src/tools/handlers/shell_spec.rs`, lines 23-114):

- `name: "exec_command"`
- `description: "Runs a command in a PTY, returning output or a session ID for ongoing interaction."`
- `strict: false`
- parameters: `cmd` (string, "Shell command to execute.", the only required field), `workdir` ("Working directory for the command. Defaults to the turn cwd."), `tty` (boolean), `yield_time_ms` ("Wait before yielding output. Defaults to 10000 ms; effective range is 250-30000 ms."), `max_output_tokens` ("Output token budget. Defaults to 10000 tokens; larger requests may be capped by policy."), optional `shell`, `login`, `environment_id`, and approval parameters.
- `additionalProperties: false`, plus an `output_schema`.

Every built-in tool is a short one-sentence description with parameter-level descriptions carried in the JSON schema. The long behavioural guidance (when to use the shell, how to parallelize, how `apply_patch` works) lives in the system prompt, not in the tool description.

### 1.5 Tool output size limits

Codex truncates every tool result before it enters history, and the limit comes from the model catalog, not from the tool.

- Unit of measure. `TruncationPolicy::{Bytes(usize), Tokens(usize)}` (`protocol/src/protocol.rs`, line 3501). Byte-token conversion uses a fixed `APPROX_BYTES_PER_TOKEN: usize = 4` (`utils/string/src/truncate.rs`, line 6).
- Default. The fallback model descriptor for unknown models sets `truncation_policy: TruncationPolicyConfig::bytes(10_000)` (`models-manager/src/model_info.rs`, line 126), that is about 2,500 tokens per tool output. Known models carry their own value in the model catalog; the user config key `tool_output_token_limit` overrides it (`models-manager/src/model_info.rs`, lines 32-44).
- `exec_command` additionally takes `max_output_tokens` from the model, default 10,000 tokens, and the effective policy is the smaller of the model's request and the catalog policy (`tools/context.rs`, `model_output_policy`, lines 482-489).
- Strategy. Truncation keeps the head and tail and removes the middle (`truncate_middle_chars`, `truncate_middle_with_token_budget`). The formatted variant prefixes a warning (`utils/output-truncation/src/lib.rs`, lines 23-33):

  ```
  Warning: truncated output (original token count: {n})
  Total output lines: {lines}

  {head ... tail}
  ```

- Exec results are wrapped with metadata (`tools/mod.rs`, `format_exec_output_for_model`, lines 88-114): `Exit code: {code}`, `Wall time: {seconds} seconds`, `Total output lines: {n}` when truncated, then `Output:` and the body. Timeouts prepend `command timed out after {ms} milliseconds`.
- History applies a 20 percent serialization allowance on top: `with_serialization_allowance(policy) = policy * 1.2` (`output-truncation/src/lib.rs`, line 19), and `ExecCommandToolOutput::response_text` shrinks the body until header plus body fit that budget so "it does not truncate an already-truncated output a second time" (`tools/context.rs`, lines 552-575).
- MCP results that exceed the byte limit are replaced by a bounded text preview that keeps `is_error` (`truncate_mcp_tool_result`).
- Other caps worth noting: `MAX_THREAD_INSTRUCTIONS_TOKENS = 10_000` for AGENTS.md (`core/src/agents_md_manager.rs`, line 190), `MAX_MANAGED_DEVELOPER_INSTRUCTIONS_TOKENS = 10_000`, `COMPACT_USER_MESSAGE_MAX_TOKENS = 20_000` for user messages retained through compaction (`core/src/compact.rs`, line 63), memory snippets at 8,900 bytes (`core/src/context/memory.rs`, line 38), exec default timeout `DEFAULT_EXEC_COMMAND_TIMEOUT_MS = 10_000` (`core/src/exec.rs`, line 63).

### 1.6 Parallel tool calls

- Requested from the model on every sampling request: `parallel_tool_calls: true` in `build_prompt` (`turn.rs`, line 1680). It is disabled only for "responses lite" models (`client.rs`, line 1083: `prompt.parallel_tool_calls && !model_info.use_responses_lite`).
- Enforced at execution by the read/write lock described in 1.3, so a parallel request from the model does not by itself make side-effecting tools run concurrently.
- Prompted explicitly in `gpt_5_2_prompt.md` under "Shell commands": "Parallelize tool calls whenever possible - especially file reads, such as `cat`, `rg`, `sed`, `ls`, `git show`, `nl`, `wc`. Use `multi_tool_use.parallel` to parallelize tool calls and only this." The orchestrator template (`core/templates/agents/orchestrator.md`) has the same line commented out, which suggests it was found unhelpful in the multi-agent setting.

### 1.7 Error and retry policy

Transport retries (`core/src/responses_retry.rs`, `handle_response_stream_error`):

- Budget: `stream_max_retries()` from the provider, default `DEFAULT_STREAM_MAX_RETRIES: u64 = 5`; HTTP-level `DEFAULT_REQUEST_MAX_RETRIES: u64 = 4`; both user-configurable up to a hard cap of 100 (`model-provider-info/src/lib.rs`, lines 66-75). Stream idle timeout defaults to 300,000 ms.
- Delay: `CodexErr::retry_delay(retry_count)` (`protocol/src/error.rs`, line 410) returns `None` for terminal errors and otherwise the server's `Retry-After` or `backoff(attempt)`. The backoff is `base * 2^(attempt-1) * jitter(0.9..1.1)` (`codex-client/src/retry.rs`, line 43).
- Terminal errors (no retry): `ContextWindowExceeded`, `UsageLimitReached`, `QuotaExceeded`, `InvalidRequest`, `InvalidPrompt`, `ResponseIncomplete`, `SessionBudgetExceeded`, `TurnAborted`, `Interrupted`, `Fatal`, `ToolCollision`, policy violations.
- Retried errors: `Stream`, `ContentFilter`, `RateLimitExceeded`, `Timeout`, `RequestTimeout`, `UnexpectedStatus`, `ResponseStreamFailed`, `ConnectionFailed`, `InternalServerError`, `ServerOverloaded`, IO and JSON errors.
- Connection failures can be retried without bound when `Feature::UnboundedConnectionRetries` is on, with delay doubling from 5 s to a 60 s cap (`INITIAL_CONNECTION_RETRY_DELAY`, `MAX_CONNECTION_RETRY_DELAY`).
- After the retry budget is exhausted on WebSocket transport, the client falls back to HTTPS once and resets the counter ("Falling back from WebSockets to HTTPS transport").
- On `ContentFilter`, a `ContentFilterGuidance` developer message (from the model catalog, at most 512 bytes) is appended to history before retrying.
- The same sampling request is resent with the same input on retry; `original_input` is kept so the recorded input is the first attempt's.

Compaction retries (`core/src/compact.rs`, lines 336-385): on `ContextWindowExceeded` while compacting, the oldest history item is removed and the compaction retried ("Trim from the beginning to preserve cache (prefix-based) and keep recent messages intact"); other errors use the same `max_retries` and `backoff`.

Tool-level errors are not retried by the harness; they are returned to the model as text (section 1.3). The system prompt asks the model to "persevere even when function calls fail."

### 1.8 Context compaction

Thresholds (`core/src/session/context_window.rs`, `context_window_token_status_with_config`):

- `resolved_context_window()` = catalog `context_window` (or `max_context_window`) times `effective_context_window_percent` (default 95) / 100 (`protocol/src/openai_models.rs`, lines 518-526). The fallback descriptor uses `context_window: Some(272_000)`.
- `auto_compact_token_limit()` = min(configured `model_auto_compact_token_limit`, 90 percent of the resolved window): `(context_window * 9) / 10` (`openai_models.rs`, lines 529-540). For the fallback model this is 272,000 x 0.95 x 0.9 = about 232,000 tokens.
- `token_limit_reached` when the scoped usage reaches the (buffered) auto-compact limit or the full window. Scope is `Total` by default, or `BodyAfterPrefix` which counts only tokens added after the cached prefix.
- `turn_end_compaction_threshold_reached` when `model_post_turn_compact_threshold_percent` (default 0, disabled) is set and usage exceeds that percent of the window.
- `async_compaction_threshold_percent` defaults to 65 (`core/src/config/mod.rs`, line 225) and only applies to providers with remote compaction V2 support.

When it runs (`turn.rs`):

- Pre-turn: `run_pre_sampling_compact` before the new user message is recorded.
- Mid-turn: after a sampling request that needs follow-up, if `token_limit_reached` or a background candidate is ready, `run_auto_compact(..., CompactionPhase::MidTurn)` then `continue` the loop.
- Post-turn: after the final message, if the post-turn threshold is configured.
- Manual: `/compact` runs `run_compact_task` with `CompactionReason::UserRequested`.

Mechanism (`core/src/compact.rs`, `run_compact_task_inner_impl`, lines 287-450):

1. Append the compaction prompt as a user message and call the model once over the full history (with the normal `max_retries`).
2. Take the last assistant message as the summary.
3. Build a new history: the kept user messages (`collect_annotated_user_messages`, excluding earlier summaries, each capped at 20,000 tokens), then one summary user message `"{SUMMARY_PREFIX}\n{summary}"`.
4. Re-insert the canonical initial context (base instructions, environment, AGENTS.md) "immediately before the last real user, agent message, or retained standalone output" (`insert_initial_context_before_last_real_user_or_summary`).
5. Replace history, advance the "auto-compact window" counter, recompute token usage, and emit the warning: "Heads up: Long threads and multiple compactions can cause the model to be less accurate. Start a new thread when possible to keep threads small and targeted."

The compaction prompt (`codex-rs/prompts/templates/compact/prompt.md`, complete):

> You are performing a CONTEXT CHECKPOINT COMPACTION. Create a handoff summary for another LLM that will resume the task.
>
> Include:
> - Current progress and key decisions made
> - Important context, constraints, or user preferences
> - What remains to be done (clear next steps)
> - Any critical data, examples, or references needed to continue
>
> Be concise, structured, and focused on helping the next LLM seamlessly continue the work.

The summary prefix (`prompts/templates/compact/summary_prefix.md`, complete):

> Another language model started to solve this problem and produced a summary of its thinking process. You also have access to the state of the tools that were used by that language model. Use this to build on the work that has already been done and avoid duplicating work. Here is the summary produced by the other language model, use the information in this summary to assist with your own analysis:

A user-configurable `compact_prompt` replaces the default.

Variants. Remote compaction V2 (`compact_remote_v2*.rs`) lets the OpenAI backend produce the compacted history, retaining recent agent messages up to `MAX_RETAINED_AGENT_MESSAGE_TOKENS = 10_000`. A "token budget" mode (`compact_token_budget.rs`, `Feature::TokenBudget`, only for ChatGPT Plus/Pro accounts) "skips model/server summarization and installs a fresh context window instead", driven by reminder messages injected when `base_window_tokens_remaining` drops below a threshold and an "auto compact fallback prompt" when it reaches zero (`session/token_budget.rs`). There is also a `get_context_remaining` tool and a `new_context_window` tool the model can call (`tools/handlers/get_context_remaining_spec.rs`, `new_context_window_spec.rs`).

### 1.9 The system prompts

Selection. Prompts are per model and come from the model catalog: `ModelMessages.instructions_template` (`protocol/src/openai_models.rs`, line 559), rendered by `render_model_instructions` (`prompts/src/model_instructions.rs`). The repo ships the templates as Markdown in `codex-rs/core/`: `gpt_5_2_prompt.md` (298 lines), `gpt_5_1_prompt.md` (331), `gpt-5.2-codex_prompt.md` (80), `gpt_5_codex_prompt.md` (68), `gpt-5.1-codex-max_prompt.md` (80). Unknown or local models get `codex-rs/models-manager/prompt.md` (275 lines, `BASE_INSTRUCTIONS`), which is a near-copy of the GPT-5.1 prompt without the model name. The `# Personality` section can be stripped by `personality = "none"`.

Two families. The general GPT-5.x prompts are long and tutorial-like. The "codex" model prompts are short and assume the model was trained for the harness, for example `gpt-5.2-codex_prompt.md` begins "You are Codex, based on GPT-5. You are running as a coding agent in the Codex CLI on a user's computer." and has no planning tutorial, only "Skip using the planning tool for straightforward tasks (roughly the easiest 25%). Do not make single-step plans."

The parts of `gpt_5_2_prompt.md` that govern planning, information gathering, and stopping:

Autonomy and persistence:

> Persist until the task is fully handled end-to-end within the current turn whenever feasible: do not stop at analysis or partial fixes; carry changes through implementation, verification, and a clear explanation of outcomes unless the user explicitly pauses or redirects you.
>
> Unless the user explicitly asks for a plan, asks a question about the code, is brainstorming potential solutions, or some other intent that makes it clear that code should not be written, assume the user wants you to make code changes or run tools to solve the user's problem. In these cases, it's bad to output your proposed solution in a message, you should go ahead and actually implement the change. If you encounter challenges or blockers, you should attempt to resolve them yourself.

Task execution (the stop rule):

> You are a coding agent. You must keep going until the query or task is completely resolved, before ending your turn and yielding back to the user. Persist until the task is fully handled end-to-end within the current turn whenever feasible and persevere even when function calls fail. Only terminate your turn when you are sure that the problem is solved. Autonomously resolve the query to the best of your ability, using the tools available to you, before coming back to the user. Do NOT guess or make up an answer.

Planning (when to plan, and when not to):

> You have access to an `update_plan` tool which tracks steps and progress and renders them to the user. [...] Note that plans are not for padding out simple work with filler steps or stating the obvious. The content of your plan should not involve doing anything that you aren't capable of doing (i.e. don't try to test things that you can't test). Do not use plans for simple or single-step queries that you can just do or answer immediately.
>
> Use a plan when:
> - The task is non-trivial and will require multiple actions over a long time horizon.
> - There are logical phases or dependencies where sequencing matters.
> - The work has ambiguity that benefits from outlining high-level goals.
> - You want intermediate checkpoints for feedback and validation.
> - When the user asked you to do more than one thing in a single prompt
> - The user has asked you to use the plan tool (aka "TODOs")
> - You generate additional steps while working, and plan to do them before yielding to the user

The plan is a tool call (`update_plan`) with 1-sentence steps "no more than 5-7 words each" and statuses `pending`, `in_progress`, `completed`, with "exactly one item in_progress at a time". The prompt includes three "high-quality" and three "low-quality" example plans, that is, few-shot examples embedded in the system prompt.

Information gathering. The GPT-5.1 prompt and the fallback prompt have a "Responsiveness" section that tells the model to narrate before tool calls ("Before making tool calls, send a brief preamble to the user explaining what you're about to do", with eight example preambles). The GPT-5.2 prompt leaves "## Responsiveness" empty, so preambles were dropped for that model. Shell guidance: "prefer using `rg` or `rg --files` [...] because `rg` is much faster", "Do not use python scripts to attempt to output larger chunks of a file", "Do not waste tokens by re-reading files after calling `apply_patch` on them. The tool call will fail if it didn't work." Repository knowledge: "The contents of the AGENTS.md file at the root of the repo and any directories from the CWD up to the root are included with the developer message and don't need to be re-read."

Verification: "If the codebase has tests, or the ability to build or run tests, consider using them to verify changes once your work is complete. When testing, your philosophy should be to start as specific as possible to the code you changed [...] then make your way to broader tests as you build confidence." Formatting: "you can iterate up to 3 times to get formatting right".

Final answer length: "Brevity is very important as a default. You should be very concise (i.e. no more than 10 lines), but can relax this requirement for tasks where additional detail and comprehensiveness is important." Then a detailed plain-text formatting spec (headers, bullets, monospace, file references, "Tiny/small single-file change (<= ~10 lines): 2-5 sentences or <=3 bullets").

Citations: "NEVER output inline citations like 【F:README.md†L5-L14】 in your outputs. The CLI is not able to render these". Relevant to a RAG agent: Codex deliberately replaces a learned citation syntax with clickable file paths.

Persistent (daemon) mode (`prompts/templates/persistent_mode.md`) adds stopping discipline for unattended operation: "Bound a follow-up by its purpose, scope, and outcome, not an arbitrary number of checks. A pending, running, inconclusive, or unchanged result is not by itself completion." and "Persistence does not broaden that scope."

Multi-agent orchestrator (`core/templates/agents/orchestrator.md`): "Prefer multiple sub-agents to parallelize your work", "If sub-agents are running, wait for them before yielding", "When you ask sub-agent to do the work for you, your only role becomes to coordinate them." The plan-tool threshold there is "roughly the easiest 40%".

### 1.10 Model and provider handling

Provider abstraction (`codex-rs/model-provider-info/src/lib.rs`). `ModelProviderInfo { name, base_url, model_catalog_url, env_key, auth, wire_api, capabilities, http_headers, request_max_retries, stream_max_retries, stream_idle_timeout_ms, requires_openai_auth, supports_websockets, ... }`. Providers are built in (OpenAI, Amazon Bedrock) or user-defined under `[model_providers]` in `~/.codex/config.toml`.

Wire API. Only the Responses API is supported. `WireApi` has a single variant `Responses`; deserializing `"chat"` fails with: "`wire_api = \"chat\"` is no longer supported.\nHow to fix: set `wire_api = \"responses\"` in your provider config.\nMore info: https://github.com/openai/codex/discussions/7782". The `ollama-chat` provider id is likewise removed. Any third-party or local server must speak `/v1/responses`.

Local open-weight models. `codex --oss` (or `--local-provider`) selects Ollama or LM Studio; the default model is `gpt-oss:20b` on Ollama (`ollama/src/lib.rs`, line 16, `DEFAULT_OSS_MODEL`) and `openai/gpt-oss-20b` on LM Studio (`lmstudio/src/lib.rs`, line 7). `ensure_oss_ready` pulls the model if missing; `ensure_responses_supported` requires Ollama >= 0.13.4 because of the Responses-only wire API. This is the only explicit treatment of small or open-weight models in the harness: it is a provider and download concern, with no prompt or budget changes.

Unknown models. `model_info_from_slug` (`models-manager/src/model_info.rs`, lines 100-150) logs "Unknown model {slug} is used. This will use fallback model metadata." and supplies: `context_window: Some(272_000)`, `effective_context_window_percent: 95`, `truncation_policy: bytes(10_000)`, `shell_type: UnifiedExec`, `supports_reasoning_effort_updates: false`, `supports_parallel_tool_calls` not set (per-tool), `default_reasoning_level: None`, and the fallback `prompt.md`. A gpt-oss:20b run therefore gets a GPT-5-sized context assumption unless `model_context_window` is set in config.

Reasoning effort. `ReasoningEffort { None, Minimal, Low, Medium (default), High, XHigh, Max, Ultra, Persistent, Custom(String) }` (`protocol/src/openai_models.rs`, line 62). Selected per turn from `model_reasoning_effort` config or the catalog's `default_reasoning_level`. Mid-thread effort changes are written into history as `ConfigurationUpdate` items so the prompt cache survives, but only when `reasoning_effort_override_enabled && provider.is_openai() && model_info.supports_reasoning_effort_updates` (`core/src/client.rs`, line 621). Everything else is per-request and provider-neutral. Reasoning summaries are requested via `supports_reasoning_summary_parameter`.

Capability flags in `ModelInfo` that change harness behaviour: `shell_type` (which shell tool to expose), `apply_patch_tool_type` (freeform vs function), `web_search_tool_type`, `input_modalities`, `use_responses_lite` (disables parallel tool calls and image detail), `supports_search_tool`, `tool_mode` (direct vs code mode), `experimental_supported_tools`, `multi_agent_version`.

What is not said. There is no guidance, code path, or prompt variant for weak or small models beyond the generic fallback. The prompts are written for frontier models (`gpt-5.2`, `gpt-5.1-codex-max`). The hardcoded model presets were removed in favour of a server-side catalog (`models-manager/src/model_presets.rs`: "Hardcoded model presets were removed; model listings are now derived from the active catalog."). The only degradation-related text is the post-compaction warning about accuracy loss.

---

## Part 2. Anthropic guidance

### 2.1 Building effective agents (Dec 19, 2024)

URL: https://www.anthropic.com/engineering/building-effective-agents. "Written by Erik S. and Barry Zhang." The page now carries a note that much of its tooling content is outdated and points to newer material, but the definitions remain the canonical ones.

Definitions (verbatim):

- "At Anthropic, we categorize all these variations as agentic systems."
- "Workflows are systems where LLMs and tools are orchestrated through predefined code paths."
- Agents are systems where "LLMs dynamically direct their own processes and tool usage, maintaining control over how they accomplish tasks."

When (and when not) to use agents:

- "we recommend finding the simplest solution possible, and only increasing complexity when needed."
- "Agentic systems often trade latency and cost for better task performance."
- "workflows offer predictability and consistency for well-defined tasks."
- "agents are the better option when flexibility and model-driven decision-making are needed at scale."
- "optimizing single LLM calls with retrieval and in-context examples is usually enough."

Patterns and stated trade-offs:

| Pattern | Description (verbatim fragments) | When to use | Trade-off stated |
| --- | --- | --- | --- |
| Augmented LLM | "an LLM enhanced with augmentations such as retrieval, tools, and memory" | the building block | none |
| Prompt chaining | each call "processes the output of the previous one" | task "can be easily and cleanly decomposed into fixed subtasks" | "trade[s] off latency for higher accuracy" |
| Routing | "Routing classifies an input and directs it to a specialized followup task." | "distinct categories that are better handled separately" | without it, "optimizing for one kind of input can hurt performance on other inputs" |
| Parallelization (sectioning, voting) | "independent subtasks run in parallel"; "the same task multiple times to get diverse outputs" | "for speed" or when "multiple perspectives or attempts are needed for higher confidence results" | none stated |
| Orchestrator-workers | "a central LLM dynamically breaks down tasks, delegates them to worker LLMs, and synthesizes their results" | subtasks "aren't pre-defined" | none stated |
| Evaluator-optimizer | "one LLM call generates a response while another provides evaluation and feedback in a loop" | "when we have clear evaluation criteria" | none stated |
| Autonomous agent | "They are typically just LLMs using tools based on environmental feedback in a loop." | open-ended problems where the number of steps is hard to predict | "higher costs, and the potential for compounding errors" |

Summary guidance: "you should consider adding complexity _only_ when it demonstrably improves outcomes." "Start with simple prompts, optimize them with comprehensive evaluation" and "add multi-step agentic systems only when simpler solutions fall short." Three principles: keep the design simple, make planning steps transparent, craft the agent-computer interface (ACI) through documentation and testing.

Appendix 2, "Prompt engineering your tools" (the ACI rules):

- "Give the model enough tokens to "think" before it writes itself into a corner."
- "Keep the format close to what the model has seen naturally occurring in text on the internet."
- Avoid "formatting overhead" "such as having to keep an accurate count of thousands of lines of code, or string-escaping any code it writes."
- "Put yourself in the model's shoes."
- "A good tool definition often includes example usage, edge cases, input format requirements."
- "Think of this as writing a great docstring for a junior developer on your team."
- "Run many example inputs in our workbench to see what mistakes the model makes, and iterate."
- "Poka-yoke your tools. Change the arguments so that it is harder to make mistakes."
- Example: the team "changed the tool to always require absolute filepaths" and the model then "used this method flawlessly."

Relevance to the paper. The routing pipeline in the thesis is exactly the "routing" workflow (classifier directs to a specialised path), and the baseline is the "autonomous agent" pattern. The paper can frame its question as the empirical test of the trade-off this post asserts: predictability and cost (workflow) versus flexibility at "higher costs, and the potential for compounding errors" (agent), on a small model where compounding errors are more likely.

### 2.2 Writing tools for agents (Sep 11, 2025)

URL: https://www.anthropic.com/engineering/writing-tools-for-agents. "Written by Ken Aizawa."

- "Tools are a new kind of software which reflects a contract between deterministic systems and non-deterministic agents."
- Evaluation: "Start by generating lots of evaluation tasks, grounded in real world uses." "Strong evaluation tasks might require multiple tool calls—potentially dozens." "Avoid overly strict verifiers that reject correct responses due to spurious differences." "We relied on held-out test sets to ensure we did not overfit". Metrics to track include "the total runtime of individual tool calls and tasks". "Lots of redundant tool calls might suggest some rightsizing of pagination or token limit parameters is warranted."
- Choosing tools: "More tools don't always lead to better outcomes." Avoid tools that "merely wrap existing software functionality or API endpoints." "We recommend building a few thoughtful tools targeting specific high-impact workflows." Consolidate, for example "a `schedule_event` tool which finds availability and schedules an event." "Too many tools or overlapping tools can also distract agents from pursuing efficient strategies."
- Namespacing: "Namespacing (grouping related tools under common prefixes) can help delineate boundaries between lots of tools." "Effects vary by LLM and we encourage you to choose a naming scheme according to your own evaluations."
- Returning context: "return only high signal information back to agents." Avoid "`uuid`, `256px_image_url`, `mime_type`." "resolving arbitrary alphanumeric UUIDs to more semantically meaningful and interpretable language" improved precision. Offer a `response_format` enum with "“concise” or “detailed” responses." (206 vs 72 tokens, "⅓ of the tokens").
- Token efficiency: "implementing some combination of pagination, range selection, filtering, and/or truncation". "For Claude Code, we restrict tool responses to 25,000 tokens by default." Prefer "making many small and targeted searches instead of a single, broad search." "prompt-engineer your error responses to clearly communicate specific and actionable improvements."
- Descriptions: "think of how you would describe your tool to a new hire on your team." "Avoid ambiguity by clearly describing (and enforcing with strict data models) expected inputs and outputs." "instead of a parameter named `user`, try a parameter named `user_id`." "Even small refinements to tool descriptions can yield dramatic improvements." (Claude Sonnet 3.5 reached state of the art on SWE-bench Verified after description refinements.)

### 2.3 Effective context engineering for AI agents (Sep 29, 2025)

URL: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents.

- Definition: context engineering is "the set of strategies for curating and maintaining the optimal set of tokens (information) during LLM inference." Prompt engineering is the subset about writing instructions.
- "context rot": as "the number of tokens in the context window increases," recall declines. Models have an "attention budget"; each token "depletes this budget by some amount".
- System prompts: "The right altitude is the Goldilocks zone between two common failure modes." Hard-coded logic is brittle, vague guidance gives no signal; "The optimal altitude strikes a balance: specific enough to guide behavior effectively." Start minimal, add rules from observed failures.
- Tools: "Because tools define the contract between agents and their information/action space," they must be token-efficient. "If a human engineer can't definitively say which tool should be used in a given situation" an agent cannot either.
- Examples: curate "a set of diverse, canonical examples that effectively portray the expected behavior of the agent" instead of long edge-case rule lists.
- Just-in-time retrieval: keep "lightweight identifiers (file paths, stored queries, web links, etc.)" and load content with tools at runtime. Claude Code's hybrid: "CLAUDE.md files are naively dropped into context up front," while glob and grep fetch files just in time. Runtime exploration is slower and needs guidance; the hybrid may suit "less dynamic domains like legal or finance".
- Long-horizon techniques: compaction, structured note-taking, sub-agents.
  - "Compaction is the practice of taking a conversation nearing the context window limit," summarising it, and starting a new window. Claude Code keeps "architectural decisions, unresolved bugs, and implementation details" and drops redundant tool outputs. Tune for recall first, then precision. Tool result clearing is "one of the safest lightest touch forms of compaction".
  - Structured note-taking: notes "persisted to memory outside of the context window" (to-do lists, a `NOTES.md`, the Pokemon example tracking that Pikachu "has gained 8 levels toward the target of 10").
  - Sub-agents: "Specialized sub-agents can handle focused tasks with clean context windows." Each returns "a condensed, distilled summary of its work (often 1,000-2,000 tokens)" and "the detailed search context remains isolated within sub-agents."
  - Choosing: compaction for extended back-and-forth, note-taking for milestone-driven iterative work, multi-agent for parallel research.
- Conclusion: "find the smallest set of high-signal tokens that maximize the likelihood of your desired outcome." Treat "context as a precious, finite resource".

### 2.4 Building agents with the Claude Agent SDK (Sep 29, 2025)

URL (current): https://claude.com/blog/building-agents-with-the-claude-agent-sdk (the anthropic.com/engineering URL redirects here).

- "the agent harness that powers Claude Code (the Claude Code SDK) can power many other types of agents, too."
- The loop: "gather context -> take action -> verify work -> repeat."
- Gather context: "Semantic search is usually faster than agentic search, but less accurate, more difficult to maintain, and less transparent." Recommendation: "starting with agentic search." Subagents "enable parallelization" and "use their own isolated context windows." Compaction "automatically summarizes previous messages when the context limit approaches."
- Take action: "Tools are the primary building blocks of execution for your agent." "Bash is useful as a general-purpose tool". "Code is precise, composable, and infinitely reusable, making it an ideal output for agents." MCP "provides standardized integrations to external services".
- Verify: "The best form of feedback is providing clearly defined rules for an output, then explaining which rules failed and why." Visual feedback helps for UI. LLM as judge: "This is generally not a very robust method, and can have heavy latency tradeoffs."
- "Agents that can check and improve their own output are fundamentally more reliable." "The best way to improve an agent is to look carefully at its output, especially the cases where it fails." Build "a representative test set for programmatic evaluations (or evals) based on customer usage."

### 2.5 Agent SDK documentation: "How the agent loop works" (fetched 2026-10-14)

URL: https://code.claude.com/docs/en/agent-sdk/agent-loop (the `docs.claude.com/en/api/agent-sdk/overview` URL in the task redirects to `platform.claude.com` then `code.claude.com/docs/en/agent-sdk/overview`).

Verbatim loop description:

> 1. **Receive prompt.** Claude receives your prompt, along with the system prompt, tool definitions, and conversation history. [...]
> 2. **Evaluate and respond.** Claude evaluates the current state and determines how to proceed. It may respond with text, request one or more tool calls, or both. [...]
> 3. **Execute tools.** The SDK runs each requested tool and collects the results. Each set of tool results feeds back to Claude for the next decision. [...]
> 4. **Repeat.** Steps 2 and 3 repeat as a cycle. Each full cycle is one turn. Claude continues calling tools and processing results until it produces a response with no tool calls.
> 5. **Return result.** The SDK yields a final `AssistantMessage` with the text response (no tool calls), followed by a `ResultMessage` with the final text, token usage, cost, and session ID.

Stop rule: "Turns continue until Claude produces output with no tool calls, at which point the loop ends and the final result is delivered."

Caps: "You can cap the loop with `max_turns` / `maxTurns`, which counts tool-use turns only." "You can also use `max_budget_usd` / `maxBudgetUsd` to cap turns based on a spend threshold." Defaults: "Max turns [...] No limit", "Max budget [...] No limit". "Without limits, the loop runs until Claude finishes on its own, which is fine for well-scoped tasks but can run long on open-ended prompts ("improve this codebase"). Setting a budget is a good default for production agents." The worked example uses `max_turns=30`. Result subtypes: `success`, `error_max_turns`, `error_max_budget_usd`, `error_during_execution`, `error_max_structured_output_retries`; `stop_reason` carries `end_turn`, `max_tokens`, `refusal`.

Parallel execution: "When Claude requests multiple tool calls in a single turn, both SDKs can run them concurrently or sequentially depending on the tool. Read-only tools (like `Read`, `Glob`, `Grep`, and MCP tools marked as read-only) can run concurrently. Tools that modify state (like `Edit`, `Write`, and `Bash`) run sequentially to avoid conflicts." Custom tools opt in with `readOnlyHint`.

Effort: `"low" | "medium" | "high" | "xhigh" | "max"`; "Lower effort levels use fewer tokens per turn and reduce cost." "Use lower effort for agents doing simple, well-scoped tasks (like listing files or running a single grep)".

Context: "Everything accumulates: the system prompt, tool definitions, conversation history, tool inputs, and tool outputs." "Large tool outputs consume significant context." "When the context window approaches its limit, the SDK automatically compacts the conversation: it summarizes older history to free space, keeping your most recent exchanges and key decisions intact." Persistent rules belong in CLAUDE.md "because CLAUDE.md content is re-injected on every request." Compaction instructions can be put in CLAUDE.md; there is a `PreCompact` hook and manual `/compact`.

Tool-denial semantics: "When a tool is denied, Claude receives a rejection message as the tool result and typically attempts a different approach or reports that it couldn't proceed." (Same design as Codex's `RespondToModel`.)

Hooks: `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`, `SubagentStart`/`SubagentStop`, `PreCompact`. "Hooks run in your application process, not inside the agent's context window, so they don't consume context."

Built-in tools: `Read`, `Edit`, `Write`, `Glob`, `Grep`, `Bash`, `WebSearch`, `WebFetch`, `ToolSearch`, `Agent`, `Skill`, `AskUserQuestion`, `TaskCreate`, `TaskUpdate`.

### 2.6 "How Claude Code works" (fetched 2026-10-14)

URL: https://code.claude.com/docs/en/how-claude-code-works.

- "When you give Claude a task, it works through three phases: **gather context**, **take action**, and **verify results**. These phases blend together."
- Harness definition: "Claude Code is the layer around the model that provides the tools and manages the context the model sees. This surrounding layer is what the term agentic harness refers to."
- "Claude decides what each step requires based on what it learned from the previous step, chaining dozens of actions together and course-correcting along the way."
- Compaction order: "Claude Code manages context automatically as you approach the limit. It clears older tool outputs first, then summarizes the conversation if needed. Your requests and key code snippets are preserved; detailed instructions from early in the conversation may be lost."
- Thrash guard: "If a single file or tool output is so large that context refills immediately after each summary, Claude Code stops auto-compacting after a few attempts and shows an error instead of looping."
- Tool definitions: "MCP tool definitions are deferred by default and loaded on demand via tool search, so only tool names and server instructions consume context until Claude uses a specific tool."
- Auto memory: "The first 200 lines or 25KB of MEMORY.md, whichever comes first, load at the start of each session."

### 2.7 How we built our multi-agent research system (Jun 13, 2025)

URL: https://www.anthropic.com/engineering/multi-agent-research-system.

- "uses a multi-agent architecture with an orchestrator-worker pattern".
- Opus 4 lead with Sonnet 4 subagents "outperformed single-agent Claude Opus 4 by 90.2% on our internal research eval."
- Cost: agents use about 4x the tokens of chat, multi-agent "about 15× more tokens than chats."
- Eight prompting principles: think like your agents; teach the orchestrator how to delegate (objective, output format, tool guidance, task boundaries); scale effort to query complexity (explicit effort rules, simple queries get one agent); tool design and selection are critical; let agents improve themselves (self-rewritten tool descriptions cut completion time 40 percent); start wide, then narrow down; guide the thinking process (extended thinking as a scratchpad); parallel tool calling (up to 90 percent faster on complex queries).
- Evaluation: "Start small" with about 20 representative queries; a single LLM-as-judge call with a rubric and a 0.0-1.0 score plus pass/fail was most consistent; human evaluation caught source-selection bias toward SEO content farms.
- Production: resume from the point of failure plus retries and checkpoints; rainbow deployments; synchronous lead-waits-for-subagents simplifies coordination but bottlenecks.

### 2.8 Effective harnesses for long-running agents (Nov 26, 2025)

URL: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents.

- Two failure modes: "the agent tended to try to do too much at once" and ran out of context mid-implementation; or a later agent "would look around, see that progress had been made, and declare the job done."
- Design: an initializer session ("The very first agent session uses a specialized prompt that asks the model to set up the initial environment.") and coding sessions ("Every subsequent session asks the model to make incremental progress, then leave structured updates.").
- Feature list as JSON with every feature "marked as “failing”"; "We prompt coding agents to edit this file only by changing the status of a passes field." JSON was chosen because "the model is less likely to inappropriately change or overwrite JSON files compared to Markdown files."
- A `claude-progress.txt` log; agents "commit its progress to git with descriptive commit messages".
- "the next iteration of the coding agent was then asked to work on only one feature at a time."
- "Self-verify all features. Only mark features as “passing” after careful testing." Test "as a human user would".

### 2.9 Dynamic workflows and loop engineering (2026)

"A harness for every task: dynamic workflows in Claude Code", https://claude.dev/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code/ (claude.com/blog URL redirects), "PUBLISHED Jun 02, 2026", Thariq Shihipar and Sid Bidasaria.

- "Claude can now write its own harness on the fly, custom-built for the task at hand."
- Static vs dynamic: "because static workflows need to work for all edge cases, they are usually more generic." "A static harness runs the same steps for every question; a dynamic workflow is shaped to the one in front of it."
- Mechanism: "Dynamic workflows execute a javascript file with a few special functions that help spawn and coordinate subagents." Building blocks `agent(prompt, opts)`, `parallel()`, `pipeline()`; options `schema`, `model` (opus, sonnet, haiku), `isolation`, `agentType`.
- Named failure modes of single-context agents: "Agentic laziness refers to when Claude stops before finishing a particularly complex, multi-part task", "Self-preferential bias refers to Claude's tendency to prefer its own results or findings", "Goal drift refers to the gradual loss of fidelity to the original objective across many turns, especially after compaction."
- Trade-offs: "dynamic workflows often use more tokens and are best suited for complex, high value tasks." "most traditional coding tasks do not need a panel of 5 reviewers." "parallelism and specialization have to earn their coordination cost." "You can set explicit token usage budgets for dynamic workflows".
- Patterns: fan-out and synthesize, adversarial verification, tournament, "loop until done" with a stop condition.

"Loop engineering: getting started with loops", https://claude.com/blog/getting-started-with-loops, June 30, 2026, Delba de Oliveira and Michael Segner.

- Loops are "agents repeating cycles of work until a stop condition is met."
- Turn-based: "Every prompt you send starts a manual loop with you directing each turn." Goal-based (`/goal`): stops when "Goal achieved OR maximum number of turns reached"; "an evaluator model checks your condition and sends it back to work"; the model "doesn't have to make a determination on what is 'good enough' and end the loop early." Deterministic criteria recommended.
- "Your model and effort level choices are among the biggest levers on what a loop costs." "Loops that write code need loops that check it." "Not all tasks require complex loops; start with the simplest solution."

### 2.10 Claude Code best practices (docs, fetched 2026-10-14)

URL: https://code.claude.com/docs/en/best-practices (the engineering-blog URL redirects here).

- "Most best practices are based on one constraint: Claude's context window fills up fast, and performance degrades as it fills."
- "Claude stops when the work looks done. Without a check it can run, "looks done" is the only signal available". "Give Claude something that produces a pass or fail, and the loop closes on its own."
- Stop gating options: in one prompt; `/goal` (a separate evaluator re-checks after every turn); a Stop hook as "a deterministic gate"; a verification subagent "so the agent doing the work isn't the one grading it."
- CLAUDE.md: "keep it short and human-readable"; "For each line, ask: *"Would removing this cause Claude to make mistakes?"* If not, cut it. Bloated CLAUDE.md files cause Claude to ignore your actual instructions!"
- Plan mode: "If you could describe the diff in one sentence, skip the plan."
- Context: "/clear between unrelated tasks"; "After two failed corrections, `/clear` and write a better initial prompt"; use subagents so exploration "doesn't consume your main context"; "The infinite exploration" failure pattern.
- "A reviewer prompted to find gaps will usually report some, even when the work is sound".

---

## Part 3. Model agnosticism: synthesis across both sources

What Codex does:

- Abstracts the provider (base URL, auth, headers, retries, websocket support) but not the protocol: it is Responses-API-only. A local server must implement `/v1/responses`, which Ollama (>= 0.13.4), LM Studio, and vLLM-compatible gateways do.
- Carries per-model metadata (context window, truncation policy, reasoning levels, tool variants, prompt template) in a server-side catalog with a hard-coded fallback for unknown slugs. The fallback assumes a 272k window and a 10,000-byte tool-output cap.
- Ships the system prompt per model. There is no "small model" prompt; the fallback is the long GPT-5.1-style prompt.
- Reasoning effort is a per-request parameter with a model-default; mid-thread changes are an OpenAI-only optimisation.
- `--oss` defaults to `gpt-oss:20b`, an open-weight 20B model, which shows the harness is expected to work with a model of that size, but nothing is tuned for it.

What Anthropic says:

- The SDK and Claude Code are Claude-only. Model choice is `model` plus `effort`; the docs recommend "lower effort for routine tasks" and note that effort "trades latency and token cost for reasoning depth within each response."
- Dynamic workflows pick `opus`, `sonnet`, or `haiku` per subagent; the research system used a stronger lead with cheaper workers. That is the only "small model" pattern: cheap models as workers under a stronger orchestrator.
- "Building effective agents" explicitly advises that for most applications "optimizing single LLM calls with retrieval and in-context examples is usually enough", which is the strongest published statement in favour of a workflow baseline when the model is weak or the budget is tight.

Implication for the paper. Neither source provides a harness designed for small or open-weight models. Both assume a frontier model and treat weaker models as a cost knob (effort, worker tier). This supports the paper's framing: the published harness designs assume model-driven control is reliable, and the experiment tests whether that assumption holds for small models on a domain QA task.

---

## Part 4. What to borrow for a minimal, fair ReAct baseline in a RAG setting

Goal: an agent baseline that is faithful to how production harnesses work, uses the same retriever and corpus as the routing pipeline, and does not hand the agent extra advantages (or handicaps) that would confound the comparison.

### 4.1 Tool set shape

Borrow:

- Few tools, each a complete workflow, not an API wrapper (Writing tools for agents: "a few thoughtful tools targeting specific high-impact workflows"). For drug QA: a `search_drugs(query, top_k)` returning short hits with human-readable identifiers (drug name, section name, snippet) rather than internal ids; a `get_section(drug, section)` that returns one section of a monograph; optionally `lookup_interaction(drug_a, drug_b)` if the corpus has an interaction table. Three tools at most.
- Responses-API or Anthropic function shape: `name`, one-sentence `description`, JSON-schema `parameters` with per-parameter descriptions and `required`, `additionalProperties: false`, `strict: false` (Codex `exec_command` declaration).
- Parameter names that cannot be confused (`drug_name` not `name`; `section` with an enum of allowed section names, which is the "poka-yoke" rule).
- Tool results in plain text or Markdown, head-and-tail truncated with an explicit marker and the original size, exactly as Codex's `Warning: truncated output (original token count: N)` header. Errors returned as tool output text with an actionable message ("No drug named X; closest matches: ...").
- `response_format: concise | detailed` on `get_section` if monograph sections are long, mirroring the Slack example.

Leave out: shell, file tools, MCP, tool search, deferred loading, namespaces, output schemas on tools.

### 4.2 Stop rules

Borrow:

- The universal stop rule: the loop ends when a model response contains no tool calls (Codex `needs_follow_up == false`, Claude SDK "until it produces a response with no tool calls"). No explicit "finish" tool is needed; the final assistant message is the answer. This keeps the agent interface identical to the pipeline's final generation step.
- A hard step cap, which Codex lacks but the Claude SDK recommends ("Setting a budget is a good default for production agents"). Count tool-use rounds, not model calls; a reasonable cap for a 2-3 tool RAG task is 6 to 8 rounds. On hitting the cap, make one final model call with tools disabled and an injected user-role note ("You have used all retrieval steps; answer now from what you have"), so the agent still produces a graded answer instead of an error. Report `error_max_turns`-style outcomes separately.
- A duplicate-call guard for small models: if the same tool and arguments are requested twice, return the previous result with a one-line note rather than re-executing. Neither harness does this explicitly, but both rely on the model noticing; small models often do not, so this is a fairness-preserving mitigation that should be documented as such.

### 4.3 Step and token budgets

Borrow:

- Step cap as above. Also cap total tokens per question (input plus output across all calls) and record it, because both Anthropic and Codex treat tokens as the primary budget (Codex `RolloutBudgetConfig`, SDK `max_budget_usd`).
- Reasoning effort fixed at one level for both systems (Codex `model_reasoning_effort`, SDK `effort`). Report it.
- Retries: 5 attempts with exponential backoff `base * 2^(n-1)` with 0.9-1.1 jitter on transport, rate-limit, 5xx, and timeout errors (Codex defaults). Do not retry invalid-request or context-length errors. Treat a malformed tool call (bad JSON, unknown tool) as a tool error returned to the model, not as a crash, and count it as a round.

### 4.4 Output-size limits

Borrow:

- A per-tool-result cap in tokens, enforced by the harness, not by the tool. Codex's fallback is 10,000 bytes (about 2,500 tokens) per result; Claude Code's is 25,000 tokens. For small models with 8k-32k windows, 1,000-2,000 tokens per result is proportionate. Use the same cap for the chunks the routing pipeline passes to the generator, so both systems see the same amount of evidence per retrieval.
- Head-and-tail truncation with a visible marker and the original size, so the model knows it is looking at a partial result.
- A fixed `top_k` on search with a short snippet per hit (ids, names, one-line snippet), following "return only high signal information" and "many small and targeted searches instead of a single, broad search."

### 4.5 Prompt patterns

Borrow from the Codex prompts, adapted to QA:

- The persistence and no-guessing clause: "keep going until the query [...] is completely resolved [...] Do NOT guess or make up an answer." For drug QA, rephrase as: use the tools to find the relevant monograph text before answering; if the corpus does not contain the answer, say so.
- The planning threshold: no plan tool, but the equivalent instruction "Do not use plans for simple or single-step queries that you can just do or answer immediately" becomes "Most questions need one or two retrievals."
- The "start wide, then narrow" search strategy from the multi-agent post: first a broad `search_drugs`, then `get_section` for the specific section.
- A short final-answer format spec (Codex: "no more than 10 lines" default, headers only when they help). Match the pipeline's answer format exactly so the grader sees the same shape.
- Right-altitude rule from context engineering: a few canonical examples of good tool sequences rather than a long rule list; the Codex prompt embeds three good and three bad plan examples.
- Keep the system prompt short for a small model; Claude's best practices warn that bloated instructions get ignored. The Codex "codex" prompts (80 lines) are the better template than the 300-line GPT-5.x prompts.

### 4.6 Context handling

Borrow:

- Resend the full history each call (both harnesses). With a step cap of 6-8 and result caps of about 1,500 tokens, the context stays under roughly 15k tokens, so no summarisation compaction is needed. State this explicitly in the paper.
- If a run approaches the window, use tool-result clearing (keep the last two results in full, replace older ones with a one-line stub) rather than LLM summarisation, following "one of the safest lightest touch forms of compaction" and Claude Code's "clears older tool outputs first, then summarizes".

### 4.7 Parallel tool calls

Decision: allow the model to emit several calls in one response and execute read-only tools concurrently (all RAG tools are read-only), recording results in emission order (Codex `FuturesOrdered`). Count one round regardless of how many calls it contains, as the Claude SDK does. If the target small model does not emit parallel calls reliably, keep the capability but do not prompt for it; Codex's orchestrator template commented out the parallelism instruction, which shows it is optional.

### 4.8 What to leave out, and why

- Sandboxing, approval policies, permission modes, hooks: safety for side-effecting tools; the RAG tools are read-only.
- The `update_plan` tool and plan mode: Codex itself skips planning for "the easiest 25%" of tasks and single-step queries; a drug question is one.
- Summarising compaction and token-budget windows: unnecessary under the step cap, and adding them would introduce a second LLM call whose quality depends on the small model.
- Sub-agents, orchestrator-workers, dynamic workflows, tournaments: these are a different experimental condition (multi-agent) and cost about 15x tokens per the research-system post.
- Streaming, websockets, prompt caching, transport fallback: engineering concerns that do not change what the model sees.
- Persistent or proactive modes, memory, AGENTS.md/CLAUDE.md injection, skills, MCP, tool search.
- Preamble narration ("Before making tool calls, send a brief preamble"): it spends output tokens and was removed from the GPT-5.2 prompt; for a small model it only adds noise to grading.
- Any citation syntax the model must emit; instead have tool results carry the drug and section name so the final answer can reference them in plain text.

### 4.9 Fairness checklist for the comparison

- Same model, same effort level, same temperature, same corpus, same retriever and `top_k`, same per-chunk token cap, same final-answer format, same grader.
- Record per question: number of model calls, number of tool rounds, total tokens, wall time, whether the step cap was hit, whether any tool call was malformed.
- Report agent failures by category (malformed call, step cap, duplicate-call guard triggered, context overflow) since "compounding errors" is the trade-off the literature predicts.
- Run the agent with and without the duplicate-call guard and the forced final answer if budget allows, to show how much of the gap is harness mitigation versus model capability.

---

## Part 5. Citable sources for related work (workflows vs agents, harness design)

Primary (vendor engineering posts and docs):

1. Erik S., Barry Zhang. "Building effective agents." Anthropic Engineering, Dec 19, 2024. https://www.anthropic.com/engineering/building-effective-agents. Definitions of workflow vs agent; routing, prompt chaining, orchestrator-workers, evaluator-optimizer, autonomous agent; "simplest solution possible".
2. Ken Aizawa. "Writing tools for agents." Anthropic Engineering, Sep 11, 2025. https://www.anthropic.com/engineering/writing-tools-for-agents. Tool design rules, 25,000-token tool-result cap in Claude Code, concise/detailed response formats.
3. "Effective context engineering for AI agents." Anthropic Engineering, Sep 29, 2025. https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents. Context rot, attention budget, just-in-time retrieval, compaction, note-taking, sub-agents.
4. "Building agents with the Claude Agent SDK." Anthropic, Sep 29, 2025. https://claude.com/blog/building-agents-with-the-claude-agent-sdk (originally anthropic.com/engineering/building-agents-with-the-claude-agent-sdk). Gather context, take action, verify work; agentic vs semantic search.
5. "How we built our multi-agent research system." Anthropic Engineering, Jun 13, 2025. https://www.anthropic.com/engineering/multi-agent-research-system. Orchestrator-worker, 90.2 percent gain, 15x tokens, LLM-as-judge rubric.
6. "Effective harnesses for long-running agents." Anthropic Engineering, Nov 26, 2025. https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents. Initializer and coding agents, feature list, one feature at a time.
7. Thariq Shihipar, Sid Bidasaria. "A harness for every task: dynamic workflows in Claude Code." Claude blog, Jun 2, 2026. https://claude.dev/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code/. Static vs dynamic harness, agentic laziness, goal drift, coordination cost.
8. Delba de Oliveira, Michael Segner. "Loop engineering: getting started with loops." Claude blog, Jun 30, 2026. https://claude.com/blog/getting-started-with-loops. Loop as cycles until a stop condition; goal-based loops with evaluator and max turns.
9. Anthropic. "How the agent loop works." Claude Agent SDK documentation, accessed Oct 14, 2026. https://code.claude.com/docs/en/agent-sdk/agent-loop. Turn definition, stop on no tool calls, `max_turns`, `max_budget_usd`, read-only parallelism, compaction.
10. Anthropic. "How Claude Code works." Claude Code documentation, accessed Oct 14, 2026. https://code.claude.com/docs/en/how-claude-code-works. Three-phase loop, definition of "agentic harness", tool-result clearing before summarisation.
11. Anthropic. "Best practices for Claude Code." Claude Code documentation, accessed Oct 14, 2026. https://code.claude.com/docs/en/best-practices. Verification closes the loop, CLAUDE.md brevity, context management.
12. OpenAI. `openai/codex` repository, commit 95273b84 (Oct 14, 2026). https://github.com/openai/codex. Files: `codex-rs/core/src/session/turn.rs`, `codex-rs/core/src/tools/parallel.rs`, `codex-rs/core/src/compact.rs`, `codex-rs/prompts/templates/compact/prompt.md`, `codex-rs/core/gpt_5_2_prompt.md`, `codex-rs/model-provider-info/src/lib.rs`, `codex-rs/ollama/src/lib.rs`. License: Apache-2.0 (`LICENSE` at repo root; verify before quoting prompts at length).

Academic anchors the paper will likely pair these with (not fetched here, listed for completeness): Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models" (ICLR 2023); Schick et al., "Toolformer" (2023); Lewis et al., "Retrieval-Augmented Generation" (NeurIPS 2020); Asai et al., "Self-RAG" (ICLR 2024); Jeong et al., "Adaptive-RAG" (NAACL 2024) for query-complexity routing.

---

## Appendix A. Codex file index with line anchors

- `codex-rs/core/src/session/turn.rs`
  - 153-165: loop contract doc comment
  - 166: `run_turn`
  - 456-520: pending input drain, step context capture
  - 560-640: post-sampling token status, `needs_follow_up = model_needs_follow_up || has_pending_input`
  - 672-715: mid-turn compaction rollover
  - 718-800: stop hooks, post-turn compaction, `break`
  - 1668-1700: `build_prompt` (`parallel_tool_calls: true`)
  - 1707-1835: `run_sampling_request` (retry wrapper)
  - 2565-2595: `drain_in_flight`
  - 2618-3130: `try_run_sampling_request` (stream consumer; `in_flight.push_back(tool_future)` at 2905; `end_turn` at 3112)
- `codex-rs/core/src/stream_events_utils.rs` 330-430: `handle_output_item_done` tool-call vs message branches
- `codex-rs/core/src/tools/router.rs` 86-100 (`ToolRouter`), 244-249 (`tool_supports_parallel`), 262-310 (`build_tool_call`)
- `codex-rs/core/src/tools/parallel.rs` 206-236 (read/write lock gate), 100-125 (failure to `FunctionCallOutput`)
- `codex-rs/core/src/tools/handlers/shell_spec.rs` 23-114: `exec_command` declaration
- `codex-rs/core/src/tools/context.rs` 482-489 (`model_output_policy`), 552-575 (`response_text` budget loop)
- `codex-rs/core/src/tools/mod.rs` 88-124: `format_exec_output_for_model`, `format_exec_output_str`
- `codex-rs/utils/output-truncation/src/lib.rs` 19-40: allowance, `formatted_truncate_text`
- `codex-rs/utils/string/src/truncate.rs` 6: `APPROX_BYTES_PER_TOKEN = 4`
- `codex-rs/tools/src/tool_spec.rs` 19-56; `codex-rs/tools/src/responses_api.rs` 14-43
- `codex-rs/core/src/compact.rs` 63 (`COMPACT_USER_MESSAGE_MAX_TOKENS`), 287-450 (compaction turn), 592-640 (initial context re-insertion)
- `codex-rs/core/src/session/context_window.rs` 56-130: thresholds
- `codex-rs/protocol/src/openai_models.rs` 62-75 (`ReasoningEffort`), 408-471 (`ModelInfo`), 518-540 (`resolved_context_window`, `auto_compact_token_limit`)
- `codex-rs/models-manager/src/model_info.rs` 19-56 (config overrides), 100-150 (fallback model)
- `codex-rs/core/src/config/mod.rs` 225 (`DEFAULT_ASYNC_COMPACTION_THRESHOLD_PERCENT = 65`), 651-665 (compaction config fields), 1341-1346 (`RolloutBudgetConfig`)
- `codex-rs/core/src/responses_retry.rs` 23-24 (connection retry delays), 59-180 (`handle_response_stream_error`)
- `codex-rs/protocol/src/error.rs` 410-456: `retry_delay`
- `codex-rs/codex-client/src/retry.rs` 43-51: `backoff`
- `codex-rs/model-provider-info/src/lib.rs` 66-75 (retry defaults), 103-131 (`WireApi`, chat removed), 134-200 (`ModelProviderInfo`)
- `codex-rs/ollama/src/lib.rs` 16-60; `codex-rs/lmstudio/src/lib.rs` 7
- `codex-rs/core/src/client.rs` 621-625: `reasoning_effort_override_enabled`
- `codex-rs/core/src/rollout_budget.rs` 1-121
- Prompts: `codex-rs/core/gpt_5_2_prompt.md`, `gpt_5_1_prompt.md` (34-62 Responsiveness), `gpt-5.2-codex_prompt.md`, `gpt_5_codex_prompt.md`, `codex-rs/models-manager/prompt.md`, `codex-rs/prompts/templates/compact/prompt.md`, `summary_prefix.md`, `persistent_mode.md`, `codex-rs/core/templates/agents/orchestrator.md`

## Appendix B. Terminology map

| Concept | Codex | Claude Agent SDK | Suggested paper term |
| --- | --- | --- | --- |
| One model call | sampling request | (model response within a turn) | model call |
| Model call plus its tool executions | one iteration of `run_turn` | turn | step (tool round) |
| User prompt to final answer | turn | session / query | episode |
| Loop ends | `needs_follow_up == false` | response with no tool calls | termination by answer |
| Step cap | none | `max_turns` (default none) | step cap (set to N) |
| Token cap | `RolloutBudgetConfig.limit_tokens` | `max_budget_usd` | token budget |
| Tool output cap | `truncation_policy` (10,000 bytes fallback) | 25,000 tokens | result cap |
| Parallel calls | `parallel_tool_calls: true` plus per-tool read/write lock | read-only tools concurrent | parallel read-only calls |
| Context reduction | summarising compaction at 90% of 95% window | tool-result clearing then summary | not used (step cap keeps context small) |
