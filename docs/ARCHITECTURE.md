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
**Caching (task 021):** objects never change (unique keys), so every signed GET carries a signed query parameter
`response-cache-control` (no request header, so bucket CORS and `presign_upload` are untouched): `private, max-age=<DOWNLOAD_URL_EXPIRE_SECONDS>, immutable`
for private files and downloads, `public, ...` for public images. `GET /files/{id}/content` answers `Cache-Control: public, max-age=N`:
N = lifetime minus a margin (a quarter, 1 s to 10 min; default 3600 -> 3000 s) when it redirects to a signed URL, so a cached
redirect never points at an expired URL; 86400 when `S3_PUBLIC_BASE_URL` is set (unsigned, permanent URL). 404/503 send `max-age=0`.
Stale window: after a public image is deleted or made private, browsers that already hold the redirect keep showing it for up to N
(about 50 min, worst case about 2x the lifetime with the image copy itself; a day with `S3_PUBLIC_BASE_URL`, which is public anyway).
URLs inside API responses (`avatar_url`, file lists) are freshly signed per request, so only the stable `/content` URL is reused.
Limits and R2 free-tier guidance: `docs/deploy-vercel.md`. Usage report: `GET /api/v1/files/usage` (admin or superuser).

**Cleanup command** (no scheduler): pending uploads older than 24 hours (object and row) are removed with
```
cd backend && uv run python -m app.scripts.cleanup_files
```
Run it by hand or from any cron/scheduled job with the production env vars. Deleting a user also deletes their objects
(best effort; failures are logged and the orphan object can be removed by hand).
Community notifications older than 90 days are removed the same way: `uv run python -m app.scripts.cleanup_notifications`.

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
`service.py`, `routes.py`; the pure helpers `richtext.py` (body allow-list) and `slugs.py` live in `app/core/`, so other modules reuse them). Routes live under `/api/v1/content`.

**Data model** (tables always exist; one migration):
`post` (title, unique `slug`, excerpt, `body` JSONB, `cover_file_id` -> file SET NULL, `category_id` -> category SET NULL,
`status` draft|published, `published_at`, `author_id` -> user SET NULL, `seo_title`, `seo_description`, timestamps),
`page` (the same minus excerpt/cover/category/tags), `category` (name, unique slug, description; a post has one optional),
`tag` (name, unique slug), `post_tag` (post_id, tag_id, both ON DELETE CASCADE). Publishing sets `published_at` on the
first publish only; unpublishing returns to draft and keeps the date. Deleting posts/pages never deletes image files.

**Body format:** (`app/core/richtext.py`) Tiptap/ProseMirror JSON (`{"type":"doc","content":[...]}`), never HTML (D15). `richtext.sanitize_body` runs
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

**Slugs:** `app/core/slugs.py` lowercases to ASCII (accents folded), turns other characters into single hyphens, trims, max 80
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
- `GET /sitemap.xml` is a core route (`app/api/public.py`) built from every enabled module's `Module.sitemap_entries(session)`
  (content: `/blog`, published posts and pages, categories/tags that have published posts; commerce: `/shop` and published
  products); it is 404 when no enabled module provides entries. Absolute URLs from `SITE_URL`, `lastmod` = last update date.
  `GET /robots.txt` is a core route, always on (disallows `/content/`, `/admin`, `/settings`, `/api/`); the `Sitemap:` line is
  present when at least one enabled module adds sitemap entries.
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

