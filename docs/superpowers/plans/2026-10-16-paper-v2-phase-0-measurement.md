# Paper v2 phase 0: measurement infrastructure — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every end-to-end run reports quality, seconds per turn (by step, p50 and p95) and USD per turn, runs can be compared pairwise, pipeline switches and retriever variants are configurable from the harness, and the A1 (Gemini) and A2 (Qwen3.5-9B) tables are re-run on the v2 release with the new columns.

**Architecture:** The backend records what it already knows (action timestamps, retrieval and rerank wall time, reasoning tokens) and exposes two more pipeline switches; pharma-lab turns those into per-step latency, a price table, cost metrics, a `cost` table, an `e2e compare` command and a `--latency-run` option of `e2e report`. Nothing here changes the agent's behaviour in production: the new `PipelineOptions` fields default to today's behaviour and the retrieval timing is observational.

**Tech Stack:** Python 3.12, pydantic 2, LangGraph (backend chat graph), typer CLI, numpy (statistics), pytest, uv workspace. Gemini and Claude through the `cli-proxy-api` compose service (`http://127.0.0.1:8317/v1`, key `proxypal-local`); Qwen3.5-9B self-hosted on Kaggle through `pharma-lab e2e llm-server`.

**Spec:** `docs/superpowers/specs/2026-10-14-paper-v2-design.md` — §2.1b (model paths, judge reasoning check), §2.5 (latency and cost), §2.6 (switches, except enrichment), §4.A (A1, A2), §4.E (`e2e compare`), §5 (statistics), §7 item 1 (phase 0). Spec `docs/superpowers/specs/2026-10-15-chunk-reading-unit.md` fixes top 5 chunks per round and `max_evidence_chars = 60_000`.

## Global Constraints

- Every self-hosted model is Q8_0 (`qwen3.5:9b-q8_0` and the embedding and reranker of the agent layer), served replicated 2×1 on Kaggle, one kernel per model on its own account (spec §2.1b). The agent's embedding and reranker are **chosen from the v2 retrieval table** (Task 11 Step 0), never fixed in advance (user decision 2026-10-16). Below, `<EMB>` and `<RER>` stand for the chosen catalog names (for example `qwen3-embedding:8b-q8_0`, `qwen3-reranker:4b-q8_0`), `<EMB_SLUG>`/`<EMB_DIM>` for the embedding's slug and dimension.
- Reasoning off or lowest: Gemini 3.8 Flash only as `gemini-3.8-flash-high` with the proxy's `thinkingLevel: low`; Claude Opus 5.5 as `claude-opus-5-5` with `reasoning_effort: minimal`; Qwen3.5-9B with `chat_template_kwargs.enable_thinking: false` (spec §2.1b).
- Prices are list prices per 1M tokens, dated: Qwen3.5-9B 0.10/0.15; Gemini 3.8 Flash 0.75/3.75; Claude Opus 5.5 4/20; gemini-3.1-flash-lite 0.25/1.50; Jev 0.042/0 (spec §2.5, read 2026-10-14). No GPU-hour cost model.
- Latency protocol: latency numbers come from a run at concurrency 1 on the same machine and endpoint; quality runs may use concurrency 4 (spec §2.5). Report p50 and p95.
- `rerank.max_candidates = 40`, `rerank.top_n = 5`, `candidate_k = 20`, `max_evidence_chars = 60_000` (spec §2.6, §3.0c). Not changed here.
- Statistics: Wilson for rates, percentile bootstrap (10,000) for means, paired sign-flip with Holm within one table (spec §5). Existing helpers in `pharma_lab/e2e/statistics.py`.
- Never commit secrets; `backend/.env` and `pharma-lab/.env` are git-ignored. Commits carry no `Co-Authored-By` trailer.
- Repo rules in `AGENTS.md`: no `# noqa`, no `# type: ignore`, no `ignore_imports`; tests live under `tests/` mirroring `src/`; import-linter contracts must stay green (`uv run lint-imports` in `backend/`; pharma-lab's contracts arrive with branch `arch/pharma-lab-layers`, run them if present).
- Long jobs (Kaggle servers, full runs, judging) run inside tmux; logs under `pharma-lab/data/work/logs-p0/`.
- Code changes are made in a git worktree branched from `dev` and fast-forwarded into `dev` (Kaggle jobs read the main checkout; pre-commit's stash briefly reverts tracked data files there).

## Review Focus

1. An `answers.jsonl` written before this plan (no `steps`, no `reasoning_tokens`) must still load: every new record field has a default and `extra="forbid"` stays. Test: `test_old_answer_record_loads` (Task 3).
2. A run whose role model has no price must fail the report loudly, not silently price it at zero. Test: `test_unpriced_model_is_an_error` (Task 4).
3. A `--pipeline-option` with an unknown key or an unparsable value must be refused before any item runs. Test: `test_unknown_pipeline_option_is_refused` (Task 5).
4. `e2e compare` on two runs that share no item must refuse, and on runs judged by different judges must say so in the output rows. Test: `test_compare_refuses_disjoint_runs` (Task 7).
5. Latency from `--latency-run` must come from the same config directory name; a missing config there must raise, never fall back to the quality run's numbers. Test: `test_latency_run_requires_the_same_config` (Task 8).

---

### Task 1: Reasoning tokens in usage

**Files:**
- Modify: `backend/src/pharma_agent/domain/llm/models.py:19-33` (`LlmUsage`)
- Modify: `backend/src/pharma_agent/infrastructure/llm/openai_adapter.py:133-143` (`_usage`)
- Modify: `pharma-lab/src/pharma_lab/e2e/records.py:16-22` (`TokenUsage`), `pharma-lab/src/pharma_lab/e2e/recording_llm.py:23-31`
- Test: `backend/tests/domain/test_llm_models.py`, `backend/tests/infrastructure/test_openai_adapter.py`, `pharma-lab/tests/e2e/test_executor.py`

**Interfaces:**
- Produces: `LlmUsage.reasoning_tokens: int = 0` (part of `completion_tokens`, reported by OpenAI-compatible servers in `usage.completion_tokens_details.reasoning_tokens`); `TokenUsage.reasoning_tokens: int = 0`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/domain/test_llm_models.py` (append):

```python
def test_usage_adds_reasoning_tokens() -> None:
    total = LlmUsage(
        prompt_tokens=1, completion_tokens=5, reasoning_tokens=2
    ) + LlmUsage(completion_tokens=3, reasoning_tokens=1)
    assert total.reasoning_tokens == 3
    assert total.completion_tokens == 8
```

`backend/tests/infrastructure/test_openai_adapter.py` (append; `make_adapter` and `FakeCompletions` exist in the file):

```python
async def test_structured_reads_reasoning_tokens() -> None:
    adapter, created = make_adapter()
    _, usage = await adapter.structured(LlmRole.JUDGE, [user("q")], Verdict)
    client = next(iter(created.values()))
    client.completions.usage_details = SimpleNamespace(reasoning_tokens=7)
    _, usage = await adapter.structured(LlmRole.JUDGE, [user("q")], Verdict)
    assert usage.reasoning_tokens == 7
```

and in `FakeCompletions.__init__` add `self.usage_details: object | None = None`; in `parse` return `usage=SimpleNamespace(prompt_tokens=12, completion_tokens=3, completion_tokens_details=self.usage_details)`.

`pharma-lab/tests/e2e/test_executor.py` (append):

```python
def test_recording_llm_sums_reasoning_tokens() -> None:
    llm = ScriptedLlm()
    llm.script(
        LlmRole.JUDGE, JudgeDecision(decision=JudgeOutcome.ANSWER, gaps=[], reason="r")
    )
    recorder = RecordingLlm(llm)
    asyncio.run(recorder.structured(LlmRole.JUDGE, [], JudgeDecision))
    assert recorder.usage_by_role()["judge"].reasoning_tokens == 0
```

(`ScriptedLlm` returns `LlmUsage(prompt_tokens=10, completion_tokens=2)`; the field exists and sums to 0. Import `RecordingLlm` from `pharma_lab.e2e.recording_llm`.)

- [ ] **Step 2: Run them, watch them fail**

Run: `cd backend && uv run pytest tests/domain/test_llm_models.py tests/infrastructure/test_openai_adapter.py -q -k reasoning` and `cd pharma-lab && uv run pytest tests/e2e/test_executor.py -q -k reasoning`
Expected: FAIL — `LlmUsage` has no field `reasoning_tokens` / `TokenUsage` has no field `reasoning_tokens`.

- [ ] **Step 3: Implement**

`domain/llm/models.py`:

```python
class LlmUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    prompt_tokens: int = 0
    completion_tokens: int = 0
    # Reasoning tokens inside completion_tokens, when the server reports them.
    reasoning_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: "LlmUsage") -> "LlmUsage":
        return LlmUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
        )
```

`openai_adapter._usage`:

```python
def _usage(usage: Any) -> LlmUsage:
    if usage is None:
        return LlmUsage()
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    total = int(getattr(usage, "total_tokens", 0) or 0)
    details = getattr(usage, "completion_tokens_details", None)
    reasoning = int(getattr(details, "reasoning_tokens", 0) or 0)
    # OpenAI counts reasoning tokens inside completion_tokens; some OpenAI-compatible
    # proxies report them only in total_tokens. The larger value bills them either way.
    return LlmUsage(
        prompt_tokens=prompt,
        completion_tokens=max(completion, total - prompt),
        reasoning_tokens=reasoning,
    )
```

`records.TokenUsage`: add `reasoning_tokens: int = 0`. `recording_llm._record`: add `reasoning_tokens=current.reasoning_tokens + usage.reasoning_tokens`.

- [ ] **Step 4: Run the tests**

Run: the two commands of Step 2, then `cd backend && uv run pytest -q` and `cd pharma-lab && uv run pytest -q`
Expected: PASS; full suites green (backend 607 + 2, pharma-lab 926 + 1).

- [ ] **Step 5: Commit**

```bash
git add backend/src/pharma_agent/domain/llm/models.py backend/src/pharma_agent/infrastructure/llm/openai_adapter.py backend/tests/domain/test_llm_models.py backend/tests/infrastructure/test_openai_adapter.py pharma-lab/src/pharma_lab/e2e/records.py pharma-lab/src/pharma_lab/e2e/recording_llm.py pharma-lab/tests/e2e/test_executor.py
git commit -m "feat(llm): usage carries the reasoning tokens a server reports"
```

---

### Task 2: Retrieval and rerank wall time in `SearchResult`

**Files:**
- Modify: `backend/src/pharma_agent/domain/retrieval/models.py` (`SearchResult`)
- Modify: `backend/src/pharma_agent/domain/retrieval/service.py:41-100` (`RetrievalService.search`)
- Modify: `backend/src/pharma_agent/domain/agent/run.py:241-278` (`record_search` payload)
- Test: `backend/tests/domain/test_retrieval_service.py`, `backend/tests/domain/test_agent_run.py`

**Interfaces:**
- Produces: `SearchResult.retrieval_seconds: float = 0.0` (the `search_many` call), `SearchResult.rerank_seconds: float = 0.0` (the `rerank` call, 0 when nothing was fresh or rerank is off); search action payload keys `retrieval_seconds`, `rerank_seconds`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/domain/test_retrieval_service.py` (append; the file already builds a `RetrievalService` from `FakeRetriever`/`FakeReranker` in `tests/fakes.py` — reuse its helper that constructs the service, named `service(...)` or build one inline as the existing tests do):

