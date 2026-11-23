# 007 — Backend tests use their own database

**Status:** approved · **Agent:** backend-engineer · **Branch:** `feat/007-test-database` · **Size:** small

## Why
`backend/tests/conftest.py` connects with the app's `DATABASE_URL` and, at the end of the session, deletes **all** rows in
`item` and `user`. Locally that is the dev database, so every `pytest` run wipes your local users (see `docs/TROUBLESHOOTING.md`).

## Scope
- Tests always run against a separate database: same server and credentials as `DATABASE_URL`, database name + `_test`
  (e.g. `app` → `app_test`). Override with `TEST_DATABASE_URL` if set.
- The switch happens in `conftest.py` **before** any `app.*` import (set `DATABASE_URL` in `os.environ`), so the global
  `settings` and `engine` point at the test DB everywhere.
- A session fixture creates the test database if missing (connect to the `postgres` maintenance DB, `CREATE DATABASE`)
  and runs `alembic upgrade head` on it, so the schema always matches migrations.
- **Safety guard:** the cleanup refuses to run (fails loudly) unless the connected database name ends with `_test`.
- Cleanup deletes rows from all tables in FK-safe order using `SQLModel.metadata.sorted_tables` (reversed), not a
  hard-coded list, so future module tables are cleaned too.
- CI (`test-backend.yml`, `tests-start.sh`) keeps working unchanged; the test DB is created automatically there too.
- Update `docs/TROUBLESHOOTING.md` entry → FIXED, and `development.md`/`CLAUDE.md` if they mention running tests.

## Out of scope
Per-test transaction rollback (option B).

## New dependencies
None.

## Acceptance criteria
- Create a marker user in the dev DB, run `uv run pytest`, the marker user and the admin still exist afterwards.
- `uv run pytest` passes twice in a row (DB creation is idempotent) and in CI.
- A test proves the guard: pointing cleanup at a DB not ending in `_test` raises.
