import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { type AuthorPublic, CommunityService } from "@/client"
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
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"
import { communityKeys } from "../api"
import { RadioChoice } from "../components/RadioChoice"

/** Days of suspension; 0 means indefinite. */
const DURATIONS = [
  { value: 1, label: "1 day" },
  { value: 7, label: "7 days" },
  { value: 30, label: "30 days" },
  { value: 0, label: "Indefinite" },
]

export function SuspendDialog({
  member,
  onClose,
}: {
  member: AuthorPublic | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [days, setDays] = useState(7)
  const [reason, setReason] = useState("")

  const mutation = useMutation({
    mutationFn: (user: AuthorPublic) =>
      CommunityService.createSuspension({
        body: {
          user_id: user.id,
          until:
            days > 0
              ? new Date(Date.now() + days * 24 * 3600 * 1000).toISOString()
              : null,
          reason: reason.trim() || null,
        },
      }),
    onSuccess: (_, user) => {
      showSuccessToast(`${user.display_name} is suspended from commenting`)
      setReason("")
      onClose()
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: communityKeys.moderation }),
  })

  return (
    <Dialog open={member !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (member) mutation.mutate(member)
          }}
        >
          <DialogHeader>
            <DialogTitle>Suspend member</DialogTitle>
            <DialogDescription>
              {member?.display_name} will not be able to comment, like or report
              until the suspension ends. Everything else keeps working.
            </DialogDescription>
          </DialogHeader>
          <div className="my-4 flex flex-col gap-4">
            <RadioChoice
              legend="Duration"
              name="suspension-duration"
              choices={DURATIONS}
              value={days}
              onChange={setDays}
            />
            <div className="flex flex-col gap-2">
              <Label htmlFor="suspension-reason">Reason (optional)</Label>
              <Textarea
                id="suspension-reason"
                value={reason}
                maxLength={500}
                onChange={(e) => setReason(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={mutation.isPending}
            >
              Cancel
            </Button>
            <LoadingButton
              type="submit"
              variant="destructive"
              loading={mutation.isPending}
            >
              Suspend
            </LoadingButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
