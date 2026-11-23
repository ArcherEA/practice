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

## Deployment
| | Own server | Vercel |
|---|---|---|
| App | Docker image (FastAPI serving built frontend) behind Traefik, auto HTTPS | Python function wrapping the FastAPI app; frontend as static build (see task 001) |
| Database | Postgres container | Neon (pooled connection string) |
| Files | SeaweedFS container (S3 API) | Cloudflare R2 |
| Email | SMTP provider | SMTP provider |

Known Vercel limits: function time limit and cold starts. If long AI streams hit them, fallback is
frontend on Vercel + API on own server (only an env var changes).
