# 004 — Module system and feature flags

**Status:** draft (needs user approval) · **Agents:** backend-engineer, then frontend-engineer · **Branch:** `feat/004-module-system`

## Why
Every later phase (Content, AI, Community, Commerce, SaaS) is an optional module. We need one agreed way to add a
module and switch it on or off per deployment, before building any of them.

## Scope — backend
- Setting `MODULES: list[str]` (env var `MODULES=content,ai`; empty = only Core). Unknown names fail at startup with a clear error.
- Package `backend/app/modules/` with a small registry: each module exposes `name`, `router` (APIRouter) and optional
  `models` import so Alembic sees its tables. `app/api/main.py` includes routers only for enabled modules.
- Alembic always imports **all** modules' models (tables exist even if a module is off, so turning it on needs no migration).
- Move the template's demo **items** feature into `app/modules/items/` as the reference module (routes, models, crud,
  tests), keeping the same URLs `/api/v1/items/` so nothing breaks. Enabled by default in `.env.example`.
- Public endpoint `GET /api/v1/utils/config` → `{ "project_name": ..., "modules": [...] }` (no auth) for the frontend.
- Document "how to add a module" in `docs/ARCHITECTURE.md` (checklist of files to create).

## Scope — frontend (after backend is merged and the client regenerated)
- Fetch `/utils/config` once (TanStack Query) and expose `useModules()` / `isModuleEnabled(name)`.
- Sidebar items come from enabled modules; routes of disabled modules show the NotFound page.
- Move the items UI into `src/features/items/` as the reference frontend module.

## Out of scope
Per-organization or per-user flags (that's SaaS, Phase 6). Admin UI to toggle modules (env var only for now).

## New dependencies
None.

## Acceptance criteria
- With `MODULES=items`: items page and API work as today. With `MODULES=` (empty): `/api/v1/items/` is 404 and the
  sidebar has no Items entry; everything else works.
- Tests cover both settings. All existing tests and Playwright still pass. Docker and Vercel unaffected (add `MODULES` to `docs/deploy-vercel.md`).
