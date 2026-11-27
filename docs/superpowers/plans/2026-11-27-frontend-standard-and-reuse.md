# Frontend Standard and Reuse Rule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the ViPharmind frontend to the backend's standard and add a "don't reinvent the wheel" rule to the guide of ViPharmind and of `python-project-template`.

**Architecture:** Tools and checks first (Biome replacing oxlint and prettier, a JSDoc presence test, coverage), so the work to do is measured by failing checks; then parallel agents fix findings per feature area; guide, AGENTS.md and template last.

**Tech Stack:** React Router 7, TypeScript 7.0.2, Biome 2.6.9 (lint + format, replacing oxlint and prettier), vitest 5.1.2 (+ browser, coverage-v8), shadcn.

**Spec:** `docs/superpowers/specs/2026-11-27-frontend-standard-and-reuse-design.md`

## Global Constraints

- "popular": about ≥ 5,000 GitHub stars or ≥ 100,000 weekly downloads, a release in the last 12 months, a compatible licence.
- Biome 2.6.9 for lint and format (`frontend/biome.json`); oxlint, oxlint-tsgolint, prettier, prettier-plugin-tailwindcss and their config files removed.
- Formatter = current prettier style: no semicolons, double quotes, 2 spaces, trailing commas es5, width 80, LF; class order by `useSortedClasses` with functions `cn`, `cva`.
- Linter: `recommended` + `a11y`; `noExcessiveCognitiveComplexity` ≤ 10; `noExcessiveLinesPerFunction` ≤ 60; `useMaxParams` ≤ 4; `noMagicNumbers`; `noImportCycles`; `useHookAtTopLevel`; `useExhaustiveDependencies`; `noFloatingPromises`; `noMisusedPromises`; feature boundaries as `noRestrictedImports` overrides (same table as today).
- `noRestrictedElements` in `app/features/**` and `app/routes/**`: `button`, `input`, `select`, `textarea`, `dialog`, `table`, `label`, `form`.
- JSDoc on every exported component, hook, function, class and type outside `app/api/gen/**` and `app/components/ui/**`, saying something the name doesn't.
- Coverage ≥ 80% (`npm run test:coverage`).
- No suppressions (`biome-ignore`, `@ts-ignore`, `@ts-expect-error`, `any`), no change to UI behaviour, routes, API or `frontend/openapi.json`.
- AGENTS.md: `@docs/engineering-guide.md` plus only rules an agent must never miss.
- pharma-lab/ is being edited by another workflow: do not touch it.

## Review Focus

- A refactored component renders and behaves exactly as before: the browser tests (`*.browser.test.tsx`) and `app/architecture.test.ts` still pass.
- Replacing a raw `<button>`/`<form>` with shadcn keeps keyboard and screen-reader behaviour: jsx-a11y rules stay errors and the browser tests that click those controls pass.
- Splitting long components keeps hooks rules valid: `react/rules-of-hooks` and `react/exhaustive-deps` stay errors.
- The generated client and OpenAPI document are untouched: `npm run api:check` passes and `git diff --stat frontend/app/api/gen frontend/openapi.json` is empty.
- The feature import table survives the move: `app/architecture.test.ts` reads `biome.json` and still fails when the lint overrides and its table disagree.
- Formatting churn stays small: after `biome format --write`, `git diff --stat` is dominated by class-order changes, not quote/semicolon flips (check the formatter options if not).

---

### Task 1: Biome replaces oxlint and prettier; vitest 5.1.2

**Files:**
- Create: `frontend/biome.json`
- Delete: `frontend/.oxlintrc.json`, `frontend/.prettierrc`, `frontend/.prettierignore`
- Modify: `frontend/package.json` (+ lock: add `@biomejs/biome` 2.6.9; remove oxlint, oxlint-tsgolint, prettier, prettier-plugin-tailwindcss; vitest and `@vitest/*` 5.1.2; scripts `lint` = `biome lint .`, `format` = `biome format .`, `format:write` = `biome format --write .`, `check` = `biome check .`), `frontend/app/architecture.test.ts` (read the boundary overrides from `biome.json`), `.pre-commit-config.yaml` (frontend lint/format hooks call `npm --prefix frontend run lint` / `format`), `.github/workflows/ci.yml` (step names and commands), `frontend/README.md` (tool names)