```python
async def test_search_reports_retrieval_and_rerank_seconds() -> None:
    retriever = FakeRetriever([make_hit("a", "drug:x:s1")])
    reranker = FakeReranker()
    retriever.delay = 0.02
    reranker.delay = 0.02
    service = RetrievalService(
        retriever,
        reranker,
        RetrievalConfig(candidate_k=20, rerank_top_n=5, rerank_candidates=40),
    )
    result = await service.search(
        [Query(text="q", origin=QueryOrigin.INITIAL)], rerank_query="q"
    )
    assert result.retrieval_seconds >= 0.02
    assert result.rerank_seconds >= 0.02
```

Add to `tests/fakes.py` `FakeRetriever.delay: float = 0.0` (awaited with `asyncio.sleep` at the top of `search_many`) and the same on `FakeReranker.rerank`.

`backend/tests/domain/test_agent_run.py` (append):

```python
def test_search_action_records_retrieval_timing() -> None:
    run = AgentRun.start(
        user_id="u", original_query="q", limits=BudgetLimits(), now=NOW
    )
    result = SearchResult(
        items=[], queries=[], retrieval_seconds=0.5, rerank_seconds=0.25
    )
    run.record_search([Query(text="q", origin=QueryOrigin.INITIAL)], result, now=NOW)
    payload = run.actions.entries[-1].payload
    assert payload["retrieval_seconds"] == 0.5
    assert payload["rerank_seconds"] == 0.25
```

- [ ] **Step 2: Run them, watch them fail**

Run: `cd backend && uv run pytest tests/domain/test_retrieval_service.py tests/domain/test_agent_run.py -q -k "seconds or timing"`
Expected: FAIL — `SearchResult` has no field `retrieval_seconds`.

- [ ] **Step 3: Implement**

`SearchResult` in `domain/retrieval/models.py`: add after the existing fields

```python
    # Wall time of this round's retrieval and of its rerank call (0 when none ran).
    retrieval_seconds: float = 0.0
    rerank_seconds: float = 0.0
```

`RetrievalService.search`: `import time` at the top; wrap the two calls:

```python
        started = time.perf_counter()
        try:
            if scope is not None and not scope:
                return SearchResult(queries=list(queries))
            per_query = await self._retriever.search_many(
                queries, self._config.candidate_k, scope
            )
        except RetrievalError as exc:
            return SearchResult(queries=list(queries), error=str(exc))
        retrieval_seconds = time.perf_counter() - started
        ...
        rerank_failed = False
        rerank_started = time.perf_counter()
        try:
            scored = (... unchanged ...)
            ranked = ...
        except RetrievalError:
            ...
        rerank_seconds = time.perf_counter() - rerank_started if fresh else 0.0
        return SearchResult(
            items=ranked,
            queries=list(queries),
            rerank_failed=rerank_failed,
            rerank_scored=len(fresh),
            rerank_reused=len(reused),
            retrieval_seconds=retrieval_seconds,
            rerank_seconds=rerank_seconds,
        )
```

(`fresh` is reset to `[]` in the failure branch today; compute `had_fresh = bool(fresh)` before the `try` and use it for the `rerank_seconds` condition.)

`AgentRun.record_search` payload: add `"retrieval_seconds": result.retrieval_seconds, "rerank_seconds": result.rerank_seconds`.

- [ ] **Step 4: Run the tests**

Run: `cd backend && uv run pytest -q && uv run lint-imports`
Expected: PASS, contracts kept.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pharma_agent/domain/retrieval/models.py backend/src/pharma_agent/domain/retrieval/service.py backend/src/pharma_agent/domain/agent/run.py backend/tests/fakes.py backend/tests/domain/test_retrieval_service.py backend/tests/domain/test_agent_run.py
git commit -m "feat(retrieval): a search result carries its retrieval and rerank wall time"
```

---

### Task 3: Per-step latency in `AnswerRecord`

**Files:**
- Modify: `pharma-lab/src/pharma_lab/e2e/records.py` (new `StepRecord`, fields on `AnswerRecord`)
- Modify: `pharma-lab/src/pharma_lab/e2e/executor.py:66-135` (`answer_record`)
- Modify: `pharma-lab/src/pharma_lab/e2e/report.py:180-250` (`METRICS`)
- Test: `pharma-lab/tests/e2e/test_executor.py`, `pharma-lab/tests/e2e/test_report.py`

**Interfaces:**
- Consumes: `Action.at`, `AgentRun.started_at`, search payload `retrieval_seconds`/`rerank_seconds` (Task 2).
- Produces: `StepRecord(kind: str, outcome: str, started_at: str, seconds: float)`; `AnswerRecord.steps: list[StepRecord]`, `AnswerRecord.retrieval_seconds: float`, `AnswerRecord.rerank_seconds: float`, `AnswerRecord.rerank_scored: int`; metrics `llm_seconds_per_turn`, `retrieval_seconds_per_turn`, `rerank_seconds_per_turn`, `decision_seconds_per_turn`.

- [ ] **Step 1: Write the failing tests**

`pharma-lab/tests/e2e/test_executor.py` (append; `item()`, `ScriptedLlm`, `retrieval_service`, `make_hit`, `BackendTurnExecutor`, `build_chat_graph` are already imported there; reuse the LLM scripting the file's first test uses — guard, rephrase, judge answer):

```python
def test_answer_record_has_one_step_per_action_with_seconds() -> None:
    llm = ScriptedLlm()
    llm.script(
        LlmRole.GUARDRAIL, LlmGuardVerdict(is_attack=False, in_scope=True, reason="ok")
    )
    llm.script(
        LlmRole.REPHRASE,
        RephraseResult(
            standalone_query="liều paracetamol",
            audience=Audience.GENERAL_PUBLIC,
            language=Language.VI,
            intent=Intent.PHARMA_QUESTION,
        ),
    )
    llm.script(
        LlmRole.JUDGE, JudgeDecision(decision=JudgeOutcome.ANSWER, gaps=[], reason="đủ")
    )
    executor = BackendTurnExecutor(
        graph=build_chat_graph(),
        llm=llm,
        retrieval=retrieval_service(FakeRetriever([make_hit("c1", SECTION)])),
        limits=BudgetLimits(),
        pipeline=pipeline_for(E2EConfig.FULL),
        config="full",
    )
    record = asyncio.run(executor.execute(item()))
    assert [s.kind for s in record.steps] == [
        "guard",
        "rephrase",
        "search",
        "judge",
        "answer",
    ]
    assert all(s.seconds >= 0 for s in record.steps)
    assert abs(sum(s.seconds for s in record.steps) - record.latency_seconds) < 0.05
    assert record.rerank_scored == 1


def test_old_answer_record_loads() -> None:
    old = {"item_id": "e2e-ans-0001", "config": "full", "status": "completed"}
    record = AnswerRecord.model_validate(old)
    assert record.steps == [] and record.retrieval_seconds == 0.0
```

`pharma-lab/tests/e2e/test_report.py` (append; `answer()` and `golden()` helpers exist):

```python
def test_seconds_per_turn_metrics_read_steps_and_roles() -> None:
    record = answer(1, "full")
    record = record.model_copy(
        update={
            "retrieval_seconds": 0.4,
            "rerank_seconds": 0.6,
            "usage_by_role": {
                "guardrail": TokenUsage(calls=1, seconds=0.2),
                "judge": TokenUsage(calls=1, seconds=0.3),
                "answer": TokenUsage(calls=1, seconds=2.0),
            },
        }
    )
    view = ItemView(golden(1), record, judgement(1, "full", 1.0), {})
    by_name = {metric.name: metric for metric in METRICS}
    assert by_name["llm_seconds_per_turn"].read(view) == pytest.approx(2.5)
    assert by_name["retrieval_seconds_per_turn"].read(view) == pytest.approx(1.0)
    assert by_name["rerank_seconds_per_turn"].read(view) == pytest.approx(0.6)
    assert by_name["decision_seconds_per_turn"].read(view) == pytest.approx(0.5)
```

- [ ] **Step 2: Run them, watch them fail**

Run: `cd pharma-lab && uv run pytest tests/e2e/test_executor.py tests/e2e/test_report.py -q -k "step or old_answer or seconds_per_turn"`
Expected: FAIL — `AnswerRecord` has no attribute `steps`; `llm_seconds_per_turn` not in `METRICS`.

- [ ] **Step 3: Implement**

`records.py`:

```python
class StepRecord(BaseModel):
    """One action of the agent loop: when it started and how long it took."""

    model_config = _RECORD

    kind: str
    outcome: str
    started_at: str
    seconds: float
```

On `AnswerRecord` add (all with defaults):

```python
    steps: list[StepRecord] = Field(default_factory=list)
    # Wall time of retrieval and rerank calls summed over the search rounds.
    retrieval_seconds: float = 0.0
    rerank_seconds: float = 0.0
    # Candidates the reranker scored over the turn (the priced rerank work).
    rerank_scored: int = 0
```

`executor.py`: add

```python
def step_records(run: AgentRun, latency: float) -> list[StepRecord]:
    """Seconds between consecutive actions; the answer step runs to the end of the turn
    because its action is logged when the plan is submitted, before streaming."""
    steps: list[StepRecord] = []
    previous = run.started_at
    entries = run.actions.entries
    for index, action in enumerate(entries):
        if index == len(entries) - 1:
            seconds = max(0.0, latency - (previous - run.started_at).total_seconds())
        else:
            seconds = (action.at - previous).total_seconds()
        steps.append(
            StepRecord(
                kind=action.kind.value,
                outcome=action.outcome,
                started_at=previous.isoformat(timespec="milliseconds"),
                seconds=round(seconds, 3),
            )
        )
        previous = action.at
    return steps
