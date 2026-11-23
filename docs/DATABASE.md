# Database guide

Everything about our PostgreSQL databases: where they live, how schema changes ship, and how to back up, restore or
rebuild them. Commands are **PowerShell**, run from the repo root unless a step says otherwise.

## 1. The big picture

| | Local development | Production |
|---|---|---|
| Where | Docker container `db` (`compose.yml`), image `postgres:18` | Neon project (branch `production`) |
| Database name | `app` (+ `app_test`, used only by backend tests) | `neondb` |
| Data stored in | Docker volume `product_app-db-data` | Neon storage |
| Connection settings | `.env` (`DATABASE_URL`, `POSTGRES_PASSWORD`) | Vercel env vars; local copy in `.env.neon` (gitignored) |
| Who changes the schema | you, with Alembic | you, with Alembic (manual step after each merge — see §3) |

Two different things live in a database:

- **Schema** (tables, columns) — defined in code (`backend/app/models.py`, `backend/app/modules/*/models.py`) and
  versioned as **Alembic migrations** in `backend/app/alembic/versions/`. It's in git, so it can always be rebuilt:
  `alembic upgrade head` turns any empty Postgres into the current schema.
- **Data** (users, items, …) — exists only inside the database. If the database is gone and there is no backup, it is gone.

`backend/app/initial_data.py` creates the first superuser (`FIRST_SUPERUSER` / `FIRST_SUPERUSER_PASSWORD`) if missing.
`backend/scripts/prestart.sh` runs both: migrations, then initial data.

## 2. Local database

Start it (and Mailpit), then migrate and create the admin:
```powershell
docker compose up -d db mailpit
```
```powershell
cd backend; uv run bash scripts/prestart.sh; cd ..
```

