# Roadmap

Each phase is split into task files in `docs/tasks/`. One task = one branch = one reviewed merge.

- [ ] **Phase 0 — Foundation**
  - [x] Import template, init git, project rules and docs
  - [x] Run locally (Docker Compose), first commit, GitHub repo, CI green
  - [x] 001 Vercel deployment — live on Vercel with Neon Postgres (2026-11-22, see `docs/deploy-vercel.md`)
  - [ ] 002 Own-server deployment (template's Traefik setup + domain)
- [ ] **Phase 1 — Core gaps** (task files drafted, awaiting approval; build in this order)
  - [x] 003 Keep `requirements.txt` in sync with `uv.lock` (CI check) — implemented 2026-11-22: `scripts/export-requirements.sh` + `check-requirements.yml`; Dependabot kept, fix documented in `docs/deploy-vercel.md`
  - [x] 004 Module system + feature flags (`MODULES` env var; items demo becomes the reference module)
  - [x] 007 Backend tests use their own `<db>_test` database (dev data no longer wiped by `pytest`)
  - [x] 005 Roles: member / editor / moderator / admin (+ superuser as owner)
  - [x] 006 File uploads: presigned URLs to S3-compatible storage (SeaweedFS local/own server, R2 on Vercel); avatar as first use
- [ ] **Phase 2 — Content:** models + API, Tiptap editor, public pages + SEO
- [ ] **Phase 3 — AI:** provider layer (Pydantic AI), streaming chat UI, AI writing help, rate limits
- [ ] **Phase 4 — Community**
- [ ] **Phase 5 — Commerce** (Stripe Checkout)
- [ ] **Phase 6 — SaaS** teams + billing (Stripe Billing)
- [ ] Later: pgvector search, OAuth (Authlib), i18n
