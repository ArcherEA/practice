# Product spec

## Goal
One reusable platform that can be configured into a SaaS app, a content site, a store or a community,
with AI features built in. Published on Vercel and on a self-hosted server from the same codebase.

## Modules
| Module | Status | Contents |
|---|---|---|
| Core | from template + gaps | Auth (JWT, password recovery), users, admin role, email. To add: feature flags, file uploads, finer roles |
| Content | planned | Pages, posts, categories, Tiptap editor, SEO meta, public pages |
| AI | planned | Pydantic AI provider layer, streaming chat, AI writing help in the editor; later pgvector search |
| Community | planned | Profiles, posts, comments, likes, follows, notifications |
| Commerce | planned | Products, cart, Stripe Checkout, orders |
| SaaS | planned | Organizations/teams, invites, plans, Stripe Billing + Customer Portal |

Every module except Core can be switched on/off with a feature flag (env var `MODULES=content,ai,...`).

## Non-goals (for now)
Mobile apps, multi-language UI (i18n), marketplace / multi-vendor commerce, self-hosted LLMs.
