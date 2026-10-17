# Paper v2 phase 2: ReAct agent — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A minimal, fair ReAct agent runs on the same corpus, retriever, reranker, evidence budget, answer format and judge as the graph-routing pipeline, so matrix C of the paper (graph routing versus ReAct on Qwen3.5-9B, Gemini 3.8 Flash and Claude Opus 5.5) differs only in who controls the loop.

**Architecture:** The LLM port gains one call, `tool_call`, implemented on the OpenAI adapter with native tool calling. A second LangGraph graph, `react_graph`, reuses the pipeline's guard node, then loops `agent` (one tool-calling model call) and `tools` (runs `search_corpus` calls in parallel) until the model answers without a tool call or the round cap forces one last call without tools. The tool's result text, evidence numbering, budget and duplicate rules are pure domain code (`domain/agent/react.py`); the answer is post-processed with the pipeline's `CitationSanitizer` and the same answer modes. The e2e harness gets a `react` configuration that picks this graph, records per-turn ReAct statistics, and reports a failure table.

**Tech Stack:** Python 3.12, pydantic 2, LangGraph, OpenAI SDK chat completions with `tools` and `parallel_tool_calls`, typer, pytest, uv workspace.

**Spec:** `docs/superpowers/specs/2026-10-14-paper-v2-design.md` — §2.4 (ReAct agent: port, graph, tool, stop rule, budgets, prompt, post-processing, records), §4.C (matrix C: three models, fixed factors, reports), §2.5 (latency and cost, phase 0), §5 (statistics). Research notes: `docs/research/paper-v2/02-codex-claude-agent-loop.md` Part 4 (minimal fair ReAct baseline), `docs/research/paper-v2/01-deepseek-harness.md` §1–§2.

Builds on branch `feat/paper-v2-phase-1` (phase 0 measurement and phase 1 decision model): per-step latency, pricing, `--pipeline-option`, `e2e compare --config-b`, `--latency-run`, `e2e embed-server`, the chosen agent retrieval pair `<EMB>`/`<RER>` (phase 0 Task 11 Step 0).

## Global Constraints

- One tool, read-only, parallel-callable: `search_corpus(query: str)` = `RetrievalService.search` with the same hybrid RRF and reranker, at most 5 chunks per call (`rerank.top_n = 5`), chunk text exactly as the pipeline reads it (spec §2.4, §3.0c). No neighbour-reading tool.
- Stop rule: the loop ends when a model response has no tool call; at most 6 tool rounds (one round = one model response, however many calls it holds); after the 6th round one last call without tools carries the note "đã hết lượt tra cứu, trả lời từ những gì đã có" (spec §2.4).
- Same `max_llm_calls`, `max_tokens`, `max_evidence_chars` (60,000) and deadline as the pipeline (`BudgetLimits`). Evidence budget counts the chunk text placed in messages; a chunk already shown is shown again only as its id; a result that would overflow the budget is replaced by "hết ngân sách bằng chứng, trả lời từ những gì đã có" and counted (spec §2.4).
- A repeated (tool, arguments) call returns the earlier result plus a one-line note; a tool error returns `Error: ...` as the tool's text and never raises (spec §2.4).
- The prompt is short, Vietnamese, Codex style: pharmacist role, the pipeline's citation rule, "dùng tool để tìm đúng mục trước khi trả lời, không đoán", "phần lớn câu chỉ cần một đến hai lần tìm", "đi rộng rồi thu hẹp". No plan tool, no compaction, no subagents (spec §2.4).
- Post-processing reuses `CitationSanitizer` and the pipeline's answer modes (spec §2.4).
- Matrix C fixes tool, retriever, reranker, evidence level, answer format, reasoning effort, temperature and judge across graph routing and ReAct; interfaces are structured output (pipeline) and native tool calling (ReAct) and the paper names them (spec §4.C).
- ReAct never runs on the decision model: every step is an LLM call (spec §2.4).
- Repo rules (`AGENTS.md`): no `# noqa`, no `# type: ignore`, no `ignore_imports`; tests mirror `src/` under `tests/`; backend import-linter contracts green (`uv run lint-imports` in backend; application must not import `openai`).
- Commits carry no Co-Authored-By or other trailer. Code changes in a worktree branched from `feat/paper-v2-phase-1`; long runs in tmux, logs under `pharma-lab/data/work/logs-p2/`.

## Review Focus

1. A model that returns malformed tool arguments (not JSON, missing `query`, an unknown tool name) gets `Error: ...` as that call's tool message and the loop continues; the round still counts and the turn's `malformed_calls` grows. Test: `test_malformed_tool_call_becomes_a_tool_error` (Task 4).
2. A model that never stops calling tools ends after exactly 6 rounds plus one final call without tools, and the answer is marked partial with `round_cap_hit`. Test: `test_round_cap_forces_one_final_call_without_tools` (Task 4).
3. Two calls with the same normalized query in one turn (same round or later) search once; the second gets the earlier result text plus the note and `duplicate_calls` grows. Test: `test_duplicate_query_reuses_the_first_result` (Task 3, Task 4).
4. Citation numbers in the final answer that point to no shown chunk are dropped by `CitationSanitizer`; cited chunks map back to the chunks the model saw, numbered in first-shown order across rounds. Test: `test_answer_citations_map_to_shown_chunks` (Task 4).
5. A provider that answers a tool-calling request with plain text and no tool calls on the first response (it decided not to search) yields an answer in `NO_RETRIEVAL` mode with no evidence and no crash; a search that returns no hit yields `ABSTAIN` mode. Test: `test_answer_without_search_is_no_retrieval` (Task 4).

