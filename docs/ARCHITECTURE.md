# Architecture

## As inherited from the template
- **One deployable app:** the React frontend is built by Vite and served by FastAPI itself
  (`backend/app/main.py`: `app.frontend("/", directory=FRONTEND_DIR)`, build output in `backend/app/frontend/`).
  The API lives under `/api/v1`, docs at `/api/v1/docs`.
- `backend/app/`: `api/routes/` (login, users, items, utils, private), `models.py` (SQLModel), `crud.py`,
  `core/` (config, db, security), `alembic/`, `email-templates/`.
- `frontend/src/`: `routes/` (TanStack file routes), `components/`, `client/` (generated), `hooks/`.
- `packages/react-email/`: email templates.
- `compose.yml` (+ `compose.override.yml` for local, `compose.deploy.yml` for server): Traefik, Postgres, Adminer, Mailpit, backend.

## What we add
- **Modules:** backend `app/modules/<name>/{models.py, schemas.py, service.py, routes.py, tests/}`, registered in
  `app/modules/registry.py` and mounted by `app/api/main.py` only when enabled in `settings.MODULES`. Frontend `src/features/<name>/` + `src/routes/<name>/`.
- **AI layer:** `app/ai/` wraps Pydantic AI; modules call it, never a provider SDK directly. Streaming over SSE.
- **Storage:** `app/core/storage.py` — S3-compatible client (R2 on Vercel, SeaweedFS container locally and on the own server).

### How to add a module
`MODULES=a,b` (comma-separated; unset = `items`; `none` = Core only). Tables of **all** modules always exist, enabled or not.
1. Backend `backend/app/modules/<name>/`: `__init__.py`, `models.py` (SQLModel tables), `crud.py`/`service.py`, `routes.py` (`router = APIRouter(prefix="/<name>", tags=["<name>"])`). Use `app/modules/items/` as the template.
2. Register: add the name to `MODULE_NAMES` in `app/modules/__init__.py` and a `Module(name=..., router=...)` entry in `app/modules/registry.py`.
3. Alembic/ORM: add `import app.modules.<name>.models` at the bottom of `app/models.py`; reference core models by string (`Optional["User"]`) with `TYPE_CHECKING` imports to avoid cycles. Then `uv run alembic revision --autogenerate -m "add <name>"` and review it.
4. Tests in `backend/tests/modules/<name>/` (the registry test checks that names match).
5. Run `scripts/generate-client.sh` so the frontend client includes the new endpoints.
6. Frontend: `src/features/<name>/` (components, hooks; see `features/items/`), a route `src/routes/_layout/<name>.tsx` that is thin (imports the page from the feature) and has `beforeLoad: ({ context }) => requireModule(context.queryClient, "<name>")` (shows NotFound when the module is off), and one entry in `moduleNavItems` in `src/features/modules/nav.ts` (the sidebar shows it only when enabled). `useModules()` / `isEnabled(name)` come from `src/features/modules/`.
7. Docs: mention any extra env vars in `.env.example` and `docs/deploy-vercel.md`.

The frontend learns which modules are on from the public `GET /api/v1/utils/config` (`{project_name, modules}`).

## File storage (task 006)
Core infrastructure, always on (not a `MODULES` entry: avatars and every later module depend on it). Code:
`app/core/storage.py` (boto3 behind a `Storage` protocol, injected with the `StorageDep` dependency so tests use a fake),
`app/core/files.py` (service: limits, confirm, avatars, cleanup), `app/api/routes/files.py`, models `File` and
`User.avatar_file_id` in `app/models.py`.

Upload flow (the file bytes never pass through our API):
1. `POST /api/v1/files/` `{filename, content_type, size, public?}` checks the limits, stores a `pending` row (it counts
   toward the quotas) and returns a presigned **PUT** URL.
2. The browser `PUT`s the bytes to that URL with the returned headers. `Content-Length` and `Content-Type` are part of the
   signature, so the bucket rejects any other size or type (R2 has no presigned POST with a size condition).
3. `POST /api/v1/files/{id}/confirm` does a HEAD on the object: real size must match and be within `UPLOAD_MAX_BYTES`,
   otherwise the object and row are deleted and the API answers 400. Success sets the file `ready`.

Two hostnames: the backend talks to the bucket at `S3_ENDPOINT_URL` (inside Docker `http://storage:8333`), but a presigned
URL contains the host the **browser** must reach, so it is signed for `S3_PUBLIC_ENDPOINT_URL` (falls back to
`S3_ENDPOINT_URL`). Locally the browser uses `http://localhost:9000`; on the own server `https://storage.<DOMAIN>` (Traefik
in `compose.deploy.yml`); on Vercel both are the R2 endpoint. The one-shot `storage-init` service creates the bucket and
sets CORS for `FRONTEND_HOST`.

