import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query"

import { CommunityService } from "@/client"

// Profiles, follows and notifications (task 017).

export const PEOPLE_PER_PAGE = 20
export const NOTIFICATIONS_PER_PAGE = 20
/** Unread badge refresh; there are no websockets (D18). */
export const UNREAD_POLL_MS = 60_000

export const profileKeys = {
  profile: (username: string) => ["community", "profile", username] as const,
  comments: (username: string) =>
    ["community", "profile", username, "comments"] as const,
  followers: (username: string) =>
    ["community", "profile", username, "followers"] as const,
  following: (username: string) =>
    ["community", "profile", username, "following"] as const,
  activity: ["community", "following-activity"] as const,
}

export const notificationKeys = {
  all: ["community", "notifications"] as const,
  latest: (limit: number) =>
    ["community", "notifications", "latest", limit] as const,
  page: ["community", "notifications", "page"] as const,
  unread: ["community", "notifications", "unread-count"] as const,
}

/** Next `skip` for list endpoints that return `{ data, count }`. */
const nextSkip = (
  last: { data: unknown[]; count: number },
  all: { data: unknown[] }[],
): number | undefined => {
  const loaded = all.reduce((n, p) => n + p.data.length, 0)
  return loaded < last.count && last.data.length > 0 ? loaded : undefined
}

export const profileOptions = (username: string) =>
  queryOptions({
    queryKey: profileKeys.profile(username),
    // An unknown user is a 404, not a hiccup: show "not found" right away.
    retry: false,
    queryFn: async () =>
      (await CommunityService.readProfile({ path: { username } })).data,
  })

export const userCommentsOptions = (username: string) =>
  infiniteQueryOptions({
    queryKey: profileKeys.comments(username),
    initialPageParam: 0,
    queryFn: async ({ pageParam }) =>
      (
        await CommunityService.readUserComments({
          path: { username },
          query: { skip: pageParam, limit: PEOPLE_PER_PAGE },
        })
      ).data,
    getNextPageParam: nextSkip,
  })

export const followersOptions = (username: string) =>
  infiniteQueryOptions({
    queryKey: profileKeys.followers(username),
    initialPageParam: 0,
    queryFn: async ({ pageParam }) =>
      (
        await CommunityService.readFollowers({
          path: { username },
          query: { skip: pageParam, limit: PEOPLE_PER_PAGE },
        })
      ).data,
    getNextPageParam: nextSkip,
  })

export const followingOptions = (username: string) =>
  infiniteQueryOptions({
    queryKey: profileKeys.following(username),
    initialPageParam: 0,
    queryFn: async ({ pageParam }) =>
      (
        await CommunityService.readFollowing({
          path: { username },
          query: { skip: pageParam, limit: PEOPLE_PER_PAGE },
        })
      ).data,
    getNextPageParam: nextSkip,
  })

export const followingActivityOptions = infiniteQueryOptions({
  queryKey: profileKeys.activity,
  initialPageParam: 0,
  queryFn: async ({ pageParam }) =>
    (
      await CommunityService.readFollowingActivity({
        query: { skip: pageParam, limit: PEOPLE_PER_PAGE },
      })
    ).data,
  getNextPageParam: nextSkip,
})

/** Unread count: refreshed every minute and whenever the window gets focus. */
export const unreadCountOptions = queryOptions({
  queryKey: notificationKeys.unread,
  queryFn: async () => (await CommunityService.readUnreadCount()).data,
  refetchInterval: UNREAD_POLL_MS,
  refetchOnWindowFocus: "always",
})

export const latestNotificationsOptions = (limit: number, enabled: boolean) =>
  queryOptions({
    queryKey: notificationKeys.latest(limit),
    enabled,
    queryFn: async () =>
      (await CommunityService.readNotifications({ query: { limit } })).data,
  })

export const notificationsPageOptions = infiniteQueryOptions({
  queryKey: notificationKeys.page,
  initialPageParam: 0,
  queryFn: async ({ pageParam }) =>
    (
      await CommunityService.readNotifications({
        query: { skip: pageParam, limit: NOTIFICATIONS_PER_PAGE },
      })
    ).data,
  getNextPageParam: nextSkip,
  refetchOnWindowFocus: "always",
})
