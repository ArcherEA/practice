import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { Bell } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useModules } from "@/features/modules/useModules"
import { isLoggedIn } from "@/hooks/useAuth"
import { cn } from "@/lib/utils"
import { latestNotificationsOptions, unreadCountOptions } from "../profileApi"
import { relativeTime } from "../time"
import { NotificationLink, notificationText } from "./NotificationLink"
import { useNotificationActions } from "./useNotificationActions"

const LATEST = 8

/**
 * Bell with the unread badge, for the app header and the public header. Renders
 * nothing for visitors or when the community module is off.
 */
export function NotificationBell() {
  const { isEnabled } = useModules()
  if (!isLoggedIn() || !isEnabled("community")) return null
  return <BellMenu />
}

function BellMenu() {
  const [open, setOpen] = useState(false)
  const unread = useQuery(unreadCountOptions)
  const latest = useQuery(latestNotificationsOptions(LATEST, open))
  const { markAllRead, markRead } = useNotificationActions()
  const count = unread.data?.unread_count ?? 0
  const items = latest.data?.data ?? []

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={
            count > 0 ? `Notifications, ${count} unread` : "Notifications"
          }
          data-testid="notification-bell"
        >
          <Bell className="size-4" aria-hidden="true" />
          {count > 0 && (
            <span
              data-testid="unread-badge"
              className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold leading-none text-white"
            >
              {count > 99 ? "99+" : count}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <div className="flex items-center justify-between pr-1">
          <DropdownMenuLabel>Notifications</DropdownMenuLabel>
          <Button
            variant="ghost"
            size="sm"
            disabled={count === 0 || markAllRead.isPending}
            onClick={() => markAllRead.mutate()}
          >
            Mark all read
          </Button>
        </div>
        <DropdownMenuSeparator />
        {latest.isLoading ? (
          <p className="px-2 py-3 text-sm text-muted-foreground">Loading...</p>
        ) : items.length === 0 ? (
          <p className="px-2 py-3 text-sm text-muted-foreground">
            No notifications yet.
          </p>
        ) : (
          items.map((n) => (
            <DropdownMenuItem key={n.id} asChild>
              <NotificationLink
                notification={n}
                className="flex cursor-pointer flex-col items-start gap-0.5"
                onNavigate={() => {
                  if (!n.read) markRead.mutate(n.id)
                }}
              >
                <span
                  className={cn("text-sm", !n.read && "font-semibold")}
                  data-testid="notification-item"
                >
                  {notificationText(n)}
                </span>
                {n.comment_snippet && (
                  <span className="line-clamp-2 text-xs text-muted-foreground">
                    {n.comment_snippet}
                  </span>
                )}
                <span className="text-xs text-muted-foreground">
                  {relativeTime(n.created_at)}
                </span>
              </NotificationLink>
            </DropdownMenuItem>
          ))
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/notifications" className="justify-center">
            View all notifications
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
