# Decisions — every tool and why

Add an entry before adopting any new dependency. Format: what, license, why, rejected alternatives.

| # | Decision | License | Why | Rejected |
|---|---|---|---|---|
| D1 | Base on `fastapi/full-stack-fastapi-template` | MIT | Matches chosen stack (React + FastAPI); maintained by the FastAPI org, ~46k stars, active (last commit Nov 2026); gives auth, users, admin, email, generated client, tests, CI, Docker + Traefik HTTPS — saves weeks and avoids hand-written auth | From scratch (slow, risky); Next.js starters (drop Python); headless CMS as core (second backend) |
| D2 | Pydantic AI for the AI layer | MIT | Same team as Pydantic → native FastAPI fit; one API for Claude/OpenAI/Gemini/local, so swapping provider is config; streaming, tools, typed output built in | Raw provider SDKs (lock-in, own abstraction); LangChain (heavy) |
| D3 | assistant-ui or Vercel AI SDK UI for chat | MIT / Apache-2.0 | Ready chat components (streaming, markdown); final pick in the AI task based on Pydantic AI stream compatibility | Hand-built chat UI |
| D4 | pgvector for search/RAG (later) | PostgreSQL | Vectors inside existing Postgres, supported by Neon; no extra service | Pinecone/Qdrant (extra service/cost) |
| D5 | Tiptap editor | MIT (core) | Most used headless React editor, Tailwind-friendly, extensible for AI writing help | Quill, Slate (less active / lower level) |
| D6 | Stripe Checkout + Billing | proprietary SDK, per-transaction fee | No realistic open alternative for card payments; hosted checkout keeps card data off our servers (PCI burden on Stripe) | Saleor (whole separate Django/GraphQL platform) |
| D7 | boto3 + R2 / MinIO for files | Apache-2.0 / AGPL server (self-host use only) | One S3 API on both targets; keeps backend stateless for Vercel | Local disk (breaks Vercel) |
| D8 | Authlib for OAuth (later) | BSD | Standard OAuth client, plugs into existing JWT auth | fastapi-users (would replace template auth) |
| D9 | slowapi for rate limits | MIT | Cap AI calls per user to control cost | Custom middleware |
| D11 | Presigned direct-to-bucket uploads | — | Vercel functions reject bodies over ~4.5 MB; presigned URLs keep large files off our server on both targets | Uploading through the API |
| D12 | Simple role field (member/editor/moderator/admin) + superuser flag | — | Covers Content/Community needs with one column and one dependency; no permission tables until a module needs them | Full RBAC tables (premature) |
| D13 | Feature flags via `MODULES` env var | — | Per-deployment on/off with zero infrastructure; tables always migrated so enabling needs no migration | Runtime flag service / DB-stored flags (later, for per-org SaaS) |
| D10 | SQLAdmin for internal CRUD (optional) | BSD | Auto admin pages from models | Hand-built admin screens |
| D14 | SeaweedFS (`chrislusf/seaweedfs`, pinned tag) as the local / own-server S3 server instead of MinIO; `amazon/aws-cli` (Apache-2.0) as the one-shot bucket/CORS setup job | Apache-2.0 | Checked 2026-11-23: the `minio/minio` repository is archived and its README says "no longer maintained" (<https://github.com/minio/minio>), the Docker Hub image `minio/minio` is gone, and the replacement (AIStor) has a free but non-open license. SeaweedFS: Apache-2.0, ~36k stars, releases weekly (4.55 on 2026-11-23), official Docker image with 45M pulls, `weed mini` gives a single-container S3 server that pre-creates the bucket. Verified here: presigned PUT with signed `Content-Length`/`Content-Type` (wrong size or type rejected), CORS, HEAD, `response-content-disposition`. Code only uses the S3 API through boto3, so any server (or R2) is interchangeable. Supersedes the MinIO half of D7 | MinIO (unmaintained, AGPL); Garage (AGPL, needs a layout/config bootstrap, no one-command bucket); LocalStack (heavier, emulates AWS) |
