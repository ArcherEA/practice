import {
  IMAGE_CONTENT_TYPES,
  MAX_UPLOAD_BYTES,
  MAX_UPLOAD_LABEL,
} from "./constants"

export interface ValidationOptions {
  /** Allowed content types. Omit to allow any type. */
  accept?: readonly string[]
}

/** Client-side pre-check. Returns an error message, or null when the file is fine. */
export function validateFile(
  file: File,
  { accept }: ValidationOptions = {},
): string | null {
  if (file.size === 0) {
    return "This file is empty."
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `This file is too large. The maximum size is ${MAX_UPLOAD_LABEL}.`
  }
  if (accept && !accept.includes(file.type)) {
    return accept === IMAGE_CONTENT_TYPES
      ? "Please choose a JPEG, PNG, WebP or GIF image."
      : "This file type is not allowed."
  }
  return null
}
