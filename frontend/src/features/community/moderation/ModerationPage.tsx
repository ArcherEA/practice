import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { useState } from "react"

import {
  type AuthorPublic,
  CommunityService,
  type ModerationComment,
  type QueueFilter,
} from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { LoadingButton } from "@/components/ui/loading-button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"
import { communityKeys, queueOptions, suspensionsOptions } from "../api"
import { formatDateTime, relativeTime } from "../time"
import { SuspendDialog } from "./SuspendDialog"

export default function ModerationPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Moderation</h1>
        <p className="text-muted-foreground">
          Review reported and hidden comments and manage suspensions.
        </p>
      </div>
      <Tabs defaultValue="reported">
        <TabsList>
          <TabsTrigger value="reported">Reported</TabsTrigger>
          <TabsTrigger value="hidden">Hidden</TabsTrigger>
          <TabsTrigger value="suspensions">Suspensions</TabsTrigger>
        </TabsList>
        <TabsContent value="reported">
          <Queue filter="reported" />
        </TabsContent>
        <TabsContent value="hidden">
          <Queue filter="hidden" />
        </TabsContent>
        <TabsContent value="suspensions">
          <Suspensions />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function Queue({ filter }: { filter: QueueFilter }) {
  const { data, isLoading, isError } = useQuery(queueOptions(filter))
  const [suspending, setSuspending] = useState<AuthorPublic | null>(null)

  if (isLoading) return <p className="text-muted-foreground">Loading...</p>
  if (isError || !data) {
    return (
      <p className="text-muted-foreground">The queue could not be loaded.</p>
    )
  }
  if (data.data.length === 0) {
    return (
      <p className="py-8 text-center text-muted-foreground">
        {filter === "reported"
          ? "No reported comments. All clear."
          : "No hidden comments."}
      </p>
    )
  }
  return (
    <>
      <ul className="flex flex-col gap-4" data-testid={`queue-${filter}`}>
        {data.data.map((comment) => (
          <QueueItem
            key={comment.id}
            comment={comment}
            onSuspend={setSuspending}
          />
        ))}
      </ul>
      <SuspendDialog member={suspending} onClose={() => setSuspending(null)} />
    </>
  )
}

/**
 * A moderation action. The backend answers 403 with a readable message when a
 * moderator acts on an admin's content; it is shown as is in the error toast.
 */
function useModerationMutation(
  action: () => Promise<unknown>,
  message: string,
  after?: () => void,
) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  return useMutation({
    mutationFn: action,
    onSuccess: () => {
      showSuccessToast(message)
      after?.()
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: communityKeys.moderation }),
  })
}

