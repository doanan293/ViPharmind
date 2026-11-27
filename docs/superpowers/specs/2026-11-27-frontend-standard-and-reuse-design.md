# Frontend standard and "don't reinvent the wheel" (design)

Owner request, 2026-11-27. Approved in conversation.

## Intent

AI agents hand-roll what a popular library or a shadcn component already does (ugly, slow to
build, more bugs), and the frontend is checked less strictly than the backend. Bring the
frontend to the same standard as the backend and pharma-lab, and add one reuse rule for every
part of ViPharmind and of the owner's `python-project-template`.

## Goals

1. **Reuse rule** in `docs/engineering-guide.md` (ViPharmind and template), for backend,
   frontend and pharma-lab:
   - order of preference: what the repo already uses (dependency, service, component) → the
     language or framework's own feature → a popular library → write it yourself;
   - "popular": about ≥ 5,000 GitHub stars or ≥ 100,000 weekly downloads, a release in the
     last 12 months, a compatible licence; below that, don't add it;
   - enforced in the frontend by Biome `noRestrictedElements`: no raw `button`, `input`, `select`,
     `textarea`, `dialog`, `table`, `label`, `form` in `app/features/` and `app/routes/` when
     a shadcn component exists; elsewhere by the code reviewer (rubric item "reuse").
2. **Frontend standard**:
   - JSDoc on every exported component, hook, function, class and type that says something
     the name doesn't (Google TypeScript style); enforced by a test in the style of
     `app/architecture.test.ts` (Biome has no presence rule). Generated (`app/api/gen`) and
     registry-copied shadcn files (`app/components/ui`) are third-party code, outside the rule,
     like generated code everywhere else.
   - **Biome replaces oxlint and prettier** (owner, 2026-11-27: one tool, one config,
     `frontend/biome.json`), latest stable 2.6.9, for both lint and format:
     - formatter set to the current prettier style (no semicolons, double quotes, 2 spaces,
       trailing commas es5, width 80, LF), so reformatting is minimal; Tailwind class order
       moves from `prettier-plugin-tailwindcss` to `useSortedClasses` (functions `cn`, `cva`);
     - linter: the `recommended` set plus `a11y`; feature import boundaries and the shared-code
       rule move from `.oxlintrc.json` overrides to `noRestrictedImports` overrides (same table,
       and `app/architecture.test.ts` checks `biome.json` instead); `noImportCycles`;
       `useHookAtTopLevel`, `useExhaustiveDependencies`; `noExcessiveCognitiveComplexity` ≤ 10,
       `noExcessiveLinesPerFunction` ≤ 60, `useMaxParams` ≤ 4, `noMagicNumbers`;
       `noRestrictedElements` (above);
     - Biome's type-aware rules are enabled, nursery ones included (`noFloatingPromises`,
       `noMisusedPromises`, `useAwaitThenable`, `noUnnecessaryConditions`, `useArraySortCompare`,
       `useExhaustiveSwitchCases`, `noBaseToString`, `noMisusedSpread`, `noUnsafeUnaryMinus`):
       they cover most of oxlint's type-aware set; not covered: for-in over arrays, unnecessary
       type assertions, unbound methods, template-expression types;
     - oxlint, oxlint-tsgolint, prettier, prettier-plugin-tailwindcss, `.oxlintrc.json`,
       `.prettierrc`, `.prettierignore` are removed; `npm run lint` / `format` / `format:write`,
       the pre-commit hooks and the CI steps call Biome.
   - Coverage ≥ 80% with `@vitest/coverage-v8` (`npm run test:coverage`).
   - Latest stable tools: Biome 2.6.9, vitest / @vitest/* 5.1.2 (TypeScript 7.0.2 already
     latest).
3. **AGENTS.md stays short**: one line pointing to the guide plus the few rules an agent must
   never miss; details live only in the guide.
4. **Template sync**: the same reuse rule, the same AGENTS.md shape; the template is Python
   only, so the frontend parts do not apply there.

## Non-goals

- No change to user-visible behaviour, routes, API or the OpenAPI document.
- No redesign of components; refactors only split code to meet the limits.

## Anti-goals

- Lint suppressions, disabled rules or `any` to make checks pass.
- An AGENTS.md that restates the guide.

## Approach

One sensible way: tools first (Biome replacing oxlint and prettier, the JSDoc check), then
agents fix the findings per area in parallel, then coverage. Alternatives (only a guide rule
without tooling; or ESLint for `jsdoc/require-jsdoc`) were dropped: the first isn't enforced,
the second adds a second linter. Keeping oxlint + prettier was dropped by the owner in favour of
one tool (Biome); what it costs: oxlint's type-aware rules beyond the two promise rules.

## Left to the builder

The Biome rules beyond those named here (each turned off only with a reason), the split of
the work between agents, and the tests added for coverage.