```

and in `answer_record(...)` set

```python
steps = (step_records(run, latency),)
retrieval_seconds = (
    round(
        sum(
            float(a.payload.get("retrieval_seconds", 0.0))
            for a in entries
            if a.kind is ActionKind.SEARCH
        ),
        3,
    ),
)
rerank_seconds = (
    round(
        sum(
            float(a.payload.get("rerank_seconds", 0.0))
            for a in entries
            if a.kind is ActionKind.SEARCH
        ),
        3,
    ),
)
rerank_scored = (
    sum(
        int(a.payload.get("rerank_scored", 0))
        for a in entries
        if a.kind is ActionKind.SEARCH
    ),
)
```

(import `AgentRun` from `pharma_agent.domain.agent.run` and `StepRecord` from records).

`report.py` `METRICS`, after `Metric("latency_seconds", ...)`:

```python
(
    Metric(
        "llm_seconds_per_turn",
        lambda v: sum(u.seconds for u in v.answer.usage_by_role.values()),
        False,
        False,
    ),
)
(
    Metric(
        "retrieval_seconds_per_turn",
        lambda v: v.answer.retrieval_seconds + v.answer.rerank_seconds,
        False,
        False,
    ),
)
(Metric("rerank_seconds_per_turn", lambda v: v.answer.rerank_seconds, False, False),)
# Guard and judge are the decision steps; phase 1 moves them to the decision model.
(
    Metric(
        "decision_seconds_per_turn",
        lambda v: sum(
            v.answer.usage_by_role[r].seconds
            for r in ("guardrail", "judge")
            if r in v.answer.usage_by_role
        ),
        False,
        False,
    ),
)
```

- [ ] **Step 4: Run the tests**

Run: `cd pharma-lab && uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pharma-lab/src/pharma_lab/e2e/records.py pharma-lab/src/pharma_lab/e2e/executor.py pharma-lab/src/pharma_lab/e2e/report.py pharma-lab/tests/e2e/test_executor.py pharma-lab/tests/e2e/test_report.py
git commit -m "feat(e2e): answers record per-step seconds and retrieval timing"
```

---

### Task 4: Price table, cost metrics and the `cost` table

**Files:**
- Create: `pharma-lab/src/pharma_lab/e2e/pricing.py`
- Modify: `pharma-lab/src/pharma_lab/e2e/report.py` (`ItemView`, `_values`, `_load`, `METRICS`, `METRIC_LABELS`, new `_cost_table`, `write_report`)
- Test: `pharma-lab/tests/e2e/test_pricing.py`, `pharma-lab/tests/e2e/test_report.py`

**Interfaces:**
- Consumes: `AnswerRecord.usage_by_role`, `AnswerRecord.rerank_scored`, `AnswerRecord.search_queries`, `run.json` `role_models[role]["model"]`, `retrieval["embedding_model"]` and `rerank["model"]` (`identity_from_settings`).
- Produces: `ModelPrice(usd_per_1m_prompt, usd_per_1m_completion, source, date)`; `PRICES: dict[str, ModelPrice]`; `RetrievalPricing(candidate_tokens_mean=1_001, chars_per_token=3.1)`; `turn_cost_usd(record, role_models) -> float`; `retrieval_cost_usd(record, embedding_model: str, reranker_model: str | None) -> float`; `UnpricedModel(ValueError)`; metrics `usd_per_turn`, `llm_usd_per_turn`, `retrieval_usd_per_turn`; `reports/cost.csv|tex`.

- [ ] **Step 1: Write the failing tests**

`pharma-lab/tests/e2e/test_pricing.py`:

```python
import pytest

from pharma_lab.e2e.pricing import (
    PRICES,
    UnpricedModel,
    retrieval_cost_usd,
    turn_cost_usd,
)
from pharma_lab.e2e.records import AnswerRecord, TokenUsage


def record(**fields) -> AnswerRecord:
    base = {"item_id": "e2e-ans-0001", "config": "full", "status": "completed"}
    return AnswerRecord.model_validate({**base, **fields})


def test_turn_cost_prices_each_role_by_its_model() -> None:
    usage = {
        "guardrail": TokenUsage(calls=1, prompt_tokens=1_000_000),
        "answer": TokenUsage(
            calls=1, prompt_tokens=1_000_000, completion_tokens=1_000_000
        ),
    }
    roles = {
        "guardrail": {"model": "gemini-3.1-flash-lite"},
        "answer": {"model": "gemini-3.8-flash-high"},
    }
    assert turn_cost_usd(record(usage_by_role=usage), roles) == pytest.approx(
        0.25 + 0.75 + 3.75
    )


def test_unpriced_model_is_an_error() -> None:
    usage = {"answer": TokenUsage(calls=1, prompt_tokens=10)}
    with pytest.raises(UnpricedModel, match="gpt-7-nano"):
        turn_cost_usd(record(usage_by_role=usage), {"answer": {"model": "gpt-7-nano"}})


def test_retrieval_cost_counts_reranked_candidates_and_query_tokens() -> None:
    rec = record(rerank_scored=20, search_queries=[["x" * 31]])
    reranker = PRICES["qwen3-reranker:8b-q8_0"].usd_per_1m_prompt
    embedding = PRICES["qwen3-embedding:4b-q8_0"].usd_per_1m_prompt
    expected = (20 * 1_001 * reranker + 10 * embedding) / 1_000_000
    assert retrieval_cost_usd(
        rec, "qwen3-embedding:4b-q8_0", "qwen3-reranker:8b-q8_0"
    ) == pytest.approx(expected)
    assert retrieval_cost_usd(rec, "qwen3-embedding:4b-q8_0", None) == pytest.approx(
        10 * embedding / 1_000_000
    )


def test_every_paper_model_has_a_dated_price() -> None:
    for name in (
        "qwen3.5:9b-q8_0",
        "qwen/qwen3.5-9b",
        "gemini-3.8-flash-high",
        "gemini-3.1-flash-lite",
        "claude-opus-5-5",
        "~typesafe/jev-latest",
    ):
        assert PRICES[name].date and PRICES[name].source
```

`pharma-lab/tests/e2e/test_report.py` (append; the file has a test that writes a full run to `tmp_path` and calls `write_report` — copy its setup, which writes `run.json` through `open_run` or a literal dict; the literal must now include `role_models`):

```python
def test_cost_table_has_usd_per_turn_and_cost_of_pass(tmp_path: Path) -> None:
    run_root = _write_judged_run(
        tmp_path
    )  # helper used by the existing write_report test
    write_report(run_root, {golden(n).item_id: golden(n) for n in range(1, 5)})
    rows = list(
        csv.DictReader((run_root / "reports" / "cost.csv").open(encoding="utf-8"))
    )
    metrics = {(r["config"], r["metric"]) for r in rows}
    assert ("full", "usd_per_turn") in metrics
    assert ("full", "usd_per_1000_turns") in metrics
    assert ("full", "cost_of_pass") in metrics
    assert ("full", "latency_p50") in metrics
    assert (
        (run_root / "reports" / "cost.tex")
        .read_text("utf-8")
        .startswith("\\begin{table}")
    )
```

(`_write_judged_run` must write `run.json` with `role_models` = `{"answer": {"model": "gemini-3.8-flash-high"}, ...}` for every role, `retrieval` = `{"embedding_model": "qwen3-embedding:4b-q8_0"}` and `rerank` = `{"model": "qwen3-reranker:4b-q8_0"}`; if the existing helper has another name, use that name and add these keys to the `run.json` it writes.)

- [ ] **Step 2: Run them, watch them fail**

Run: `cd pharma-lab && uv run pytest tests/e2e/test_pricing.py tests/e2e/test_report.py -q -k "cost or price"`
Expected: FAIL — `No module named pharma_lab.e2e.pricing`.

- [ ] **Step 3: Write `pricing.py`**

```python
"""List prices of every model a run may use (spec v2 §2.5).

USD per million tokens, read on the date given. Costs in the paper are list prices
times tokens, for self-hosted models too (Qwen3.5-9B at its OpenRouter/DeepInfra bf16
price), never GPU hours. Retrieval is priced per reranked candidate and per query token.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pharma_lab.e2e.records import AnswerRecord


class UnpricedModel(ValueError):
    pass


@dataclass(frozen=True)
class ModelPrice:
    usd_per_1m_prompt: float
    usd_per_1m_completion: float
    source: str
    date: str


_GOOGLE = "https://ai.google.dev/gemini-api/docs/pricing"
_OPENROUTER_QWEN = "https://openrouter.ai/qwen/qwen3.5-9b (DeepInfra bf16)"

PRICES: dict[str, ModelPrice] = {
    "gemini-3.8-flash-high": ModelPrice(0.75, 3.75, _GOOGLE, "2026-10-14"),
    "gemini-3.1-flash-lite": ModelPrice(0.25, 1.50, _GOOGLE, "2026-10-14"),
    "claude-opus-5-5": ModelPrice(
        4.0, 20.0, "https://claude.com/pricing", "2026-10-14"
    ),
    # The self-hosted name and the OpenRouter id are the same model at the same price.
    "qwen3.5:9b-q8_0": ModelPrice(0.10, 0.15, _OPENROUTER_QWEN, "2026-10-14"),
    "qwen/qwen3.5-9b": ModelPrice(0.10, 0.15, _OPENROUTER_QWEN, "2026-10-14"),
    "~typesafe/jev-latest": ModelPrice(
        0.042, 0.0, "https://docs.typesafe.ai/models.md", "2026-10-14"
    ),
    # Retrieval components the agent may use (the pair is chosen from the retrieval table).
    # OpenRouter serves the 8B pair through /api/v1/embeddings and /api/v1/rerank; their
    # price is read on the day of the first phase-0 run (Task 4 Step 3b). Until then every
    # entry carries Qwen3.5-9B's input price, an upper bound for models of that size or
    # smaller.
    "qwen3-embedding:0.6b-q8_0": ModelPrice(
        0.10, 0.0, "upper bound: " + _OPENROUTER_QWEN, "2026-10-16"
    ),
    "qwen3-embedding:4b-q8_0": ModelPrice(
        0.10, 0.0, "upper bound: " + _OPENROUTER_QWEN, "2026-10-16"
    ),
    "qwen3-embedding:8b-q8_0": ModelPrice(
        0.10, 0.0, "upper bound: " + _OPENROUTER_QWEN, "2026-10-16"
    ),
    "bge-m3:567m-q8_0": ModelPrice(
        0.10, 0.0, "upper bound: " + _OPENROUTER_QWEN, "2026-10-16"
    ),
    "embeddinggemma:300m-q8_0": ModelPrice(
        0.10, 0.0, "upper bound: " + _OPENROUTER_QWEN, "2026-10-16"
    ),
    "qwen3-reranker:0.6b-q8_0": ModelPrice(
        0.10, 0.0, "upper bound: " + _OPENROUTER_QWEN, "2026-10-16"
    ),
    "qwen3-reranker:4b-q8_0": ModelPrice(
        0.10, 0.0, "upper bound: " + _OPENROUTER_QWEN, "2026-10-16"
    ),
    "qwen3-reranker:8b-q8_0": ModelPrice(
        0.10, 0.0, "upper bound: " + _OPENROUTER_QWEN, "2026-10-16"
    ),
    "bge-reranker-v2-m3:q8_0": ModelPrice(
        0.10, 0.0, "upper bound: " + _OPENROUTER_QWEN, "2026-10-16"
    ),
}


@dataclass(frozen=True)
class RetrievalPricing:
    # Mean Qwen3 tokens of a chunk's embedding text, measured on the formulary bundle
    # (13,408 chunks, 2026-10-15, spec v2 §3.0c); the reranker reads one chunk per candidate.
    candidate_tokens_mean: int = 1_001
    # Vietnamese characters per token (spec v2 §2.1), for the short query embeddings.
    chars_per_token: float = 3.1


RETRIEVAL = RetrievalPricing()


def price_of(model: str) -> ModelPrice:
    try:
        return PRICES[model]
    except KeyError as exc:
        raise UnpricedModel(
            f"no list price for model {model!r}; add it to pricing.PRICES"
        ) from exc


def turn_cost_usd(
    record: AnswerRecord, role_models: Mapping[str, Mapping[str, object]]
) -> float:
    """USD of the LLM and decision-model calls of one turn."""
    total = 0.0
    for role, usage in record.usage_by_role.items():
        price = price_of(str(role_models[role]["model"]))
        total += usage.prompt_tokens * price.usd_per_1m_prompt / 1e6
        total += usage.completion_tokens * price.usd_per_1m_completion / 1e6
    return total


def retrieval_cost_usd(
    record: AnswerRecord,
    embedding_model: str,
    reranker_model: str | None,
    pricing: RetrievalPricing = RETRIEVAL,
) -> float:
    """USD of embedding every search query and reranking every scored candidate; the
    models come from the run's identity (`retrieval.embedding_model`, `rerank.model`)."""
    reranker = (
        0.0 if reranker_model is None else price_of(reranker_model).usd_per_1m_prompt
    )
    embedding = price_of(embedding_model).usd_per_1m_prompt
    query_tokens = sum(
        len(q) / pricing.chars_per_token
        for queries in record.search_queries
        for q in queries
    )
    return (
        record.rerank_scored * pricing.candidate_tokens_mean * reranker
        + query_tokens * embedding
    ) / 1e6
