import { useInfiniteQuery } from "@tanstack/react-query"

import { Button } from "@/components/ui/button"
import { followingActivityOptions } from "../profileApi"
import { UserComment } from "./UserComment"

/** Recent comments of the people I follow. */
export default function FollowingPage() {
  const query = useInfiniteQuery(followingActivityOptions)
  const items = query.data?.pages.flatMap((p) => p.data) ?? []

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Following</h1>
        <p className="text-muted-foreground">
          Recent comments from the people you follow
        </p>
      </div>
      {query.isError ? (
        <p className="text-sm text-muted-foreground">
          Activity could not be loaded.
        </p>
      ) : query.isLoading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Nothing here yet. Follow people from their profile to see what they
          write.
        </p>
      ) : (
        <ul className="divide-y">
          {items.map((c) => (
            <UserComment key={c.id} comment={c} showAuthor />
          ))}
        </ul>
      )}
      {query.hasNextPage && (
        <Button
          variant="outline"
          className="self-center"
          disabled={query.isFetchingNextPage}
          onClick={() => query.fetchNextPage()}
        >
          Load more
        </Button>
      )}
    </div>
  )
}
