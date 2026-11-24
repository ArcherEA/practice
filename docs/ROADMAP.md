# Roadmap

Each phase is split into task files in `docs/tasks/`. One task = one branch = one reviewed merge.

- [ ] **Phase 0 — Foundation**
  - [x] Import template, init git, project rules and docs
  - [x] Run locally (Docker Compose), first commit, GitHub repo, CI green
  - [x] 001 Vercel deployment — live on Vercel with Neon Postgres (2026-11-22, see `docs/deploy-vercel.md`)
  - [ ] 002 Own-server deployment (template's Traefik setup + domain)
- [x] **Phase 1 — Core gaps** (complete 2026-11-23)
  - [x] 003 Keep `requirements.txt` in sync with `uv.lock` (CI check) — implemented 2026-11-22: `scripts/export-requirements.sh` + `check-requirements.yml`; Dependabot kept, fix documented in `docs/deploy-vercel.md`
  - [x] 004 Module system + feature flags (`MODULES` env var; items demo becomes the reference module)
  - [x] 007 Backend tests use their own `<db>_test` database (dev data no longer wiped by `pytest`)
  - [x] 005 Roles: member / editor / moderator / admin (+ superuser as owner)
  - [x] 006 File uploads: presigned URLs to S3-compatible storage (SeaweedFS local/own server, R2 on Vercel); avatar as first use
- [x] **Phase 2 — Content** (complete 2026-11-23)
  - [x] 009 Content backend: posts + pages, categories + tags, Tiptap JSON body (validated), stable public image URLs  — implemented 2026-11-23
  - [x] 010 Editor UI: Tiptap editor (open-source packages), posts/pages/taxonomy screens for editors+  — implemented 2026-11-23
  - [x] 011 Public pages + SEO: /blog, /p/<slug>, meta-tag injection in FastAPI, sitemap.xml, robots.txt  — implemented 2026-11-23
  - Later: scheduled publishing, revision history, RSS, search
- [x] **Project process** (alongside the phases)
  - [x] 008 Log out automatically when the logged-in user no longer exists
  - [x] 012 README + quick start verified with a fresh clone
  - [x] 013 Required CI checks (`alls-green-*`) + pull-request workflow (`docs/BRANCH-PROTECTION.md`)
  - [x] 018 Published content is easy to find: View on site / Copy link, View blog link, published pages in the public menu  — implemented 2026-11-23
  - [x] 020 Fix content editor toolbar flake on CI  — done 2026-11-23
  - [ ] 021 File caching
  - [x] 022 UI follow-ups: scroll to linked comment, moderation paging, return to page after login  — done 2026-11-23
  - [ ] 023 Dependency updates  — in progress
- [x] **Phase 3 — Community** (complete 2026-11-23)
  - [x] 014 Comments on posts/pages (1 level of replies), likes, reports, moderation queue + suspensions (backend)  — implemented 2026-11-23
  - [x] 015 Usernames, public profiles, follows, in-app notifications (backend)  — implemented 2026-11-23
  - [x] 016 Comments, likes, reporting and moderation UI  — implemented 2026-11-23
  - [x] 017 Profiles (/u/<username>), follows and notifications bell UI  — implemented 2026-11-23
  - Later: forum/discussions, social feed, email notifications, blocking/muting
- [ ] **Phase 4 — Commerce** (planned and approved 2026-11-23; D20/D21; build in this order)
  - [x] 024 Catalog backend: products (digital / physical / service), variants, prices per currency, stock, booking slots  — implemented 2026-11-23
  - [ ] 025 Store admin screens
  - [ ] 026 Storefront, currency switcher and cart (+ product SEO and sitemap)
  - [ ] 027 Stripe Checkout, webhooks and orders (backend) — needs a Stripe account (test mode)
  - [ ] 028 Checkout UI, orders, downloads, bookings, admin fulfilment and order emails
  - Later: tax (Stripe Tax), coupons, refunds from our admin, reviews, product search, weekly-availability bookings
- [ ] **Phase 5 — SaaS:** teams + billing (Stripe Billing)
- [ ] **Phase 6 — AI (last, decided 2026-11-23):** planned once the other modules show where AI helps most.
  Ideas to evaluate then: provider layer (Pydantic AI, D2), AI writing help in the content editor, chat assistant,
  semantic search (pgvector), community moderation. Rules already in `CLAUDE.md` (all AI calls through `backend/app/ai/`,
  timeouts, per-user rate limits, keys server-side) stay in force.
- [ ] Later: pgvector search, OAuth (Authlib), i18n