```

- [ ] **Step 3b: Read the OpenRouter price of the two retrieval models**

Run: `curl -s https://openrouter.ai/api/v1/models | python3 -c "import json,sys; [print(m['id'], m['pricing']) for m in json.load(sys.stdin)['data'] if 'qwen3-embedding' in m['id'] or 'qwen3-reranker' in m['id'] or 'bge' in m['id']]"`. When an id is listed, copy `pricing.prompt` × 1e6 into its `ModelPrice` entry with source `https://openrouter.ai/<id>` and today's date. When the listing has no such id (the case on 2026-10-16: OpenRouter serves the 8B pair only through `/api/v1/embeddings` and `/api/v1/rerank`), open the OpenRouter dashboard's activity row of one production call (`backend/.env.production` targets these models) and take the price from its cost ÷ tokens; failing both, the upper bound stays and the ledger records it. Only the chosen pair (Task 11 Step 0) must have a real price before the runs are reported.

- [ ] **Step 4: Wire the report**

In `report.py`:
- `ItemView` gains `llm_usd: float | None = None` and `retrieval_usd: float | None = None` (dataclass fields with defaults, after `accepted`).
- `_load` returns, per config, a third element: `identity = json.loads((directory / RUN_FILE).read_text())` (import `RUN_FILE` from `run_identity`). Update the two unpackings in `write_report` and `_group_table`'s type.
- `_values(items, answers, judgments, relevance, identity)` builds the view with `llm_usd=turn_cost_usd(record, identity["role_models"])` and `retrieval_usd=retrieval_cost_usd(record, identity["retrieval"]["embedding_model"], identity["rerank"]["model"])` (a closed-book run has `rerank_scored == 0` and no queries, so its retrieval cost is 0).
- `METRICS` gains:

```python
(Metric("llm_usd_per_turn", lambda v: v.llm_usd, False, False),)
(Metric("retrieval_usd_per_turn", lambda v: v.retrieval_usd, False, False),)
(
    Metric(
        "usd_per_turn",
        lambda v: (
            None
            if v.llm_usd is None or v.retrieval_usd is None
            else v.llm_usd + v.retrieval_usd
        ),
        False,
        True,
    ),
)
```

and `METRIC_LABELS["usd_per_turn"] = f"USD / turn {_DOWN}"`.
- New `_cost_table(directory, configs, values) -> list[Path]` writing `cost.csv` (columns `config, metric, n, mean, ci_low, ci_high`) with rows per config: `usd_per_turn` (bootstrap), `llm_usd_per_turn`, `retrieval_usd_per_turn`, `usd_per_1000_turns` (= 1000 × mean usd, interval scaled), `cost_of_pass` (= mean `usd_per_turn` ÷ mean `perfect_rate`; `inf` when perfect_rate is 0; no interval), `llm_seconds_per_turn`, `retrieval_seconds_per_turn`, `decision_seconds_per_turn` (bootstrap), `latency_p50`, `latency_p95` (`_percentile`). `cost.tex`: label `tab:e2e-cost`, caption "Cost and latency per turn: USD at list prices, seconds by step (p50 latency), per configuration.", columns Config | USD/1000 turns | Cost of pass | LLM s | Retrieval s | Decision s | p50 s | p95 s, one row per config in `configs`.
- `write_report` appends `_cost_table(...)` to `written`.

- [ ] **Step 5: Run the tests**

Run: `cd pharma-lab && uv run pytest -q`
Expected: PASS. The existing `write_report` tests need `role_models` in their `run.json`; add it where they write the identity.

- [ ] **Step 6: Commit**

```bash
git add pharma-lab/src/pharma_lab/e2e/pricing.py pharma-lab/src/pharma_lab/e2e/report.py pharma-lab/tests/e2e/test_pricing.py pharma-lab/tests/e2e/test_report.py
git commit -m "feat(e2e): list-price table, USD per turn and the cost table"
```

---

### Task 5: Pipeline switches from the harness: `guard`, `--pipeline-option`, retriever variants

**Files:**
- Modify: `backend/src/pharma_agent/application/chat/context.py:22-27` (`PipelineOptions.guard`), `backend/src/pharma_agent/application/chat/nodes.py:69-83` (`guard_node`)
- Modify: `pharma-lab/src/pharma_lab/e2e/configs.py`, `pharma-lab/src/pharma_lab/e2e/run_identity.py:21-31`, `pharma-lab/src/pharma_lab/e2e/harness.py:100-180`, `pharma-lab/src/pharma_lab/e2e/judging/service.py:119-130` (`JudgeRequest.config: str`), `pharma-lab/src/pharma_lab/e2e/report.py` (`_load`, `CONFIG_LABELS` lookups), `pharma-lab/src/pharma_lab/cli/commands/e2e.py` (`run`, `judge`)
- Test: `backend/tests/application/test_chat_graph.py`, `pharma-lab/tests/e2e/test_run_setup.py`, `pharma-lab/tests/e2e/test_report.py`

**Interfaces:**
- Produces: `PipelineOptions.guard: bool = True`; `E2EConfig.NO_GUARD = "no-guard"`, `E2EConfig.BM25 = "bm25"`, `E2EConfig.DENSE = "dense"`, `E2EConfig.HYBRID_K60 = "hybrid-k60"`; `parse_pipeline_options(base: PipelineOptions, pairs: Sequence[str]) -> PipelineOptions`; `config_label(config: E2EConfig, pairs: Sequence[str]) -> str` (`"full"` or `"full+refine_threshold=0.5"`); `RunIdentity.pipeline: dict[str, object]`; `E2ERunRequest.pipeline_options: tuple[str, ...] = ()`; `JudgeRequest.config: str` (the directory name); report `_load` scans directories.

- [ ] **Step 1: Write the failing tests**

`backend/tests/application/test_chat_graph.py` (append; mirror `test_one_step_pipeline_calls_guard_and_answer_only` which builds deps with `build_deps` and a `ChatTurnRunner(..., pipeline=PipelineOptions(...))`):

```python
async def test_no_guard_skips_the_guard_llm_and_records_a_skipped_verdict() -> None:
    llm = passing_llm()
    llm.structured_responses.pop(LlmRole.GUARDRAIL)  # no guard call may happen
    outcome = await run_turn(llm, pipeline=PipelineOptions(guard=False))
    assert outcome.run.actions.entries[0].kind is ActionKind.GUARD
    assert outcome.run.actions.entries[0].payload["source"] == "skipped"
    assert outcome.run.status is RunStatus.COMPLETED
```

