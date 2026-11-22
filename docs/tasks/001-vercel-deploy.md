# 001 — Vercel deployment

**Status:** draft (needs user approval) · **Agent:** backend-engineer · **Branch:** `feat/001-vercel-deploy`

## Goal
The same commit that runs on the own server also deploys to Vercel: frontend + API on one Vercel project, database on Neon.

## Scope
- Add `vercel.json` at repo root and an entry point (e.g. `api/index.py`) that imports `app.main:app` from `backend/`.
- Frontend: build with Bun/Vite and serve as Vercel static output; route `/api/*` to the Python function, everything else to the SPA (`index.html` fallback).
- Make `backend/app/main.py`'s `app.frontend(...)` mount tolerant of a missing `backend/app/frontend/` directory (on Vercel, static files are served by Vercel, not FastAPI).
- Database: document using Neon's **pooled** `DATABASE_URL`; migrations + first superuser run from a GitHub Action (or locally) — not inside the function.
- Document required env vars for Vercel in `docs/deploy-vercel.md` (`SECRET_KEY`, `FIRST_SUPERUSER*`, `DATABASE_URL`, `FRONTEND_HOST`, SMTP vars, `FASTAPI_ENV=production`).

## Out of scope
File storage, AI, custom domain, own-server deploy (task 002).

## New dependencies
None expected. If Vercel's Python runtime needs a `requirements.txt`, generate it from `uv.lock` (`uv export`) — explain in the report.

## Acceptance criteria
- `vercel build` succeeds locally (or a preview deploy succeeds).
- On the preview URL: the login page loads, `/api/v1/utils/health-check/` returns OK, login with the superuser works.
- Local Docker Compose flow still works unchanged; backend tests still pass.

## Open questions for the lead
- Confirm Vercel's current Python runtime version supports Python 3.14; if not, pin the function to the newest supported version and report.
