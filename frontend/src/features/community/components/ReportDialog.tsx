import { useState } from "react"

import type { ReportReason } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"
import { Textarea } from "@/components/ui/textarea"
import { RadioChoice } from "./RadioChoice"

const REASONS: { value: ReportReason; label: string }[] = [
  { value: "spam", label: "Spam" },
  { value: "abuse", label: "Abuse or harassment" },
  { value: "other", label: "Something else" },
]

export function ReportDialog({
  open,
  onOpenChange,
  pending,
  onSubmit,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  pending: boolean
  onSubmit: (reason: ReportReason, note: string | null) => Promise<unknown>
}) {
  const [reason, setReason] = useState<ReportReason>("spam")
  const [note, setNote] = useState("")

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form
          onSubmit={async (e) => {
            e.preventDefault()
            try {
              await onSubmit(reason, note.trim() || null)
              setNote("")
              onOpenChange(false)
            } catch {
              // Toast shown by the mutation (for example "already reported").
              onOpenChange(false)
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>Report comment</DialogTitle>
            <DialogDescription>
              Tell the moderators what is wrong with this comment.
            </DialogDescription>
          </DialogHeader>
          <div className="my-4 flex flex-col gap-4">
            <RadioChoice
              legend="Reason"
              name="report-reason"
              choices={REASONS}
              value={reason}
              onChange={setReason}
            />
            <div className="flex flex-col gap-2">
              <Label htmlFor="report-note">Note (optional)</Label>
              <Textarea
                id="report-note"
                value={note}
                maxLength={500}
                onChange={(e) => setNote(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={pending}
            >
              Cancel
            </Button>
            <LoadingButton type="submit" loading={pending}>
              Send report
            </LoadingButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