(`run_turn(llm, pipeline=...)` is the file's helper that starts a turn and drains events; if it has another name, use that one.)

`pharma-lab/tests/e2e/test_run_setup.py` (append):

```python
def test_pipeline_options_parse_and_label() -> None:
    options = parse_pipeline_options(PipelineOptions(), ["guard=false"])
    assert options == PipelineOptions(guard=False)
    assert config_label(E2EConfig.FULL, ["guard=false"]) == "full+guard=false"
    assert config_label(E2EConfig.FULL, []) == "full"


def test_unknown_pipeline_option_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown pipeline option 'rerank'"):
        parse_pipeline_options(PipelineOptions(), ["rerank=false"])
    with pytest.raises(ValueError, match="guard"):
        parse_pipeline_options(PipelineOptions(), ["guard=maybe"])


def test_retriever_variants_change_only_retrieval_settings() -> None:
    base = base_settings()
    assert settings_for(base, E2EConfig.BM25).retrieval.mode == "bm25"
    assert settings_for(base, E2EConfig.DENSE).retrieval.mode == "dense"
    assert settings_for(base, E2EConfig.HYBRID_K60).retrieval.rrf_k == 60
    assert settings_for(base, E2EConfig.HYBRID_K60).retrieval.mode == "hybrid"
    assert pipeline_for(E2EConfig.NO_GUARD) == PipelineOptions(guard=False)
```

`pharma-lab/tests/e2e/test_report.py` (append):

```python
def test_report_loads_swept_config_directories(tmp_path: Path) -> None:
    run_root = _write_judged_run(
        tmp_path, configs=("full", "full+refine_threshold=0.5")
    )
    written = write_report(
        run_root, {golden(n).item_id: golden(n) for n in range(1, 5)}
    )
    rows = list(
        csv.DictReader((run_root / "reports" / "ablation.csv").open(encoding="utf-8"))
    )
    assert {r["config"] for r in rows} == {"full+refine_threshold=0.5"}
```

(extend `_write_judged_run` with a `configs` parameter defaulting to `("full", "one-step")`.)

- [ ] **Step 2: Run them, watch them fail**

Run: `cd backend && uv run pytest tests/application/test_chat_graph.py -q -k no_guard`; `cd pharma-lab && uv run pytest tests/e2e/test_run_setup.py tests/e2e/test_report.py -q -k "pipeline_option or retriever_variants or swept"`
Expected: FAIL — `PipelineOptions.__init__() got an unexpected keyword argument 'guard'`; `parse_pipeline_options` undefined; `E2EConfig` has no member `BM25`.

- [ ] **Step 3: Backend**

`context.PipelineOptions`:

```python
@dataclass(frozen=True)
class PipelineOptions:
    """Steps of the agent loop. Only the evaluation harness turns any of them off."""

    rephrase: bool = True
    judge_refine: bool = True
    guard: bool = True
```

`nodes.guard_node`, after `_emit(...)`:

```python
if not runtime.context.pipeline.guard:
    run.record_guard(
        Verdict(
            passed=True,
            in_scope=True,
            source=VerdictSource.SKIPPED,
            reason="guard disabled",
        ),
        now=deps.clock.now(),
    )
    return {"run": run}
```

(import `Verdict` from `pharma_agent.domain.guardrail.models`.)

- [ ] **Step 4: pharma-lab**

`configs.py`:

```python
class E2EConfig(StrEnum):
    FULL = "full"
    ONE_STEP = "one-step"
    NO_JUDGE_REFINE = "no-judge-refine"
    NO_REPHRASE = "no-rephrase"
    NO_RERANK = "no-rerank"
    NO_GUARD = "no-guard"
    # Retriever variants of the full agent (spec v2 §2.6, §4.D D6).
    BM25 = "bm25"
    DENSE = "dense"
    HYBRID_K60 = "hybrid-k60"
    CLOSED_BOOK = "closed-book"
```

`_PIPELINES[E2EConfig.NO_GUARD] = PipelineOptions(guard=False)`; the three retriever variants map to `PipelineOptions()`. In `settings_for`:

```python
    if config is E2EConfig.BM25:
        retrieval = retrieval.model_copy(update={"mode": "bm25"})
    elif config is E2EConfig.DENSE:
        retrieval = retrieval.model_copy(update={"mode": "dense"})
    elif config is E2EConfig.HYBRID_K60:
        retrieval = retrieval.model_copy(update={"mode": "hybrid", "rrf_k": 60})
```

Add:

```python
def parse_pipeline_options(
    base: PipelineOptions, pairs: Sequence[str]
) -> PipelineOptions:
    """`key=value` overrides of PipelineOptions; bools are true/false, None is none."""
    types = {field.name: field.type for field in fields(PipelineOptions)}
    updates: dict[str, object] = {}
    for pair in pairs:
        key, sep, raw = pair.partition("=")
        if not sep or key not in types:
            raise ValueError(
                f"unknown pipeline option {key!r}; known: {', '.join(types)}"
            )
        updates[key] = _coerce(key, types[key], raw.strip())
    return replace(base, **updates)


def _coerce(key: str, annotation: object, raw: str) -> object:
    text = str(annotation)
    if raw.lower() == "none" and "None" in text:
        return None
    if text.startswith("bool") or text == "bool":
        if raw.lower() in {"true", "false"}:
            return raw.lower() == "true"
        raise ValueError(f"pipeline option {key} takes true or false, not {raw!r}")
    if "float" in text:
        return float(raw)
    return raw


def config_label(config: E2EConfig, pairs: Sequence[str]) -> str:
    """Directory name of a configuration with its options, e.g. full+refine_threshold=0.5."""
    return "+".join(
        [str(config), *(f"{k}={v}" for k, v in (p.split("=", 1) for p in pairs))]
    )
```

(`from dataclasses import fields, replace`; annotations are strings under `from __future__ import annotations`, hence the text checks. Phase 1 adds `refine_threshold: float | None` and `refine_mode: str`, which these rules already cover.)

`run_identity.RunIdentity.pipeline: dict[str, object]`; `identity_from_settings(..., pipeline: dict[str, object], ...)`.

`harness.E2ERunRequest`: add `pipeline_options: tuple[str, ...] = ()`. In `run_e2e`: `pipeline = parse_pipeline_options(pipeline_for(request.config), request.pipeline_options)`; `label = config_label(request.config, request.pipeline_options)`; `directory = config_dir(request.run_root, label)`; pass `config=label` to `identity_from_settings`, the executors and `run_items`.

`JudgeRequest.config: str`; `run_judge` uses `config_dir(request.run_root, request.config)` unchanged. CLI `e2e judge --config` becomes `str` (help: "configuration directory name, e.g. full or full+refine_threshold=0.5"). CLI `e2e run` gains `pipeline_option: Annotated[list[str] | None, typer.Option("--pipeline-option", help="key=value override of PipelineOptions; repeatable")] = None` passed as `tuple(pipeline_option or ())`.

`report._load`: iterate `sorted(p for p in Path(run_root).iterdir() if p.is_dir() and (p / JUDGMENTS_FILE).is_file())`, keyed by `p.name`. Every `CONFIG_LABELS[config]` becomes `CONFIG_LABELS.get(config, config)`; add labels `"no-guard": "w/o guard"`, `"bm25": "BM25 retriever"`, `"dense": "Dense retriever"`, `"hybrid-k60": "Hybrid, RRF k=60"`. `_ablation_tables` already compares every non-`full` config with `full`.

`calibration.export_calibration(configs: Sequence[E2EConfig])` keeps working for enum members; `config_dir` already accepts `str`.

- [ ] **Step 5: Run the tests**

Run: `cd backend && uv run pytest -q && uv run lint-imports`; `cd pharma-lab && uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/pharma_agent/application/chat/context.py backend/src/pharma_agent/application/chat/nodes.py backend/tests/application/test_chat_graph.py pharma-lab/src/pharma_lab/e2e/configs.py pharma-lab/src/pharma_lab/e2e/run_identity.py pharma-lab/src/pharma_lab/e2e/harness.py pharma-lab/src/pharma_lab/e2e/judging/service.py pharma-lab/src/pharma_lab/e2e/report.py pharma-lab/src/pharma_lab/cli/commands/e2e.py pharma-lab/tests/e2e/test_run_setup.py pharma-lab/tests/e2e/test_report.py
git commit -m "feat(e2e): guard switch, --pipeline-option sweeps and retriever variants"
```

---

### Task 6: Judge reasoning as a recorded option

**Files:**
- Modify: `pharma-lab/src/pharma_lab/e2e/judging/structured.py:16-17,149-170` (`JUDGE_REASONING`, `judge_llm_settings`, `judge_llm`), `pharma-lab/src/pharma_lab/e2e/judging/service.py:119-145` (`JudgeRequest.judge_reasoning`, `pin_judge`), `pharma-lab/src/pharma_lab/cli/commands/e2e.py` (`--judge-reasoning`)
- Test: `pharma-lab/tests/e2e/test_judge_service.py`

**Interfaces:**
- Produces: `DEFAULT_JUDGE_REASONING = "medium"` (Task 10 may change it to `"none"`); `JudgeRequest.judge_reasoning: str`; `judge.json` = `{"model", "reasoning_effort", "base_url"}`.

- [ ] **Step 1: Write the failing test**

```python
def test_pin_judge_records_reasoning_and_endpoint(tmp_path: Path) -> None:
    pin_judge(
        tmp_path,
        model="gemini-3.1-flash-lite",
        reasoning="none",
        base_url="http://127.0.0.1:8317/v1",
        force=False,
    )
    stored = json.loads((tmp_path / "judge.json").read_text("utf-8"))
    assert stored == {
        "model": "gemini-3.1-flash-lite",
        "reasoning_effort": "none",
        "base_url": "http://127.0.0.1:8317/v1",
    }
    with pytest.raises(ValueError, match="--force"):
        pin_judge(
            tmp_path,
            model="gemini-3.1-flash-lite",
            reasoning="medium",
            base_url="http://127.0.0.1:8317/v1",
            force=False,
        )
```

- [ ] **Step 2: Run it, watch it fail**

Run: `cd pharma-lab && uv run pytest tests/e2e/test_judge_service.py -q -k pin_judge`
Expected: FAIL — `pin_judge() got an unexpected keyword argument 'reasoning'`.

- [ ] **Step 3: Implement**

`structured.py`: rename the constant to `DEFAULT_JUDGE_REASONING = "medium"`; `judge_llm_settings(settings, model=JUDGE_MODEL, reasoning=DEFAULT_JUDGE_REASONING)` sets `reasoning_effort=reasoning`; `judge_llm(settings, model, reasoning)` passes it on. `service.JudgeRequest.judge_reasoning: str = DEFAULT_JUDGE_REASONING`; `pin_judge(directory, *, model, reasoning, base_url, force)` writes the three keys; `run_judge` calls `pin_judge(directory, model=request.judge_model, reasoning=request.judge_reasoning, base_url=settings.llm.default.base_url or "", force=request.force)` and `judge_llm(settings, request.judge_model, request.judge_reasoning)`; `build_ragas_scorer` receives the same reasoning (check its signature in `ragas_scorer.py` and thread the value through its `LlmSettings` the same way). CLI: `judge_reasoning: Annotated[str, typer.Option("--judge-reasoning", help="none, low or medium")] = DEFAULT_JUDGE_REASONING`.

- [ ] **Step 4: Run the tests**

Run: `cd pharma-lab && uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pharma-lab/src/pharma_lab/e2e/judging pharma-lab/src/pharma_lab/cli/commands/e2e.py pharma-lab/tests/e2e/test_judge_service.py
git commit -m "feat(e2e): judge reasoning effort is an option recorded in judge.json"
```

---

### Task 7: `e2e compare --run A --run B`

**Files:**
- Create: `pharma-lab/src/pharma_lab/e2e/compare.py`
- Modify: `pharma-lab/src/pharma_lab/cli/commands/e2e.py` (new command), `pharma-lab/src/pharma_lab/e2e/report.py` (make `_values`, `_load`, `_write_csv`, `_write_tex`, `_cell`, `summarise` importable as public names: `values_of`, `load_run`, `write_csv`, `write_tex`, `cell`; keep the old private names as aliases so existing tests pass)
- Test: `pharma-lab/tests/e2e/test_compare.py`

**Interfaces:**
- Consumes: `load_run(run_root)`, `values_of(...)`, `paired_test`, `holm`, `bootstrap_mean` (statistics).
- Produces: `CompareRow(metric, n, mean_a, mean_b, delta, ci_low, ci_high, p_value, p_holm, same_judge: bool)`; `compare_runs(run_a: Path, run_b: Path, config: str, items, relevance) -> list[CompareRow]`; files `<run_b>/reports/compare-<run_a.name>-<config>.csv|tex`.

- [ ] **Step 1: Write the failing tests**

```python
def test_compare_pairs_shared_items_and_marks_judges(tmp_path: Path) -> None:
    a = _write_judged_run(tmp_path / "a", recall={1: 1.0, 2: 1.0, 3: 0.0, 4: 1.0})
    b = _write_judged_run(tmp_path / "b", recall={1: 0.0, 2: 1.0, 3: 0.0, 4: 0.0})
    rows = compare_runs(
        a, b, "full", {golden(n).item_id: golden(n) for n in range(1, 5)}, None
    )
    recall = next(r for r in rows if r.metric == "nugget_recall")
    assert recall.n == 4 and recall.delta == pytest.approx(-0.5)
    assert recall.same_judge is True
    assert (b / "reports" / "compare-a-full.csv").is_file()
    assert (b / "reports" / "compare-a-full.tex").is_file()


def test_compare_refuses_disjoint_runs(tmp_path: Path) -> None:
    a = _write_judged_run(tmp_path / "a", item_numbers=(1, 2))
    b = _write_judged_run(tmp_path / "b", item_numbers=(3, 4))
    with pytest.raises(ValueError, match="no item in common"):
        compare_runs(
            a, b, "full", {golden(n).item_id: golden(n) for n in range(1, 5)}, None
        )
```

(`_write_judged_run` from `test_report.py` moves to `tests/e2e/report_fixtures.py` with parameters `configs`, `recall: Mapping[int, float] | None`, `item_numbers`.)

- [ ] **Step 2: Run them, watch them fail**

Run: `cd pharma-lab && uv run pytest tests/e2e/test_compare.py -q`
Expected: FAIL — `No module named pharma_lab.e2e.compare`.

- [ ] **Step 3: Write `compare.py`**

```python
"""Paired comparison of one configuration across two runs (spec v2 §4.E)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pharma_lab.e2e.golden import GoldenItem
from pharma_lab.e2e.judging.service import JUDGE_FILE
from pharma_lab.e2e.report import (
    METRICS,
    REPORTS_DIR,
    cell,
    load_run,
    values_of,
    write_csv,
    write_tex,
)
from pharma_lab.e2e.statistics import bootstrap_mean, holm, paired_test
from pharma_lab.evaluation.relevance_judgments import LoadedJudgments


@dataclass(frozen=True)
class CompareRow:
    metric: str
    n: int
    mean_a: float
    mean_b: float
    delta: float
    ci_low: float
    ci_high: float
    p_value: float
    p_holm: float
    same_judge: bool


def _judge(run_root: Path, config: str) -> dict[str, object]:
    path = run_root / config / JUDGE_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def compare_runs(
    run_a: Path,
    run_b: Path,
    config: str,
    items: Mapping[str, GoldenItem],
    relevance: LoadedJudgments | None,
) -> list[CompareRow]:
    values_a = _config_values(run_a, config, items, relevance)
    values_b = _config_values(run_b, config, items, relevance)
    same_judge = _judge(run_a, config) == _judge(run_b, config)
    rows: list[CompareRow] = []
    p_values: list[float] = []
    for metric in METRICS:
        shared = sorted(set(values_a[metric.name]) & set(values_b[metric.name]))
        if not shared:
            continue
        differences = [
            values_b[metric.name][k] - values_a[metric.name][k] for k in shared
        ]
        interval = bootstrap_mean(differences)
        test = paired_test(differences)
        rows.append(
            CompareRow(
                metric.name,
                len(shared),
                sum(values_a[metric.name][k] for k in shared) / len(shared),
                sum(values_b[metric.name][k] for k in shared) / len(shared),
                interval.mean,
                interval.ci_low,
                interval.ci_high,
                test.p_value,
                1.0,
                same_judge,
            )
        )
        p_values.append(test.p_value)
    if not rows:
        raise ValueError(
            f"{run_a.name} and {run_b.name} have no item in common for {config}"
        )
    adjusted = holm(p_values)
    rows = [
        CompareRow(**{**row.__dict__, "p_holm": p})
        for row, p in zip(rows, adjusted, strict=True)
    ]
    _write(run_b, run_a.name, config, rows)
    return rows


def _config_values(run_root, config, items, relevance):
    answers, judgments, role_models = load_run(run_root)[config]
    return values_of(items, answers, judgments, relevance, role_models)


def _write(run_b: Path, name_a: str, config: str, rows: list[CompareRow]) -> None:
    directory = run_b / REPORTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    write_csv(
        directory / f"compare-{name_a}-{config}.csv",
        [
            "metric",
            "n",
            "mean_a",
            "mean_b",
            "delta",
            "ci_low",
            "ci_high",
            "p_value",
            "p_holm",
            "same_judge",
        ],
        [
            [
                r.metric,
                r.n,
                r.mean_a,
                r.mean_b,
                r.delta,
                r.ci_low,
                r.ci_high,
                r.p_value,
                r.p_holm,
                r.same_judge,
            ]
            for r in rows
        ],
    )
    write_tex(
        directory / f"compare-{name_a}-{config}.tex",
        f"Paired comparison of {config}: {run_b.name} minus {name_a}, mean difference [95\\% CI]; * marks Holm-adjusted p < 0.05.",
        f"tab:e2e-compare-{config}",
        ["Metric", name_a, run_b.name, "$\\Delta$"],
        [
            [
                r.metric,
                f"{r.mean_a:.3f}",
                f"{r.mean_b:.3f}",
                f"{r.delta:+.3f} [{r.ci_low:+.3f}, {r.ci_high:+.3f}]"
                + ("*" if r.p_holm < 0.05 else ""),
            ]
            for r in rows
            if next(m for m in METRICS if m.name == r.metric).primary
        ],
    )
```

(`PairedTest` has `p_value`; check the attribute name in `statistics.py:62-66` and use it.) CLI:

```python
@e2e_app.command("compare")
def compare(
    ctx: typer.Context,
    run_a: Annotated[str, typer.Option("--run-a")],
    run_b: Annotated[str, typer.Option("--run-b")],
    config: Annotated[str, typer.Option("--config")] = "full",
    golden: Annotated[Path, typer.Option("--golden", dir_okay=False)] = GOLDEN_E2E_PATH,
    evaluation: Annotated[
        Path, typer.Option("--evaluation", dir_okay=False)
    ] = GOLD_PATH,
) -> None:
    """Paired sign-flip test of one configuration between two runs."""
```

building `items` and `relevance` as `report` does and returning `CommandResult("e2e compare", COMPLETE, e2e_run_dir(run_b) / "reports", {row.metric: f"{row.delta:+.3f} p_holm={row.p_holm:.3f}" for row in rows if row.p_holm < 0.05})`.

- [ ] **Step 4: Run the tests**

Run: `cd pharma-lab && uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pharma-lab/src/pharma_lab/e2e/compare.py pharma-lab/src/pharma_lab/e2e/report.py pharma-lab/src/pharma_lab/cli/commands/e2e.py pharma-lab/tests/e2e/test_compare.py pharma-lab/tests/e2e/report_fixtures.py pharma-lab/tests/e2e/test_report.py
git commit -m "feat(e2e): compare one configuration across two runs with a paired test"
```

---

### Task 8: Latency from a concurrency-1 run: `e2e report --latency-run`

**Files:**
- Modify: `pharma-lab/src/pharma_lab/e2e/report.py` (`write_report(..., latency_root: Path | None = None)`, `_main_tables`, `_cost_table`), `pharma-lab/src/pharma_lab/e2e/run_identity.py` (record `concurrency`), `pharma-lab/src/pharma_lab/e2e/harness.py`, `pharma-lab/src/pharma_lab/cli/commands/e2e.py` (`report --latency-run`)
- Test: `pharma-lab/tests/e2e/test_report.py`

**Interfaces:**
- Produces: `RunIdentity` keeps its fields; `run.json` gains informational `concurrency` (listed in `INFORMATIONAL` so a resume with another concurrency is allowed but recorded); `latency_values(latency_root, config) -> dict[str, dict[str, float]]` with keys `latency_seconds`, `llm_seconds_per_turn`, `retrieval_seconds_per_turn`, `rerank_seconds_per_turn`, `decision_seconds_per_turn`; `provenance.json` records `latency_run`.

- [ ] **Step 1: Write the failing tests**

```python
def test_latency_rows_come_from_the_latency_run(tmp_path: Path) -> None:
    quality = _write_judged_run(
        tmp_path / "q", latency={1: 10.0, 2: 10.0, 3: 10.0, 4: 10.0}
    )
    slow = _write_judged_run(tmp_path / "c1", latency={1: 2.0, 2: 2.0, 3: 2.0, 4: 2.0})
    write_report(
        quality, {golden(n).item_id: golden(n) for n in range(1, 5)}, latency_root=slow
    )
    rows = list(
        csv.DictReader((quality / "reports" / "cost.csv").open(encoding="utf-8"))
    )
    p50 = next(
        r for r in rows if r["config"] == "full" and r["metric"] == "latency_p50"
    )
    assert float(p50["mean"]) == 2.0
    provenance = json.loads(
        (quality / "reports" / "provenance.json").read_text("utf-8")
    )
    assert provenance["latency_run"] == str(slow)


def test_latency_run_requires_the_same_config(tmp_path: Path) -> None:
    quality = _write_judged_run(tmp_path / "q", configs=("full", "one-step"))
    slow = _write_judged_run(tmp_path / "c1", configs=("full",))
    with pytest.raises(ValueError, match="one-step"):
        write_report(
            quality,
            {golden(n).item_id: golden(n) for n in range(1, 5)},
            latency_root=slow,
        )
```

- [ ] **Step 2: Run them, watch them fail**

Run: `cd pharma-lab && uv run pytest tests/e2e/test_report.py -q -k latency_run`
Expected: FAIL — `write_report() got an unexpected keyword argument 'latency_root'`.

- [ ] **Step 3: Implement**

`report.py`:

```python
LATENCY_METRICS = (
    "latency_seconds",
    "llm_seconds_per_turn",
    "retrieval_seconds_per_turn",
    "rerank_seconds_per_turn",
    "decision_seconds_per_turn",
)


def latency_values(latency_root: Path, config: str) -> dict[str, Values]:
    """Per-item seconds of one configuration of the concurrency-1 run; judgments not needed."""
    path = config_dir(latency_root, config) / ANSWERS_FILE
    if not path.is_file():
        raise ValueError(f"latency run {latency_root} has no {config} answers")
    answers = JsonlStore(path, AnswerRecord).latest()
    by_name = {m.name: m for m in METRICS}
    table: dict[str, Values] = {name: {} for name in LATENCY_METRICS}
    for key, record in answers.items():
        if record.error is not None:
            continue
        view = ItemView(
            None, record, None, {}
        )  # metrics in LATENCY_METRICS read only the answer
        for name in LATENCY_METRICS:
            value = by_name[name].read(view)
            if value is not None:
                table[name][key] = value
    return table
```

(`ItemView.item` and `.judgement` become `GoldenItem | None` / `Judgement | None`; the latency metrics only touch `v.answer`.) In `write_report`, when `latency_root` is given, replace `values[config][name]` for every `name in LATENCY_METRICS` and every config by `latency_values(latency_root, config)[name]` before the tables are written; `_provenance(...)` gets `latency_run=str(latency_root) if latency_root else None`. `harness.run_e2e`: pass `concurrency=request.concurrency` into the `run.json` extras (extend `open_run(directory, identity, *, commit, extra: dict[str, object] | None = None)` and add `"concurrency"` to `INFORMATIONAL`). CLI `report`: `latency_run: Annotated[str | None, typer.Option("--latency-run", help="run name whose concurrency-1 answers supply every latency number")] = None` → `latency_root=e2e_run_dir(latency_run) if latency_run else None`.

- [ ] **Step 4: Run the tests**

Run: `cd pharma-lab && uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pharma-lab/src/pharma_lab/e2e/report.py pharma-lab/src/pharma_lab/e2e/run_identity.py pharma-lab/src/pharma_lab/e2e/harness.py pharma-lab/src/pharma_lab/cli/commands/e2e.py pharma-lab/tests/e2e/test_report.py pharma-lab/tests/e2e/report_fixtures.py
git commit -m "feat(e2e): latency numbers come from a concurrency-1 run"
```

---

### Task 8b: `e2e embed-server` — the query embedding served on Kaggle

The agent embeds every search query with the chosen embedding model. On the laptop's CPU a 4B or 8B model takes seconds per query and would dominate the latency split, so the embedding is served like the reranker: its own kernel, its own account, replicated 2×1, through a tunnel. The tests below use `qwen3-embedding:8b-q8_0` as the example; the command takes any catalog embedding model.

**Files:**
- Modify: `pharma-lab/src/pharma_lab/integrations/kaggle/models.py:124-126` (`StageName.EMBED_SERVE = "embed-serve"`), `pharma-lab/src/pharma_lab/integrations/kaggle/stages.py:423-424` (register `ModelServeStage(StageName.EMBED_SERVE, ModelKind.EMBEDDING)`), `pharma-lab/src/pharma_lab/e2e/model_server.py:76-100,214-220,272-300` (`env_lines`, `serve_stage`, `_serve_profile`), `pharma-lab/src/pharma_lab/cli/commands/e2e.py:552-600` (`embed-server` command next to `rerank-server`)
- Test: `pharma-lab/tests/e2e/test_model_server.py`, `pharma-lab/tests/integrations/kaggle/test_stages.py`

**Interfaces:**
- Produces: `uv run pharma-lab e2e embed-server --model qwen3-embedding:8b-q8_0 --hours H --kaggle-account accN|auto` writing `data/work/serve/qwen3_embedding_8b_q8_0.env` with `PHARMA_RETRIEVAL__EMBEDDING__BASE_URL=<url>/v1`, `PHARMA_RETRIEVAL__EMBEDDING__API_KEY`, `PHARMA_RETRIEVAL__EMBEDDING__MODEL=qwen3-embedding:8b-q8_0`, `PHARMA_RETRIEVAL__EMBEDDING__DIMENSION=4096`, `PHARMA_RETRIEVAL__EMBEDDING__TIMEOUT_SECONDS=120`.

- [ ] **Step 1: Write the failing tests**

`tests/e2e/test_model_server.py` (append; the file already tests `env_lines` for the reranker):

```python
def test_env_lines_for_an_embedding_model_point_the_backend_embedder_at_the_tunnel() -> (
    None
):
    text = env_lines(
        model="qwen3-embedding:8b-q8_0", url="https://x.trycloudflare.com", api_key="k"
    )
    assert (
        "PHARMA_RETRIEVAL__EMBEDDING__BASE_URL=https://x.trycloudflare.com/v1\n" in text
    )
    assert "PHARMA_RETRIEVAL__EMBEDDING__MODEL=qwen3-embedding:8b-q8_0\n" in text
    assert "PHARMA_RETRIEVAL__EMBEDDING__DIMENSION=4096\n" in text
    assert "PHARMA_RETRIEVAL__EMBEDDING__API_KEY=k\n" in text


def test_serve_stage_of_an_embedding_model() -> None:
    assert serve_stage("qwen3-embedding:8b-q8_0") is StageName.EMBED_SERVE
```

`tests/integrations/kaggle/test_stages.py` (append):

```python
def test_embed_serve_stage_builds_a_serve_job_for_an_embedding_model(tmp_path) -> None:
    job = get_stage_adapter(StageName.EMBED_SERVE).build_job(
        serve_request(StageName.EMBED_SERVE, "qwen3-embedding:8b-q8_0", tmp_path)
    )
    assert job.worker_config["model"] == "qwen3-embedding:8b-q8_0"
```

(`serve_request` is the helper the file's `rerank-serve` test uses to build a `StageRequest` with a `runtime_profile`; if it is inlined there, inline the same construction.)

- [ ] **Step 2: Run them, watch them fail**

Run: `cd pharma-lab && uv run pytest tests/e2e/test_model_server.py tests/integrations/kaggle/test_stages.py -q -k embed`
Expected: FAIL — `StageName` has no member `EMBED_SERVE`; `serve_stage` raises "must select a reranker or a chat model".

- [ ] **Step 3: Implement**

`models.StageName`: `EMBED_SERVE = "embed-serve"` with the comment "# A query embedding model served over a tunnel for the E2E runs (spec v2 §2.1b)." `stages.py`: `StageName.EMBED_SERVE: ModelServeStage(StageName.EMBED_SERVE, ModelKind.EMBEDDING)`; confirm `ModelServeStage` validates the kind the way it does for rerankers (read its `build_job`), and that the serve worker passes `--embedding` to llama-server for `ModelKind.EMBEDDING` (`workers/runtime.py:390` already does). `model_server.env_lines`: a third branch

```python
    elif spec.kind is ModelKind.EMBEDDING:
        pairs = [
            ("PHARMA_RETRIEVAL__EMBEDDING__BASE_URL", f"{url}/v1"),
            ("PHARMA_RETRIEVAL__EMBEDDING__API_KEY", api_key),
            ("PHARMA_RETRIEVAL__EMBEDDING__MODEL", model),
            ("PHARMA_RETRIEVAL__EMBEDDING__DIMENSION", str(spec.vector_dimension)),
            ("PHARMA_RETRIEVAL__EMBEDDING__TIMEOUT_SECONDS", "120"),
        ]
```

`serve_stage`: `if kind is ModelKind.EMBEDDING: return StageName.EMBED_SERVE`. `_serve_profile`: for an embedding model, the production profile of the corpus-embed benchmark (`spec.embedding_search_space.query` candidates; take the stored benchmark profile exactly as the reranker branch takes `rerank-benchmark`'s, with `benchmark_stage=StageName.QUERY_EMBED_BENCHMARK.value`). CLI: `embed-server` mirrors `rerank-server` with default model `qwen3-embedding:8b-q8_0`.

- [ ] **Step 4: Run the tests and a real serve**

Run: `cd pharma-lab && uv run pytest -q`, then `uv run pharma-lab e2e embed-server --model qwen3-embedding:8b-q8_0 --hours 1 --kaggle-account acc3` in tmux; when the env file appears, `set -a; . data/work/serve/qwen3_embedding_8b_q8_0.env; set +a; curl -s "$PHARMA_RETRIEVAL__EMBEDDING__BASE_URL/embeddings" -H "Authorization: Bearer $PHARMA_RETRIEVAL__EMBEDDING__API_KEY" -d '{"model":"qwen3-embedding:8b-q8_0","input":"paracetamol liều dùng"}' | python3 -c "import json,sys; print(len(json.load(sys.stdin)['data'][0]['embedding']))"`
Expected: tests PASS; the curl prints `4096`.

- [ ] **Step 5: Commit**

```bash
git add pharma-lab/src/pharma_lab/integrations/kaggle/models.py pharma-lab/src/pharma_lab/integrations/kaggle/stages.py pharma-lab/src/pharma_lab/e2e/model_server.py pharma-lab/src/pharma_lab/cli/commands/e2e.py pharma-lab/tests/e2e/test_model_server.py pharma-lab/tests/integrations/kaggle/test_stages.py
git commit -m "feat(e2e): embed-server serves the query embedding model on Kaggle"
```

---

### Task 9: Documentation

**Files:**
- Modify: `pharma-lab/docs/guides/e2e-evaluation.md` (§1 model paths, §3 configs table, options, judge reasoning, compare, latency protocol, cost table), `pharma-lab/docs/guides/cli-reference.md` (`e2e run --pipeline-option`, `e2e judge --judge-reasoning`, `e2e compare`, `e2e report --latency-run`)

- [ ] **Step 1: Write the sections**

In `e2e-evaluation.md`:
- §1: add the three model paths of spec §2.1b as a table (model, proxy id or Kaggle command, thinking setting, price source); note that `claude-opus-5-5` runs with `PHARMA_LLM__ROLES__<ROLE>__REASONING_EFFORT=minimal` and that the report prints its measured reasoning tokens. State that the agent layer's embedding and reranker are the pair chosen from the retrieval table (name them once Task 11 Step 0 has run, with the rule and the numbers), each served on Kaggle (`e2e embed-server`, `e2e rerank-server`) on its own account, with the LLM on a third; replace the `compose.local-models.yaml` embedding paragraph accordingly (the CPU embedder stays a demo path only).
- §3 configs table: add rows `no-guard`, `bm25`, `dense`, `hybrid-k60`; a paragraph on `--pipeline-option key=value` (repeatable; the directory becomes `full+key=value`; such directories appear in `ablation.csv` against `full`).
- Judge: `--judge-reasoning none|low|medium` (default from Task 10), `judge.json` fields.
- New paragraph "Độ trễ và chi phí": the concurrency-1 protocol, `--latency-run`, `cost.csv|tex` columns, the price table in `pharma_lab/e2e/pricing.py` with date and sources, the retrieval pricing rule (reranked candidates × 1,001 tokens, query chars ÷ 3.1).
- New paragraph "So sánh hai run": `uv run pharma-lab e2e compare --run-a e2e-v2-gemini --run-b e2e-v2-qwen9b --config full`.

- [ ] **Step 2: Commit**

```bash
git add pharma-lab/docs/guides/e2e-evaluation.md pharma-lab/docs/guides/cli-reference.md
git commit -m "docs(e2e): model paths, pipeline options, cost and latency protocol, compare"
```

---

### Task 10: Judge reasoning `none` against the v1 pharmacist grades

**Files:**
- Create: `docs/research/paper-v2/09-phase-0-results.md` (section "Judge reasoning")
- Modify (possibly): `pharma-lab/src/pharma_lab/e2e/judging/structured.py` (`DEFAULT_JUDGE_REASONING`)

**Interfaces:**
- Consumes: v1 archive (`vipharmind-data` version 1): `evaluation/e2e/runs/e2e-gemini/{full,one-step,closed-book}/answers.jsonl`, `.../calibration/{items.jsonl,key.json,grades.jsonl,agreement.json}`, the same under `e2e-qwen35-9b`, and `evaluation/e2e/golden_e2e.jsonl` of v1.

- [ ] **Step 1: Restore v1 into a separate workspace root**

```bash
cd pharma-lab
mkdir -p data/work/v1-root
PHARMA_LAB_ROOT=$PWD/data/work/v1-root uv run pharma-lab data pull --version 1 --kaggle-account acc1
ls data/work/v1-root/data/evaluation/e2e/runs/
```

Expected: `e2e-gemini` and `e2e-qwen35-9b` present with `calibration/grades.jsonl`. (`PHARMA_LAB_ROOT` is `WORKSPACE_ROOT_ENV` in `config/paths.py`; it keeps the 4.9 GB archive away from the v2 `data/`.)

- [ ] **Step 2: Copy each run's answers and calibration into a new run root of the v2 workspace**

```bash
for R in e2e-gemini e2e-qwen35-9b; do
  SRC=data/work/v1-root/data/evaluation/e2e/runs/$R; DST=data/evaluation/e2e/runs/$R-judge-none
  for C in full one-step closed-book; do mkdir -p $DST/$C; cp $SRC/$C/answers.jsonl $SRC/$C/run.json $DST/$C/; done
  cp -r $SRC/calibration $DST/
done
cp data/work/v1-root/data/evaluation/e2e/golden_e2e.jsonl data/work/v1-root/golden_v1.jsonl
```

- [ ] **Step 3: Judge with reasoning `none` and score the agreement**

In tmux, with `cli-proxy-api` up (`docker compose -f ../compose.yaml -f ../compose.llm-proxy.yaml up -d cli-proxy-api`) and `backend/.env` pointing `PHARMA_LLM__DEFAULT__BASE_URL=http://127.0.0.1:8317/v1`, `PHARMA_LLM__DEFAULT__API_KEY=proxypal-local`:

```bash
for R in e2e-gemini-judge-none e2e-qwen35-9b-judge-none; do
  for C in full one-step closed-book; do
    uv run pharma-lab e2e judge --run $R --config $C --golden data/work/v1-root/golden_v1.jsonl --judge-model gemini-3.1-flash-lite --judge-reasoning none --force
  done
  uv run pharma-lab e2e calibration score --run $R --golden data/work/v1-root/golden_v1.jsonl
done
```

Expected: `runs/<R>/calibration/agreement.json` for both runs. (Each `calibration score` checks that the blind items still match; the answers are byte-copies, so they do.)

- [ ] **Step 4: Decide**

Compare `agreement.json` of each `-judge-none` run with the v1 `agreement.json` (`medium`), per metric row (`percent_agreement`, `cohen_kappa`, `gwet_ac1` for binary labels, `spearman` for continuous). Rule: use `none` for every v2 run when, for both runs, no `gwet_ac1` or `spearman` value drops by more than 0.05; otherwise keep `medium`. Write the table (metric, medium, none, difference) and the decision into `docs/research/paper-v2/09-phase-0-results.md` §"Judge reasoning", with the spec's rationale (§2.1b). If `none` wins, set `DEFAULT_JUDGE_REASONING = "none"` and update the guide's default.

- [ ] **Step 5: Commit**

```bash
git add docs/research/paper-v2/09-phase-0-results.md pharma-lab/src/pharma_lab/e2e/judging/structured.py pharma-lab/docs/guides/e2e-evaluation.md pharma-lab/data/evaluation/e2e/runs/e2e-gemini-judge-none/*/judge.json pharma-lab/data/evaluation/e2e/runs/e2e-qwen35-9b-judge-none/*/judge.json
git commit -m "docs: judge reasoning effort chosen on the v1 pharmacist grades"
```

---

### Task 11: Re-run A1 (Gemini) and A2 (Qwen3.5-9B) with seconds and USD

Prerequisite: phase D's v2 golden set (`e2e golden build`, Task 7b of the phase D plan) and the phase D retrieval table complete (five dense runs, four rerankers on `hybrid-qwen4b-v2-p50-k20-rrf2`, D1's rerank on `dense-qwen4b-v2-k20`). All runs read the same `backend/.env` plus the exports below; logs in `data/work/logs-p0/`.

- [ ] **Step 0: Choose the agent's embedding and reranker from the retrieval table**

Rule (spec §0: numbers in the paper come from report files; user decision 2026-10-16: choose the best pair from the results, not in advance):
1. Reranker: among the four `reports/rerank/<slug>/top20/report.md` of `hybrid-qwen4b-v2-p50-k20-rrf2`, take the highest nDCG@5; when the next smaller reranker is within 1.0 point of nDCG@5 (×100), take the smaller one (same quality, cheaper and faster; D4's cost column justifies it).
2. Embedding: among the five `dense-<model>-v2-k20` baseline reports, take the highest nDCG@5 with the same "within 1.0 point, take the smaller" rule. If the choice is not Qwen3-Embedding-4B, build the agent's hybrid run on it before the e2e runs: `uv run pharma-lab retrieve --run hybrid-<slug>-v2-p50-k20-rrf2 --retriever hybrid --prefetch-k 50 --candidate-k 20 --rrf-k 2` with that model's release published, then `rerank` with the chosen reranker and `metrics --top-k 20`; the paper's agent row reports that run.
3. Write the choice, the rule and the two tables into `docs/research/paper-v2/09-phase-0-results.md` §"Retrieval pair of the agent", and set `<EMB>`, `<RER>`, `<EMB_SLUG>`, `<EMB_DIM>` for the steps below (Qdrant alias `eval_<EMB_SLUG>`; dimensions from `runtime/catalog.py`).

Expected: a section with the two tables and one sentence per choice.

- [ ] **Step 1: Shared services**

```bash
cd pharma-lab
docker compose -f ../compose.yaml -f ../compose.llm-proxy.yaml up -d cli-proxy-api
tmux new -d -s rerank-serve "uv run pharma-lab e2e rerank-server --model <RER> --hours 11 --kaggle-account acc2 > data/work/logs-p0/rerank-serve.log 2>&1"
tmux new -d -s embed-serve "uv run pharma-lab e2e embed-server --model <EMB> --hours 11 --kaggle-account acc3 > data/work/logs-p0/embed-serve.log 2>&1"
```

Expected: `data/work/serve/<rer_slug>.env` and `data/work/serve/<EMB_SLUG>.env` appear. Every run session starts with `set -a; . data/work/serve/<rer_slug>.env; . data/work/serve/<EMB_SLUG>.env; set +a` and the eval-stack exports (`PHARMA_POSTGRES__DSN=postgresql+psycopg://vipharmind:vipharmind@localhost:5434/vipharmind`, `PHARMA_QDRANT__URL=http://localhost:6335`, `PHARMA_RETRIEVAL__QDRANT_COLLECTION=eval_<EMB_SLUG>`), with `<EMB>`'s release the published one (`pharma-agent corpus import ... --publish` under its embedding settings if not). The three Kaggle accounts each hold one kernel: acc1 the LLM, acc2 the reranker, acc3 the embedding.

- [ ] **Step 2: A1 — Gemini roles through the proxy**

```bash
export PHARMA_LLM__DEFAULT__BASE_URL=http://127.0.0.1:8317/v1 PHARMA_LLM__DEFAULT__API_KEY=proxypal-local
for ROLE in JUDGE REFINE ANSWER; do export PHARMA_LLM__ROLES__${ROLE}__MODEL=gemini-3.8-flash-high; done
for ROLE in GUARDRAIL REPHRASE; do export PHARMA_LLM__ROLES__${ROLE}__MODEL=gemini-3.1-flash-lite; done
for C in full one-step closed-book; do uv run pharma-lab e2e run --run e2e-v2-gemini --config $C --limit 20; done   # smoke
for C in full one-step closed-book; do uv run pharma-lab e2e run --run e2e-v2-gemini --config $C --concurrency 4; done
for C in full one-step; do uv run pharma-lab e2e run --run e2e-v2-gemini-c1 --config $C --concurrency 1; done
```

Expected: `run.json` of every config lists `gemini-3.8-flash-high` for judge/refine/answer and `gemini-3.1-flash-lite` for guard/rephrase; `answers.jsonl` rows carry `steps` and `reasoning_tokens == 0`.

- [ ] **Step 3: A2 — Qwen3.5-9B self-hosted**

```bash
tmux new -d -s llm-serve "uv run pharma-lab e2e llm-server --model qwen3.5:9b-q8_0 --hours 11 --kaggle-account acc1 > data/work/logs-p0/llm-serve.log 2>&1"
set -a; . data/work/serve/qwen3_5_9b_q8_0.env; . data/work/serve/<rer_slug>.env; . data/work/serve/<EMB_SLUG>.env; set +a
for C in full one-step closed-book; do uv run pharma-lab e2e run --run e2e-v2-qwen9b --config $C --limit 20 --deadline-seconds 900; done
for C in full one-step closed-book; do uv run pharma-lab e2e run --run e2e-v2-qwen9b --config $C --concurrency 8 --deadline-seconds 900; done
for C in full one-step; do uv run pharma-lab e2e run --run e2e-v2-qwen9b-c1 --config $C --concurrency 1 --deadline-seconds 900; done
```

Expected: every `run.json` names `qwen3.5:9b-q8_0` for all six roles with `extra_body` `{"chat_template_kwargs": {"enable_thinking": false}}`. If a Kaggle session ends mid-run, re-serve and re-run the same command (the harness resumes).

- [ ] **Step 4: Judge, calibrate, report**

```bash
unset $(env | grep -o '^PHARMA_LLM__ROLES__[A-Z]*__[A-Z_]*')   # judge uses the default proxy endpoint
for R in e2e-v2-gemini e2e-v2-qwen9b; do
  for C in full one-step closed-book; do uv run pharma-lab e2e judge --run $R --config $C --judge-model gemini-3.1-flash-lite; done
  uv run pharma-lab e2e calibration export --run $R --config full --config one-step --config closed-book
done
uv run pharma-lab e2e report --run e2e-v2-gemini --latency-run e2e-v2-gemini-c1
uv run pharma-lab e2e report --run e2e-v2-qwen9b --latency-run e2e-v2-qwen9b-c1
uv run pharma-lab e2e compare --run-a e2e-v2-gemini --run-b e2e-v2-qwen9b --config full
```

Expected: `reports/{main,ablation,cost}.csv|tex`, `provenance.json` with `latency_run`, `compare-e2e-v2-gemini-full.csv|tex` under the Qwen run. The pharmacist grades `calibration/items.jsonl` (50 per config) into `grades.jsonl`; then `calibration score` per run.

- [ ] **Step 5: Record and commit**

Add to `docs/research/paper-v2/09-phase-0-results.md`: the A1 and A2 tables with the new columns (seconds p50/p95, USD per 1,000 turns, cost of pass), the per-step time split, the compare result, and the measured Opus reasoning-token behaviour is left for phase 1 (no Opus run here). Commit `run.json`, `judge.json`, `reports/` of the four runs and the results doc; answers and judgments go to the archive at the end of the phase (`pharma-lab data push --kaggle-account acc1 --message "Paper v2 phase 0: measurement runs"`, after the user's go-ahead, paired with a git tag `v2.0.0-phase0`).

```bash
git add docs/research/paper-v2/09-phase-0-results.md pharma-lab/data/evaluation/e2e/runs/e2e-v2-*/**/run.json pharma-lab/data/evaluation/e2e/runs/e2e-v2-*/**/judge.json pharma-lab/data/evaluation/e2e/runs/e2e-v2-*/reports
git commit -m "data: A1 and A2 on the v2 release with seconds and USD"
```

---

## Self-review

- **Spec coverage:** §2.1b model paths (Task 8b embedding server, Task 9 docs, Task 11 runs; the Opus proxy path is exercised in phase 1 where Opus first runs), judge reasoning check on v1 grades (Task 10); §2.5 steps latency (Tasks 2–3), `retrieval_seconds`/`rerank_seconds` (Task 2), pricing table with sources and dates (Task 4), metrics `usd_per_turn`, `usd_per_1000_turns`, `llm/retrieval/decision_seconds_per_turn`, `cost_of_pass`, `cost.csv|tex` (Task 4), concurrency-1 latency protocol and p50/p95 (Task 8); §2.6 guard switch and retriever variants (Task 5), `rerank` limits unchanged (constraint); §4.E `e2e compare` (Task 7); §7 phase 0 runs A1 and A2 (Task 11). Enrichment (§2.6) is out of scope by the spec's own phase order. Reasoning tokens for Opus (§2.1b) are recorded by Task 1 and reported when Opus runs in phase 1.
- **Placeholders:** none; the retrieval prices are a stated upper bound with a replacement rule, and `<EMB>`/`<RER>` are bound by Task 11 Step 0's rule before any command that uses them.
- **Type consistency:** `StepRecord`, `AnswerRecord.steps/retrieval_seconds/rerank_seconds/rerank_scored` (Task 3) are what Task 4's `retrieval_cost_usd` and Task 8's `latency_values` read; `load_run`/`values_of` (Task 7) are the public names Task 8's loader and `compare.py` use; `config_label` (Task 5) names the directories Task 7 and Task 8 open; `pin_judge(..., reasoning, base_url)` (Task 6) is what Task 10 relies on via `--judge-reasoning`.
- **Review Focus:** each line has its test in the owning task (1→Task 3, 2→Task 4, 3→Task 5, 4→Task 7, 5→Task 8).
