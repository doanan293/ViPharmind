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
   - enforced in the frontend by `react/forbid-elements`: no raw `button`, `input`, `select`,
     `textarea`, `dialog`, `table`, `label`, `form` in `app/features/` and `app/routes/` when
     a shadcn component exists; elsewhere by the code reviewer (rubric item "reuse").
2. **Frontend standard**:
   - JSDoc on every exported component, hook, function, class and type that says something
     the name doesn't (Google TypeScript style); enforced by a test in the style of
     `app/architecture.test.ts` (oxlint has no presence rule). Generated (`app/api/gen`) and
     registry-copied shadcn files (`app/components/ui`) are third-party code, outside the rule,
     like generated code everywhere else.
   - oxlint: categories `correctness`, `suspicious`, `pedantic`, `perf` as errors;
     `complexity` ≤ 10, `max-lines-per-function` ≤ 60 (blank lines and comments not counted),
     `max-depth` ≤ 4, `max-params` ≤ 4. Rules that contradict the codebase's settled
     conventions or React itself are decided per rule with a reason in `.oxlintrc.json`.
   - Coverage ≥ 80% with `@vitest/coverage-v8` (`npm run test:coverage`).
   - Latest stable tools: oxlint 1.95.0, vitest / @vitest/* 5.1.2, prettier 3.10.1
     (TypeScript 7.0.2 already latest).
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

One sensible way: tools first (versions, config, the JSDoc and forbid-elements checks), then
agents fix the findings per area in parallel, then coverage. Alternatives (only a guide rule
without tooling; or a separate ESLint for `jsdoc/require-jsdoc`) were dropped: the first
isn't enforced, the second adds a second linter next to oxlint.

## Left to the builder

The exact list of pedantic/perf rules kept or turned off (each with a reason), the split of
the work between agents, and the tests added for coverage.
