import { AxiosError } from "axios"

export interface ParsedApiError {
  /** Messages for fields named in a 422 response, keyed by the API field name (`seo_title`). */
  fields: Record<string, string>
  /** Everything that is not tied to one field (string `detail`, 409, network errors, ...). */
  message: string | null
}

interface ValidationItem {
  loc?: (string | number)[]
  msg?: string
}

const cleanMessage = (msg: string): string =>
  msg.replace(/^Value error,\s*/, "").replace(/^Assertion failed,\s*/, "")

/**
 * Splits an API error into per-field messages and one general message.
 * FastAPI 422s carry `detail: [{loc: ["body", "title"], msg}]`; our own checks
 * carry a plain string `detail`.
 */
export function parseApiError(err: unknown): ParsedApiError {
  const result: ParsedApiError = { fields: {}, message: null }
  if (!(err instanceof AxiosError)) {
    result.message = "Something went wrong. Please try again."
    return result
  }
  const detail: unknown = err.response?.data?.detail
  if (typeof detail === "string" && detail) {
    result.message = detail
  } else if (Array.isArray(detail)) {
    const general: string[] = []
    for (const item of detail as ValidationItem[]) {
      const msg = cleanMessage(item.msg ?? "Invalid value")
      const loc = (item.loc ?? []).filter((p) => p !== "body")
      const field = typeof loc[0] === "string" ? loc[0] : undefined
      if (field && loc[0] !== "query" && loc[0] !== "path") {
        result.fields[field] ??= msg
      } else {
        general.push(msg)
      }
    }
    if (general.length > 0) result.message = general.join(" ")
  } else if (err.response?.status === 403) {
    result.message = "You do not have permission to do this."
  } else if (err.response?.status === 404) {
    result.message = "This item no longer exists. Reload the page."
  } else {
    result.message = err.message
  }
  return result
}

/** One line for toasts and inline alerts. */
export function errorText(err: unknown): string {
  const { fields, message } = parseApiError(err)
  const parts = [...Object.entries(fields).map(([k, v]) => `${k}: ${v}`)]
  if (message) parts.unshift(message)
  return parts.join(" ") || "Something went wrong."
}
