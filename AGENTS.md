# Agent rules

@docs/engineering-guide.md

Projects: `backend/` (Clean Architecture), `frontend/` (feature-based), `pharma-lab/` (offline
data tooling, one-way layers).

- Reuse before writing: repo → framework → popular library → own code; UI from shadcn.
- Fix lint and type errors in the code; never suppress them or loosen a rule or contract.
- Before saying a task is done, run the checks of every project you changed; all must pass.

Backend (`cd backend`):

```bash
uv run ruff check . && uv run ruff format --check .
uv run pyrefly check --min-severity warn
uv run lint-imports
uv run pytest -m "" --cov=src --cov-fail-under=90 -q   # needs Docker
```

Frontend (`cd frontend`):

```bash
npm run check && npm run typecheck
npm run test:coverage
npm run api:check
```

pharma-lab (`cd pharma-lab`):

```bash
uv run ruff check src tests && uv run ruff format --check src tests
uv run pyrefly check --min-severity warn
uv run lint-imports
uv run pytest -q
```
