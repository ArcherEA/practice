# 006 — File uploads (S3-compatible storage)

**Status:** decisions agreed 2026-11-23, ready to start · **Agents:** backend-engineer, then frontend-engineer · **Branch:** `feat/006-file-uploads`

## Decisions (agreed with the user)
| Topic | Decision |
|---|---|
| Production storage | **Cloudflare R2** (S3-compatible). Locally and on the own server: **SeaweedFS** (MinIO is no longer maintained — see D14). One S3 code path everywhere. |
| First use | **Profile avatars** (upload in Settings, shown in the sidebar). The generic `/files` API is built too, without a file-manager UI. |
| Allowed files | **Any type, max 10 MB.** Only images (JPEG, PNG, WebP, GIF) are ever shown inline; everything else — including SVG and HTML — is always served as a download (`Content-Disposition: attachment`) so a malicious file can't run in the browser. Avatars additionally must be one of those image types. |
| Visibility | **Private by default:** files are reached only through short-lived signed URLs handed out by the API to allowed users. Avatars may be public (permanent URL) when `S3_PUBLIC_BASE_URL` is configured; otherwise they're served with signed URLs too. |

## Usage limits (stay inside the R2 free tier)
Cloudflare has **no hard spending cap for R2** (only email alerts), so the app enforces limits itself. R2 free tier per
month: 10 GB Standard storage, 1M Class A ops (uploads/lists), 10M Class B ops (downloads/heads); egress and deletes free.

| Setting (env var) | Default | Enforced where |
|---|---|---|
| `STORAGE_TOTAL_LIMIT_BYTES` | 8 GB (8 × 1024³) | create-upload: refuse (HTTP 507 "Storage is full") if `sum(size of ready + pending files) + declared size` would exceed it |
| `STORAGE_USER_QUOTA_BYTES` | 100 MB | create-upload: refuse (HTTP 413 "Your storage quota is full") per owner, same sum |
| `UPLOADS_PER_USER_PER_DAY` | 50 | create-upload: refuse (HTTP 429) when the user created ≥ N file rows in the last 24 h (count rows, incl. pending/deleted-by-cleanup is fine — keep it simple and DB-based, no Redis) |
| `UPLOAD_MAX_BYTES` | 10 MB | per file (see Decisions) |

- Superusers are exempt from the per-user quota and daily limit, **not** from the total limit.
- Pending reservations count toward totals, so parallel uploads can't overshoot; pending files older than 24 h are
  removed by the cleanup command (object + row).
- Replacing an avatar deletes the previous avatar file (object + row). Deleting a user deletes their files' objects.
- Never use the Infrequent Access storage class (the free tier doesn't cover it) — don't set `StorageClass` at all.
- `GET /api/v1/files/usage` (admin or superuser): total bytes / limit, file count, top users by bytes. Plain JSON, no UI yet.
- Limits are env vars so they can be tuned without code changes; document them in `.env.example` and `docs/deploy-vercel.md`.
- Docs: add a short "Stay in the R2 free tier" section to `docs/deploy-vercel.md`: set a Cloudflare **budget alert** at
  $1 (informational only, it doesn't block), optional lifecycle rule ideas, and what each limit protects.

## Why
Content (images), Community (avatars, attachments) and Commerce (product photos) all need files. The backend must
stay stateless for Vercel, so files go to object storage, not local disk.

## Design
- **Direct-to-bucket uploads with presigned URLs:** the browser asks the API for a short-lived upload URL, uploads the
  file straight to the bucket, then confirms. Reason: Vercel functions reject request bodies over ~4.5 MB, and this keeps
  large files off our server entirely.
- Same code everywhere through the S3 API: **SeaweedFS** container locally and on the own server, **Cloudflare R2** on Vercel
  (R2: free egress, generous free tier).
- Files are private by default; downloads use short-lived presigned GET URLs. A `public` flag allows permanent public URLs (e.g. avatars).

## Scope — backend
- Settings: `S3_ENDPOINT_URL`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET`, `S3_PUBLIC_BASE_URL` (optional),
  `UPLOAD_MAX_BYTES` (default 10 MB). All in `.env.example` with local MinIO values.
- `app/core/storage.py`: thin wrapper over boto3 (presign put/get, delete, head). Unit-testable with a fake.
- `File` model + migration: id, owner_id, key, filename, content_type, size, public, status (`pending`/`ready`), created_at.
- Endpoints under `/api/v1/files`: create upload (validates declared type/size, returns a presigned upload + file id), confirm
  (checks the object exists and its real size ≤ limit and matches → `ready`; otherwise deletes it and returns 400),
  list mine, get download URL, delete (DB row + object). Prefer a presigned **POST** with a `content-length-range`
  condition so the bucket itself rejects files over 10 MB; if R2/MinIO compatibility forces presigned PUT, the confirm
  step's size check is the enforcement.
- Download URLs set `Content-Disposition: attachment` (with the original filename) for everything except the inline-safe
  image types listed above.
- Background-free: pending files older than 24h are cleaned up by a script/command, not a scheduler (document it).
- **First consumer:** user avatar — `avatar_file_id` on User, set via `/users/me`.

## Scope — infrastructure and docs
- Add SeaweedFS (+ one-shot bucket/CORS setup) to `compose.yml`/`compose.override.yml`; add to `compose.deploy.yml` for the own server.
- Document R2 setup for Vercel in `docs/deploy-vercel.md` (bucket, API token, CORS for the Vercel domain).

## Scope — frontend
- Reusable `useFileUpload()` hook + `FileUpload` component (progress, size/type errors) in `src/features/files/`.
- Settings page: upload/change avatar; avatar shown in the sidebar user menu.

## Out of scope
Image resizing/thumbnails, virus scanning, a media library UI (comes with Content).

## New dependencies
- `boto3` (Apache-2.0) — the standard, maintained S3 client for Python; works with SeaweedFS and R2 (decisions D7, D14).
- `boto3-stubs[s3]` (MIT, dev only) — keeps mypy strict.
- SeaweedFS server image `chrislusf/seaweedfs` (Apache-2.0) and `amazon/aws-cli` for bucket/CORS init (D14).

## Acceptance criteria
- Locally with Docker: upload an avatar in Settings, refresh, it's still shown; the object is visible in the SeaweedFS filer UI (http://127.0.0.1:8888).
- Files over 10 MB are rejected (before upload when declared, and at confirm by real size); non-images download instead of opening; a non-image avatar is rejected. Deleting a file removes the object.
- Each usage limit has a test (total full → 507, user quota → 413, daily count → 429, superuser exemptions, old avatar deleted on replace).
- Tests for the service (fake storage) and endpoints; Playwright avatar upload flow. CI green; `requirements.txt` regenerated (task 003).
