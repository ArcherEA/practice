import { useCallback, useState } from "react"

import { type FilePublic, FilesService } from "@/client"
import { getUploadErrorMessage } from "./errors"
import { putToStorage } from "./putToStorage"
import { type ValidationOptions, validateFile } from "./validate"

export interface UploadOptions extends ValidationOptions {
  public?: boolean
}

/**
 * Runs the upload flow: validate -> create upload ticket -> PUT to the bucket
 * (with progress) -> confirm. Resolves with the ready file, or null on failure
 * (the message is then in `error`).
 */
export function useFileUpload() {
  const [progress, setProgress] = useState(0)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reset = useCallback(() => {
    setProgress(0)
    setError(null)
  }, [])

  const upload = useCallback(
    async (
      file: File,
      { public: isPublic = false, accept }: UploadOptions = {},
    ): Promise<FilePublic | null> => {
      setError(null)
      setProgress(0)
      const problem = validateFile(file, { accept })
      if (problem) {
        setError(problem)
        return null
      }
      setIsUploading(true)
      try {
        const { data: ticket } = await FilesService.createUpload({
          body: {
            filename: file.name,
            content_type: file.type || "application/octet-stream",
            size: file.size,
            public: isPublic,
          },
        })
        await putToStorage(
          ticket.upload_url,
          ticket.upload_headers,
          file,
          setProgress,
        )
        const { data: confirmed } = await FilesService.confirmUpload({
          path: { file_id: ticket.file.id },
        })
        setProgress(100)
        return confirmed
      } catch (err) {
        setError(getUploadErrorMessage(err))
        return null
      } finally {
        setIsUploading(false)
      }
    },
    [],
  )

  return { upload, progress, isUploading, error, reset }
}
