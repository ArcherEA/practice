# Deploying to Vercel (frontend + API on one domain, DB on Neon)

Task 001. Same commit also deploys with Docker Compose (see `deployment.md`); nothing here changes that path.

## What was chosen and why

Checked against Vercel's current docs (page dates Aug-Nov 2026):

- FastAPI on Vercel: <https://vercel.com/docs/frameworks/backend/fastapi>
- Python runtime: <https://vercel.com/docs/functions/runtimes/python>
- Function duration: <https://vercel.com/docs/functions/configuring-functions/duration>

Findings used:

| Topic | Vercel says |
|---|---|
| Python versions | 3.12 (default), 3.13, 3.14. We have `.python-version` = 3.14, so 3.14 is used. |
| Entrypoint | Vercel looks for a `FastAPI` instance named `app` in `app.py`, `index.py`, `server.py`, `main.py`, ... at the repo root, or in `src/` / `app/`; otherwise `tool.vercel.entrypoint` in `pyproject.toml`. |
| Static files | `app.frontend("/", directory=...)` is promoted to the CDN at build time. API routes always win over frontend files. The default `fallback="auto"` serves `index.html` (HTTP 200) for browser navigation to unknown paths, so SPA deep links work. |
| Dependencies | `pyproject.toml` (with or without `uv.lock`) or `requirements.txt`. |
| Build command | `buildCommand` in `vercel.json` (takes precedence over `[tool.vercel.scripts]`). |
| Duration | Fluid compute is on by default. Default 300 s; max 300 s on Hobby, 800 s on Pro (30 min beta). Configure with `functions.<entrypoint>.maxDuration` in `vercel.json`. |

So the simplest setup is the **native FastAPI preset**, not hand-written `routes`/`rewrites`:

- `index.py` (repo root): adds `backend/` to `sys.path` and re-exports `app` from `backend/app/main.py`. Needed because our app lives in `backend/`, not at the root.
- `backend/app/main.py`: `app.frontend("/", ...)` is now mounted only if `backend/app/frontend/` exists. Vercel's build runs the Vite build first (so the folder exists and its files are promoted to the CDN); plain `uvicorn`/tests/dev without a build no longer crash.
- `vercel.json`: `buildCommand` installs Bun and builds the frontend (output goes to `backend/app/frontend` per `frontend/vite.config.ts`); `maxDuration` 60 s for the function.
- `requirements.txt` (repo root): generated from `uv.lock` (`uv export`). Our root `pyproject.toml` is only a uv workspace with no `[project]` dependencies (they live in `backend/pyproject.toml`), so Vercel needs this file to know what to install. **Regenerate when backend dependencies change** (any OS, from any directory; it wraps `uv export --package app --no-hashes --frozen --no-emit-workspace --no-dev -o requirements.txt`):
  ```bash
  scripts/export-requirements.sh
  ```
  The `Check requirements.txt` workflow (`.github/workflows/check-requirements.yml`) regenerates the file in CI and fails with `requirements.txt is out of date` if it differs from the committed one.

  **Dependabot:** the monthly `uv` group in `.github/dependabot.yml` only updates `uv.lock`, so its PRs fail this check until fixed. We kept it (a red check is a clear signal; silently skipping would hide stale deploys). Fix: check out the PR branch, run `scripts/export-requirements.sh`, commit `requirements.txt`, push.
- `.vercelignore`: keeps `node_modules`, `.venv`, `.env` out of the upload.

`VITE_API_URL` must be **unset/empty** on Vercel: the frontend then calls `/api/v1/...` on the same domain.
No `FASTAPI_ENV` on Vercel: the settings only accept the value `development` (or unset), and unset means production behaviour.
`.env` is not needed: pydantic-settings ignores a missing env file and reads project env vars.

## Step by step (you do these)

### 1. Neon (database)
1. Sign in at <https://console.neon.tech>, **Create project** (pick a region near your Vercel function region, default `iad1`/US East; Postgres 17 or newer is fine).
2. On the project dashboard click **Connect**, tick **Connection pooling** (the host contains `-pooler`), copy the string. It looks like
   `postgresql://USER:PASSWORD@ep-xxx-pooler.REGION.aws.neon.tech/neondb?sslmode=require`. This is the **pooled** `DATABASE_URL`. (`postgresql://` is rewritten to the psycopg driver automatically by `config.py`.)
3. Also copy the **unpooled** string (untick pooling) if you want to run migrations through it; the pooled one normally also works for Alembic, but the unpooled one is the safe choice for DDL.

