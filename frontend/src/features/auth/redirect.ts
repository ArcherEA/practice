/**
 * Validates a post-login destination from the `redirect` search param.
 * Only same-site relative paths are accepted (a single leading slash, no
 * protocol-relative `//host`, no backslashes, no control characters);
 * anything else returns undefined so the caller falls back to "/".
 */
export function safeRedirect(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined
  if (!value.startsWith("/") || value.startsWith("//")) return undefined
  for (const char of value) {
    const code = char.charCodeAt(0)
    if (char === "\\" || code < 0x20 || code === 0x7f) return undefined
  }
  return value
}
