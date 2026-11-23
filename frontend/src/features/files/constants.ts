/** Mirrors the backend limit `UPLOAD_MAX_BYTES` (10 MB). The server enforces it too. */
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024
export const MAX_UPLOAD_LABEL = "10 MB"

/** The only image types that may be used as an avatar (same list as the backend). */
export const IMAGE_CONTENT_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
] as const
