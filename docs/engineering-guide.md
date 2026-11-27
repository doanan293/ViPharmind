# Engineering Guide

Rules for `backend/` (Clean Architecture) and `frontend/` (feature-based). `pharma-lab/` keeps its
own one-way layers; only "Reuse before writing", naming and test layout apply to it. `Entity`,
`<feature>`, `<subdomain>` are placeholders.

## Reuse before writing

Take, in this order:

1. What the repo already has (dependency, service, helper, component).
2. The language or framework (stdlib, FastAPI, pydantic, SQLAlchemy, React, React Router).
3. A popular library: ≥ 5,000 GitHub stars or ≥ 100,000 weekly downloads, released in the
   last 12 months, compatible licence. Nothing below that bar.
4. Only then your own code.

- UI: shadcn first. Installed components are in `frontend/app/components/ui/`; check the
  registry (`npx shadcn@latest view <name>`) before building a widget.
- No raw `button`, `input`, `select`, `textarea`, `dialog`, `table`, `label`, `form` in
  `app/features/` or `app/routes/`.
- Python: validation with pydantic, HTTP with httpx; never hand-roll retries, parsing or
  date handling.

## Backend

```
api ──► infrastructure ──► application ──► domain
```

| Layer | Holds | May import |
|---|---|---|
| `domain` | entities, rules, ports (`Protocol`), domain errors; no I/O | stdlib, `pydantic` |
| `application/<feature>/` | `<Feature>Service`: one public method per use case | `domain`; `application/{errors,progress,pagination,tracing}` |
| `infrastructure` | adapters for ports (Postgres, Qdrant, LLM, email, SMS), settings, composition root | `application`, `domain`, drivers, SDKs |
| `api` | routers, schemas, error → HTTP | `application`; `infrastructure` only in `api/deps.py`, `api/app.py` |

- Build adapters only in `infrastructure/container.py` and `infrastructure/*_factory.py`;
  pass ports through constructors. Routers call services via `Container` (`api/deps.py`).
- Use cases and adapters are classes with dependencies in the constructor. Module-level
  functions only for pure logic, route handlers and LangGraph nodes.
- No module-level state (clients, connections, caches, registries). Module-level values are
  `UPPER_CASE` constants, type aliases or loggers.
- `application/<A>` never imports `application/<B>`; compose features in `api` or
  `infrastructure`.
- Async end to end; no blocking I/O on an async path.
- Business errors subclass `application.errors.ApplicationError`; they leave the API as
  problem+json with a `code` from `errors.json`.
- Deployment values go in `Settings` (`PHARMA_` prefix, documented in `backend/.env.example`);
  business limits and allowed values are named constants or policies in `domain`. No magic
  numbers or literal lists in logic.
- Fix a broken import contract by fixing the import, never the contract.

```python
# domain/<subdomain>/ports.py
class EntityRepository(Protocol):
    async def get(self, entity_id: UUID) -> Entity | None: ...


# application/<feature>/service.py
class EntityService:
    def __init__(self, repository: EntityRepository) -> None: ...
    async def get(self, entity_id: UUID) -> Entity: ...  # raises EntityNotFound


# infrastructure/container.py
entities = EntityService(PostgresEntityRepository(sessions))


# api/routers/entities.py
@router.get("/{entity_id}")
async def get_entity(entity_id: UUID, container: ContainerDep) -> EntityResponse:
    return EntityResponse.model_validate(await container.entities.get(entity_id))
```

## Frontend

```
app/routes/              thin, compose features
app/features/<feature>/  components/ hooks/ lib/
app/{api,components,hooks,i18n,lib}/  shared; app/api/gen/ is generated (orval)
```

- Shared code never imports features or routes; features never import routes.
- Feature → feature imports allowed only: `chat` → `conversations`; `shell` → `auth`,
  `conversations`; `organizations` → `audit`; `admin` → `auth`, `chat`, `audit`. A new
  direction goes in both `biome.json` and `app/architecture.test.ts`.
- Call the backend only through `app/api/gen/`; after an API change run `npm run api:openapi`
  then `npx orval`.
- Every user-visible string through i18n (`vi` and `en`); error text from the problem+json
  `code`.

## Code

- Python 3.12, types on every parameter and return; TypeScript strict, no `any`, no `!`.
- Google-style docstrings on public Python classes, functions, methods. JSDoc on every
  exported TS component, hook, function, class, type (not in `app/api/gen`,
  `app/components/ui`). Say what the name doesn't.
- Names: classes nouns, functions verbs, booleans `is_`/`has_`/`can_`, components
  `PascalCase`, hooks `useX`.
- Functions: aim for 15–20 lines. Limits: complexity ≤ 10; Python ≤ 40 statements; TS ≤ 60
  lines and ≤ 4 parameters.
- No `# noqa`, `# type: ignore`, `# pyrefly: ignore`, `biome-ignore`, `@ts-ignore`, no
  disabled rules. Fix the code.

## Tests

- Python tests mirror `src/<package>/` under `tests/`; fakes in `tests/fakes.py`,
  `tests/*_fakes.py` instead of mocks; real-Postgres tests marked `integration`.
- Frontend tests beside the code: `*.test.ts(x)`, `*.browser.test.tsx`; Playwright in
  `tests/e2e/`.
- Coverage: backend ≥ 90% (whole suite), frontend ≥ 80% of lines.
- Test names describe behaviour: `test_<behavior>`, `it("…")`.

## API

- REST + JSON under `/api/v1/`; errors are problem+json with a `code`.
- Status: `201` created, `204` no content, `401` not signed in, `403` not allowed, `404` not
  found or hidden, `409` conflict, `413` too large, `422` invalid, `429` too many requests,
  `503` dependency down.
- Check permissions in `application`, not only in the UI.
- Each new endpoint: route docstring, request example, error statuses in OpenAPI.
- Secrets only in `.env`.
