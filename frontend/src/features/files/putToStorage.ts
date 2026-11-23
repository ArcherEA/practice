import { UPLOAD_FAILED_MESSAGE, UploadError } from "./errors"

/**
 * PUT the raw file to the presigned storage URL, reporting progress (0-100).
 *
 * This is the one deliberate call that does not use the generated API client:
 * it goes straight to the S3-compatible bucket (not our API), and the
 * generated client cannot report upload progress. XMLHttpRequest can.
 * The signature covers Content-Type and Content-Length, so we send exactly the
 * `headers` we were given (no others) and the whole file as the body.
 */
export function putToStorage(
  url: string,
  headers: Record<string, string>,
  file: File,
  onProgress: (percent: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open("PUT", url)
    for (const [name, value] of Object.entries(headers)) {
      xhr.setRequestHeader(name, value)
    }
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve()
      } else {
        // 403 = signature mismatch; any other status is a storage problem too.
        reject(new UploadError(UPLOAD_FAILED_MESSAGE))
      }
    }
    xhr.onerror = () => reject(new UploadError(UPLOAD_FAILED_MESSAGE))
    xhr.onabort = () => reject(new UploadError(UPLOAD_FAILED_MESSAGE))
    xhr.send(file)
  })
}
