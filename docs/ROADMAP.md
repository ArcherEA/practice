# Roadmap

Each phase is split into task files in `docs/tasks/`. One task = one branch = one reviewed merge.

- [ ] **Phase 0 — Foundation**
  - [x] Import template, init git, project rules and docs
  - [x] Run locally (Docker Compose), first commit, GitHub repo, CI green
  - [x] 001 Vercel deployment — live on Vercel with Neon Postgres (2026-11-22, see `docs/deploy-vercel.md`)
  - [ ] 002 Own-server deployment (template's Traefik setup + domain)
- [ ] **Phase 1 — Core gaps:** module system + feature flags, file uploads (S3/R2/MinIO), roles beyond admin/user
- [ ] **Phase 2 — Content:** models + API, Tiptap editor, public pages + SEO
- [ ] **Phase 3 — AI:** provider layer (Pydantic AI), streaming chat UI, AI writing help, rate limits
- [ ] **Phase 4 — Community**
- [ ] **Phase 5 — Commerce** (Stripe Checkout)
- [ ] **Phase 6 — SaaS** teams + billing (Stripe Billing)
- [ ] Later: pgvector search, OAuth (Authlib), i18n
