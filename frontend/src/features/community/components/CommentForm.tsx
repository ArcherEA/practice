import { useState } from "react"

import { Button } from "@/components/ui/button"
import { LoadingButton } from "@/components/ui/loading-button"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import { COMMENT_MAX_LENGTH } from "../api"

/**
 * Textarea with a character counter. Used for new comments, replies and for
 * editing (`initialValue` + `submitLabel`). `onSubmit` resolves when saved;
 * on failure the text stays so nothing is lost.
 */
export function CommentForm({
  label,
  submitLabel,
  initialValue = "",
  pending,
  autoFocus,
  onSubmit,
  onCancel,
}: {
  label: string
  submitLabel: string
  initialValue?: string
  pending: boolean
  autoFocus?: boolean
  onSubmit: (body: string) => Promise<unknown>
  onCancel?: () => void
}) {
  const [value, setValue] = useState(initialValue)
  const length = value.length
  const empty = value.trim().length === 0

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={async (e) => {
        e.preventDefault()
        if (empty || length > COMMENT_MAX_LENGTH || pending) return
        try {
          await onSubmit(value.trim())
          if (!initialValue) setValue("")
        } catch {
          // The error toast is shown by the mutation; keep the text.
        }
      }}
    >
      <Textarea
        aria-label={label}
        value={value}
        maxLength={COMMENT_MAX_LENGTH}
        autoFocus={autoFocus}
        placeholder={label}
        rows={3}
        onChange={(e) => setValue(e.target.value)}
      />
      <div className="flex items-center justify-between gap-2">
        <span
          className={cn(
            "text-xs tabular-nums text-muted-foreground",
            length >= COMMENT_MAX_LENGTH && "text-destructive",
          )}
          data-testid="char-counter"
        >
          {length} / {COMMENT_MAX_LENGTH}
        </span>
        <div className="flex gap-2">
          {onCancel && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onCancel}
              disabled={pending}
            >
              Cancel
            </Button>
          )}
          <LoadingButton
            type="submit"
            size="sm"
            loading={pending}
            disabled={empty}
          >
            {submitLabel}
          </LoadingButton>
        </div>
      </div>
    </form>
  )
}
