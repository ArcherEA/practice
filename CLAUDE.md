# PRODUCT — rules for every agent

Modular full-stack platform (SaaS / content / commerce / community + AI), built on
[fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) (MIT).
Read `docs/SPEC.md`, `docs/ARCHITECTURE.md` and `docs/DECISIONS.md` before changing structure.

## Stack (fixed — changing it needs a decision in docs/DECISIONS.md)
- Backend `backend/`: Python 3.14, FastAPI, SQLModel + Alembic, PostgreSQL, uv, pytest, ruff, mypy.
- Frontend `frontend/`: React + TypeScript + Vite, TanStack Router + Query, Tailwind + shadcn/ui, Bun, Playwright.
- API client in `frontend/src/client` is **generated** (`scripts/generate-client.sh`) — never hand-edit, never hand-write fetch calls.
- Deploy targets: own server (Docker Compose + Traefik, `compose*.yml`) and Vercel. Both must keep working.

## Workflow
- Every change starts from a task file `docs/tasks/NNN-<slug>.md`. Do only what its scope says; list anything else under "Follow-ups" in your report.
- Work on branch `feat/NNN-<slug>`. Conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- Before reporting done: backend `uv run ruff check . && uv run mypy app && uv run pytest`; frontend `bun run lint && bun run build`; Playwright for touched user flows.
- The lead reviews; the user approves every merge to `main`.

## Code rules
- Follow the template's existing patterns first (look at `users`/`items` routes, models, crud, tests, frontend routes).
- Prefer a well-known open-source library over custom code — but **no new dependency unless the task lists it with a reason**. Must be permissive (MIT/BSD/Apache), maintained and widely used. Record it in `docs/DECISIONS.md`.
- Modules live in their own folders (backend `app/modules/<name>/`, frontend `src/features/<name>/` + routes) and talk to each other only through service functions / public schemas.
- After changing backend dependencies (`uv add/remove/lock`, merging a Dependabot uv PR), run `scripts/export-requirements.sh` and commit the updated root `requirements.txt` (Vercel installs from it; CI `check-requirements` fails if it is stale).
- Every DB change = a new Alembic migration. Never edit an applied migration.
- Backend must stay stateless (Vercel): no writes to local disk — files go to S3-compatible storage. All config via env vars, documented in `.env.example`.
- AI calls only through `backend/app/ai/` (Pydantic AI), with timeouts, error handling and per-user rate limits. Keys server-side only.
- Strict typing; no `Any`/`any`, `# type: ignore` or `@ts-ignore` without a comment explaining why.
- Tests for every feature: pytest for services and API, Playwright for key flows.
- Never commit secrets or `.env`. Keep the template's `LICENSE` notice.