---

### Task 1: Tool-calling messages and the port

**Files:**
- Modify: `backend/src/pharma_agent/domain/llm/models.py` (`ChatRole.TOOL`, `ChatMessage.tool_calls`, `ChatMessage.tool_call_id`, new `ToolSpec`, `ToolCall`, `ToolTurn`, `LlmRole.AGENT`), `backend/src/pharma_agent/domain/llm/port.py` (`LlmPort.tool_call`)
- Modify: `backend/tests/fakes.py` (`FakeLlm.tool_turns`, `FakeLlm.tool_call`), `pharma-lab/tests/e2e/factories.py` (`ScriptedLlm.tool_call`), `pharma-lab/src/pharma_lab/e2e/recording_llm.py` (`RecordingLlm.tool_call`)
- Test: `backend/tests/domain/test_llm_models.py`, `pharma-lab/tests/e2e/test_executor.py`

**Interfaces:**
- Produces:

```python
class ChatRole(StrEnum):
    SYSTEM = "system"; USER = "user"; ASSISTANT = "assistant"; TOOL = "tool"

class ToolCall(BaseModel):          # frozen
    id: str
    name: str
    arguments: str                  # the raw JSON text the model produced; parsed by the caller

class ChatMessage(BaseModel):       # frozen
    role: ChatRole
    content: str
    tool_calls: tuple[ToolCall, ...] = ()   # assistant messages that called tools
    tool_call_id: str | None = None         # tool messages answer one call

class ToolSpec(BaseModel):          # frozen
    name: str
    description: str
    parameters: dict[str, object]   # JSON schema of the arguments

class ToolTurn(BaseModel):          # frozen
    text: str
    tool_calls: tuple[ToolCall, ...]
    finish_reason: str

class LlmRole(StrEnum): ... AGENT = "agent"   # the ReAct loop's model calls

class LlmPort(Protocol):
    async def tool_call(
        self, role: LlmRole, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]
    ) -> tuple[ToolTurn, LlmUsage]:
        """One model call that may request tools; empty `tools` forbids tool calls.
        Raises LlmError."""
```

- `FakeLlm.script_tool_turns(*turns: ToolTurn | Exception)`; `FakeLlm.tool_call` pops the next turn, records `(LlmRole, messages, tools)` in `self.tool_calls_seen`, returns `LlmUsage(prompt_tokens=200, completion_tokens=20)`. Same shape on pharma-lab `ScriptedLlm` (`script_tool_turns`).
- `RecordingLlm.tool_call` records usage and seconds under the role like `structured`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/domain/test_llm_models.py`:

```python
def test_tool_messages_carry_calls_and_answers() -> None:
    call = ToolCall(
        id="c1", name="search_corpus", arguments='{"query": "paracetamol liều"}'
    )
    asked = ChatMessage(role=ChatRole.ASSISTANT, content="", tool_calls=(call,))
    answered = ChatMessage(role=ChatRole.TOOL, content="[1] ...", tool_call_id="c1")
    assert asked.tool_calls[0].name == "search_corpus"
    assert answered.tool_call_id == "c1"
    assert ChatMessage(role=ChatRole.USER, content="x").tool_calls == ()


def test_llm_roles_cover_every_pipeline_step() -> None:
    assert {role.value for role in LlmRole} == {
        "guardrail",
        "rephrase",
        "judge",
        "refine",
        "answer",
        "summarizer",
        "agent",
    }
```

(the second replaces the existing test of the same name.)

`pharma-lab/tests/e2e/test_executor.py`:

```python
def test_recording_llm_records_tool_calls() -> None:
    llm = ScriptedLlm()
    llm.script_tool_turns(ToolTurn(text="xong", tool_calls=(), finish_reason="stop"))
    recorder = RecordingLlm(llm)
    turn, _ = asyncio.run(recorder.tool_call(LlmRole.AGENT, [], []))
    assert turn.text == "xong"
    assert recorder.usage_by_role()["agent"].calls == 1
```

- [ ] **Step 2: Run them, watch them fail**

Run: `cd backend && uv run pytest tests/domain/test_llm_models.py -q`; `cd pharma-lab && uv run pytest tests/e2e/test_executor.py -q -k tool_calls`
Expected: FAIL — `cannot import name 'ToolCall'`; role set lacks "agent".

- [ ] **Step 3: Implement** the models and port exactly as in Interfaces; `FakeLlm`/`ScriptedLlm` as described; `RecordingLlm.tool_call`:

```python
    async def tool_call(
        self, role: LlmRole, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]
    ) -> tuple[ToolTurn, LlmUsage]:
        started = time.perf_counter()
        turn, usage = await self._inner.tool_call(role, messages, tools)
        self._record(role, usage, started)
        return turn, usage
