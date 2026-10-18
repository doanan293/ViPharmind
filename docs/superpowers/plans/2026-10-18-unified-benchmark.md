# Unified Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One retrieval benchmark with nine groups, and a golden e2e set drawn from the same groups, so every retrieval and e2e table of the paper reports the same groups end to end.

**Architecture:** `evaluation extend` appends three generated groups (colloquial, glossary, conversational) to the 10,000-question gold file in place and rebuilds its judgments; the separate enrichment-probe and conversational gold directories go away. Runs are redone under `-v3-` names on the extended file, reusing the query-embedding and rerank caches. The golden set's answerable groups gain colloquial and glossary, probes keep their source group, and the multi-turn items are redrafted from the conversational group.

**Tech Stack:** pharma-lab (typer CLI, pydantic), backend retrieval, Kaggle workers for embedding and reranking.

**Spec:** `docs/superpowers/specs/2026-10-14-paper-v2-design.md` (§3.0b golden, §3.1 conversational layer, §4.D retrieval). User decision 2026-10-18: "Nếu tách ra như này thì nó không xuyên suốt" → one benchmark, same groups in every table.

## Global Constraints

- Golden total stays 500: answerable 270, multi_hop 150, multi_turn 50, unanswerable 10, out_of_scope 10, injection 10.
- Benchmark groups: formulary, leaflet, structured, leaflet_short, noisy, multi_intent (10,000 rows, unchanged), colloquial 636, glossary 219, conversational 1,500.
- Golden answerable: 30 natural items for each of the six base groups, 20 colloquial, 10 glossary, plus probes rerank_probe 21, lexical_probe 19, semantic_probe 20 that keep their source group.
- Golden multi_turn: 50 items from the conversational group, 6 per phenomenon and 8 for pronoun and ellipsis (6 × 6 + 7 × 2 = 50).
- Draft model gemini-3.1-flash-lite; review by Claude Fable 5.1 with `pharma-lab/data/work/golden-review/review-rubric.md`.
- Run names: the `-v2-` runs stay as they are; extended-benchmark runs use `-v3-` (for example `hybrid-qwen4b-v3-p50-k20-rrf2`).
- No `# noqa`, no `# type: ignore`; ruff, pyrefly `--min-severity warn`, lint-imports, pytest must pass.

## Review Focus

