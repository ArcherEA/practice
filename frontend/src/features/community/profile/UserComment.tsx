import { Link } from "@tanstack/react-router"
import { Heart } from "lucide-react"

import type { AuthorPublic, UserCommentPublic } from "@/client"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { apiUrl } from "@/features/content/public/api"
import { getInitials } from "@/utils"
import { formatDateTime, relativeTime } from "../time"

export function AuthorAvatar({
  author,
  className,
}: {
  author: AuthorPublic
  className?: string
}) {
  return (
    <Avatar className={className ?? "size-8"}>
      {author.avatar_url && (
        <AvatarImage src={apiUrl(author.avatar_url)} alt="" />
      )}
      <AvatarFallback className="text-xs">
        {getInitials(author.display_name)}
      </AvatarFallback>
    </Avatar>
  )
}

/** A comment listed on a profile or in the following feed, linking to its post or page. */
export function UserComment({
  comment,
  showAuthor,
}: {
  comment: UserCommentPublic
  showAuthor?: boolean
}) {
  const { target, author } = comment
  const hash = `comment-${comment.id}`
  const title = target.title
  return (
    <li className="flex flex-col gap-1 py-4" data-testid="user-comment">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        {showAuthor && (
          <Link
            to="/u/$username"
            params={{ username: author.username }}
            className="flex items-center gap-2 font-medium hover:underline"
          >
            <AuthorAvatar author={author} className="size-6" />
            {author.display_name}
          </Link>
        )}
        <span className="text-muted-foreground">commented on</span>
        {target.type === "post" ? (
          <Link
            to="/blog/$slug"
            params={{ slug: target.slug }}
            hash={hash}
            className="font-medium underline-offset-4 hover:underline"
          >
            {title}
          </Link>
        ) : (
          <Link
            to="/p/$slug"
            params={{ slug: target.slug }}
            hash={hash}
            className="font-medium underline-offset-4 hover:underline"
          >
            {title}
          </Link>
        )}
        <time
          dateTime={comment.created_at}
          title={formatDateTime(comment.created_at)}
          className="text-xs text-muted-foreground"
        >
          {relativeTime(comment.created_at)}
        </time>
      </div>
      <p className="whitespace-pre-wrap break-words text-sm">{comment.body}</p>
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        <Heart className="size-3" aria-hidden="true" />
        {comment.like_count}
        <span className="sr-only"> likes</span>
      </span>
    </li>
  )
}