Only JPEG, PNG, WebP and GIF are served inline; every other type gets `Content-Disposition: attachment` in the signed GET.
Only those image types may be `public` (served from `S3_PUBLIC_BASE_URL` when set) or used as an avatar.
Limits and R2 free-tier guidance: `docs/deploy-vercel.md`. Usage report: `GET /api/v1/files/usage` (admin or superuser).

**Cleanup command** (no scheduler): pending uploads older than 24 hours (object and row) are removed with
```
cd backend && uv run python -m app.scripts.cleanup_files
```
Run it by hand or from any cron/scheduled job with the production env vars. Deleting a user also deletes their objects
(best effort; failures are logged and the orphan object can be removed by hand).

## Roles and permissions
`User.role` (`member` default, `editor`, `moderator`, `admin`; VARCHAR(20), enum in `app/core/roles.py`) plus the
`is_superuser` "owner" flag. One pure function, `has_role(user, required)`, decides everything.

| Role | Also satisfies |
|---|---|
| `admin` | `editor`, `moderator`, `member` |
| `editor` | `member` |
| `moderator` | `member` |
| `member` | — |
| superuser | every check, regardless of `role` |

`editor` and `moderator` are siblings: neither includes the other.

Protect an endpoint in a module with the dependency from `app/api/deps.py`:
```python
from app.api.deps import require_role
from app.core.roles import UserRole

@router.post("/", dependencies=[Depends(require_role(UserRole.editor))])
def create_article(...): ...
# or use the aliases: RequireEditor, RequireModerator, RequireAdmin, AdminUser (injects the user)
```
It returns 403 "The user doesn't have enough privileges". `get_current_active_superuser` still exists for owner-only routes.

User management (`/users` list/create/read/update/delete) needs `admin` or superuser. Only superusers can grant or revoke
`admin`, create admins, set `is_superuser`, or modify/delete admins and superusers (admins manage everyone except
admins and superusers; an admin edits their own record via `/users/me`). Nobody can change their own role (`/users/me`
does not accept `role`; the admin endpoint returns 403), remove their own superuser flag, or deactivate themselves —
this prevents locking out the last superuser. Signup always creates a `member`; `FIRST_SUPERUSER` is created as `admin`.
To add a role later: extend `UserRole` and `ROLE_INCLUDES` (no DB migration needed).

Database operations (migrations, Neon, backups, recovery): see `docs/DATABASE.md`.

## Content module (task 009)
Enable with `MODULES=items,content`. Code: `app/modules/content/` (`models.py` tables, `schemas.py` API models,
`body.py` + `slugs.py` pure functions, `service.py`, `routes.py`). Routes live under `/api/v1/content`.

**Data model** (tables always exist; one migration):
`post` (title, unique `slug`, excerpt, `body` JSONB, `cover_file_id` -> file SET NULL, `category_id` -> category SET NULL,
`status` draft|published, `published_at`, `author_id` -> user SET NULL, `seo_title`, `seo_description`, timestamps),
`page` (the same minus excerpt/cover/category/tags), `category` (name, unique slug, description; a post has one optional),
`tag` (name, unique slug), `post_tag` (post_id, tag_id, both ON DELETE CASCADE). Publishing sets `published_at` on the
first publish only; unpublishing returns to draft and keeps the date. Deleting posts/pages never deletes image files.

**Body format:** Tiptap/ProseMirror JSON (`{"type":"doc","content":[...]}`), never HTML (D15). `body.sanitize_body` runs
on every save and rejects anything not on the allow-list: nodes `paragraph`, `heading` (level 1-3), `bulletList`,
`orderedList`, `listItem`, `blockquote`, `codeBlock`, `horizontalRule`, `hardBreak`, `image`, `text`; marks `bold`, `italic`,
`strike`, `code`, `link`. Unknown node/mark types, unknown fields or attributes, misplaced children, nesting deeper than 24
levels and bodies over 1 MB (UTF-8 bytes) are rejected with 422 (the message names the JSON path). Link `href` must be
`http:`, `https:`, `mailto:` or start with a single `/` (trimmed, case-insensitive; `javascript:`, `data:`, `//host`
and control characters are refused). The saved body is the cleaned copy.

**Images:** an `image` node carries `attrs.fileId` only. On save the service checks the file exists, is `ready`, `public`
and a JPEG/PNG/WebP/GIF; the owner may be any user, so editors can reuse each other's images. A `src` sent by the client is
dropped; responses add `attrs.src` = `/api/v1/files/{id}/content`, and posts get `cover_url` the same way.
`GET /api/v1/files/{id}/content` (no auth, part of the files routes) 302-redirects to `S3_PUBLIC_BASE_URL` or a fresh
signed URL for public, ready, inline-image files and returns 404 otherwise, so the URL stored in pages never expires.

