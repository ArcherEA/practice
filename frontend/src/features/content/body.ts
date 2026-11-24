import type { JSONContent } from "@tiptap/react"

/** Base URL of the API ("" when the frontend is served by the API itself). */
export const API_BASE: string = import.meta.env.VITE_API_URL ?? ""

export const EMPTY_BODY: JSONContent = {
  type: "doc",
  content: [{ type: "paragraph" }],
}

export const fileContentUrl = (fileId: string): string =>
  `${API_BASE}/api/v1/files/${fileId}/content`

/**
 * Responses carry image `attrs.src` as a relative path (`/api/v1/files/{id}/content`).
 * When the frontend runs on another origin (dev) it must be prefixed with the API base.
 * Returns a copy; the input is not modified.
 */
export function resolveBodyImages(node: JSONContent): JSONContent {
  const next: JSONContent = { ...node }
  if (node.type === "image" && node.attrs) {
    const src = node.attrs.src
    if (
      typeof src === "string" &&
      src.startsWith("/") &&
      !src.startsWith("//")
    ) {
      next.attrs = { ...node.attrs, src: `${API_BASE}${src}` }
    }
  }
  if (node.content) {
    next.content = node.content.map(resolveBodyImages)
  }
  return next
}

/** API bodies are typed as plain objects; this narrows one to editor JSON. */
export function toEditorContent(
  body: { [key: string]: unknown } | null | undefined,
): JSONContent {
  if (body?.type !== "doc") return EMPTY_BODY
  return resolveBodyImages(body as JSONContent)
}

/** Same idea as the backend: ASCII-fold, lowercase, hyphens. May return "" (the server then makes one). */
export function slugify(text: string): string {
  return text
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80)
    .replace(/-+$/g, "")
}
