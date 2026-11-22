# Deploying to Vercel (frontend + API on one domain, DB on Neon)

Task 001. Same commit also deploys with Docker Compose (see `deployment.md`); nothing here changes that path.

## What was chosen and why

Checked against Vercel's current docs (page dates Aug-Nov 2026):

- FastAPI on Vercel: <https://vercel.com/docs/frameworks/backend/fastapi>
- Python runtime: <https://vercel.com/docs/functions/runtimes/python>
- Function duration: <https://vercel.com/docs/functions/configuring-functions/duration>

Findings used:

| Topic | Vercel says |
|---|---|
| Python versions | 3.12 (default), 3.13, 3.14. We have `.python-version` = 3.14, so 3.14 is used. |
| Entrypoint | Vercel looks for a `FastAPI` instance named `app` in `app.py`, `index.py`, `server.py`, `main.py`, ... at the repo root, or in `src/` / `app/`; otherwise `tool.vercel.entrypoint` in `pyproject.toml`. |
| Static files | `app.frontend("/", directory=...)` is promoted to the CDN at build time. API routes always win over frontend files. The default `fallback="auto"` serves `index.html` (HTTP 200) for browser navigation to unknown paths, so SPA deep links work. |
| Dependencies | `pyproject.toml` (with or without `uv.lock`) or `requirements.txt`. |
| Build command | `buildCommand` in `vercel.json` (takes precedence over `[tool.vercel.scripts]`). |
| Duration | Fluid compute is on by default. Default 300 s; max 300 s on Hobby, 800 s on Pro (30 min beta). Configure with `functions.<entrypoint>.maxDuration` in `vercel.json`. |

So the simplest setup is the **native FastAPI preset**, not hand-written `routes`/`rewrites`:

- `index.py` (repo root): adds `backend/` to `sys.path` and re-exports `app` from `backend/app/main.py`. Needed because our app lives in `backend/`, not at the root.
- `backend/app/main.py`: `app.frontend("/", ...)` is now mounted only if `backend/app/frontend/` exists. Vercel's build runs the Vite build first (so the folder exists and its files are promoted to the CDN); plain `uvicorn`/tests/dev without a build no longer crash.
- `vercel.json`: `buildCommand` installs Bun and builds the frontend (output goes to `backend/app/frontend` per `frontend/vite.config.ts`); `maxDuration` 60 s for the function.
- `requirements.txt` (repo root): generated from `uv.lock` (`uv export`). Our root `pyproject.toml` is only a uv workspace with no `[project]` dependencies (they live in `backend/pyproject.toml`), so Vercel needs this file to know what to install. **Regenerate when backend dependencies change:**
  ```bash
  uv export --package app --no-hashes --frozen --no-emit-workspace --no-dev -o requirements.txt
  ```
- `.vercelignore`: keeps `node_modules`, `.venv`, `.env` out of the upload.

`VITE_API_URL` must be **unset/empty** on Vercel: the frontend then calls `/api/v1/...` on the same domain.
No `FASTAPI_ENV` on Vercel: the settings only accept the value `development` (or unset), and unset means production behaviour.
`.env` is not needed: pydantic-settings ignores a missing env file and reads project env vars.

## Step by step (you do these)

### 1. Neon (database)
1. Sign in at <https://console.neon.tech>, **Create project** (pick a region near your Vercel function region, default `iad1`/US East; Postgres 17 or newer is fine).
2. On the project dashboard click **Connect**, tick **Connection pooling** (the host contains `-pooler`), copy the string. It looks like
   `postgresql://USER:PASSWORD@ep-xxx-pooler.REGION.aws.neon.tech/neondb?sslmode=require`. This is the **pooled** `DATABASE_URL`. (`postgresql://` is rewritten to the psycopg driver automatically by `config.py`.)
3. Also copy the **unpooled** string (untick pooling) if you want to run migrations through it; the pooled one normally also works for Alembic, but the unpooled one is the safe choice for DDL.

### 2. Vercel (project)
1. <https://vercel.com/new> > **Import Git Repository** > choose `ArcherEA/practice` (grant the GitHub app access if asked).
2. Root Directory: leave as repo root. Framework Preset: should auto-detect **FastAPI**; leave Build/Install/Output settings as default (the Build Command comes from `vercel.json`). Do not set an Output Directory.
3. Add environment variables (Project Settings > Environment Variables, for Production and Preview) before the first deploy:

