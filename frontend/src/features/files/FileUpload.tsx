import { Upload } from "lucide-react"
import { useId, useRef } from "react"

import { Button } from "@/components/ui/button"

interface FileUploadProps {
  onSelect: (file: File) => void
  label?: string
  /** Value for the input's `accept` attribute (a hint only; we validate again). */
  accept?: string
  isUploading?: boolean
  progress?: number
  error?: string | null
  testId?: string
}

/** Button with a hidden file input, a progress bar and error text. */
export function FileUpload({
  onSelect,
  label = "Upload file",
  accept,
  isUploading = false,
  progress = 0,
  error,
  testId = "file-upload",
}: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const errorId = useId()

  return (
    <div className="flex flex-col gap-2">
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="sr-only"
        tabIndex={-1}
        aria-label={label}
        aria-describedby={error ? errorId : undefined}
        data-testid={`${testId}-input`}
        onChange={(e) => {
          const file = e.target.files?.[0]
          // Reset so choosing the same file again still fires onChange.
          e.target.value = ""
          if (file) onSelect(file)
        }}
      />
      <Button
        type="button"
        variant="outline"
        disabled={isUploading}
        onClick={() => inputRef.current?.click()}
        className="w-fit"
      >
        <Upload />
        {isUploading ? "Uploading..." : label}
      </Button>
      {isUploading && (
        <div
          role="progressbar"
          aria-label="Upload progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress}
          className="h-2 w-full max-w-xs overflow-hidden rounded-full bg-muted"
        >
          <div
            className="h-full bg-primary transition-[width]"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
      {error && (
        <p id={errorId} role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
