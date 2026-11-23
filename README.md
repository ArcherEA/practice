# PRODUCT

A modular full-stack web platform — **FastAPI + PostgreSQL** backend, **React + TypeScript** frontend — that can be
configured into a SaaS app, a content site, a store or a community, with AI features planned. It deploys to
**Vercel** (with Neon Postgres and Cloudflare R2) and to **your own server** (Docker Compose + Traefik).

Built on the open-source [Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template) (MIT).

[![Test Backend](../../actions/workflows/test-backend.yml/badge.svg)](../../actions/workflows/test-backend.yml)
[![Test Docker Compose](../../actions/workflows/test-docker-compose.yml/badge.svg)](../../actions/workflows/test-docker-compose.yml)
[![Playwright Tests](../../actions/workflows/playwright.yml/badge.svg)](../../actions/workflows/playwright.yml)

## What's inside
- **Core:** login (JWT), users, roles (member / editor / moderator / admin + superuser), password recovery by email,
  file uploads (S3-compatible storage) with usage limits, profile pictures.
- **Modules** you switch on with `MODULES` in `.env`: `items` (demo) and `content` (posts, pages, categories, tags).
- Status and plans: [docs/ROADMAP.md](docs/ROADMAP.md). Why each tool was chosen: [docs/DECISIONS.md](docs/DECISIONS.md).

## Tools you need

| Tool | Why | Install |
|---|---|---|
| **Git** | get the code | <https://git-scm.com/downloads> |
| **Docker Desktop** (Compose v2) | runs PostgreSQL, Mailpit (test email inbox) and SeaweedFS (file storage) | <https://www.docker.com/products/docker-desktop/> — start it before the steps below |
| **uv** | Python packages; installs **Python 3.14** for you (from `.python-version`) | <https://docs.astral.sh/uv/getting-started/installation/> |
| **Bun** | frontend packages and dev server | <https://bun.sh> |
| Node.js 20+ | *optional* — some frontend tools use it when present | <https://nodejs.org> |
| Playwright browser | *optional* — only to run end-to-end tests locally: `cd frontend; bunx playwright install chromium` | — |

After installing uv or Bun, **open a new terminal** so it's on your `PATH`.

## Quick start (local development)

Commands work in **Windows PowerShell** and in **macOS/Linux** shells. Run them from the project folder.

```bash
# 1. Get the code
git clone https://github.com/ArcherEA/practice.git PRODUCT
cd PRODUCT

# 2. Create your local settings from the examples (these files are not in git)
cp .env.example .env
cp frontend/.env.example frontend/.env

# 3. Start the database, the email catcher and the file storage (Docker Desktop must be running)
docker compose up -d --wait db mailpit storage storage-init

# 4. Install backend packages, create the database tables, create the first admin
cd backend
uv sync
uv run alembic upgrade head
uv run python app/initial_data.py

# 5. Start the backend API (keep this terminal open)
uv run fastapi dev
```

**Windows only:** if step 5 crashes with `UnicodeEncodeError: 'gbk' codec…`, run `$env:PYTHONUTF8 = "1"` first
(PowerShell) — see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

In a **second terminal**, from the project folder:

```bash
# 6. Install frontend packages and start the frontend
bun install
bun run dev
```

Open **<http://localhost:5173>** and log in with `FIRST_SUPERUSER` / `FIRST_SUPERUSER_PASSWORD` from your `.env`
(default `admin@example.com` / `changethis`).

| URL | What |
|---|---|
| <http://localhost:5173> | the app (frontend dev server) |
| <http://localhost:8000/docs> | interactive API docs |
| <http://localhost:8025> | Mailpit — every email the app sends lands here |
| <http://127.0.0.1:8888> | SeaweedFS file browser (uploaded files) |

Next time you only need step 3 (if Docker was stopped), step 5 and step 6. After pulling new code, run
`uv run alembic upgrade head` (in `backend/`) again — it applies only the new database changes.

## Configuration and the database

| File | What it holds | In git? |
|---|---|---|
| `.env` | **all backend settings**: secrets, first admin, **database** (`POSTGRES_PASSWORD`, `DATABASE_URL`), modules, storage | no — create it from `.env.example` |
| `.env.example` | every setting with safe local defaults and comments | yes |
| `frontend/.env` | where the dev frontend finds the API (`VITE_API_URL`) | no — create it from `frontend/.env.example` |
| `compose.yml` | the Docker services; Postgres database `app`, data kept in a Docker volume | yes |

The local database needs no manual setup: Docker creates an empty PostgreSQL, and `alembic upgrade head` creates every
table (each schema change is a numbered *migration* in `backend/app/alembic/versions/`; `upgrade head` applies the ones
your database doesn't have yet). The default `changethis` passwords are fine on your own machine — change them for
anything others can reach. Full guide (backups, Neon production database, recovery): [docs/DATABASE.md](docs/DATABASE.md).

## Guides
- [development.md](development.md) — local development in detail, full stack in Docker (`docker compose watch`)
- [docs/DATABASE.md](docs/DATABASE.md) — migrations, Neon, backups and recovery
- [docs/deploy-vercel.md](docs/deploy-vercel.md) — deploy to Vercel (+ Neon, Cloudflare R2)
- [deployment-docker-compose.md](deployment-docker-compose.md) — deploy to your own server
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the code is organised, modules, roles, storage
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — problems we hit and how they were solved
- [CLAUDE.md](CLAUDE.md) — rules for contributors (human or AI): workflow, testing tiers, code rules

## Running tests
```bash
cd backend
uv run pytest                     # backend tests (use their own database, app_test — your data is safe)
cd ../frontend
bunx playwright test tests/login.spec.ts   # one end-to-end spec (needs the app running)
```
CI runs everything on every push to `main`.

## License
MIT — see [LICENSE](LICENSE). Based on the Full Stack FastAPI Template by Sebastián Ramírez, also MIT.
