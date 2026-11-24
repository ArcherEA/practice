import { ArrowLeft, ArrowRight, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { IMAGE_CONTENT_TYPES } from "@/features/files/constants"
import { FileUpload } from "@/features/files/FileUpload"
import { useFileUpload } from "@/features/files/useFileUpload"
import { imageUrl } from "../api"

export const MAX_IMAGES = 10

interface Props {
  value: string[]
  onChange: (ids: string[]) => void
}

/**
 * Product images: uploaded as public images through the shared upload flow (same
 * as the content cover image), stored as an ordered list of file ids. The first
 * image is the main one.
 */
export function ProductImagesField({ value, onChange }: Props) {
  const { upload, isUploading, progress, error } = useFileUpload()

  const move = (index: number, to: number) => {
    const next = [...value]
    const [item] = next.splice(index, 1)
    next.splice(to, 0, item)
    onChange(next)
  }

  return (
    <div className="flex flex-col gap-2">
      {value.length > 0 && (
        <ul className="grid grid-cols-2 gap-2" aria-label="Product images">
          {value.map((id, index) => (
            <li key={id} className="relative overflow-hidden rounded-md border">
              <img
                src={imageUrl(id)}
                alt={
                  index === 0
                    ? "Main product image"
                    : `Product image ${index + 1}`
                }
                className="aspect-square w-full object-cover"
              />
              {index === 0 && (
                <span className="absolute top-1 left-1 rounded bg-background/90 px-1.5 py-0.5 text-xs">
                  Main
                </span>
              )}
              <div className="absolute right-1 bottom-1 flex gap-1">
                <Button
                  type="button"
                  variant="secondary"
                  size="icon"
                  className="size-7"
                  aria-label={`Move image ${index + 1} earlier`}
                  disabled={index === 0}
                  onClick={() => move(index, index - 1)}
                >
                  <ArrowLeft />
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="icon"
                  className="size-7"
                  aria-label={`Move image ${index + 1} later`}
                  disabled={index === value.length - 1}
                  onClick={() => move(index, index + 1)}
                >
                  <ArrowRight />
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="icon"
                  className="size-7"
                  aria-label={`Remove image ${index + 1}`}
                  onClick={() => onChange(value.filter((x) => x !== id))}
                >
                  <X />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {value.length < MAX_IMAGES ? (
        <FileUpload
          label="Add image"
          accept={IMAGE_CONTENT_TYPES.join(",")}
          isUploading={isUploading}
          progress={progress}
          error={error}
          testId="product-image-upload"
          onSelect={async (file) => {
            const uploaded = await upload(file, {
              public: true,
              accept: IMAGE_CONTENT_TYPES,
            })
            if (uploaded && !value.includes(uploaded.id)) {
              onChange([...value, uploaded.id])
            }
          }}
        />
      ) : (
        <p className="text-sm text-muted-foreground">
          The maximum of {MAX_IMAGES} images is reached.
        </p>
      )}
    </div>
  )
}
