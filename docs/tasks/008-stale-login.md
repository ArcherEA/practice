# 008 — Log out automatically when the logged-in user no longer exists

**Status:** approved 2026-11-23 · **Who:** lead (small fix) · **Branch:** `feat/008-stale-login` · **Size:** small

## Why
A login token stays valid for 8 days. If its user is deleted (by an admin, or locally when the dev DB was reset), the
backend answered **404 "User not found"** from `get_current_user`. The frontend only logs out on 401/403, so the app
stayed half logged in: the sidebar account menu disappeared and every data page (e.g. Items) failed.

## Scope
- `backend/app/api/deps.py` `get_current_user`: a valid token whose user doesn't exist → **401
  "Could not validate credentials"** with `WWW-Authenticate: Bearer` (it's an authentication failure, not a missing
  resource). The frontend already logs out on 401 and redirects to `/login`.
- Route-level "User not found" (e.g. `GET /users/{id}` for an unknown id) stays 404 — unchanged.
- Test: token for a deleted user → 401 on `/users/me` and on a module route (`/items/`).

## Out of scope
Inactive-user handling (400) and token revocation.

## Acceptance criteria
- Backend tests pass (coverage ≥ 90%).
- In the browser: with a token for a nonexistent user, opening `/items` lands on `/login` instead of a blank page.
