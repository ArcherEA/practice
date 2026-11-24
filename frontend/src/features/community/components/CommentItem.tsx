import { Link } from "@tanstack/react-router"
import { MoreHorizontal } from "lucide-react"
import { useState } from "react"

import type { CommentPublic, ReplyPublic } from "@/client"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { LoadingButton } from "@/components/ui/loading-button"
import { apiUrl } from "@/features/content/public/api"
import { getInitials } from "@/utils"
import type { CommentTarget } from "../api"
import { formatDateTime, relativeTime } from "../time"
import type { useCommentActions } from "../useCommentActions"
import { CommentForm } from "./CommentForm"
import { LikeButton } from "./LikeButton"
import { ReportDialog } from "./ReportDialog"

type AnyComment = CommentPublic | ReplyPublic

const PLACEHOLDERS: Partial<Record<AnyComment["state"], string>> = {
  deleted: "This comment was deleted.",
  removed: "This comment was removed by a moderator.",
  hidden: "This comment is hidden.",
}

export function CommentItem({
  comment,
  target,
  currentUserId,
  canComment,
  returnTo,
  actions,
}: {
  comment: AnyComment
  target: CommentTarget
  /** Undefined when nobody is logged in. */
  currentUserId: string | undefined
  /** Logged in and not suspended. */
  canComment: boolean
  returnTo: string
  actions: ReturnType<typeof useCommentActions>
}) {
  const [editing, setEditing] = useState(false)
  const [replying, setReplying] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [reporting, setReporting] = useState(false)

  const loggedIn = currentUserId !== undefined
  const isReply = comment.parent_id != null
  const replies = "replies" in comment ? (comment.replies ?? []) : []
  const placeholder = PLACEHOLDERS[comment.state]
  const isOwn = loggedIn && comment.author?.id === currentUserId
  const author = comment.author
  const name = author?.display_name ?? "Deleted user"

  return (
    <li className="flex flex-col gap-3" data-testid="comment-thread">
      <article
        id={`comment-${comment.id}`}
        data-testid="comment"
        className="flex scroll-mt-24 gap-3 rounded-md transition-colors data-[highlight=true]:bg-primary/10 data-[highlight=true]:ring-2 data-[highlight=true]:ring-primary/40"
      >
        <Avatar className="size-8">
          {author?.avatar_url && (
            <AvatarImage src={apiUrl(author.avatar_url)} alt="" />
          )}
          <AvatarFallback className="text-xs">
            {placeholder ? "?" : getInitials(name)}
          </AvatarFallback>
        </Avatar>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          {placeholder ? (
            <p className="text-sm italic text-muted-foreground">
              {placeholder}
            </p>
          ) : (
            <>
              <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
                {author ? (
                  <Link
                    to="/u/$username"
                    params={{ username: author.username }}
                    className="font-medium hover:underline"
                  >
                    {name}
                  </Link>
                ) : (
                  <span className="font-medium">{name}</span>
                )}
                <time
                  dateTime={comment.created_at}
                  title={formatDateTime(comment.created_at)}
                  className="text-xs text-muted-foreground"
                >
                  {relativeTime(comment.created_at)}
                </time>
                {comment.edited_at && (
                  <span
                    className="text-xs text-muted-foreground"
                    title={formatDateTime(comment.edited_at)}
                  >
                    (edited)
                  </span>
                )}
              </div>
              {editing ? (
                <CommentForm
                  label="Edit comment"
                  submitLabel="Save"
                  initialValue={comment.body}
                  pending={actions.update.isPending}
                  autoFocus
                  onSubmit={async (body) => {
                    await actions.update.mutateAsync({ id: comment.id, body })
                    setEditing(false)
                  }}
                  onCancel={() => setEditing(false)}
                />
              ) : (
                // Plain text only: React escapes it, newlines are kept.
                <p
                  className="whitespace-pre-wrap break-words text-sm"
                  data-testid="comment-body"
                >
                  {comment.body}
                </p>
              )}
              {!editing && (
                <div className="-ml-2 flex items-center gap-1">
                  <LikeButton
                    what="comment"
                    count={comment.like_count}
                    liked={comment.liked_by_me ?? false}
                    loggedIn={loggedIn}
                    returnTo={returnTo}
                    pending={actions.likeComment.isPending}
                    onToggle={(like) =>
                      actions.likeComment.mutate({ id: comment.id, like })
                    }
                  />
                  {canComment && !isReply && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setReplying((r) => !r)}
                    >
                      Reply
                    </Button>
                  )}
                  {loggedIn && (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-8"
                          aria-label="Comment actions"
                        >
                          <MoreHorizontal className="size-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="start">
                        {comment.can_edit && (
                          <DropdownMenuItem onSelect={() => setEditing(true)}>
                            Edit
                          </DropdownMenuItem>
                        )}
                        {isOwn && (
                          <DropdownMenuItem
                            variant="destructive"
                            onSelect={() => setConfirmDelete(true)}
                          >
                            Delete
                          </DropdownMenuItem>
                        )}
                        {!isOwn && (
                          <DropdownMenuItem onSelect={() => setReporting(true)}>
                            Report
                          </DropdownMenuItem>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </article>

      {(replies.length > 0 || replying) && (
        <ul className="ml-11 flex flex-col gap-4 border-l pl-4">
          {replies.map((reply) => (
            <CommentItem
              key={reply.id}
              comment={reply}
              target={target}
              currentUserId={currentUserId}
              canComment={canComment}
              returnTo={returnTo}
              actions={actions}
            />
          ))}
          {replying && (
            <li>
              <CommentForm
                label="Write a reply"
                submitLabel="Send reply"
                pending={actions.create.isPending}
                autoFocus
                onSubmit={async (body) => {
                  await actions.create.mutateAsync({
                    body,
                    parentId: comment.id,
                  })
                  setReplying(false)
                }}
                onCancel={() => setReplying(false)}
              />
            </li>
          )}
        </ul>
      )}

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete comment</DialogTitle>
            <DialogDescription>
              This comment will be deleted. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>
              Cancel
            </Button>
            <LoadingButton
              variant="destructive"
              loading={actions.remove.isPending}
              onClick={() =>
                actions.remove.mutate(comment.id, {
                  onSettled: () => setConfirmDelete(false),
                })
              }
            >
              Delete
            </LoadingButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ReportDialog
        open={reporting}
        onOpenChange={setReporting}
        pending={actions.report.isPending}
        onSubmit={(reason, note) =>
          actions.report.mutateAsync({ id: comment.id, data: { reason, note } })
        }
      />
    </li>
  )
}