```

`LlmRole.AGENT` is a new role, so `LlmSettings.resolve` serves it from the default endpoint; `OpenAiLlmAdapter` resolves every role at construction, which keeps working. Update the env examples (`backend/.env.example`, the role list comment) and `pharma_lab/e2e/model_server.env_lines` needs no change (it loops over `LlmRole`). Any test asserting the exact role set or role_models keys of run.json gains "agent".

- [ ] **Step 4: Run the tests** — backend gates (`uv run ruff check src tests && uv run ruff format --check src tests && uv run pyrefly check --min-severity warn && uv run lint-imports && uv run pytest -q`) and pharma-lab gates. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(llm): tool-calling messages, the tool_call port and the agent role"
```

---

### Task 2: `tool_call` on the OpenAI adapter

**Files:**
- Modify: `backend/src/pharma_agent/infrastructure/llm/openai_adapter.py` (`tool_call`, `_to_openai` for tool messages)
- Test: `backend/tests/infrastructure/test_openai_adapter.py`

**Interfaces:**
- Consumes: Task 1 types.
- Produces: `OpenAiLlmAdapter.tool_call(role, messages, tools)` → `chat.completions.create(model=..., messages=..., tools=[{"type": "function", "function": {"name", "description", "parameters"}}], parallel_tool_calls=True, **_options(endpoint))` when `tools` is non-empty, and without `tools`/`parallel_tool_calls` when empty; maps `choices[0].message.content` (None → ""), `.tool_calls` (each `id`, `function.name`, `function.arguments`), `finish_reason`, and `usage` through `_usage`. OpenAI errors → `LlmError(f"{role.value}: {exc}")`.

