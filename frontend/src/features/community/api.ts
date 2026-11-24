import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query"

import { type CommentSort, CommunityService, type QueueFilter } from "@/client"

export const COMMENT_MAX_LENGTH = 5000
export const COMMENTS_PER_PAGE = 20

export type CommentTarget = { type: "post" | "page"; id: string }

export const communityKeys = {
  /** Prefix of every comment list of one post or page (any sort). */
  comments: (t: CommentTarget) =>
    ["community", "comments", t.type, t.id] as const,
  mySuspension: ["community", "my-suspension"] as const,
  moderation: ["community", "moderation"] as const,
  queue: (filter: QueueFilter) =>
    ["community", "moderation", "queue", filter] as const,
  suspensions: ["community", "moderation", "suspensions"] as const,
}

export const commentsOptions = (target: CommentTarget, sort: CommentSort) =>
  infiniteQueryOptions({
    queryKey: [...communityKeys.comments(target), sort],
    initialPageParam: 0,
    queryFn: async ({ pageParam }) => {
      const query = { sort, skip: pageParam, limit: COMMENTS_PER_PAGE }
      return (
        target.type === "post"
          ? await CommunityService.readPostComments({
              path: { post_id: target.id },
              query,
            })
          : await CommunityService.readPageComments({
              path: { page_id: target.id },
              query,
            })
      ).data
    },
    getNextPageParam: (last, all) => {
      const loaded = all.reduce((n, p) => n + p.data.length, 0)
      return loaded < last.count && last.data.length > 0 ? loaded : undefined
    },
  })

export const mySuspensionOptions = (enabled: boolean) =>
  queryOptions({
    queryKey: communityKeys.mySuspension,
    enabled,
    queryFn: async () => (await CommunityService.readMySuspension()).data,
  })

export const MODERATION_PAGE_SIZE = 20

/** Next `skip` for an offset-paged list answering `{ data, count }`, or undefined at the end. */
const nextSkip = (
  last: { data: unknown[]; count: number },
  all: { data: unknown[] }[],
) => {
  const loaded = all.reduce((n, p) => n + p.data.length, 0)
  return loaded < last.count && last.data.length > 0 ? loaded : undefined
}

export const queueOptions = (filter: QueueFilter) =>
  infiniteQueryOptions({
    queryKey: communityKeys.queue(filter),
    initialPageParam: 0,
    queryFn: async ({ pageParam }) =>
      (
        await CommunityService.readModerationQueue({
          query: { filter, skip: pageParam, limit: MODERATION_PAGE_SIZE },
        })
      ).data,
    getNextPageParam: nextSkip,
  })

export const suspensionsOptions = infiniteQueryOptions({
  queryKey: communityKeys.suspensions,
  initialPageParam: 0,
  queryFn: async ({ pageParam }) =>
    (
      await CommunityService.readSuspensions({
        query: {
          active_only: true,
          skip: pageParam,
          limit: MODERATION_PAGE_SIZE,
        },
      })
    ).data,
  getNextPageParam: nextSkip,
})
