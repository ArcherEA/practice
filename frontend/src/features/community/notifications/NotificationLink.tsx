import { Link } from "@tanstack/react-router"
import type { ReactNode } from "react"

import type { NotificationPublic } from "@/client"

export function notificationText(n: NotificationPublic): string {
  const actor = n.actor?.display_name ?? "Someone"
  switch (n.type) {
    case "comment_replied":
      return `${actor} replied to your comment`
    case "comment_liked":
      return `${actor} liked your comment`
    case "new_follower":
      return `${actor} started following you`
    case "comment_moderated":
      return "A moderator acted on your comment"
  }
}

/**
 * Links a notification to its target: the commenter's profile for a follow,
 * otherwise the post or page (at the comment). Plain text when the target is gone.
 */
export function NotificationLink({
  notification: n,
  className,
  onNavigate,
  children,
}: {
  notification: NotificationPublic
  className?: string
  onNavigate?: () => void
  children: ReactNode
}) {
  if (n.type === "new_follower" && n.actor) {
    return (
      <Link
        to="/u/$username"
        params={{ username: n.actor.username }}
        className={className}
        onClick={onNavigate}
      >
        {children}
      </Link>
    )
  }
  const hash = n.comment_id ? `comment-${n.comment_id}` : undefined
  if (n.target?.type === "post") {
    return (
      <Link
        to="/blog/$slug"
        params={{ slug: n.target.slug }}
        hash={hash}
        className={className}
        onClick={onNavigate}
      >
        {children}
      </Link>
    )
  }
  if (n.target?.type === "page") {
    return (
      <Link
        to="/p/$slug"
        params={{ slug: n.target.slug }}
        hash={hash}
        className={className}
        onClick={onNavigate}
      >
        {children}
      </Link>
    )
  }
  return <div className={className}>{children}</div>
}