### 2. Vercel (project)
1. <https://vercel.com/new> > **Import Git Repository** > choose `ArcherEA/practice` (grant the GitHub app access if asked).
2. Root Directory: leave as repo root. Framework Preset: should auto-detect **FastAPI**; leave Build/Install/Output settings as default (the Build Command comes from `vercel.json`). Do not set an Output Directory.
3. Add environment variables (Project Settings > Environment Variables, for Production and Preview) before the first deploy:

| Variable | Value |
|---|---|
| `PROJECT_NAME` | Display name, e.g. `PRODUCT` |
| `SECRET_KEY` | Random string: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Not `changethis`. |
| `DATABASE_URL` | Neon **pooled** string from step 1 |
| `FIRST_SUPERUSER` | Admin email |
| `FIRST_SUPERUSER_PASSWORD` | Strong password. Not `changethis`. |
| `FRONTEND_HOST` | Your production URL, e.g. `https://<project>.vercel.app` (only used for CORS; same-origin works anyway) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TLS`, `EMAILS_FROM_EMAIL`, `EMAILS_FROM_NAME` | Your SMTP provider. Optional: without `SMTP_HOST` + `EMAILS_FROM_EMAIL` email features (password reset) are disabled. |
| `SENTRY_DSN` | Optional |
| `MODULES` | Optional. Comma-separated optional modules, e.g. `items,content`. **Add `content` to enable the blog/pages module** (its tables are migrated either way; apply the migration to Neon first, see `docs/DATABASE.md`). **Add `community` to enable comments, likes and moderation (it needs `content` too, e.g. `items,content,community`; the app refuses to start otherwise).** Apply its migration to Neon before the deploy. Unset = `items` (the demo module). `none` = Core only (an empty value is ignored). Unknown names fail at startup. |
| `SITE_URL` | Public base URL, no trailing slash, e.g. `https://<project>.vercel.app` or your custom domain. Used for canonical links, Open Graph URLs, `sitemap.xml` and `robots.txt` (content module). Preview deployments can use the same production value (their canonical then points to production, which is what you want). |
| `VITE_API_URL` | **Do not set** (empty = same domain) |
| `FASTAPI_ENV` | **Do not set** (only `development` is valid; unset = production) |

   Vercel build output uses these too, so they must exist before the first build (the app is imported at build time).
4. Click **Deploy**.

### 3. Migrations and first superuser (from your machine, not in the function)
Run once after the first deploy and after every new Alembic migration (full procedure, backups and recovery: `docs/DATABASE.md`). Use the Neon string (pooled works; unpooled preferred):

PowerShell, from the repo root:
```powershell
$env:DATABASE_URL = "postgresql://USER:PASSWORD@ep-xxx.REGION.aws.neon.tech/neondb?sslmode=require"
$env:SECRET_KEY = "<same as Vercel>"; $env:PROJECT_NAME = "PRODUCT"
$env:FIRST_SUPERUSER = "<same as Vercel>"; $env:FIRST_SUPERUSER_PASSWORD = "<same as Vercel>"
cd backend
uv run bash scripts/prestart.sh
```
Git Bash equivalent: `export` the same variables, then `cd backend && uv run bash scripts/prestart.sh`. The script runs `alembic upgrade head` then `python app/initial_data.py` (creates the first superuser if missing). Real environment variables take priority over the local `.env`, so your local dev `.env` is not used for these variables.
Do this before expecting login to work. A GitHub Action doing the same on each push is a possible follow-up.

### 4. Check
- `https://<project>.vercel.app/` shows the login page, a deep link such as `/login` also loads (SPA fallback).
- `https://<project>.vercel.app/api/v1/utils/health-check/` returns `true`.
- Log in with `FIRST_SUPERUSER` / `FIRST_SUPERUSER_PASSWORD`.

## File storage on Cloudflare R2 (task 006)

