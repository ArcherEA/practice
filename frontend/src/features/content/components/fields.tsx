import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { X } from "lucide-react"
import { useId, useState } from "react"

import type { TagPublic } from "@/client"
import { ContentService } from "@/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { IMAGE_CONTENT_TYPES } from "@/features/files/constants"
import { FileUpload } from "@/features/files/FileUpload"
import { useFileUpload } from "@/features/files/useFileUpload"
import useCustomToast from "@/hooks/useCustomToast"
import { cn } from "@/lib/utils"
import { handleError } from "@/utils"
import { contentKeys, fetchTags } from "../api"
import { fileContentUrl } from "../body"

/** "42 / 60" style counter; turns amber when above the recommended length. */
export function CharCounter({
  value,
  recommended,
}: {
  value: string
  recommended: number
}) {
  const over = value.length > recommended
  return (
    <span
      className={cn(
        "text-xs tabular-nums",
        over ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground",
      )}
      aria-live="polite"
    >
      {value.length} / {recommended}
      {over && " (longer than recommended)"}
    </span>
  )
}

interface TagPickerProps {
  value: string[]
  onChange: (ids: string[]) => void
}

/** Choose existing tags or create new ones by typing a name and pressing Enter. */
export function TagPicker({ value, onChange }: TagPickerProps) {
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()
  const [text, setText] = useState("")
  const listId = useId()
  const { data } = useQuery({ queryKey: contentKeys.tags, queryFn: fetchTags })
  const tags: TagPublic[] = data?.data ?? []

  const create = useMutation({
    mutationFn: async (name: string) =>
      (await ContentService.createManageTag({ body: { name } })).data,
    onSuccess: (tag) => {
      onChange([...value, tag.id])
      setText("")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: contentKeys.tags })
    },
  })

  const selected = value
    .map((id) => tags.find((t) => t.id === id))
    .filter((t): t is TagPublic => !!t)
  const needle = text.trim().toLowerCase()
  const suggestions = tags.filter(
    (t) =>
      !value.includes(t.id) &&
      (!needle || t.name.toLowerCase().includes(needle)),
  )

  const commit = () => {
    const name = text.trim()
    if (!name) return
    const existing = tags.find(
      (t) => t.name.toLowerCase() === name.toLowerCase(),
    )
    if (existing) {
      if (!value.includes(existing.id)) onChange([...value, existing.id])
      setText("")
      return
    }
    create.mutate(name)
  }

  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-wrap gap-1.5" aria-label="Selected tags">
        {selected.map((tag) => (
          <li
            key={tag.id}
            className="inline-flex items-center gap-1 rounded-full bg-secondary px-2.5 py-0.5 text-xs"
          >
            {tag.name}
            <button
              type="button"
              aria-label={`Remove tag ${tag.name}`}
              className="rounded-full hover:text-destructive"
              onClick={() => onChange(value.filter((id) => id !== tag.id))}
            >
              <X className="size-3" />
            </button>
          </li>
        ))}
      </ul>
      <Input
        aria-label="Add tag"
        placeholder="Type a tag and press Enter"
        value={text}
        disabled={create.isPending}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault()
            commit()
          }
        }}
      />
      {suggestions.length > 0 && (
        <ul
          id={listId}
          className="flex flex-wrap gap-1.5"
          aria-label="Existing tags"
        >
          {suggestions.slice(0, 12).map((tag) => (
            <li key={tag.id}>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-6 rounded-full px-2 text-xs"
                onClick={() => {
                  onChange([...value, tag.id])
                  setText("")
                }}
              >
                + {tag.name}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

interface CoverImageFieldProps {
  value: string | null
  onChange: (fileId: string | null) => void
}

/** Cover image: uploads a public image through useFileUpload and stores its file id. */
export function CoverImageField({ value, onChange }: CoverImageFieldProps) {
  const { upload, isUploading, progress, error } = useFileUpload()

  return (
    <div className="flex flex-col gap-2">
      {value && (
        <img
          src={fileContentUrl(value)}
          alt="Cover preview"
          className="max-h-40 w-full rounded-md border object-cover"
        />
      )}
      <div className="flex flex-wrap items-start gap-2">
        <FileUpload
          label={value ? "Replace cover image" : "Upload cover image"}
          accept={IMAGE_CONTENT_TYPES.join(",")}
          isUploading={isUploading}
          progress={progress}
          error={error}
          testId="cover-upload"
          onSelect={async (file) => {
            const uploaded = await upload(file, {
              public: true,
              accept: IMAGE_CONTENT_TYPES,
            })
            if (uploaded) onChange(uploaded.id)
          }}
        />
        {value && (
          <Button type="button" variant="ghost" onClick={() => onChange(null)}>
            Remove cover
          </Button>
        )}
      </div>
    </div>
  )
}