**Events -> notifications:** `events.emit(CommunityEvent)` is called by the service after the commit for `comment_replied`
(to the parent's author), `comment_liked`, `comment_hidden`, `comment_deleted_by_moderator` and, from the follow code,
`user_followed`. `emit` opens its own session and calls `notifications.handle_event`; a failure there is logged and never
breaks the request that already succeeded.

### Usernames, profiles, follows and notifications (task 015)
Code: `app/core/usernames.py` (rules, pure), `modules/community/profiles.py`, `modules/community/notifications.py`;
tables `user_follow` and `notification` (community) plus `user.username`, `user.username_changed_at`, `user.bio` (core).

**Username rules:** stored lowercase and unique (so the unique index is case-insensitive); 3-30 characters of `[a-z0-9_]`
with at least one letter or digit; input is lowercased and trimmed. Reserved (422): admin, administrator, api, blog, content,
community, settings, login, signup, logout, p, u, moderation, notifications, root, support, help, me, null, undefined.
When none is given (signup, admin create, `crud.create_user`, `init_db`, `/private/users`) one is generated from the full
name, else `member_<first 8 hex of the user id>` — **never from the email**, because usernames are public (profiles,
comment authors). Name rules: lowercase, other characters become `_`, collapsed and trimmed, padded with `0` to 3
characters, cut to 30; clashes and reserved names get `_2`, `_3`, ... The migration backfills existing users with the same
rules (oldest first). A member changes it with `PATCH /users/me` at most once per 30 days (400 with the date it works
again; the first change is always allowed; a refused change does not use up the period); admin edits
(`PATCH /users/{id}`) are not limited. A taken name is 400 on signup/create and 409 on update. `bio`: plain text, max 500,
trimmed (empty clears it). `UserPublic` carries `username`, `bio`, `username_changed_at` (only ever returned to the user
themself and to admins).

**Public profile** (`GET /community/users/{username}`, anyone, case-insensitive): id, username, display name, avatar URL,
bio, joined date, comment / follower / following counts, `followed_by_me` (logged-in viewers), and `is_suspended`
(moderators and above only, else null). Never the email. Inactive users are 404 (also their lists and follow). The comment
count and `GET .../comments` only include visible comments on published posts/pages of active users, newest first, each
with its target (type, id, title, slug). `AuthorPublic` now has `username`, so comment authors can link to `/u/<username>`.

**Follows** (`user_follow`, PK `follower_id`+`followee_id`, both CASCADE, check: not yourself): `PUT`/`DELETE
/community/users/{username}/follow` are idempotent, any logged-in user (suspended members too); following yourself is 400.
`GET .../followers` and `.../following` list active users (newest first, paginated). `GET /community/following/activity`
lists the visible comments of the people I follow, newest first.

**Notifications** (`notification`: recipient CASCADE; actor, comment, post, page SET NULL; `read_at`):
| Type | Created when | Recipient |
|---|---|---|
| `comment_replied` | someone replies to a comment | the parent's author |
| `comment_liked` | someone likes a comment | the comment's author |
| `new_follower` | someone follows a member | the followed member |
| `comment_moderated` | a moderator hides or deletes a comment | the comment's author |
Never for your own actions. A like (or follow) by the same person while an unread notification of that kind for the same
comment (or person) exists creates no second one; unliking does not delete it; restoring a comment sends nothing.
Endpoints (own notifications only; someone else's id is 404): `GET /community/notifications` (paginated, newest first:
type, actor, `comment_snippet` of at most 140 characters, target post/page with title and slug, `created_at`, `read`),
`GET .../unread-count`, `POST .../{id}/read`, `POST .../read-all` (the last two return the new unread count). The snippet
is left out for comments that are not public (except for their own author) and the target for unpublished content.
Retention is 90 days via `cleanup_notifications` (see above); there is no push, the UI polls (D18).

**Comments and moderation UI (task 016, `frontend/src/features/community/`):** `CommentSection` is rendered under
`/blog/$slug` and `/p/$slug` only when the `community` module is enabled (nothing is rendered or requested otherwise).
It holds the post like button, newest/oldest sort, comment form (5000-character counter), one reply level, the actions
menu (Edit when `can_edit`, Delete for own comments, Report for others'), placeholders and a suspension notice. Bodies are
plain text (`whitespace-pre-wrap`, never HTML). Anonymous visitors get "Log in to comment" -> `/login?redirect=<path>`;
`features/auth/redirect.ts` accepts only same-site relative paths. `/moderation` (sidebar entry via `moduleNavItems`,
`requiredRole: moderator`) has Reported, Hidden and Suspensions tabs; route guards = module + `canModerate`
(`hasRole(user, "moderator")`, so editors are excluded). A 403 from `/api/v1/community/*` does not log the user out (it
is a rule such as "You are suspended from commenting"); it is shown as a toast. `ModerationComment` carries `target`
(type, id, title, slug) so the queue can link to the post or page.

**Profiles, follows and notifications UI (task 017):** public profile `/u/$username` (under the public layout, guarded by
the `community` module): avatar, name, @username, bio, joined month, counts, Follow/Unfollow (a login link for visitors,
nothing on your own profile) and Comments / Followers / Following tabs. Comment authors (`CommentItem`) and people lists
link to profiles with typed links. `/following` (activity of people I follow) and `/notifications` (full list, "Load more")
are app-layout routes with sidebar entries. `NotificationBell` (app header and `PublicLayout`) renders only for logged-in
users with `community` enabled: the unread count is polled every 60 s and on window focus (`refetchInterval` /
`refetchOnWindowFocus: "always"`, D18); the dropdown lists the latest 8 with "Mark all read"; each item links to its target
(post/page at `#comment-<id>`, or the follower's profile) and marks itself read. Settings (My profile) has Username (with
the once-per-30-days rule, enforced by the API) and Bio when `community` is enabled. Code: `features/community/{profile,notifications}/`,
`profileApi.ts`.
**Profile meta tags:** `GET /u/{username}` is a `public_router` of the community module (`modules/community/public_routes.py`,
`seo.py`), mounted only when `community` is enabled. Title "Name (@username)", description = bio (or "Name on <site>"),
canonical + Open Graph via the content `PageMeta`/`render_html`. Unknown or inactive users get the plain SPA index (no
profile data leaks; the SPA shows its own not-found page). Profiles are **not** in `sitemap.xml` (privacy).

## Commerce module (task 024)
Enable with `MODULES=items,commerce` (no dependency on other modules). Product decisions: D20 (what we sell, currencies,
bookings), D21 (Stripe, task 027). Code: `app/modules/commerce/` (`models.py`, `schemas.py`, `money.py`, `service.py`,
`routes.py` public, `admin_routes.py`); routes under `/api/v1/commerce` (public) and `/api/v1/commerce/admin` (admin).
Checkout, orders and emails come in tasks 027/028; this task is the catalog only.

**Data model** (tables always exist; one migration; plain VARCHAR enums; money as **integer minor units**):
| Table | Columns / notes |
|---|---|
| `product_category` | `name`, unique `slug`, `position` |
| `product` | `type` digital, physical or service (fixed after creation), unique `slug`, `title`, `description` JSONB (Tiptap, D15), `status` draft, published or archived, `category_id` -> SET NULL, `image_file_ids` JSONB (ordered ids of public images, max 10), `seo_title/description`, `created_at`, `updated_at`, `published_at` (first publish only) |
| `product_option` | `product_id` CASCADE, `name`, `position`, `values` JSONB; unique (`product_id`, `name`); at most 3 per product |
| `product_variant` | `product_id` CASCADE, unique `sku` (stored upper-case, `A-Z0-9._-`), `option_values` JSONB (`{"Size": "M"}`), `options_key` (canonical form; unique per product), `stock` (null = unlimited; check >= 0), `file_id` -> `file` **RESTRICT**, `is_active`, `position` |
| `variant_price` | (`variant_id` CASCADE, `currency`) primary key, `amount` BIGINT > 0. A variant is sold in a currency only if it has a row |
| `service_slot` | `product_id` CASCADE, `starts_at`/`ends_at` (timestamptz, UTC), `capacity` >= 1, `is_active`; unique (`product_id`, `starts_at`, `ends_at`); check end > start |

**Money** (`money.py`): amounts are integers in the currency's minor unit (cents; whole yen). Stripe's zero-decimal list
(`jpy`, `krw`, ...) and three-decimal list (`kwd`, ...) are hard-coded; `format_amount` gives `19.99 USD` / `1,500 JPY` for
emails. Max amount per price is 99,999,999 (Stripe's limit). No conversion between currencies: the admin sets a price per
currency. Settings (all validated at startup, `.env.example`, `compose.yml`): `STORE_CURRENCIES` (comma-separated lower-case
3-letter codes, default `usd`), `STORE_DEFAULT_CURRENCY` (must be in the list; empty = first), `STORE_TIMEZONE` (IANA name,
default `UTC`; slots are stored in UTC and the API returns `store_timezone` so the UI can show them), `PRODUCT_FILE_MAX_BYTES`
(default 100 MiB).

**Variants and options:** a product with no options has exactly one variant (`option_values` = `{}`); otherwise every
variant has exactly one allowed value per option and each combination exists once. While variants exist, options cannot be
added, renamed or deleted and values still in use cannot be removed (422); values can always be added.

**Publishing rules** (`POST .../publish`, 422 with all reasons): at least one active variant; every active variant has a price;
digital variants have a file; physical variants have a stock number (0 is allowed = sold out). On a *published* product the
same rules are re-checked after every variant/price change and a change that would break them is refused and rolled back
("unpublish first"). Only draft/archived products can be deleted (409 otherwise). Services need no slot to be published; with
no upcoming slot they show as unavailable.

**Admin API** (`require_role(admin)`; superuser passes, editor/moderator/member 403, anonymous 401):
categories CRUD; `GET/POST /products`, `GET/PATCH/DELETE /products/{id}`, `POST /products/{id}/publish|unpublish|archive`;
`POST /products/{id}/options`, `PATCH/DELETE /options/{id}`; `POST /products/{id}/variants` (optional inline `prices`),
`PATCH/DELETE /variants/{id}`, `PUT/DELETE /variants/{id}/prices/{currency}`; `GET/POST /products/{id}/slots`,
`PATCH/DELETE /slots/{id}`; `POST /files` and `POST /files/{id}/confirm`. Product list filters: `status`, `type`,
`category_id`, `q` (title contains), paging `skip`/`limit` -> `{data, count}`. Validation errors are **422** with a clear
message (unknown currency, option values that do not match, digital variant without file on publish, physical without stock,
slot end <= start, naive or duplicate slot); **409** for a taken slug/SKU or an existing option combination; slugs follow the
content rules (`app/core/slugs.py`, `-2`, `-3` on clashes).

**Public API** (no auth, published products only; drafts and archived are 404): `GET /commerce/config` (currencies with
exponent, default currency, timezone), `GET /commerce/categories` (only those with published products), `GET /commerce/products`
(`category` slug, `type`, `currency`, `skip`/`limit`; each item has `from_price` = cheapest sellable variant in that currency
and `available`), `GET /commerce/products/{slug}?currency=eur` (description with image `src`, options, active variants with
`price` in the requested currency, `available` = priced **and** in stock, `in_stock`, `stock` for physical products only,
upcoming active slots with `capacity` and `remaining`). `?currency=` defaults to the store default and must be in
`STORE_CURRENCIES` (422 otherwise). A variant without a price in that currency is returned with `price: null,
available: false`. `remaining` equals `capacity` until checkout exists (sold + held seats are subtracted in task 027;
`service.remaining_capacity`). Product images are the stable `/api/v1/files/{id}/content` URLs; an image file that was
deleted simply disappears from the product. The private download file is never part of any public response.

**Digital product files:** admins upload with the presigned flow of task 006 through `POST /commerce/admin/files`
(same request body, max `PRODUCT_FILE_MAX_BYTES`, always private, not counted against the per-user quota or daily upload
limit; the global `STORAGE_TOTAL_LIMIT_BYTES` still applies) and `POST /commerce/admin/files/{id}/confirm` (re-checks the real
size against the product cap). The member flow (`/files`) is unchanged and keeps `UPLOAD_MAX_BYTES`. A variant may only
reference a ready, private file owned by an admin/superuser (never a member's private file). Product files are never served by
`/files/{id}/content`; buyers will get signed, short-lived URLs from the order (task 028).
**File protection:** `variant.file_id` is a foreign key with `ON DELETE RESTRICT`, and the core files service has a small
guard registry (`file_service.register_file_guard`, filled by the commerce service; the core never imports modules).
`DELETE /files/{id}`, `DELETE /users/{id}` and `DELETE /users/me` answer **409** while a file is in use, so the admin who
uploaded a product file cannot be deleted (or delete themself) until the variant is changed or removed. Replacing the file of
a variant, deleting a variant or deleting a draft product deletes the old file (row and object) when no other variant uses it.

**Storefront (task 026):** public pages `/shop`, `/shop/category/<slug>`, `/shop/<slug>` and `/shop/cart` live in the `_public`
layout next to the blog (`src/routes/_public.shop.*.tsx`, code in `src/features/commerce/storefront/`). `_public` is shown when
`content` **or** `commerce` is on; each page checks its own module. The header gets the Shop link, the currency switcher (two or
more currencies) and the cart link only when `commerce` is on. SEO: the commerce `public_router` (`public_routes.py`, `seo.py`)
injects meta tags for `/shop`, `/shop/category/<slug>` and `/shop/<slug>` (title/description from the SEO fields, else the
plain text of the description; first image as `og:image`; `og:type=product`); unknown or unpublished slugs get 404 + noindex.
*Currency:* the choice is stored in `localStorage` (`shop.currency`); without one the browser languages are mapped to a region
currency and used if the store sells in it, else the store default. Prices always come from the API in that currency.
*Cart:* `localStorage` key `shop.cart` holds lines `{slug, variantId, slotId, quantity, price, currency}` (the last two are the
price the visitor saw, to flag changes). Names, prices and availability are never stored: the cart page fetches each product
again by slug (one request per product, `staleTime: 0`) and flags unavailable lines, too-high quantities and changed prices.
All storage access is wrapped in try/catch (blocked storage keeps the cart in memory for the page view). Checkout is disabled
until tasks 027/028.

## Deployment
| | Own server | Vercel |
|---|---|---|
| App | Docker image (FastAPI serving built frontend) behind Traefik, auto HTTPS | Python function wrapping the FastAPI app; frontend as static build (see task 001) |
| Database | Postgres container | Neon (pooled connection string) |
| Files | SeaweedFS container (S3 API) | Cloudflare R2 |
| Email | SMTP provider | SMTP provider |

Known Vercel limits: function time limit and cold starts. If long AI streams hit them, fallback is
frontend on Vercel + API on own server (only an env var changes).