function QueueItem({
  comment,
  onSuspend,
}: {
  comment: ModerationComment
  onSuspend: (member: AuthorPublic) => void
}) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const id = comment.id
  const path = { comment_id: id }

  const hide = useModerationMutation(
    () => CommunityService.hideComment({ path }),
    "Comment hidden",
  )
  const restore = useModerationMutation(
    () => CommunityService.restoreComment({ path }),
    "Comment restored",
  )
  const resolve = useModerationMutation(
    () => CommunityService.resolveCommentReports({ path }),
    "Reports resolved",
  )
  const remove = useModerationMutation(
    () => CommunityService.moderatorDeleteComment({ path }),
    "Comment deleted",
    () => setConfirmDelete(false),
  )

  const target = comment.target
  const author = comment.author

  return (
    <li
      className="flex flex-col gap-3 rounded-lg border p-4"
      data-testid="queue-item"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <span className="font-medium">
          {author?.display_name ?? "Deleted user"}
        </span>
        {author && (
          <span className="text-muted-foreground">@{author.username}</span>
        )}
        <time
          dateTime={comment.created_at}
          title={formatDateTime(comment.created_at)}
          className="text-muted-foreground"
        >
          {relativeTime(comment.created_at)}
        </time>
        {comment.state === "hidden" && (
          <Badge variant="secondary">Hidden</Badge>
        )}
        {comment.open_report_count > 0 && (
          <Badge variant="destructive">
            {comment.open_report_count}{" "}
            {comment.open_report_count === 1 ? "report" : "reports"}
          </Badge>
        )}
        {target && (
          <span className="text-muted-foreground">
            on{" "}
            <Link
              to={target.type === "post" ? "/blog/$slug" : "/p/$slug"}
              params={{ slug: target.slug }}
              className="underline underline-offset-4"
            >
              {target.title}
            </Link>
          </span>
        )}
      </div>

      <p className="whitespace-pre-wrap break-words text-sm">{comment.body}</p>

      {comment.reports.length > 0 && (
        <ul className="flex flex-col gap-1 rounded-md bg-muted p-3 text-sm">
          {comment.reports.map((report) => (
            <li key={report.id}>
              <span className="font-medium capitalize">{report.reason}</span>
              {report.reporter && (
                <span className="text-muted-foreground">
                  {" "}
                  by {report.reporter.display_name}
                </span>
              )}
              {report.note && <span>: {report.note}</span>}
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap gap-2">
        {comment.state === "hidden" ? (
          <LoadingButton
            size="sm"
            variant="outline"
            loading={restore.isPending}
            onClick={() => restore.mutate()}
          >
            Restore
          </LoadingButton>
        ) : (
          <LoadingButton
            size="sm"
            variant="outline"
            loading={hide.isPending}
            onClick={() => hide.mutate()}
          >
            Hide
          </LoadingButton>
        )}
        {comment.open_report_count > 0 && (
          <LoadingButton
            size="sm"
            variant="outline"
            loading={resolve.isPending}
            onClick={() => resolve.mutate()}
          >
            Resolve reports
          </LoadingButton>
        )}
        <Button
          size="sm"
          variant="destructive"
          onClick={() => setConfirmDelete(true)}
        >
          Delete
        </Button>
        {author && (
          <Button size="sm" variant="outline" onClick={() => onSuspend(author)}>
            Suspend member
          </Button>
        )}
      </div>

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete comment</DialogTitle>
            <DialogDescription>
              The comment is removed for everyone and its author is notified.
              This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>
              Cancel
            </Button>
            <LoadingButton
              variant="destructive"
              loading={remove.isPending}
              onClick={() => remove.mutate()}
            >
              Delete comment
            </LoadingButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </li>
  )
}

function Suspensions() {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const { data, isLoading, isError } = useQuery(suspensionsOptions)

  const end = useMutation({
    mutationFn: (id: string) =>
      CommunityService.endSuspension({ path: { suspension_id: id } }),
    onSuccess: () => showSuccessToast("Suspension ended"),
    onError: handleError.bind(showErrorToast),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: communityKeys.moderation }),
  })

  if (isLoading) return <p className="text-muted-foreground">Loading...</p>
  if (isError || !data) {
    return (
      <p className="text-muted-foreground">Suspensions could not be loaded.</p>
    )
  }
  if (data.data.length === 0) {
    return (
      <p className="py-8 text-center text-muted-foreground">
        Nobody is suspended. To suspend a member, use "Suspend member" on one of
        their comments in the queue.
      </p>
    )
  }
  return (
    <ul className="flex flex-col gap-3" data-testid="suspension-list">
      {data.data.map((s) => (
        <li
          key={s.id}
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-4 text-sm"
          data-testid="suspension"
        >
          <div className="flex flex-col gap-1">
            <span className="font-medium">
              {s.user?.display_name ?? "Deleted user"}
              {s.user && (
                <span className="font-normal text-muted-foreground">
                  {" "}
                  @{s.user.username}
                </span>
              )}
            </span>
            <span>
              {s.until ? `Until ${formatDateTime(s.until)}` : "Indefinite"}
              {s.reason ? ` - ${s.reason}` : ""}
            </span>
            <span className="text-muted-foreground">
              By {s.created_by?.display_name ?? "a deleted user"},{" "}
              {relativeTime(s.created_at)}
            </span>
          </div>
          <LoadingButton
            size="sm"
            variant="outline"
            loading={end.isPending && end.variables === s.id}
            onClick={() => end.mutate(s.id)}
          >
            End suspension
          </LoadingButton>
        </li>
      ))}
    </ul>
  )
}