Uploaded files (avatars first) live in an S3-compatible bucket. On Vercel that is **Cloudflare R2**; the backend only uses
the S3 API through boto3, so the code is identical to the local/own-server storage container. The browser uploads
**directly** to the bucket with a presigned **PUT** URL (Vercel rejects request bodies over ~4.5 MB, and R2 does not
support presigned POST form uploads: <https://developers.cloudflare.com/r2/api/s3/presigned-urls/>), so the bucket needs CORS.

### 1. Create the bucket
Cloudflare dashboard > **R2 Object Storage** > **Create bucket** (name e.g. `product-files`, location automatic, default
storage class **Standard** — never Infrequent Access, the free tier does not cover it). Keep it private (do not enable the
public `r2.dev` URL unless you want public avatars, see `S3_PUBLIC_BASE_URL` below).

### 2. API token (scoped to this bucket)
R2 overview > **Manage API tokens** > **Create API token** > permission **Object Read & Write**, **Specify bucket** =
your bucket only. Copy the **Access Key ID** and **Secret Access Key** (shown once). The S3 endpoint is on the same page:
`https://<account_id>.r2.cloudflarestorage.com`.

### 3. CORS for the browser
Bucket > **Settings** > **CORS Policy** > **Add**, paste (replace the origin with your production URL; add a preview
domain as a second entry if you test uploads on previews):
```json
[
  {
    "AllowedOrigins": ["https://<project>.vercel.app"],
    "AllowedMethods": ["GET", "PUT", "HEAD"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

### 4. Environment variables (Vercel, Production and Preview)
| Variable | Value |
|---|---|
| `S3_ENDPOINT_URL` | `https://<account_id>.r2.cloudflarestorage.com` |
| `S3_REGION` | `auto` |
| `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` | from step 2 |
| `S3_BUCKET` | the bucket name |
| `S3_PUBLIC_ENDPOINT_URL` | leave **unset**: on Vercel the browser and the backend use the same R2 endpoint |
| `S3_PUBLIC_BASE_URL` | optional: the bucket's public domain (R2 custom domain or `https://pub-xxx.r2.dev`). Only public files (avatars) use it; without it avatars are served with signed URLs (1 hour) |
| `UPLOAD_MAX_BYTES`, `STORAGE_TOTAL_LIMIT_BYTES`, `STORAGE_USER_QUOTA_BYTES`, `UPLOADS_PER_USER_PER_DAY` | optional, see the limits below |

Not deployed yet? Uploads fail with HTTP 503 "File storage is not configured" until these are set; everything else works.

### Stay in the R2 free tier
Cloudflare has **no hard spending cap** for R2 (only email alerts), so the app limits usage itself.

1. **Budget alert (informational only, it does not block anything):** Cloudflare dashboard > **Manage account** >
   **Billing** > **Budget alerts** (or **Notifications** > **Billing**) > create an alert at **$1**. You get an email when
   estimated charges pass it; then check usage and lower the limits below.
2. **Free tier per month:** 10 GB Standard storage, 1M Class A operations (uploads, lists), 10M Class B operations
   (downloads, HEAD); egress and deletes are free. Our app does one Class A (PUT) and one Class B (HEAD) per upload.
3. **App limits** (env vars, change without code changes; pending uploads count toward the sums):

| Variable | Default | What it protects | Error |
|---|---|---|---|
| `STORAGE_TOTAL_LIMIT_BYTES` | 8 GiB (8589934592) | total bytes in the bucket stays under the 10 GB free tier. Applies to superusers too | 507 "Storage is full" |
| `STORAGE_USER_QUOTA_BYTES` | 100 MiB (104857600) | one account cannot fill the bucket. Superusers are exempt | 413 "Your storage quota is full" |
| `UPLOADS_PER_USER_PER_DAY` | 50 | caps Class A operations per account (rows created in the last 24 h). Superusers are exempt | 429 |
| `UPLOAD_MAX_BYTES` | 10 MiB (10485760) | size of one file; checked when declared, enforced by the bucket (signed `Content-Length`) and re-checked at confirm | 413 / 400 |
| `COMMENTS_PER_USER_PER_HOUR` | 30 | comments and replies a member can post per hour (community module). Superusers are exempt | 429 |
| `REPORTS_PER_USER_PER_DAY` | 20 | reports a member can file per 24 hours (community module). Superusers are exempt | 429 |

   Check usage any time as an admin: `GET /api/v1/files/usage` (total bytes vs limit, file count, top users).
4. **Housekeeping:** abandoned (never confirmed) uploads are removed by `uv run python -m app.scripts.cleanup_files`
   (run it from `backend/` with the production env vars, e.g. weekly by hand or from any cron; see `docs/ARCHITECTURE.md`).
   Optional R2 lifecycle rules (bucket > Settings > **Object lifecycle rules**): keep the default "abort incomplete
   multipart uploads after 7 days", and, if you add a prefix for temporary files later, a "delete objects after N days" rule
   on that prefix. Never add a rule that transitions objects to **Infrequent Access**.

## Public content pages and SEO on Vercel (task 011)

Checked against Vercel's docs (page dated 2026-11-14): <https://vercel.com/docs/frameworks/backend/fastapi> and
<https://vercel.com/docs/functions/runtimes/python>.

- **Routing precedence.** The docs say `app.frontend()` registers a low-priority frontend build and "every API route takes
  priority over frontend files regardless of declaration order". The CDN `index.html` fallback only applies to requests that
  match no route and no file. So `GET /blog/{slug}` (a FastAPI route) is expected to reach the function, not the static
  fallback. Static files such as `/assets/*` stay on the CDN. `/sitemap.xml` and `/robots.txt` have an extension, so the
  fallback never applies to them. We still declare the SEO routes before the mount in `create_app` (needed for Docker/local,
  where Starlette matches in order). **Not verifiable offline**: the docs do not spell out dynamic path routes, so check the
  preview (below). Contingency if the CDN wins: set `fallback=None` in `application.frontend(...)` (every miss then reaches
  the function, which serves the SPA itself) or add `rewrites` for `/blog/:path*` and `/p/:path*` to `index.py` in `vercel.json`.
- **Reading `index.html` at runtime.** "Promoted source directories are kept in the function bundle by default so the app can
  read from them at runtime" (`[tool.vercel.fastapi.static] exclude = false` is the default, and we do not set `exclude`).
  Python functions also include all project files reachable at build time. So `backend/app/frontend/index.html`, created by
  our `buildCommand`, is in the bundle and `app.state.frontend_dir` (resolved from `main.py`'s location) finds it.
  **Do not set `exclude = true`**, or the SEO routes lose their template.
- **HTML template source (chosen: the file, plus a safe fallback).** Read `backend/app/frontend/index.html` if present;
  otherwise return a minimal valid HTML page with the same tags and a link to `FRONTEND_HOST` (a warning is logged). We did
  not add an embedded copy or `includeFiles`: the bundle keeps the file by default, and a build-time copy would be a second
  source of truth. If the preview shows the minimal page, add `"includeFiles": "backend/app/frontend/**"` under
  `functions."index.py"` in `vercel.json`.
- **What to check on a preview** (replace `$URL`, `$SLUG` is a published post, `$DRAFT` a draft; `SITE_URL` must be set):
  ```bash
  curl -s -H "Accept: text/html" "$URL/blog/$SLUG" | grep -E "<title>|og:|canonical|twitter:|app\.js|assets/"
  curl -s -o /dev/null -w "%{http_code}
" -H "Accept: text/html" "$URL/blog/$DRAFT"   # 404
  curl -s -H "Accept: text/html" "$URL/blog/$DRAFT" | grep -E "noindex|assets/"
  curl -s "$URL/sitemap.xml" | head -20        # absolute SITE_URL links, published only
  curl -s "$URL/robots.txt"                    # Disallow lines + Sitemap: $SITE_URL/sitemap.xml
  curl -s -o /dev/null -w "%{http_code}
" -H "Accept: text/html" "$URL/login"   # 200, plain SPA shell
  ```
  If `/blog/$SLUG` shows the plain shell (title not the post's) the CDN fallback won: apply the contingency above.

## Known limits
- **Function timeout:** `vercel.json` sets `maxDuration` 60 s. Vercel allows up to 300 s on Hobby and 800 s on Pro by default. Long AI streams (Phase 3) must stay below that, or move to the fallback in `ARCHITECTURE.md` (frontend on Vercel, API on own server; only an env var changes). Streaming responses are supported, but the connection is cut at the limit.
- **Cold starts:** first request after idle can take a couple of seconds (Python + FastAPI + argon2 imports + a new DB connection). Fluid compute reuses warm instances, which reduces this. Use Neon's pooled host so many instances do not exhaust Postgres connections; Neon itself may also wake a suspended compute (~1 s) on free tier.
- **Stateless:** no local disk writes (files go to S3/R2, see "File storage on Cloudflare R2"); each instance has its own memory.
- **Bundle size:** 500 MB uncompressed for the function.
- **Static files:** served by the CDN, so FastAPI middleware/`Depends` do not apply to them. The built `backend/app/frontend` also stays in the function bundle (harmless); set `[tool.vercel.fastapi.static] exclude = true` in a `pyproject.toml` if size ever matters.

## Not verified offline
`vercel build` needs a linked Vercel project (`vercel pull`, i.e. login), so the full Vercel build and a preview deploy could not be run. Locally verified: app import and `/api/v1/utils/health-check/` through the root `index.py` with only environment variables, no `.env` file and no frontend folder; the frontend build command; backend tests. Unverified until the first deploy: that Vercel's build container allows `npm install -g bun`, that dependency install picks up `requirements.txt`, and CDN promotion of the SPA with `index.html` fallback.
