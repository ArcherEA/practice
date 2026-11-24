import { useCallback, useState } from "react"

import { CommerceService, type FilePublic } from "@/client"
import { getUploadErrorMessage } from "@/features/files/errors"
import { putToStorage } from "@/features/files/putToStorage"

/**
 * Upload flow for a private product file (admin endpoints, larger cap than member
 * uploads): create ticket -> PUT to the bucket -> confirm. There is no client-side
 * size limit here: the cap is the server's `PRODUCT_FILE_MAX_BYTES`, and its answer
 * is shown as the error text. Resolves with the ready file, or null on failure.
 */
export function useProductFileUpload() {
  const [progress, setProgress] = useState(0)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const upload = useCallback(async (file: File): Promise<FilePublic | null> => {
    setError(null)
    setProgress(0)
    if (file.size === 0) {
      setError("This file is empty.")
      return null
    }
    setIsUploading(true)
    try {
      const { data: ticket } =
        await CommerceService.adminCreateProductFileUpload({
          body: {
            filename: file.name,
            content_type: file.type || "application/octet-stream",
            size: file.size,
            public: false,
          },
        })
      await putToStorage(
        ticket.upload_url,
        ticket.upload_headers,
        file,
        setProgress,
      )
      const { data: confirmed } =
        await CommerceService.adminConfirmProductFileUpload({
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
  }, [])

  return { upload, progress, isUploading, error }
}
