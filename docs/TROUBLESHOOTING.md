# Troubleshooting log

Problems hit while setting up and running the project, what caused them, and how they were fixed.
Add new entries at the top. Format: date · symptom · cause · fix · prevention.

---

## 2026-11-22 — Login fails locally after running backend tests (admin user gone) — FIXED (task 007)
- **Symptom:** after `uv run pytest`, logging in locally failed (400 "Incorrect email or password").
- **Cause:** the template's `backend/tests/conftest.py` deleted all `Item` and `User` rows when the test session ended,
  and the tests used the same database as local development (`localhost:5432/app`).
- **Fix (task 007):** tests now use their own database. `tests/conftest.py` sets `DATABASE_URL` to `<name>_test`
  (e.g. `app_test`; same server and credentials, or `TEST_DATABASE_URL` if set) before any `app.*` import. A session
  fixture creates the database if missing, runs `alembic upgrade head` on it, and cleans every table afterwards.
  Cleanup refuses to run unless the database name ends with `_test`. Code: `backend/tests/db_setup.py`.
- **If you still lost the admin (older checkout):** from `backend/`, `uv run python app/initial_data.py`.

## 2026-11-22 — Neon migrations silently ran against the LOCAL database
- **Symptom:** `prestart.sh` printed "Initial data created" but Neon had no tables (`relation "alembic_version" does not exist`).
  No "Running upgrade" lines appeared — a hint that the target DB was already up to date.
- **Cause:** the env vars meant to point at Neon were loaded with `. <(grep ... .env.neon)`, which silently loaded nothing
  in this shell. `DATABASE_URL` ended up empty, so settings fell back to the local `.env` (Docker Postgres).
- **Fix:** set each variable explicitly, print the target host first
  (`uv run python -c "from app.core.config import settings; print(settings.DATABASE_URL.hosts()[0]['host'])"`),
  then run `uv run alembic upgrade head` and `uv run python app/initial_data.py`.
- **Prevention:** before any migration against a remote DB, always print the target host and check it.
  Neon production values live in the gitignored `.env.neon`.
- **Also:** the Neon "set up this app" prompt (`neon init` / `neon deploy`) was not used as-is: `neon deploy` writes Neon
  vars into `.env`, which would point local dev at production. We used the CLI only for login + `neon connection-string`.

## 2026-11-22 — FIXED (task 001): uvicorn crash / 500 on `/` when `backend/app/frontend` is missing
- **Symptom:** plain `uvicorn app.main:app` crashed at import with `Frontend directory ... does not exist`;
  under `fastapi dev`, `GET /` returned 500.
- **Cause:** `app.frontend("/", directory=FRONTEND_DIR)` ran unconditionally, but the folder only exists after a frontend build.
- **Fix:** `backend/app/main.py` now mounts the frontend only if the directory exists. Without a build, the API works and `/` is a plain 404.
  Docker still builds the frontend into that folder, so it is mounted there as before. Test: `backend/tests/test_main_without_frontend.py`.
- **Prevention:** keep static-mount code tolerant of build artifacts that do not exist in dev or on Vercel.

## 2026-11-22 — CI did not run after first push to GitHub
- **Symptom:** after `git push -u origin main`, `gh run list` showed no workflow runs.
- **Cause:** the template's workflows (`test-backend.yml`, `test-docker-compose.yml`, `playwright.yml`, `zizmor.yml`)
  only trigger on `push` to branch **`master`**. Our default branch is **`main`**.
- **Fix:** changed the push trigger branch from `master` to `main` in those four workflow files.
- **Prevention:** when importing a template, grep `.github/` for `master` and repo-specific conditions.
- **Second problem found while fixing it:** CI jobs need a `.env` file (Docker Compose and `backend/app/core/config.py`
  load it), but we removed `.env` from git for security. CI would have failed with missing settings.
  **Fix:** each CI job now runs `cp .env.example .env` right after checkout (placeholder values are fine for tests).

## 2026-11-22 — Backend crashed on start: `UnicodeEncodeError: 'gbk' codec can't encode character '\u26a1'`
- **Symptom:** `uv run fastapi dev` exited with code 1 right after starting; traceback ended in
  `rich\_win32_console.py ... write_text` with a `gbk` encoding error.
- **Cause:** the FastAPI CLI prints emoji (⚡) using the `rich` library. On this Windows machine the console
  code page is Chinese **GBK**, which has no emoji, so printing crashed the process.
- **Fix:** force Python to use UTF-8 for output by setting environment variables
  `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` (done in `.claude/launch.json`).
- **Prevention / manual runs:** in PowerShell run `$env:PYTHONUTF8 = "1"` before `uv run fastapi dev`,
  or set it permanently as a user environment variable.

## 2026-11-22 — Backend crashed with `uvicorn app.main:app`: `Frontend directory ... backend\app\frontend does not exist`
- **Symptom:** while working around the error above, starting with plain `uvicorn` failed at import with
  `RuntimeError: Frontend directory 'backend\app\frontend' does not exist`.
- **Cause:** `backend/app/main.py` mounts the built React app with `app.frontend("/", directory=FRONTEND_DIR)`.
  That folder only exists after a production frontend build. `fastapi dev` tolerates the missing folder
  in development; plain `uvicorn` does not.
- **Fix:** went back to `fastapi dev` (with the UTF-8 fix). In development the frontend is served by Vite on
  port 5173, so the API on port 8000 does not need it.
- **Note:** opening `http://localhost:8000/` in dev still logs a 500 `StaticFiles directory ... does not exist`.
  This is expected — use `http://localhost:5173` for the UI and `http://localhost:8000/api/v1/docs` for the API.
  Task 001 (Vercel) will make this mount tolerant of a missing folder.

## 2026-11-22 — `bun: command not found` right after installing Bun
- **Symptom:** Bun was installed, but `bun install` failed with `command not found`.
- **Cause:** the installer adds `%USERPROFILE%\.bun\bin` to PATH, but already-open terminals keep the old PATH.
- **Fix:** called Bun by its full path (`C:\Users\<you>\.bun\bin\bun.exe`) for this session.
- **Prevention:** open a new terminal (or restart the editor) after installing tools.

## 2026-11-22 — Docker commands failed: `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`
- **Symptom:** `docker info` / `docker compose` could not connect.
- **Cause:** Docker Desktop was installed but not running.
- **Fix:** start Docker Desktop and wait until it shows "Engine running".

## 2026-11-22 — Template ships a committed `.env` with `changethis` secrets
- **Symptom (risk, not an error):** the template's `.env` is tracked in git and contains placeholder passwords.
- **Fix:** copied it to `.env.example` (safe placeholders), generated real random values in a local `.env`,
  and added `.env` to `.gitignore` so secrets are never pushed.
