# 021 — File download caching

**Status:** in progress · **Who:** backend engineer · **Branch:** `feat/021-file-caching` · **Size:** small

## Goal
The browser should not download the same file again on every visit. Files never change (unique keys), so signed
downloads and the stable public image URL should tell the browser it may keep them.

## Scope (backend only, no migrations, no new dependencies)
1. `presign_download` adds a signed `ResponseCacheControl` query parameter: `private, max-age=<expires_in>, immutable` for
   private files and downloads, `public, max-age=<expires_in>, immutable` for public images. `presign_upload` stays
   unchanged (no new header for the browser to send, so bucket/R2 CORS keeps working).
2. `GET /api/v1/files/{id}/content` (302) becomes cacheable: `Cache-Control: public, max-age=N` with N shorter than the
   signed URL's lifetime (lifetime minus a margin); a day when `S3_PUBLIC_BASE_URL` is set. 404/503 are not cached.
   Document the stale window after a delete or a switch to private.
3. Review every place that hands out file URLs (avatars, content images, community authors, files list) and apply the
   same rules where it makes sense. No change to URL shapes or the API schema.
4. Derive everything from `DOWNLOAD_URL_EXPIRE_SECONDS`; no new settings.
5. Tests: pytest for params/headers; check against local SeaweedFS with curl.
6. Docs: `docs/ARCHITECTURE.md` (file section), `docs/DECISIONS.md` (D19).

## Out of scope
- R2 custom domain / public bucket with long-lived Cache-Control at upload time (follow-up).
- Stable (time-quantized) signed URLs inside API responses such as `avatar_url`.
- Frontend changes, `docs/ROADMAP.md`.

## Acceptance
- A presigned GET URL contains `response-cache-control` and the bucket returns that `Cache-Control` header (verified with
  curl against SeaweedFS).
- `/files/{id}/content` returns `public, max-age=N` (N < signed URL lifetime) or one day with `S3_PUBLIC_BASE_URL`;
  404/503 send `max-age=0`.
- Upload flow and CORS unchanged. Backend checks pass (ruff, format, mypy, full pytest).
