import { useInfiniteQuery, useQuery } from "@tanstack/react-query"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { notificationsPageOptions, unreadCountOptions } from "../profileApi"
import { formatDateTime, relativeTime } from "../time"
import { NotificationLink, notificationText } from "./NotificationLink"
import { useNotificationActions } from "./useNotificationActions"

export default function NotificationsPage() {
  const list = useInfiniteQuery(notificationsPageOptions)
  const unread = useQuery(unreadCountOptions)
  const { markAllRead, markRead } = useNotificationActions()
  const items = list.data?.pages.flatMap((p) => p.data) ?? []
  const count = unread.data?.unread_count ?? 0

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Notifications</h1>
          <p className="text-muted-foreground">
            {count > 0 ? `${count} unread` : "You are all caught up"}
          </p>
        </div>
        <Button
          variant="outline"
          disabled={count === 0 || markAllRead.isPending}
          onClick={() => markAllRead.mutate()}
        >
          Mark all read
        </Button>
      </div>

      {list.isError ? (
        <p className="text-sm text-muted-foreground">
          Notifications could not be loaded.
        </p>
      ) : list.isLoading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No notifications yet.</p>
      ) : (
        <ul className="flex flex-col divide-y rounded-md border">
          {items.map((n) => (
            <li key={n.id} data-testid="notification-row">
              <NotificationLink
                notification={n}
                className={cn(
                  "flex flex-col gap-0.5 px-4 py-3 hover:bg-accent",
                  !n.read && "bg-accent/40",
                )}
                onNavigate={() => {
                  if (!n.read) markRead.mutate(n.id)
                }}
              >
                <span className={cn("text-sm", !n.read && "font-semibold")}>
                  {notificationText(n)}
                  {!n.read && <span className="sr-only"> (unread)</span>}
                </span>
                {n.comment_snippet && (
                  <span className="line-clamp-2 text-sm text-muted-foreground">
                    {n.comment_snippet}
                  </span>
                )}
                {n.target && (
                  <span className="text-xs text-muted-foreground">
                    on {n.target.title}
                  </span>
                )}
                <time
                  dateTime={n.created_at}
                  title={formatDateTime(n.created_at)}
                  className="text-xs text-muted-foreground"
                >
                  {relativeTime(n.created_at)}
                </time>
              </NotificationLink>
            </li>
          ))}
        </ul>
      )}

      {list.hasNextPage && (
        <Button
          variant="outline"
          className="self-center"
          disabled={list.isFetchingNextPage}
          onClick={() => list.fetchNextPage()}
        >
          Load more
        </Button>
      )}
    </div>
  )
}
