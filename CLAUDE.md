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
- **Testing in tiers** — run what the moment needs, not everything every time:
  1. *While coding:* only the affected tests — e.g. `uv run pytest tests/api/routes/test_files.py -x`, or one Playwright spec.
  2. *Before reporting done:* backend `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest`
     (full backend suite — it's fast); frontend `bun run lint && bun run build`; Playwright **only for the specs of the
     flows you touched** (run from `frontend/`, see `docs/TROUBLESHOOTING.md`). Don't run the full Playwright suite.
  3. *CI* runs everything (full Playwright in 4 shards, coverage ≥ 90%). Docs-only changes (`docs/**`, `*.md`) skip the test workflows.
- The lead re-runs checks only where risk is high (migrations, permissions/auth, storage, deploy config) and otherwise reviews the diff and the reported results.
- The lead reviews; the user approves every merge to `main`. Changes reach `main` through a **pull request**
  (CI + Vercel preview on the PR), never by pushing to `main` directly — see `docs/BRANCH-PROTECTION.md`.

## Code rules
- Follow the template's existing patterns first (look at `users`/`items` routes, models, crud, tests, frontend routes).
- Prefer a well-known open-source library over custom code — but **no new dependency unless the task lists it with a reason**. Must be permissive (MIT/BSD/Apache), maintained and widely used. Record it in `docs/DECISIONS.md`.
- Modules live in their own folders (backend `app/modules/<name>/`, frontend `src/features/<name>/` + routes) and talk to each other only through service functions / public schemas.
- After changing backend dependencies (`uv add/remove/lock`, merging a Dependabot uv PR), run `scripts/export-requirements.sh` and commit the updated root `requirements.txt` (Vercel installs from it; CI `check-requirements` fails if it is stale).
- Every DB change = a new Alembic migration. Never edit an applied migration. Follow `docs/DATABASE.md` (migration workflow, Neon, backups); a merged migration must also be applied to Neon.
- Backend must stay stateless (Vercel): no writes to local disk — files go to S3-compatible storage. All config via env vars, documented in `.env.example`.
- AI calls only through `backend/app/ai/` (Pydantic AI), with timeouts, error handling and per-user rate limits. Keys server-side only.
- Strict typing; no `Any`/`any`, `# type: ignore` or `@ts-ignore` without a comment explaining why.
- Tests for every feature: pytest for services and API, Playwright for key flows.
- Never commit secrets or `.env`. Keep the template's `LICENSE` notice.
