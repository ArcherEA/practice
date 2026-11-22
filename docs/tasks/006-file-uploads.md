# 006 — File uploads (S3-compatible storage)

**Status:** draft (needs user approval) · **Agents:** backend-engineer, then frontend-engineer · **Branch:** `feat/006-file-uploads`

## Why
Content (images), Community (avatars, attachments) and Commerce (product photos) all need files. The backend must
stay stateless for Vercel, so files go to object storage, not local disk.

## Design
- **Direct-to-bucket uploads with presigned URLs:** the browser asks the API for a short-lived upload URL, uploads the
  file straight to the bucket, then confirms. Reason: Vercel functions reject request bodies over ~4.5 MB, and this keeps
  large files off our server entirely.
- Same code everywhere through the S3 API: **MinIO** container locally and on the own server, **Cloudflare R2** on Vercel
  (R2: free egress, generous free tier).
- Files are private by default; downloads use short-lived presigned GET URLs. A `public` flag allows permanent public URLs (e.g. avatars).

## Scope — backend
- Settings: `S3_ENDPOINT_URL`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET`, `S3_PUBLIC_BASE_URL` (optional),
  `UPLOAD_MAX_BYTES` (default 10 MB), allowed content types. All in `.env.example` with local MinIO values.
- `app/core/storage.py`: thin wrapper over boto3 (presign put/get, delete, head). Unit-testable with a fake.
- `File` model + migration: id, owner_id, key, filename, content_type, size, public, status (`pending`/`ready`), created_at.
- Endpoints under `/api/v1/files`: create upload (validates type/size, returns presigned PUT + file id), confirm
  (checks the object exists and size matches → `ready`), list mine, get download URL, delete (DB row + object).
- Background-free: pending files older than 24h are cleaned up by a script/command, not a scheduler (document it).
- **First consumer:** user avatar — `avatar_file_id` on User, set via `/users/me`.

## Scope — infrastructure and docs
- Add MinIO (+ one-shot bucket/CORS setup) to `compose.yml`/`compose.override.yml`; add to `compose.deploy.yml` for the own server.
- Document R2 setup for Vercel in `docs/deploy-vercel.md` (bucket, API token, CORS for the Vercel domain).

## Scope — frontend
- Reusable `useFileUpload()` hook + `FileUpload` component (progress, size/type errors) in `src/features/files/`.
- Settings page: upload/change avatar; avatar shown in the sidebar user menu.

## Out of scope
Image resizing/thumbnails, virus scanning, a media library UI (comes with Content).

## New dependencies
- `boto3` (Apache-2.0) — the standard, maintained S3 client for Python; works with MinIO and R2 (decision D7).
- `boto3-stubs[s3]` (MIT, dev only) — keeps mypy strict.
- MinIO server image (AGPL, used as an unmodified service — no obligation for our code).

## Acceptance criteria
- Locally with Docker: upload an avatar in Settings, refresh, it's still shown; the object is visible in the MinIO console.
- Oversized or wrong-type files are rejected before upload. Deleting a file removes the object.
- Tests for the service (fake storage) and endpoints; Playwright avatar upload flow. CI green; `requirements.txt` regenerated (task 003).
