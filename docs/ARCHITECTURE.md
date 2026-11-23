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
- **Storage:** `app/core/storage.py` — S3-compatible client (R2 on Vercel, MinIO on own server).

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
| Files | MinIO container | Cloudflare R2 |
| Email | SMTP provider | SMTP provider |

Known Vercel limits: function time limit and cold starts. If long AI streams hit them, fallback is
frontend on Vercel + API on own server (only an env var changes).
