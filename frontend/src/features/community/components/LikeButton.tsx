import { Link } from "@tanstack/react-router"
import { Heart } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

/**
 * Heart button with a count. Anonymous visitors get a link to the login page
 * (which brings them back here) instead of a toggle.
 */
export function LikeButton({
  what,
  count,
  liked,
  loggedIn,
  returnTo,
  pending,
  onToggle,
}: {
  /** "post" or "comment", used in the accessible name. */
  what: "post" | "comment"
  count: number
  liked: boolean
  loggedIn: boolean
  returnTo: string
  pending?: boolean
  onToggle: (like: boolean) => void
}) {
  const icon = (
    <Heart
      className={cn("size-4", liked && "fill-current text-rose-600")}
      aria-hidden="true"
    />
  )
  const counter = (
    <span data-testid="like-count" className="tabular-nums">
      {count}
    </span>
  )
  if (!loggedIn) {
    return (
      <Button variant="ghost" size="sm" asChild>
        <Link
          to="/login"
          search={{ redirect: returnTo }}
          aria-label={`Log in to like this ${what}`}
        >
          {icon}
          {counter}
        </Link>
      </Button>
    )
  }
  return (
    <Button
      variant="ghost"
      size="sm"
      aria-label={liked ? `Unlike ${what}` : `Like ${what}`}
      aria-pressed={liked}
      disabled={pending}
      onClick={() => onToggle(!liked)}
    >
      {icon}
      {counter}
    </Button>
  )
}