| Variable | Value |
|---|---|
| `PROJECT_NAME` | Display name, e.g. `PRODUCT` |
| `SECRET_KEY` | Random string: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Not `changethis`. |
| `DATABASE_URL` | Neon **pooled** string from step 1 |
| `FIRST_SUPERUSER` | Admin email |
| `FIRST_SUPERUSER_PASSWORD` | Strong password. Not `changethis`. |
| `FRONTEND_HOST` | Your production URL, e.g. `https://<project>.vercel.app` (only used for CORS; same-origin works anyway) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TLS`, `EMAILS_FROM_EMAIL`, `EMAILS_FROM_NAME` | Your SMTP provider. Optional: without `SMTP_HOST` + `EMAILS_FROM_EMAIL` email features (password reset) are disabled. |
| `SENTRY_DSN` | Optional |
| `VITE_API_URL` | **Do not set** (empty = same domain) |
| `FASTAPI_ENV` | **Do not set** (only `development` is valid; unset = production) |

   Vercel build output uses these too, so they must exist before the first build (the app is imported at build time).
4. Click **Deploy**.

### 3. Migrations and first superuser (from your machine, not in the function)
Run once after the first deploy and after every new Alembic migration. Use the Neon string (pooled works; unpooled preferred):

PowerShell, from the repo root:
```powershell
$env:DATABASE_URL = "postgresql://USER:PASSWORD@ep-xxx.REGION.aws.neon.tech/neondb?sslmode=require"
$env:SECRET_KEY = "<same as Vercel>"; $env:PROJECT_NAME = "PRODUCT"
$env:FIRST_SUPERUSER = "<same as Vercel>"; $env:FIRST_SUPERUSER_PASSWORD = "<same as Vercel>"
cd backend
uv run bash scripts/prestart.sh
```
Git Bash equivalent: `export` the same variables, then `cd backend && uv run bash scripts/prestart.sh`. The script runs `alembic upgrade head` then `python app/initial_data.py` (creates the first superuser if missing). Real environment variables take priority over the local `.env`, so your local dev `.env` is not used for these variables.
Do this before expecting login to work. A GitHub Action doing the same on each push is a possible follow-up.

### 4. Check
- `https://<project>.vercel.app/` shows the login page, a deep link such as `/login` also loads (SPA fallback).
- `https://<project>.vercel.app/api/v1/utils/health-check/` returns `true`.
- Log in with `FIRST_SUPERUSER` / `FIRST_SUPERUSER_PASSWORD`.

## Known limits
- **Function timeout:** `vercel.json` sets `maxDuration` 60 s. Vercel allows up to 300 s on Hobby and 800 s on Pro by default. Long AI streams (Phase 3) must stay below that, or move to the fallback in `ARCHITECTURE.md` (frontend on Vercel, API on own server; only an env var changes). Streaming responses are supported, but the connection is cut at the limit.
- **Cold starts:** first request after idle can take a couple of seconds (Python + FastAPI + argon2 imports + a new DB connection). Fluid compute reuses warm instances, which reduces this. Use Neon's pooled host so many instances do not exhaust Postgres connections; Neon itself may also wake a suspended compute (~1 s) on free tier.
- **Stateless:** no local disk writes (files go to S3/R2 later); each instance has its own memory.
- **Bundle size:** 500 MB uncompressed for the function.
- **Static files:** served by the CDN, so FastAPI middleware/`Depends` do not apply to them. The built `backend/app/frontend` also stays in the function bundle (harmless); set `[tool.vercel.fastapi.static] exclude = true` in a `pyproject.toml` if size ever matters.

## Not verified offline
`vercel build` needs a linked Vercel project (`vercel pull`, i.e. login), so the full Vercel build and a preview deploy could not be run. Locally verified: app import and `/api/v1/utils/health-check/` through the root `index.py` with only environment variables, no `.env` file and no frontend folder; the frontend build command; backend tests. Unverified until the first deploy: that Vercel's build container allows `npm install -g bun`, that dependency install picks up `requirements.txt`, and CDN promotion of the SPA with `index.html` fallback.