**Permissions:** reading published content is public. Everything under `/content/manage` needs `require_role(UserRole.editor)`:
editor, admin and superuser pass; moderator and member get 403. Drafts are only returned by `/manage` routes.

**Slugs:** `slugs.py` lowercases to ASCII (accents folded), turns other characters into single hyphens, trims, max 80
characters; nothing left (e.g. a Chinese title) -> 8 random hex characters; clashes get `-2`, `-3`... per table. A slug
sent by the client goes through the same function. Renaming a title does not change the slug.

**Editor UI (task 010):** `frontend/src/features/content/`, routes `/content/posts[/$id]`, `/content/pages[/$id]`,
`/content/taxonomy` (guarded by `requireModule("content")` + `hasRole(user, "editor")`; the sidebar entry uses
`requiredRole` in `moduleNavItems`). `extensions.ts` is the single Tiptap schema (StarterKit with headings 1-3, underline
and the bundled link disabled, own Link with http/https/mailto//path rule, Image with a `fileId` attribute); the editor
cannot produce anything outside the backend allow-list. `ContentRenderer` is the read-only renderer reused by public pages.

## Public pages and SEO (task 011, content module)
The SPA stays a single-page app (D16). Routes **outside `/api`** return the built `index.html` with real tags:
`/blog`, `/blog/{slug}`, `/blog/category/{slug}`, `/blog/tag/{slug}`, `/p/{slug}` (`modules/content/public_routes.py`,
logic in `seo.py`). Per request the backend replaces/injects `<title>`, `description`, `canonical`, Open Graph
(`og:title/description/type/url/site_name`, `og:image` = `SITE_URL` + `/api/v1/files/{id}/content` when there is a cover)
and Twitter card tags; every value goes through `html.escape`. Unknown or draft slugs return the same shell with
**404** and `<meta name="robots" content="noindex">`, so the SPA can render its own not-found page. Responses are
`Cache-Control: public, max-age=60, s-maxage=60` (404: `no-cache`).
- The template is `backend/app/frontend/index.html` (path in `app.state.frontend_dir`). If it is missing (local dev
  without a build) a minimal HTML page with the tags and a link to `FRONTEND_HOST` is returned and a warning is logged.
- `GET /sitemap.xml` (content module only): `/blog`, published posts and pages, categories/tags that have published
  posts; absolute URLs from `SITE_URL`, `lastmod` = last update date. `GET /robots.txt` is a core route, always on
  (disallows `/content/`, `/admin`, `/settings`, `/api/`); the `Sitemap:` line is present only when `content` is enabled.
- Modules declare such routes with `Module.public_router`; `create_app` includes them **before** `application.frontend(...)`
  so they win over the SPA mount. They use `include_in_schema=False`, so the generated client is unaffected.
- `SITE_URL` (public base URL, no trailing slash) is the one setting; see `docs/deploy-vercel.md` for how Vercel serves this.
- Frontend: the public site lives in its own pathless layout route `src/routes/_public.tsx` (header with site name, Blog link,
  "Log in" or "Dashboard", footer), **not** under `_layout`, so no login is required. Children: `/blog`, `/blog/$slug`,
  `/blog/category/$slug`, `/blog/tag/$slug`, `/p/$slug`; code in `src/features/content/public/`. The layout guards with
  `requireModule(..., "content")`; an API 404 in a loader becomes the layout's own not-found page. Each route's `head()` builds
  title and description with the same rules as `seo.py` (`public/api.ts`), so SPA navigation and a direct hit agree. Bodies render
  through the read-only `ContentRenderer`; image and cover URLs are prefixed with `VITE_API_URL`.
- Local dev: Vite on :5173 does not run this. Test with `bun run build` then `fastapi dev` (backend on :8000 serves the
  build), or `docker compose watch`.

## Community module (task 014)
Enable with `MODULES=items,content,community`. **`community` needs `content`**: settings validation fails at startup with
"Module 'community' requires module(s) content ..." otherwise (`MODULE_DEPENDENCIES` in `app/modules/__init__.py`).
Code: `app/modules/community/` (`models.py`, `schemas.py`, `service.py`, `routes.py`, `deps.py`, `events.py`); routes under
`/api/v1/community`. Product decisions: D17 (comments on blog content, one reply level, publish-then-moderate, plain text).

**Data model** (tables always exist; one migration; no core table changed):
| Table | Columns / notes |
|---|---|
| `comment` | `post_id` / `page_id` (exactly one, check constraint; both FK ON DELETE CASCADE), `author_id` -> user SET NULL (shown as a deleted user), `parent_id` -> comment CASCADE (null or a top-level comment), `body` text, `status` visible\|hidden, `deleted_at`, `removed_by_moderator`, `like_count`, `created_at`, `edited_at` |
| `comment_like` | (`comment_id`, `user_id`) primary key, both CASCADE; `comment.like_count` is the stored counter |
| `post_like`, `post_like_count` | likes of posts and their counter, keyed by post id, so the content module is unchanged |
| `comment_report` | `comment_id`, `reporter_id`, `reason` spam\|abuse\|other, `note`, `status` open\|resolved, `resolved_by/at`; unique (`comment_id`, `reporter_id`), so a user reports a comment once, even after it was resolved |
| `community_suspension` | `user_id`, `until` (null = indefinite), `reason`, `created_by`, `created_at`, `ended_at`. Active while `ended_at` is null and `until` is null or in the future. Ending a suspension sets `ended_at` (history is kept) |

**Comments:** plain text, 1-5000 characters after trimming; line breaks are normalised to `
`; NUL and other control
characters (except newline and tab) are rejected (422). The API never escapes or renders anything, the frontend shows it
as text. Only **published** posts/pages accept comments (404 otherwise). Replies go one level deep: `parent_id` must be a
visible top-level comment of the same post/page (replying to a reply is 400). Authors edit within **15 minutes** (sets
`edited_at`; moderators cannot edit others). The module clock is `service.now()`, which tests replace instead of sleeping.
- *Delete:* an author deleting a comment that has replies leaves a placeholder (`[deleted]`); without replies the row is
  removed. A moderator delete is the same with `[removed by a moderator]`; placeholders carry no author and no like count.
- *Hidden* (moderator): not listed, unless it has visible replies, then it is shown as a placeholder. Restore brings it back.
  A top-level placeholder (hidden/deleted/removed) is only listed while it has at least one visible reply.
- *Post unpublished:* its comments are not listed (the list answers 404, like for a draft) and cannot be liked, edited,
  reported or replied to; they come back when the post is published again. *Post or page deleted:* the comments, likes and
  reports are deleted by the database (ON DELETE CASCADE), so the content module needs no code for it.
- *Responses:* authors are `{id, display_name, avatar_url}`; `display_name` is `full_name` or `Member <first 8 id chars>`,
  **never the email**. Avatars and likes are batch-loaded, so a list costs a constant number of queries.

**Permissions:**
| Action | Who |
|---|---|
| list comments, read post like state | anyone (a valid token adds `liked_by_me` / `can_edit`) |
| comment, reply, edit own, like, report | any logged-in user who is not suspended (editors and moderators too) |
| delete own comment, remove own like | any logged-in user, also while suspended |
| `/moderation/*` | `require_role(UserRole.moderator)`: moderator, admin, superuser. Editor and member get 403 (editor and moderator are siblings) |
Same rule as user management (task 005): only **superusers** may moderate comments written by, or suspend, an **admin or
superuser**; moderators and admins get 403. A moderator can act on members, editors and other moderators (not on themselves
for suspensions).

**Moderation flow:** members report (`POST /comments/{id}/report`) -> the comment shows up in `GET /moderation/comments`
(open reports + hidden ones; filter `reported` / `hidden`) with its real body, author and the open reports -> a moderator
hides, restores or deletes it, or resolves the reports (deleting with replies also closes its reports). A moderator can
suspend the member (`POST /moderation/suspensions`, optional `until`): the member gets **403 "You are suspended from
commenting"** on comment, edit, like and report, while login and every other module keep working
(`GET /community/me/suspension` tells the UI). `DELETE /moderation/suspensions/{id}` ends it.

**Rate limits** (database counts like the uploads, per user, superusers exempt, HTTP 429; a per-user advisory lock stops
parallel requests from overshooting): `COMMENTS_PER_USER_PER_HOUR` (30, rows created in the last hour) and
`REPORTS_PER_USER_PER_DAY` (20, reports in the last 24 hours). Both are in `.env.example` and `compose.yml`.

**Events for notifications (task 015):** `events.emit(CommunityEvent)` is a no-op hook called after the commit for
`comment_replied` (to the parent's author), `comment_liked`, `comment_hidden` and `comment_deleted_by_moderator`; nothing
is sent to the actor themselves.

## Deployment
| | Own server | Vercel |
|---|---|---|
| App | Docker image (FastAPI serving built frontend) behind Traefik, auto HTTPS | Python function wrapping the FastAPI app; frontend as static build (see task 001) |
| Database | Postgres container | Neon (pooled connection string) |
| Files | SeaweedFS container (S3 API) | Cloudflare R2 |
| Email | SMTP provider | SMTP provider |

Known Vercel limits: function time limit and cold starts. If long AI streams hit them, fallback is
frontend on Vercel + API on own server (only an env var changes).