- Running `evaluation extend` twice must not duplicate the generated groups: it strips rows of the three generated groups before appending.
- A conversational row's `query` is its last user turn; retrieval of the extended file must read `query` only, so Q0 is the default for that group.
- Golden colloquial and glossary items must point at existing benchmark rows (`source_query_id` = `enrich-…`), otherwise e2e and retrieval disagree per group.
- Judgments of the extended file must cover the new rows (the judgments manifest row count equals the file's).
- Old `-v2-` run directories must still load (their evaluation sha is the old file's); new runs must not reuse them.

---

### Task 1: `evaluation extend` writes the nine-group benchmark

**Files:**
- Modify: `pharma-lab/src/pharma_lab/cli/commands/evaluation.py` (replace `enrichment-probe` and `conversational` commands with `extend`)
- Modify: `pharma-lab/src/pharma_lab/config/paths.py` (drop `ENRICHMENT_GOLD_DIR`, `CONVERSATIONAL_GOLD_DIR`), `pharma-lab/.gitignore`
- Create: `pharma-lab/src/pharma_lab/e2e/benchmark_extension.py`
- Test: `pharma-lab/tests/e2e/test_benchmark_extension.py`, `pharma-lab/tests/cli/test_evaluation_extend.py`

**Interfaces:**
- Consumes: `colloquial_benchmark`, `glossary_benchmark`, `benchmark_row` (e2e/golden_generate.py); `build_conversational` (e2e/conversational.py); `build_evaluation_judgments`.
- Produces: `GENERATED_GROUPS = ("colloquial", "glossary", "conversational")`; `extend_rows(base: Sequence[dict], corpus: CorpusText, aliases: Sequence[tuple[str, Sequence[str]]], *, covered: Mapping[str, bool] | None, conversational_total: int, seed: int) -> list[dict]` returning base rows without generated groups followed by colloquial, glossary, conversational rows.

- [ ] **Step 1: Tests** — `test_extend_appends_the_three_groups_after_the_base_rows` (groups in order, base rows unchanged and first); `test_extend_is_idempotent` (extending an extended list gives the same list); CLI `test_evaluation_extend_rewrites_the_gold_file_and_judgments` (file rows = base + generated, judgments manifest `query_count` covers new rows, `rows` and per-group counts in the result).
- [ ] **Step 2: Run, see them fail.**
- [ ] **Step 3: Implement** `extend_rows` and the `extend` command (options `--evaluation` default the gold file, `--bundle`, `--run`/`--model` for conversational stratification, `--conversational-total 1500`, `--seed 0`); delete the two old commands, their path constants and gitignore lines.
- [ ] **Step 4: Run the e2e and cli tests, ruff, pyrefly, lint-imports.**
- [ ] **Step 5: Run `uv run pharma-lab evaluation extend` on the real data; expect rows=12355, colloquial=636, glossary=219, conversational=1500. Commit.**

### Task 2: Retrieval matrix on the extended benchmark (runs, no code)

**Files:**
- Create: `pharma-lab/data/work/logs-t7/v3-retrieval.sh` (gitignored work dir)

- [ ] **Step 1:** Query embeddings of the new rows for the five embeddings (`embed queries --backend kaggle --model <m> --kaggle-account <acc>`; the cache holds the 10,000 old ones).
- [ ] **Step 2:** Retrieve on the extended file: bm25, dense × 5, hybrid 4B rrf2, hybrid 4B rrf60, hybrid 8B rrf2 (only if its `-v2-` Hit@20 beat 4B), and hybrid 4B rrf2 on the plain (no-enrichment) bundle, all `-v3-` names, each followed by `metrics --top-k 20`.
- [ ] **Step 3:** Rerank hybrid 4B rrf2 `-v3-` with the four rerankers (4B from cache), hybrid 4B plain with 4B, dense 4B with 4B; metrics with and without `--gold-only` as the `-v2-` runs had.
- [ ] **Step 4:** Check every report has the nine groups; record the table in the ledger.

### Task 3: Golden groups follow the benchmark

**Files:**
- Modify: `pharma-lab/src/pharma_lab/e2e/golden.py` (`EVAL_GROUPS` gains colloquial and glossary with `ANSWERABLE_QUOTAS: dict[str, int]` = 30 × six base groups, colloquial 20, glossary 10; `PROBE_QUOTAS` keeps rerank_probe 21, lexical_probe 19, semantic_probe 20; probes carry their source `eval_group`; `MULTI_TURN_QUOTAS` per phenomenon)
- Modify: `pharma-lab/src/pharma_lab/e2e/golden_draft.py` (a `MULTI_TURN` family: category multi_turn, turns from the row, `eval_group="conversational"`, tag = phenomenon; candidates from `multi-turn.todo.jsonl`)
- Modify: `pharma-lab/src/pharma_lab/cli/commands/e2e.py` (`golden multi-turn-candidates` writes conversational rows as candidates; `golden relabel-probes` maps colloquial and glossary probes to `enrich-` benchmark rows by gold section and subject and sets their group)
- Test: `pharma-lab/tests/e2e/test_golden.py`, `test_golden_draft.py`, `test_golden_probe.py`

- [ ] **Step 1: Tests** — quotas sum to 270 answerable and 50 multi_turn; a probe without `eval_group` is a problem; a multi_turn item must have `eval_group == "conversational"` and one phenomenon tag; the MULTI_TURN family drafts an item whose turns equal the candidate's turns.
- [ ] **Step 2: Run, see them fail. Step 3: Implement. Step 4: Tests and gates.**
- [ ] **Step 5:** Relabel the authored probes; set the probes' source groups; move the old multi_turn batches out of the authoring dir; draft 50 multi-turn items; Fable review with the rubric (history kept verbatim, last turn not rewritten); `golden build`; copy to the main repo. Commit.

### Task 4: Docs and paper

**Files:**
- Modify: spec §3.0b, §3.1, §4.D (one benchmark, nine groups; D2 and D5 are rows of the main table), `pharma-lab/docs/guides/e2e-golden-authoring.md`, `report/drafts/methods-v2.tex` (golden set paragraph: groups shared with the benchmark).
- [ ] **Step 1:** Edit; build the report warning-free; commit; fast-forward dev.