| Action | Data |
|---|---|
| `docker compose stop` / `down`, deleting the **container**, rebooting | **Kept** (it's in the volume). `docker compose up -d db` brings it back. |
| `docker compose down -v`, or deleting volume `product_app-db-data` | **Deleted.** Rebuild with the two commands above (empty DB + admin). |

Look inside: Adminer runs with the full Docker stack (`docker compose watch`, then http://localhost:8080), or use psql:
```powershell
docker compose exec db psql -U postgres -d app
```

Backend tests (`uv run pytest`) never touch `app`; they use `app_test`, created and migrated automatically
(see `backend/tests/db_setup.py`). Playwright tests do create `Test User` accounts in `app` (harmless clutter).

## 3. Changing the schema (migrations)

1. Change the SQLModel models.
2. Generate a migration (local DB must be running and at head):
   ```powershell
   cd backend; uv run alembic revision --autogenerate -m "add xyz to user"; cd ..
   ```
3. **Read the generated file** in `backend/app/alembic/versions/`. Autogenerate misses renames, data backfills and
   server defaults; fix by hand. Make sure `downgrade()` really undoes `upgrade()`.
4. Apply locally and prove the downgrade works:
   ```powershell
   cd backend; uv run alembic upgrade head; uv run alembic downgrade -1; uv run alembic upgrade head; cd ..
   ```
5. Run the tests (`uv run pytest` — the test DB migrates itself) and commit the migration with the model change.
6. **After merging to `main`, apply it to Neon** (§4) — Vercel deploys the new code automatically, and code that expects
   a new column fails until the column exists. Prefer **additive** changes (new nullable column / new table) so old and
   new code both work during the short gap.

Rules: never edit a migration that has already run anywhere shared (Neon); write a new one instead. One migration per change.

Useful commands (from `backend/`): `uv run alembic current` (where the DB is), `uv run alembic history` (all
migrations), `uv run alembic check` (do models and DB match?).

## 4. Production (Neon)

### Point the tools at Neon (PowerShell session)
Loads the Neon values from `.env.neon` into **this PowerShell window only**, and checks the target before anything runs:
```powershell
Get-Content .env.neon | Where-Object { $_ -match '^(SECRET_KEY|FIRST_SUPERUSER|FIRST_SUPERUSER_PASSWORD|PROJECT_NAME|DATABASE_URL_DIRECT)=' } | ForEach-Object { $k, $v = $_ -split '=', 2; Set-Item "env:$k" $v }; $env:DATABASE_URL = $env:DATABASE_URL_DIRECT; $env:PYTHONUTF8 = "1"
```
```powershell
cd backend; uv run python -c "from app.core.config import settings; h=settings.DATABASE_URL.hosts()[0]['host']; print('target host:', h); assert h.endswith('neon.tech')"
```
Only continue if it prints a `…neon.tech` host. **Close the window when done** — it holds production secrets.

### Apply migrations / create the admin
In that same window (still in `backend/`):
```powershell
uv run alembic upgrade head
```
```powershell
uv run python app/initial_data.py
```
Both are safe to re-run: Alembic skips applied migrations; initial data only creates the admin if missing.

### Connection strings
- **Pooled** (`…-pooler…`) → Vercel's `DATABASE_URL` (many short serverless connections).
- **Direct** (unpooled) → `DATABASE_URL_DIRECT` in `.env.neon`, for migrations, backups and restores.
- Lost them? `npx neon@latest login`, then
  `npx neon@latest connection-string production --project-id <id> --pooled` (and again without `--pooled`).

## 5. Backups

### Automatic daily backups (GitHub Actions)
Workflow `.github/workflows/backup-neon.yml` runs **every day at 03:17 UTC** (and on demand: Actions → "Backup Neon
database" → Run workflow). It dumps Neon with `pg_dump`, checks the dump contains the `user` and `alembic_version`
tables, **encrypts it** (gpg, AES256) and stores it as a workflow artifact for **30 days**.

- **Why encrypted:** this repo is public, and anyone signed in to GitHub can download artifacts of a public repo.
  Without the passphrase the file is useless.
- **Secrets it needs** (repo → Settings → Secrets and variables → Actions): `NEON_DATABASE_URL_DIRECT` (direct Neon
  string) and `BACKUP_PASSPHRASE`. Both values are also in `.env.neon`. **Keep `BACKUP_PASSPHRASE` in your password
  manager** — if it's lost, every backup is unreadable. If you rotate the Neon password or move projects, update the secret.
- **If a run fails** GitHub emails you. Check the run log; the first step says if secrets are missing.
- **Heads-up:** GitHub disables scheduled workflows in public repos after 60 days without commits. If that happens,
  re-enable it on the Actions page.
- Tested 2026-11-23: the first run's artifact was downloaded, decrypted and restored into a scratch DB; it matched
  Neon (users, roles, Alembic version).

Get the latest backup and decrypt it (PowerShell, repo root; `gpg` ships with Git for Windows):
```powershell
$id = gh run list -R ArcherEA/practice --workflow backup-neon.yml --status success --limit 1 --json databaseId -q '.[0].databaseId'; gh run download $id -R ArcherEA/practice -D backups
```
```powershell
$gpg = Join-Path (Split-Path (Get-Command git).Source -Parent) '..\usr\bin\gpg.exe'; $f = Get-ChildItem backups -Recurse -Filter *.dump.gpg | Sort-Object LastWriteTime | Select-Object -Last 1; & $gpg --pinentry-mode loopback --output ($f.FullName -replace '\.gpg$','') --decrypt $f.FullName
```
It asks for the passphrase (`BACKUP_PASSPHRASE`), and writes `backups\neon-backup-<run>\neon-<date>.dump` — restore it as in §6.

### Manual backups
Take one before risky changes (big migrations, deleting data). Backups go to `backups/` (gitignored — they contain user
data incl. password hashes; keep copies somewhere private, not in git).

Neon also keeps its own short **history** for point-in-time restore (window depends on your plan — check the Neon
dashboard). That protects against mistakes, **not** against deleting the Neon project.

All commands below use a throwaway `postgres:18` Docker container, so you don't need Postgres tools installed.
Use `-f` / `cp` as shown — do **not** redirect dumps with `>` in Windows PowerShell 5.1, it corrupts binary files.

**Back up Neon** (after "Point the tools at Neon", from the repo root):
```powershell
docker run --rm -v "${PWD}\backups:/backups" postgres:18 pg_dump "$env:DATABASE_URL_DIRECT" -Fc -f "/backups/neon-$(Get-Date -Format yyyyMMdd-HHmm).dump"
```

**Back up local:**
```powershell
docker compose exec db pg_dump -U postgres -d app -Fc -f /tmp/app.dump; docker compose cp db:/tmp/app.dump "backups/local-$(Get-Date -Format yyyyMMdd-HHmm).dump"
```

## 6. Restore and recovery

**Practise on a scratch database first** — it proves the backup works without touching anything:
```powershell
docker compose exec db psql -U postgres -c "CREATE DATABASE restore_check"
```
```powershell
$pw = (Select-String '^POSTGRES_PASSWORD=(.*)' .env).Matches[0].Groups[1].Value; docker run --rm -v "${PWD}\backups:/backups" postgres:18 pg_restore --no-owner --no-privileges -d "postgresql://postgres:$pw@host.docker.internal:5432/restore_check" /backups/<file>.dump
```
`<file>` is the path inside `backups\`, e.g. `neon-backup-45097572731/neon-20261123-0159.dump` for a downloaded daily backup.
Check it (`docker compose exec db psql -U postgres -d restore_check -c "select count(*) from public.user"`), then
`docker compose exec db psql -U postgres -c "DROP DATABASE restore_check"`.
(Tested 2026-11-23 in PowerShell and Git Bash: restored copy matched the source — same row counts and Alembic version.)

> **PowerShell gotcha:** write `public.user`, not `"user"`. Windows PowerShell 5.1 strips inner double quotes when calling
> `docker`, so `from "user"` becomes `from user` — which in Postgres means *the current login name* and always returns 1 row.

### Scenario: local DB lost
Usually fine to start empty (§2). To get data back, restore a local backup into a fresh `app` (stop the backend first):
`docker compose exec db psql -U postgres -c "DROP DATABASE app" -c "CREATE DATABASE app"`, then the `pg_restore`
command above with `/app` instead of `/restore_check`.

### Scenario: bad data change in Neon (project still exists)
Use Neon's **point-in-time restore** in the Neon dashboard (restore the `production` branch to a time before the
mistake, or create a branch at that time to inspect first). If the history window has passed, restore a backup as below.

### Scenario: Neon project deleted (or you move to a new one)
1. Create a new Neon project; copy the **pooled** and **direct** connection strings into `.env.neon`
   (`DATABASE_URL` and `DATABASE_URL_DIRECT`).
2. Vercel → Project → Settings → Environment Variables: set `DATABASE_URL` to the new **pooled** string.
   GitHub → repo → Settings → Secrets → Actions: update `NEON_DATABASE_URL_DIRECT` to the new **direct** string
   (otherwise the daily backup keeps failing).
3. Open a fresh PowerShell window and do **"Point the tools at Neon"** (§4) — it now targets the new project.
4. **With a backup** (latest daily one: see §5 "Get the latest backup and decrypt it"), restore it — it brings
   schema + data + Alembic version:
   ```powershell
   docker run --rm -v "${PWD}\backups:/backups" postgres:18 pg_restore --no-owner --no-privileges -d "$env:DATABASE_URL_DIRECT" /backups/<neon-file>.dump
   ```
   then `uv run alembic upgrade head` (from `backend/`) in case the backup is older than the latest migration.
   **Without a backup:** `uv run alembic upgrade head` and `uv run python app/initial_data.py` — the site works again
   but starts **empty**.
5. Vercel → Deployments → redeploy the latest deployment so it picks up the new `DATABASE_URL`. Log in to check.

## 7. Pitfalls we hit (details in `docs/TROUBLESHOOTING.md`)
- A migration "succeeded" against the wrong database because env vars weren't loaded — always print the target host first.
- Code was deployed before the Neon migration ran — logins fail until `alembic upgrade head` runs on Neon.
- Old tests wiped local users — fixed (tests now use `app_test`).
- Database dumps of a public repo's workflow are public — the daily backup is encrypted for that reason.
