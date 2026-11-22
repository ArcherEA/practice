# 005 — Roles beyond admin/user

**Status:** draft (needs user approval) · **Agents:** backend-engineer, then frontend-engineer · **Branch:** `feat/005-roles`

## Why
The template only has `is_superuser` (all or nothing). Content needs editors, Community needs moderators, and so on.
We add simple role-based access now so each module can say who may do what.

## Design
- New `role` field on `User`: `member` (default) · `editor` · `moderator` · `admin`.
- `is_superuser` stays as the "owner" flag (can do everything, including managing admins). Existing superusers keep it.
- Permissions are checked with one FastAPI dependency, e.g. `require_role("editor")` — a role includes the ones below it
  (`admin` > `moderator` / `editor` > `member`; moderator and editor are siblings). Superuser always passes.
- No per-permission tables yet (YAGNI); revisit if a module needs finer control.

## Scope — backend
- Alembic migration adding `role` (enum stored as string, default `member`, not null). Backfill: superusers → `admin`.
- `require_role(...)` dependency in `app/api/deps.py` (+ `RoleDep` helpers); keep `get_current_active_superuser` working.
- Admin user endpoints can set `role`; only superusers can grant/revoke `admin`. Users cannot change their own role.
- `role` included in `UserPublic` and the JWT-authenticated `/users/me` response.

## Scope — frontend
- Admin → users table shows a Role column; Add/Edit user dialogs get a role select (admin option only for superusers).
- `useAuth` exposes `hasRole(role)`; Admin sidebar entry visible for `admin` and superusers.

## Out of scope
Organization/team roles (Phase 6). Audit log.

## New dependencies
None.

## Acceptance criteria
- Migration runs cleanly on a DB with existing users (local Docker and a copy of the schema); superusers become `admin`.
- Tests: hierarchy rules, superuser bypass, non-superuser cannot grant admin, user cannot change own role.
- Playwright: admin edits a user's role and the table updates.
