import { useInfiniteQuery, useQuery } from "@tanstack/react-query"
import { Link, useRouterState } from "@tanstack/react-router"
import { useState } from "react"

import type { CommentSort } from "@/client"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { useModules } from "@/features/modules/useModules"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import {
  type CommentTarget,
  commentsOptions,
  mySuspensionOptions,
} from "../api"
import { formatDateTime } from "../time"
import { useCommentActions } from "../useCommentActions"
import { CommentForm } from "./CommentForm"
import { CommentItem } from "./CommentItem"
import { LikeButton } from "./LikeButton"

/**
 * Comments (and, for posts, the like button) under a public post or page.
 * Renders nothing when the community module is disabled, so the page looks
 * exactly as it did before.
 */
export function CommentSection({ target }: { target: CommentTarget }) {
  const { isEnabled } = useModules()
  if (!isEnabled("community")) return null
  return <Comments target={target} />
}

const SORTS: { value: CommentSort; label: string }[] = [
  { value: "newest", label: "Newest" },
  { value: "oldest", label: "Oldest" },
]

function Comments({ target }: { target: CommentTarget }) {
  const [sort, setSort] = useState<CommentSort>("newest")
  const loggedIn = isLoggedIn()
  const { user } = useAuth()
  const returnTo = useRouterState({ select: (s) => s.location.pathname })
  const actions = useCommentActions(target)

  const comments = useInfiniteQuery(commentsOptions(target, sort))
  const suspension = useQuery(mySuspensionOptions(loggedIn))
  const suspended = suspension.data?.suspended === true
  const canComment = loggedIn && !suspended && !suspension.isLoading

  const first = comments.data?.pages[0]
  const items = comments.data?.pages.flatMap((p) => p.data) ?? []

  return (
    <section
      aria-labelledby="comments-heading"
      className="mx-auto mt-12 w-full max-w-[42rem] border-t pt-8"
      data-testid="comment-section"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 id="comments-heading" className="text-xl font-semibold">
          Comments{first ? ` (${first.count})` : ""}
        </h2>
        <div className="flex items-center gap-2">
          {target.type === "post" && first && (
            <LikeButton
              what="post"
              count={first.post_like_count ?? 0}
              liked={first.post_liked_by_me ?? false}
              loggedIn={loggedIn}
              returnTo={returnTo}
              pending={actions.likePost.isPending}
              onToggle={(like) => actions.likePost.mutate(like)}
            />
          )}
          <fieldset className="flex gap-1">
            <legend className="sr-only">Sort comments</legend>
            {SORTS.map((s) => (
              <Button
                key={s.value}
                size="sm"
                variant={sort === s.value ? "secondary" : "ghost"}
                aria-pressed={sort === s.value}
                onClick={() => setSort(s.value)}
              >
                {s.label}
              </Button>
            ))}
          </fieldset>
        </div>
      </div>

      <div className="mb-6">
        {!loggedIn ? (
          <p className="text-sm">
            <Link
              to="/login"
              search={{ redirect: returnTo }}
              className="font-medium underline underline-offset-4"
            >
              Log in to comment
            </Link>
          </p>
        ) : suspended ? (
          <Alert role="status">
            <AlertTitle>You can't comment right now</AlertTitle>
            <AlertDescription>
              <p>
                Your account is suspended from commenting
                {suspension.data?.until
                  ? ` until ${formatDateTime(suspension.data.until)}`
                  : " until further notice"}
                . You can still read, and delete your own comments.
              </p>
              {suspension.data?.reason && (
                <p>Reason: {suspension.data.reason}</p>
              )}
            </AlertDescription>
          </Alert>
        ) : (
          canComment && (
            <CommentForm
              label="Add a comment"
              submitLabel="Post comment"
              pending={actions.create.isPending}
              onSubmit={(body) => actions.create.mutateAsync({ body })}
            />
          )
        )}
      </div>

      {comments.isError ? (
        <p className="text-sm text-muted-foreground">
          Comments could not be loaded.
        </p>
      ) : comments.isLoading ? (
        <p className="text-sm text-muted-foreground">Loading comments...</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No comments yet. Be the first to comment.
        </p>
      ) : (
        <ul className="flex flex-col gap-6" data-testid="comment-list">
          {items.map((comment) => (
            <CommentItem
              key={comment.id}
              comment={comment}
              target={target}
              currentUserId={user?.id}
              canComment={canComment}
              returnTo={returnTo}
              actions={actions}
            />
          ))}
        </ul>
      )}

      {comments.hasNextPage && (
        <Button
          variant="outline"
          className="mt-6"
          disabled={comments.isFetchingNextPage}
          onClick={() => comments.fetchNextPage()}
        >
          Load more comments
        </Button>
      )}
    </section>
  )
}
