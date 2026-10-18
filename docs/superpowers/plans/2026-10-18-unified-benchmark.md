# Unified Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One retrieval benchmark of exactly 10,000 questions whose groups prove every layer, and a golden e2e set whose every item is a row of it, so every retrieval and e2e table reports the same groups end to end.

**Architecture:** `evaluation assemble` builds the benchmark from the 10,000 rule-built questions (kept in `data/evaluation/gold/archive/`): colloquial 636, glossary 219, conversational 1,500, multi_hop 300 (the golden set's generated multi-hop items plus same-kind candidates) and safety 30 (the golden safety turns, no gold section, skipped by retrieval) in full; structured, leaflet_short, noisy and multi_intent whole; formulary and leaflet sampled 2:1 by intent, keeping every question the golden set or a conversational row refers to. `golden build` fails on any item that is not a benchmark row. Runs on the assembled file use `-v3-` names and reuse the query-embedding and rerank caches.

**Tech Stack:** pharma-lab (typer CLI, pydantic), backend retrieval, Kaggle workers for embedding and reranking.

**Spec:** `docs/superpowers/specs/2026-10-14-paper-v2-design.md` (§3.0b golden, §3.1 conversational layer, §4.D retrieval). User decisions 2026-10-18: "Nếu tách ra như này thì nó không xuyên suốt"; "10000 câu này có đầy đủ ablation, + golden luôn và golden chỉ việc lấy ra thôi" (exactly 10,000, safety as a group); "phần mà phải call LLM/golden thì chỉ 500 câu thôi".

## Global Constraints

- Benchmark: exactly 10,000 rows; groups formulary 3,210, leaflet 1,605, structured 1,000, leaflet_short 500, noisy 500, multi_intent 500, colloquial 636, glossary 219, conversational 1,500, multi_hop 300, safety 30.
- Golden total 500: answerable 270 (30 natural per rule-built group, colloquial 20, glossary 10, probes rerank 21, lexical 19, semantic 20 keeping their source group), multi_hop 150, multi_turn 50 (conversational group, pronoun 7, ellipsis 7, six others 6), safety 30. Every item's `source_query_id` is a benchmark row id; generated multi-hop and safety rows use the item id.
- LLM calls only on the 500 golden items: e2e configs, ablations, τ sweeps, ReAct, judges and the LLM query rewrites (Q2, Q3, Q3b, Q5) run on golden only; the benchmark is scored by retrieval only (Q0, Q1, Q1b, Q6 included).
- Draft model gemini-3.1-flash-lite; review by Claude Fable 5.1 with `pharma-lab/data/work/golden-review/review-rubric.md`.
- Run names: `-v2-` runs stay; runs on the assembled benchmark use `-v3-`.
- No `# noqa`, no `# type: ignore`; ruff, pyrefly `--min-severity warn`, lint-imports, pytest must pass.

## Review Focus

- `assemble` refuses when the rows that must stay in a sampled group exceed its share.
- Retrieval skips only the `safety` group; every other row is scored.
- A conversational row's `query` is its last user turn, so Q0 is the default for that group.
- Judgments are rebuilt for the assembled file.
- `golden build` reports every item whose source is not a benchmark row.

---

### Task 1: `evaluation assemble` writes the 10,000-row benchmark — done (commits e1efd3b, 0d9f2c9)

`pharma-lab/src/pharma_lab/e2e/benchmark_extension.py` (`assemble_benchmark`, `golden_rows`), `cli/commands/evaluation.py` (`assemble`), retrieval skips `safety` (`evaluation/backend_retrieval.py`), `golden build --evaluation` checks benchmark rows. Dry run: rows=10,000 with the group sizes above; golden builds against it.

### Task 2: Retrieval matrix on the assembled benchmark (runs, no code)

**Files:**
- Create: `pharma-lab/data/work/logs-t7/v3-retrieval.sh` (gitignored work dir)

- [ ] **Step 1:** Query embeddings of the new rows for the five embeddings (`embed queries --backend kaggle --model <m> --kaggle-account <acc>`; the cache holds the 10,000 old ones).
- [ ] **Step 0:** `evaluation assemble` on the real file (after the `-v2-` jobs end), then `golden build`.
- [ ] **Step 2:** Retrieve on the assembled file: bm25, dense × 5, hybrid 4B rrf2, hybrid 4B rrf60, hybrid 8B rrf2 (only if its `-v2-` Hit@20 beat 4B), and hybrid 4B rrf2 on the plain (no-enrichment) bundle, all `-v3-` names, each followed by `metrics --top-k 20`.
- [ ] **Step 3:** Rerank hybrid 4B rrf2 `-v3-` with the four rerankers (4B from cache), hybrid 4B plain with 4B, dense 4B with 4B; metrics with and without `--gold-only` as the `-v2-` runs had.
- [ ] **Step 4:** Check every report has the nine groups; record the table in the ledger.

### Task 3: Golden items are benchmark rows — done (commits afb6495, 8e5583d, 0d9f2c9)

Answerable groups follow the benchmark; probes keep their source group; 50 multi-turn items drafted from the conversational group and reviewed by Fable (no rejections); the 35 answerable items whose source question the rule-built benchmark no longer has were set aside in `authoring/superseded/` and replaced by 35 same-group benchmark questions (`natural-01/02`, Fable: 6 keep, 29 fixed); generated multi-hop and safety items point at their own benchmark rows.

### Task 4: Docs and paper

**Files:**
- Modify: spec §3.0b, §3.1, §4.D (one benchmark, nine groups; D2 and D5 are rows of the main table), `pharma-lab/docs/guides/e2e-golden-authoring.md`, `report/drafts/methods-v2.tex` (golden set paragraph: groups shared with the benchmark).
- [ ] **Step 1:** Edit; build the report warning-free; commit; fast-forward dev.
