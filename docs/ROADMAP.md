# Roadmap

Each phase is split into task files in `docs/tasks/`. One task = one branch = one reviewed merge.

- [ ] **Phase 0 — Foundation**
  - [x] Import template, init git, project rules and docs
  - [ ] Run locally (Docker Compose), first commit, GitHub repo
  - [ ] 001 Vercel deployment — implemented on `feat/001-vercel-deploy`, pending deploy (see `docs/deploy-vercel.md`)
  - [ ] 002 Own-server deployment (template's Traefik setup + domain)
- [ ] **Phase 1 — Core gaps:** module system + feature flags, file uploads (S3/R2/MinIO), roles beyond admin/user
- [ ] **Phase 2 — Content:** models + API, Tiptap editor, public pages + SEO
- [ ] **Phase 3 — AI:** provider layer (Pydantic AI), streaming chat UI, AI writing help, rate limits
- [ ] **Phase 4 — Community**
- [ ] **Phase 5 — Commerce** (Stripe Checkout)
- [ ] **Phase 6 — SaaS** teams + billing (Stripe Billing)
- [ ] Later: pgvector search, OAuth (Authlib), i18n