- [ ] **Step 1:** Write `biome.json` with the Global Constraints values; `files.includes` excludes `node_modules`, `build`, `.react-router`, `app/api/gen`, `tests/public/mockServiceWorker.js` (today's ignore list).
- [ ] **Step 2:** Port each `.oxlintrc.json` override to a `noRestrictedImports` override with the same globs, patterns and messages; switch the boundary test to read `biome.json`; `npx vitest run app/architecture.test.ts` passes.
- [ ] **Step 3:** `npx biome format --write .`; check the churn per Review Focus; `npm run typecheck` and `npx vitest run` pass.
- [ ] **Step 4:** `npm run lint`: record finding counts by rule in the ledger (fixed in Task 4).
- [ ] **Step 5:** Commit `chore(frontend): Biome replaces oxlint and prettier; vitest 5.1.2`.

### Task 2: JSDoc presence check

**Files:**
- Create: `frontend/app/jsdoc.test.ts`

**Interfaces:**
- Produces: `missingJsDoc(source: string, path: string): string[]` (exported for its own test) returning `"<path>:<line> <name>"` for every exported declaration without a preceding `/** … */`.

- [ ] **Step 1:** Write tests: `missingJsDoc` flags `export function f()`, `export const C = () => …`, `export class K`, `export type T`, `export interface I` without JSDoc and accepts them with one; ignores non-exported declarations and re-exports (`export { x } from`).
- [ ] **Step 2:** Run `npx vitest run app/jsdoc.test.ts`: fails (function missing).
- [ ] **Step 3:** Implement with the TypeScript compiler API (`ts.createSourceFile`, `ts.getJSDocCommentsAndTags` / leading comment ranges); a test `every export in app/ has JSDoc` walks `app/**/*.{ts,tsx}` except `api/gen/**`, `components/ui/**`, `*.test.*`, `*.d.ts`.
- [ ] **Step 4:** Unit tests pass; the repo-wide test fails listing ~224 exports (fixed in Task 4).
- [ ] **Step 5:** Commit `test(frontend): every export documented`.

### Task 3: Coverage

**Files:**
- Modify: `frontend/package.json` (`@vitest/coverage-v8` 5.1.2, script `"test:coverage": "vitest run --coverage"`), `frontend/vitest.config.ts` (provider `v8`, include `app/**`, exclude `app/api/gen/**`, `app/components/ui/**`, tests; `thresholds: { lines: 80, functions: 80, branches: 80, statements: 80 }`)

- [ ] **Step 1:** Run `npm run test:coverage`; record the four percentages.
- [ ] **Step 2:** Commit `test(frontend): coverage with an 80% threshold` (may fail until Task 5).

### Task 4: Fix lint and JSDoc findings (parallel agents)

Areas: `app/features/chat`, `app/features/{collections,conversations}`, `app/features/{admin,organizations,audit,settings,auth}`, everything else in `app/` (`routes`, `components` except `ui`, `hooks`, `lib`, `i18n`, `api` except `gen`, remaining features) and `tests/`.

- [ ] **Step 1:** Each agent fixes every Biome finding and missing JSDoc in its area by improving the code (split components/functions, extract hooks, shadcn components for raw elements, named constants); no suppressions.
- [ ] **Step 2:** Per area: `npx biome check <area>`, `npm run typecheck`, `npx vitest run <area>` pass.
- [ ] **Step 3:** After all areas: `npm run check`, `npm run typecheck`, `npx vitest run`, `npm run api:check` pass; `git diff --stat app/api/gen openapi.json` empty.
- [ ] **Step 4:** Commit `refactor(frontend): meet the strict lint rules and document every export`.

### Task 5: Coverage to ≥ 80%

- [ ] **Step 1:** Add behaviour tests (existing MSW + browser-test style) for the least-covered modules until `npm run test:coverage` passes all four thresholds.
- [ ] **Step 2:** Commit `test(frontend): coverage above 80%`.

### Task 6: Guide, AGENTS.md, reviewer rubric

**Files:**
- Modify: `docs/engineering-guide.md` (new section "Reuse before writing", frontend tooling line, JSDoc rule, coverage), `AGENTS.md` (short: `@docs/engineering-guide.md` + the must-never-miss rules), `frontend/README.md` check commands
- Modify (research repo): `code/prompts/b3/reviewer.md` (dimension `reuse`), `code/harness/src/sdlc_harness/b3/quality.py` (`DIMENSIONS` gets `"reuse"`), its test

- [ ] **Step 1:** Write the guide section with the order of preference and the "popular" bar verbatim from Global Constraints; shorten AGENTS.md.
- [ ] **Step 2:** Reviewer: add `reuse` (1-5: uses what the repo, the framework or a popular library already provides; shadcn before hand-built UI); update `test_review_parses_scores` to include it; `uv run pytest -q tests/b3/test_quality.py` passes.
- [ ] **Step 3:** Commit in each repo.

### Task 7: Template sync

**Files (template, uncommitted for the owner):** `docs/engineering-guide.md` (same "Reuse before writing" section, Python wording), `AGENTS.md` (short, same shape)

- [ ] **Step 1:** Apply; template checks (ruff, pyrefly, pytest per service with `UV_PROJECT_ENVIRONMENT=/var/tmp/b3/tpl-venv`) still pass.