- [ ] **Step 1: Write the failing tests** (the file's `FakeCompletions.create` returns a stream; add a non-stream branch: when `kwargs.get("stream")` is falsy, return `self.tool_response`, a `SimpleNamespace` the test sets):

```python
async def test_tool_call_sends_tools_and_maps_calls() -> None:
    adapter, created = make_adapter()
    spec = ToolSpec(
        name="search_corpus",
        description="Tìm",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    await adapter.structured(
        LlmRole.GUARDRAIL, [user("warm")], Verdict
    )  # creates the default client
    client = created[(None, "sk-cloud")]
    client.completions.tool_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="c1",
                            function=SimpleNamespace(
                                name="search_corpus", arguments='{"query": "liều"}'
                            ),
                        )
                    ],
                ),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=30, completion_tokens=5),
    )
    turn, usage = await adapter.tool_call(LlmRole.AGENT, [user("liều?")], [spec])
    kwargs = client.completions.create_kwargs
    assert kwargs["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "search_corpus",
                "description": "Tìm",
                "parameters": spec.parameters,
            },
        }
    ]
    assert kwargs["parallel_tool_calls"] is True
    assert turn.text == "" and turn.finish_reason == "tool_calls"
    assert turn.tool_calls == (
        ToolCall(id="c1", name="search_corpus", arguments='{"query": "liều"}'),
    )
    assert usage.prompt_tokens == 30


async def test_tool_call_without_tools_sends_none_and_tool_messages_serialize() -> None:
    adapter, created = make_adapter()
    await adapter.structured(LlmRole.GUARDRAIL, [user("warm")], Verdict)
    client = created[(None, "sk-cloud")]
    client.completions.tool_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content="Đáp [1].", tool_calls=None),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=3),
    )
    call = ToolCall(id="c1", name="search_corpus", arguments='{"query": "x"}')
    messages = [
        user("hỏi"),
        ChatMessage(role=ChatRole.ASSISTANT, content="", tool_calls=(call,)),
        ChatMessage(role=ChatRole.TOOL, content="[1] tài liệu", tool_call_id="c1"),
    ]
    turn, _ = await adapter.tool_call(LlmRole.AGENT, messages, [])
    kwargs = client.completions.create_kwargs
    assert "tools" not in kwargs and "parallel_tool_calls" not in kwargs
    assert kwargs["messages"][1] == {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "search_corpus", "arguments": '{"query": "x"}'},
            }
        ],
    }
    assert kwargs["messages"][2] == {
        "role": "tool",
        "content": "[1] tài liệu",
        "tool_call_id": "c1",
    }
    assert turn.text == "Đáp [1]." and turn.tool_calls == ()
```

- [ ] **Step 2: Run them, watch them fail** — `uv run pytest tests/infrastructure/test_openai_adapter.py -q -k tool_call`; Expected: FAIL (`'OpenAiLlmAdapter' object has no attribute 'tool_call'`).

- [ ] **Step 3: Implement**

```python
async def tool_call(
    self, role: LlmRole, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]
) -> tuple[ToolTurn, LlmUsage]:
    client, endpoint = self._client(role)
    request: dict[str, Any] = {
        "model": endpoint.model,
        "messages": _to_openai(messages),
        **_options(endpoint),
    }
    if tools:
        request["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]
        request["parallel_tool_calls"] = True
    try:
        completion = await client.chat.completions.create(**request)
    except OpenAIError as exc:
        raise LlmError(f"{role.value}: {exc}") from exc
    choice = completion.choices[0]
    calls = tuple(
        ToolCall(
            id=str(call.id),
            name=str(call.function.name),
            arguments=str(call.function.arguments or ""),
        )
        for call in (choice.message.tool_calls or [])
    )
    return ToolTurn(
        text=choice.message.content or "",
        tool_calls=calls,
        finish_reason=str(choice.finish_reason or ""),
    ), _usage(completion.usage)
```

`_to_openai` returns `list[dict[str, Any]]`: assistant messages with tool calls carry `"tool_calls": [{"id", "type": "function", "function": {"name", "arguments"}}]`; tool messages carry `"tool_call_id"`; other messages unchanged (`{"role", "content"}` only, so existing tests stay byte-identical).

- [ ] **Step 4: Run the tests** — backend gates. Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(llm): native tool calling on the OpenAI-compatible adapter"`

---

### Task 3: The ReAct domain: tool spec, prompt, result text, budget and duplicate rules

**Files:**
- Create: `backend/src/pharma_agent/domain/agent/react.py`
- Test: `backend/tests/domain/test_react.py`

**Interfaces:**
- Consumes: `ToolSpec`, `ToolCall`, `ChatMessage` (Task 1); `Evidence`, `Hit` (domain/retrieval); `ConversationContext`; `ASSISTANT_ROLE` and the citation rules in `domain/agent/prompts.py` (import the rules text; make `_CITATION_RULES` public as `CITATION_RULES` there and keep its text unchanged).
- Produces:

```python
SEARCH_TOOL: ToolSpec        # name "search_corpus", one required string parameter "query", additionalProperties false
MAX_TOOL_ROUNDS = 6
ROUND_CAP_NOTE = "Đã hết lượt tra cứu, trả lời từ những gì đã có."
BUDGET_NOTE = "Hết ngân sách bằng chứng, trả lời từ những gì đã có."
DUPLICATE_NOTE = "(Truy vấn này đã tìm ở trên; kết quả như cũ.)"
REACT_SYSTEM: str            # Vietnamese, short (see Step 3)

def react_messages(context: ConversationContext, question: str) -> list[ChatMessage]
def parse_query(call: ToolCall) -> str               # raises ValueError with a short reason
def normalize_query(text: str) -> str                 # lower-case, collapsed whitespace

@dataclass
class Shown:                                          # per-turn state, owned by the graph state
    numbers: dict[UUID, int]                          # chunk_version_id → citation number, in first-shown order
    chars: int                                        # chunk text placed in messages so far
    results: dict[str, str]                           # normalized query → result text

def render_result(hits: Sequence[Hit], shown: Shown, *, max_chars: int) -> tuple[str, list[Hit], bool]
    """Text of one search_corpus result: `[n] <context_header> (<page>):\n<chunk_text>` per new hit,
    `[n] (đã hiển thị ở trên)` for a hit shown before, `Không tìm thấy tài liệu phù hợp.` for none.
    Numbers continue across the turn. A new hit whose text would pass max_chars is not shown and
    the result ends with BUDGET_NOTE. Returns (text, newly shown hits, budget_hit)."""
```

- [ ] **Step 1: Write the failing tests**

```python
def hit(label: str, text: str = "Liều 500 mg.") -> Hit:
    return make_hit(label, text=text)  # tests/domain/factories.py; check its signature


def test_search_tool_schema_has_one_required_query() -> None:
    assert SEARCH_TOOL.name == "search_corpus"
    assert SEARCH_TOOL.parameters["required"] == ["query"]
    assert SEARCH_TOOL.parameters["additionalProperties"] is False


def test_render_numbers_new_hits_and_refers_to_shown_ones() -> None:
    shown = Shown(numbers={}, chars=0, results={})
    first, new, hit_budget = render_result(
        [hit("a"), hit("b")], shown, max_chars=60_000
    )
    assert first.startswith("[1] ") and "\n\n[2] " in first and not hit_budget
    assert [h.chunk_version_id for h in new] == [chunk_uuid("a"), chunk_uuid("b")]
    again, new_again, _ = render_result([hit("b"), hit("c")], shown, max_chars=60_000)
    assert "[2] (đã hiển thị ở trên)" in again and "[3] " in again
    assert [h.chunk_version_id for h in new_again] == [chunk_uuid("c")]
    assert shown.chars == 3 * len("Liều 500 mg.")


def test_render_stops_at_the_evidence_budget() -> None:
    shown = Shown(numbers={}, chars=0, results={})
    text, new, budget_hit = render_result(
        [hit("a", "x" * 50), hit("b", "y" * 50)], shown, max_chars=80
    )
    assert budget_hit and text.endswith(BUDGET_NOTE)
    assert len(new) == 1 and shown.chars == 50


def test_render_says_when_nothing_was_found() -> None:
    text, new, budget_hit = render_result(
        [], Shown(numbers={}, chars=0, results={}), max_chars=60_000
    )
    assert text == "Không tìm thấy tài liệu phù hợp." and new == [] and not budget_hit


def test_parse_query_rejects_malformed_arguments() -> None:
    assert (
        parse_query(
            ToolCall(
                id="1", name="search_corpus", arguments='{"query": " liều  dùng "}'
            )
        )
        == "liều  dùng"
    )
    for arguments, reason in (
        ("not json", "JSON"),
        ('{"q": "x"}', "query"),
        ('{"query": ""}', "query"),
    ):
        with pytest.raises(ValueError, match=reason):
            parse_query(ToolCall(id="1", name="search_corpus", arguments=arguments))
    with pytest.raises(ValueError, match="unknown tool"):
        parse_query(ToolCall(id="1", name="read_section", arguments='{"query": "x"}'))


def test_messages_put_history_before_the_question() -> None:
    context = ConversationContext(
        turns=[
            Turn(
                user_text="Paracetamol là gì?",
                assistant_text="Thuốc giảm đau.",
                status="completed",
            )
        ]
    )
    messages = react_messages(context, "Người lớn uống tối đa bao nhiêu?")
    assert [m.role for m in messages] == [
        ChatRole.SYSTEM,
        ChatRole.USER,
        ChatRole.ASSISTANT,
        ChatRole.USER,
    ]
    assert "search_corpus" in messages[0].content and "[n]" in messages[0].content
```

- [ ] **Step 2: Run them, watch them fail** — `uv run pytest tests/domain/test_react.py -q`; Expected: FAIL (module missing).

- [ ] **Step 3: Implement.** `REACT_SYSTEM`:

```python
REACT_SYSTEM = f"""{ASSISTANT_ROLE}
Bạn có một công cụ: search_corpus(query) tìm trong Dược thư Quốc gia và tờ hướng dẫn sử dụng thuốc, trả về tối đa 5 đoạn, mỗi đoạn có số [n].

Cách làm:
- Dùng công cụ để tìm đúng mục trước khi trả lời, không đoán.
- Phần lớn câu chỉ cần một đến hai lần tìm. Đi rộng rồi thu hẹp: tìm theo tên thuốc và ý hỏi, rồi tìm riêng phần còn thiếu.
- Câu chào hỏi hoặc hỏi về chính bạn thì trả lời ngắn, không cần tìm.
- Khi đã đủ, trả lời bằng tiếng Việt, thẳng vào câu hỏi.

{CITATION_RULES}"""
```

`CITATION_RULES` speaks of "phần Tài liệu"; the ReAct prompt's tool results are the documents, so add one line after it: "Ở đây Tài liệu là các đoạn công cụ trả về." `react_messages`: `[system(REACT_SYSTEM), *history as alternating user/assistant ChatMessages, user(question)]`; the conversation summary (if any) goes as a user message "Tóm tắt hội thoại trước: ..." before the turns, like `rephrase_messages`. `render_result` and `parse_query` as specified (parse with `json.loads`; a non-dict, a missing or blank `query` → `ValueError("query ...")`; name other than `search_corpus` → `ValueError("unknown tool <name>")`).

- [ ] **Step 4: Run the tests** — backend gates. Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(agent): ReAct tool, prompt and result rules as domain code"`

---

### Task 4: The ReAct graph

**Files:**
- Create: `backend/src/pharma_agent/application/chat/react_graph.py` (`build_react_graph`, `ReactTurnState`, nodes `agent_node`, `tools_node`, `finalize_node`, routing)
- Modify: `backend/src/pharma_agent/domain/agent/run.py` (`AgentRun.record_tool_round`, `AgentRun.record_tool_search`, `ReactStats`, `AgentRun.react: ReactStats | None`), `backend/src/pharma_agent/domain/agent/actions.py` (`ActionKind.AGENT`)
- Test: `backend/tests/application/test_react_graph.py`

**Interfaces:**
- Consumes: Tasks 1–3; `nodes.guard_node`, `nodes.answer_node` (for blocked and redirect verdicts), `nodes.fallback_node`; `RetrievalService.search`; `CitationSanitizer`, `citations_from`; `AnswerPlan`, `AnswerMode`; phase 0's search payload fields (`retrieval_seconds`, `rerank_seconds`, `rerank_scored`, `evidence`, `evidence_chars`).
- Produces:

```python
class ReactStats(BaseModel):
    rounds: int = 0                 # model responses that requested tools
    tool_calls: int = 0
    malformed_calls: int = 0
    duplicate_calls: int = 0
    round_cap_hit: bool = False
    budget_hits: int = 0            # results cut by the evidence budget
    answered_without_search: bool = False

class ReactTurnState(ChatTurnState):
    messages: list[ChatMessage] = []
    pending_calls: list[ToolCall] = []
    shown: Shown                    # Task 3 (pydantic-compatible: make Shown a pydantic model or arbitrary_types_allowed)
    final_text: str = ""

def build_react_graph() -> ChatGraph   # START → guard → (agent | answer) ; agent → (tools | finalize | fallback); tools → (agent | fallback); finalize → END; answer → END; fallback → END
```

`AgentRun.record_tool_search(query: Query, result: SearchResult, shown_hits, *, now)` merges hits into `run.evidence` **without** superseding (ReAct accumulates), increments `usage.search_rounds`, and logs `ActionKind.SEARCH` with the same payload keys as `record_search` (queries, hits, evidence list of the newly shown chunks with document/ordinal/sections, `evidence_chars` = total shown chars, retrieval/rerank seconds, rerank_scored/reused) so the e2e record's rounds, retrieval timing and rerank cost keep working. `AgentRun.record_tool_round(calls, *, now)` logs `ActionKind.AGENT` (outcome "tools" or "answer", payload: call names, raw arguments, malformed flags).

Behaviour:
- `agent_node`: if the guard did not allow processing → route to `answer` (pipeline answer node handles BLOCKED/REDIRECT). Otherwise one `deps.llm.tool_call(LlmRole.AGENT, state.messages or react_messages(...), [SEARCH_TOOL] if rounds < MAX_TOOL_ROUNDS and budget allows else [])`; when rounds reached the cap, append `user(ROUND_CAP_NOTE)` once and call with `[]`, setting `round_cap_hit`. Charge usage; on `BudgetExhausted` or when `run.calls_left < 2`, go to the final no-tool call (charge suppressed, like `answer_node`). On `LlmError` → fail the run (`ErrorCode.ANSWER_FAILED`) → fallback. A response with tool calls → append the assistant message (with its calls) to `messages`, put calls in `pending_calls`, `rounds += 1`, route `tools`. A response without tool calls → `final_text`, route `finalize`.
- `tools_node`: for every pending call, in order: `parse_query`; on ValueError → tool message `Error: <reason>`, `malformed_calls += 1`; a normalized query already in `shown.results` → earlier text + "\n" + DUPLICATE_NOTE, `duplicate_calls += 1`; otherwise search (`deps.retrieval.search([Query(text=q, origin=QueryOrigin.INITIAL if first search else REFINED)], rerank_query=q, scope=runtime.context.scope)`); a search error → `Error: tìm kiếm thất bại (<detail>)`. Independent searches run concurrently with `asyncio.gather`; results are rendered and appended in call order (render after gathering, so numbering follows call order). Each call's result becomes `ChatMessage(role=TOOL, content=text, tool_call_id=call.id)`; `tool_calls += len(calls)`; budget hits counted.
- `finalize_node`: plan = BLOCKED/REDIRECT never reach here; `NO_RETRIEVAL` when no search ran (`answered_without_search`), `ABSTAIN` when searches ran but no chunk was shown, else `GROUNDED` with `partial = round_cap_hit or budget_hits > 0`. Sanitize `final_text` with `CitationSanitizer(shown numbers)` (feed + flush), build `citations_from` with `numbered = [(n, evidence) for each shown chunk in number order]`, set `context_text` to the shown chunks rendered as `[n] <header> (<page>)\n<text>` (same shape as `EvidenceSet.context_view`), `run.submit_plan(plan)`, `run.complete()`. Emit the pipeline's progress events (phases searching/reading/answering, tokens once with the sanitized text, citations).
- `run.react = stats` is set at the end so the e2e record can read it.

- [ ] **Step 1: Write the failing tests** (`tests/application/test_react_graph.py`, using `FakeLlm` with scripted guard verdicts and tool turns, `FakeRetriever`, `build_deps`; a helper `run_react(llm, retriever, limits=None)` mirroring `test_chat_graph.run_turn` but with `build_react_graph()`):

```python
def call(cid: str, query: str) -> ToolCall:
    return ToolCall(
        id=cid, name="search_corpus", arguments=json.dumps({"query": query})
    )


async def test_one_search_then_answer_with_citation() -> None:
    llm = guard_only_llm()
    llm.script_tool_turns(
        ToolTurn(
            text="",
            tool_calls=(call("c1", "paracetamol liều người lớn"),),
            finish_reason="tool_calls",
        ),
        ToolTurn(text="Tối đa 4 g mỗi ngày [1].", tool_calls=(), finish_reason="stop"),
    )
    _, outcome = await run_react(llm, FakeRetriever([make_hit("c1", fusion=0.9)]))
    assert outcome.run.status is RunStatus.COMPLETED
    assert outcome.answer_text == "Tối đa 4 g mỗi ngày [1]."
    assert [c.index for c in outcome.citations] == [1]
    assert outcome.run.react.rounds == 1 and outcome.run.react.tool_calls == 1
    tool_message = llm.tool_calls_seen[1][1][-1]
    assert tool_message.role is ChatRole.TOOL and tool_message.content.startswith(
        "[1] "
    )


async def test_parallel_calls_count_one_round_and_number_in_call_order() -> None:
    ...
    # one ToolTurn with calls "a" and "b"; retriever returns different hits per query (FakeRetriever rounds); assert rounds == 1, tool_calls == 2, tool messages numbered [1].. then [k]..


async def test_duplicate_query_reuses_the_first_result() -> None:
    ...
    # round 1: call "paracetamol liều"; round 2: call "Paracetamol  liều"; answer; assert retriever searched once, duplicate_calls == 1, second tool message ends with DUPLICATE_NOTE


async def test_malformed_tool_call_becomes_a_tool_error() -> None:
    ...
    # ToolCall(arguments="not json") then a valid answer; assert the tool message starts with "Error:", malformed_calls == 1, rounds == 1, status COMPLETED


async def test_round_cap_forces_one_final_call_without_tools() -> None:
    ...
    # script 6 tool turns each with a fresh query + a 7th plain answer; assert the 7th call got tools == [] and its last user message is ROUND_CAP_NOTE; react.round_cap_hit; status PARTIAL


async def test_evidence_budget_cuts_results_and_marks_partial() -> None:
    ...
    # BudgetLimits(max_evidence_chars=60) with two 50-char hits; assert BUDGET_NOTE in the tool message, budget_hits == 1, status PARTIAL


async def test_answer_citations_map_to_shown_chunks() -> None:
    ...
    # answer "A [2] B [9]" after showing 2 chunks; answer_text keeps [2], drops [9]; citations == [2] mapped to the second shown chunk's chunk_version_id


async def test_answer_without_search_is_no_retrieval() -> None:
    ...
    # first tool turn is plain text; status COMPLETED, plan mode NO_RETRIEVAL, answered_without_search, no SEARCH action


async def test_search_with_no_hit_answers_in_abstain_mode() -> None: ...


async def test_blocked_guard_skips_the_agent() -> None:
    ...
    # LlmGuardVerdict(is_attack=True); assert no tool_call happened and status BLOCKED


async def test_agent_llm_error_falls_back() -> None:
    ...
    # script LlmError as the first tool turn; status ERROR, fallback text
```

Write every `...` test out in full in the test file (the comments state the setup and assertions).

- [ ] **Step 2: Run them, watch them fail** — `uv run pytest tests/application/test_react_graph.py -q`; Expected: FAIL (module missing).

- [ ] **Step 3: Implement** the graph, nodes and run methods as specified. Keep `react_graph.py` focused (graph wiring + nodes); move rendering of the context view helper into `domain/agent/react.py` if it grows. Nodes use the `guarded` decorator from `nodes.py` (`ErrorCode.ANSWER_FAILED` for the agent, `ErrorCode.SEARCH_FAILED` for tools).

- [ ] **Step 4: Run the tests** — backend gates incl. `uv run lint-imports` (application must not import openai). Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(chat): ReAct graph with one search tool, round cap, evidence budget and duplicate guard"`

---

### Task 5: The `react` configuration in the e2e harness

**Files:**
- Modify: `pharma-lab/src/pharma_lab/e2e/configs.py` (`E2EConfig.REACT = "react"`, `graph_for(config)`), `pharma-lab/src/pharma_lab/e2e/harness.py` (pick the graph), `pharma-lab/src/pharma_lab/e2e/records.py` (`ReactRecord`, `AnswerRecord.react: ReactRecord | None = None`), `pharma-lab/src/pharma_lab/e2e/executor.py` (`answer_record` copies `run.react`; `degraded_steps` ignores AGENT actions), `pharma-lab/src/pharma_lab/e2e/report.py` (metrics, labels, `react_failures.csv`), `pharma-lab/tests/test_backend_public_api.py` (`PUBLIC_MODULES += "pharma_agent.application.chat.react_graph"`)
- Test: `pharma-lab/tests/e2e/test_run_setup.py`, `pharma-lab/tests/e2e/test_executor.py`, `pharma-lab/tests/e2e/test_report.py`

**Interfaces:**
- Produces: `E2EConfig.REACT` with `PipelineOptions()` (rephrase/judge-refine do not apply; the identity records `"graph": "react"` through `run.json`'s `config`); `graph_for(E2EConfig) -> ChatGraph` (`build_react_graph()` for REACT, else `build_chat_graph()`); `ReactRecord` mirrors `ReactStats`; metrics `react_rounds` (mean), `react_tool_calls` (mean), `react_round_cap_rate`, `react_malformed_rate` (share of turns with ≥1 malformed call), `react_duplicate_rate`, `react_budget_hit_rate`, `react_no_search_rate` (binary rates, Wilson), `react_uncited_rate` (share of grounded answers with no citation); `reports/react_failures.csv` with one row per configuration that has ReAct records: config, n, and each rate with its interval.

- [ ] **Step 1: Write the failing tests**

```python
def test_react_config_selects_the_react_graph() -> None:
    assert pipeline_for(E2EConfig.REACT) == PipelineOptions()
    assert graph_for(E2EConfig.REACT).get_graph().nodes.keys() >= {
        "guard",
        "agent",
        "tools",
        "finalize",
    }
    assert "rephrase" in graph_for(E2EConfig.FULL).get_graph().nodes


async def test_react_executor_records_the_react_statistics() -> None:
    llm = guard_ok_llm()  # factories helper scripting a passing LlmGuardVerdict
    llm.script_tool_turns(
        ToolTurn(
            text="",
            tool_calls=(
                ToolCall(id="c1", name="search_corpus", arguments='{"query": "x"}'),
            ),
            finish_reason="tool_calls",
        ),
        ToolTurn(text="Đáp [1].", tool_calls=(), finish_reason="stop"),
    )
    record = await executor(
        llm,
        FakeRetriever([make_hit("a", SECTION)]),
        E2EConfig.REACT,
        graph=build_react_graph(),
    ).execute(item())
    assert record.react is not None and record.react.rounds == 1
    assert record.usage_by_role["agent"].calls == 2
    assert [s.kind for s in record.steps][:2] == ["guard", "agent"]


def test_report_writes_react_failures(tmp_path: Path) -> None:
    ...
    # write_config(tmp_path, "react", ...) with answers carrying ReactRecord(round_cap_hit=True on one item); write_report; rows(react_failures.csv) has config "react" and react_round_cap_rate mean 0.25
```

(`executor(...)` in test_executor.py gains a `graph` keyword defaulting to `build_chat_graph()`.)

- [ ] **Step 2: Run them, watch them fail.** Expected: FAIL — no `E2EConfig.REACT`.
- [ ] **Step 3: Implement.** `harness.run_e2e` passes `graph=graph_for(request.config)`; `CONFIG_LABELS["react"] = "ReAct agent"`; the main table's paper configs stay `full`/`one-step`, and `react` appears in `main.csv`, `cost.csv`, `react_failures.csv` and in `e2e compare --config-b react` against `full`.
- [ ] **Step 4: Run the tests** — pharma-lab gates. Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(e2e): react configuration, ReAct statistics and the failure table"`

---

### Task 6: Documentation

**Files:**
- Modify: `pharma-lab/docs/guides/e2e-evaluation.md` (configs table row `react`; a section "Agent ReAct": tool, round cap, budget rules, duplicate guard, answer modes, the failure table, how to compare with `full` of the same model), `pharma-lab/docs/guides/cli-reference.md` (`--config react`), `backend/README.md` if it lists the graphs or LLM roles (role `agent`).

- [ ] **Step 1: Write the sections** (Vietnamese, the guides' style), including the matrix C commands of Task 7 Step 2 as the worked example.
- [ ] **Step 2: Commit** — `git commit -m "docs(e2e): the ReAct configuration and its failure table"`

---

### Task 7: Matrix C runs (deferred until phase 1 runs exist)

Prerequisites: phase 0 Task 11 (A1/A2 runs, agent retrieval pair `<EMB>`/`<RER>` chosen and served) and the A2 graph-routing runs of phase 1 Task 11 Step 2 for Gemini and Opus (`e2e-v2-gemini`, `e2e-v2-opus`) and phase 0's `e2e-v2-qwen9b`; golden v2; free Kaggle accounts for Qwen.

- [ ] **Step 1: Smoke** — for each model (exports exactly as phase 1 Task 11 Step 1 without the Jev block): `uv run pharma-lab e2e run --run e2e-v2-<m> --config react --limit 20`. Check `answers.jsonl`: `react` stats present, no item `error` except genuine model failures; a Qwen tool-calling failure (llama.cpp tool-call parsing) is a finding to report, not a harness bug — but confirm the request reached the model with tools (`--jinja` is set in the llm-serve worker).
- [ ] **Step 2: Full runs and latency runs**

```bash
for M in qwen9b gemini opus; do ...exports for $M...
  uv run pharma-lab e2e run --run e2e-v2-$M --config react --concurrency 4
  uv run pharma-lab e2e run --run e2e-v2-$M-c1 --config react --concurrency 1
done
```

- [ ] **Step 3: Judge, report, compare**

```bash
for M in qwen9b gemini opus; do
  uv run pharma-lab e2e judge --run e2e-v2-$M --config react --judge-model gemini-3.1-flash-lite
  uv run pharma-lab e2e report --run e2e-v2-$M --latency-run e2e-v2-$M-c1
  uv run pharma-lab e2e compare --run-a e2e-v2-$M --run-b e2e-v2-$M --config full --config-b react
done
uv run pharma-lab e2e calibration export --run e2e-v2-qwen9b --config react   # 50 items for the pharmacist
```

- [ ] **Step 4: Results document** — `docs/research/paper-v2/11-phase-2-results.md`: per model the graph-routing and ReAct points (truthfulness, nugget recall, hallucination, citation recall, USD per 1,000 turns, seconds p50/p95), the paired deltas from `compare`, the failure table, and the multi-turn (50 items) and injection (10 items) slices from `by_group.csv`. Commit run.json, judge.json, reports and the doc (archive push after the user's go-ahead).

---

## Self-review

- **Spec coverage:** §2.4 port `tool_call` with `ToolTurn{text, tool_calls{id,name,arguments}, finish_reason}` (Tasks 1–2), adapter with `parallel_tool_calls=True` (Task 2), `RecordingLlm` and fakes (Task 1); graph nodes guard (reused), plan (= `agent`), tools, answer (= `finalize`), fallback, history in messages, no rephrase/judge/refine (Task 4); one read-only parallel tool `search_corpus` returning ≤5 chunks in the pipeline's text, no neighbour tool (Tasks 3–4); stop rule, 6 rounds, final no-tool call with the note, shared budgets, evidence budget with shown-once rule and overflow note and counter, duplicate guard, `Error: ...` tool errors (Tasks 3–4); short Vietnamese Codex-style prompt (Task 3); `CitationSanitizer` and answer modes (Task 4); per-turn records of rounds, tool calls, cap, malformed, duplicates (Tasks 4–5); never on the decision model (Global Constraints; the graph has no decision path). §4.C three models, fixed factors, plane plot data via `compare` and cost/latency tables, failure table by type, multi-turn and injection slices (Tasks 5, 7).
- **Ruling recorded here:** spec §2.4 writes the citation marker as `[E<n>]` "giống pipeline", but the pipeline cites `[n]`; the ReAct agent uses `[n]` so `CitationSanitizer`, `citations_from` and every citation metric are shared unchanged.
- **Placeholders:** the `...` test bodies in Task 4 Step 1 and Task 5 Step 1 carry their setup and assertions in comments and must be written out in full by the implementer; no other gaps.
- **Type consistency:** `ToolCall`/`ToolTurn`/`ToolSpec`/`ChatMessage.tool_calls`/`tool_call_id` (Task 1) are used verbatim by Tasks 2–5; `Shown`, `render_result`, `parse_query`, `SEARCH_TOOL`, notes (Task 3) by Task 4; `ReactStats` (Task 4) ↔ `ReactRecord` (Task 5).
- **Review Focus:** each line has its test (1 → Task 4 malformed; 2 → Task 4 round cap; 3 → Tasks 3–4 duplicate; 4 → Task 4 citations; 5 → Task 4 no-retrieval/abstain).
