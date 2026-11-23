# 009 — Content module: backend (posts, pages, categories, tags)

**Status:** draft (needs user approval) · **Agent:** backend-engineer · **Branch:** `feat/009-content-backend`

## Decisions (agreed with the user, 2026-11-23)
| Topic | Decision |
|---|---|
| Content types | **Posts** (blog: author, publish date, categories, tags, cover image) and **pages** (standalone: About, Terms…). |
| Who writes | **Editors, admins and superusers** create, edit, publish and delete everything. Members and anonymous visitors only read *published* content. |
| Extras now | **Categories and tags**, **images in the editor** (+ cover image). Later: scheduled publishing, revision history. |
| SEO | Meta-tag injection for public URLs — done in task 011; this task stores the SEO fields. |

## Why
First optional module built on the module system (004), roles (005) and file uploads (006).

## Scope
- Module `backend/app/modules/content/` (models, schemas, service, routes, tests) registered as `content` in the
  registry and `MODULE_NAMES`; enable it in `.env.example` (`MODULES=items,content`). Follow the "How to add a module"
  checklist in `docs/ARCHITECTURE.md`.
- **Models + one migration:**
  - `Post`: id, title, slug (unique), excerpt, body (Tiptap/ProseMirror **JSON**), cover_file_id (FK file, SET NULL),
    status (`draft` | `published`), published_at, author_id (FK user, SET NULL), seo_title, seo_description,
    created_at, updated_at.
  - `Page`: same minus categories/tags/excerpt/cover.
  - `Category` (name, slug unique, description) — a post has **one** optional category.
  - `Tag` (name, slug unique) — many-to-many with posts via `post_tag`.
- **Body format:** stored as Tiptap JSON (never raw HTML). Validate on save: allow-list of node and mark types
  (paragraph, heading 1–3, bulletList, orderedList, listItem, blockquote, codeBlock, horizontalRule, hardBreak, image,
  text; marks bold, italic, strike, code, link), link `href` only `http(s):`/`mailto:`/relative, max body size 1 MB.
  Image nodes reference a **file id** (`attrs.fileId`) of a ready, public image file — no external image URLs.
- **Slugs:** generated from the title (lowercase ASCII, hyphens), editable, unique (append `-2`, `-3`…); fall back to a
  short random slug if the title has no ASCII letters (e.g. Chinese titles). No new dependency.
- **Publishing:** `published_at` set on first publish; unpublish returns to draft.
- **Endpoints** under `/api/v1/content` (module router):
  - Public (no auth): list published posts (pagination, filter by category slug / tag slug), get published post by
    slug, get published page by slug, list categories, list tags.
  - Editor+ (`require_role(UserRole.editor)` — editor, admin, superuser; moderator does **not** qualify): full CRUD for
    posts, pages, categories, tags; publish/unpublish; list including drafts; get by id.
- **Stable image URLs:** public content images must not expire. Add `GET /api/v1/files/{id}/content` (no auth) that, for
  **public, ready, image** files only, redirects (302) to the public URL (`S3_PUBLIC_BASE_URL`) or a fresh signed URL;
  404 otherwise. Responses for posts include resolved image/cover URLs using this endpoint.
- Deleting a post/page doesn't delete its image files (they may be reused); deleting a category un-sets it on posts.
- Tests (pytest) for: permissions per role, draft invisible publicly, slug rules (incl. non-ASCII title), body
  validation (rejects unknown node, `javascript:` link, external image), category/tag filters, image redirect endpoint.

## Out of scope
Editor UI (010), public pages and SEO tags (011), scheduled publishing, revisions, comments (Phase 4 Community).

## New dependencies
None.

## Acceptance criteria
- Backend checks pass (tiered rules in `CLAUDE.md`), coverage ≥ 90%. Migration up/down/up on local DB.
- With `MODULES` not containing `content`, all `/content` routes are 404.
- API client regenerated; `bun run --filter frontend build` passes.
- After merge: apply the migration to Neon **before** pushing (docs/DATABASE.md) and add `content` to Vercel's `MODULES`.
