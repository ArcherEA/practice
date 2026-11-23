import { AxiosError } from "axios"

export class UploadError extends Error {}

export const UPLOAD_FAILED_MESSAGE = "Upload failed, please try again."

interface ValidationDetail {
  msg?: string
}

/** Maps API / upload errors to a friendly message. Prefers the API's human-readable `detail`. */
export function getUploadErrorMessage(err: unknown): string {
  if (err instanceof UploadError) {
    return err.message
  }
  if (err instanceof AxiosError) {
    const status = err.response?.status
    const detail: string | ValidationDetail[] | undefined =
      err.response?.data?.detail
    if (typeof detail === "string" && detail.length > 0) {
      return detail
    }
    switch (status) {
      case 400:
        return "This file was rejected. Please try a different file."
      case 413:
        return "The file is too large, or your storage quota is full."
      case 422:
        if (Array.isArray(detail) && typeof detail[0]?.msg === "string") {
          return detail[0].msg
        }
        return "The file details are not valid."
      case 429:
        return "Daily upload limit reached. Please try again tomorrow."
      case 503:
        return "File storage is not configured."
      case 507:
        return "Storage is full."
    }
  }
  return UPLOAD_FAILED_MESSAGE
}
