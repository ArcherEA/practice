import {
  type UseInfiniteQueryResult,
  useInfiniteQuery,
  useSuspenseQuery,
} from "@tanstack/react-query"
import { Link, useRouterState } from "@tanstack/react-router"
import type { ReactNode } from "react"

import type { AuthorPublic } from "@/client"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  followersOptions,
  followingOptions,
  profileOptions,
  userCommentsOptions,
} from "../profileApi"
import { FollowButton } from "./FollowButton"
import { AuthorAvatar, UserComment } from "./UserComment"

const joinedFormat = new Intl.DateTimeFormat(undefined, {
  month: "long",
  year: "numeric",
})

function LoadMore({
  query,
}: {
  query: Pick<
    UseInfiniteQueryResult,
    "hasNextPage" | "isFetchingNextPage" | "fetchNextPage"
  >
}) {
  if (!query.hasNextPage) return null
  return (
    <Button
      variant="outline"
      className="mt-4 self-center"
      disabled={query.isFetchingNextPage}
      onClick={() => query.fetchNextPage()}
    >
      Load more
    </Button>
  )
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="py-4 text-sm text-muted-foreground">{children}</p>
}

function CommentsTab({ username }: { username: string }) {
  const query = useInfiniteQuery(userCommentsOptions(username))
  const items = query.data?.pages.flatMap((p) => p.data) ?? []
  if (query.isLoading) return <Empty>Loading...</Empty>
  if (items.length === 0) return <Empty>No comments yet.</Empty>
  return (
    <div className="flex flex-col">
      <ul className="divide-y">
        {items.map((c) => (
          <UserComment key={c.id} comment={c} />
        ))}
      </ul>
      <LoadMore query={query} />
    </div>
  )
}

function PeopleList({
  people,
  query,
  empty,
}: {
  people: AuthorPublic[]
  query: UseInfiniteQueryResult
  empty: string
}) {
  if (query.isLoading) return <Empty>Loading...</Empty>
  if (people.length === 0) return <Empty>{empty}</Empty>
  return (
    <div className="flex flex-col">
      <ul className="divide-y">
        {people.map((p) => (
          <li key={p.id} data-testid="person">
            <Link
              to="/u/$username"
              params={{ username: p.username }}
              className="flex items-center gap-3 py-3 hover:underline"
            >
              <AuthorAvatar author={p} />
              <span className="font-medium">{p.display_name}</span>
              <span className="text-sm text-muted-foreground">
                @{p.username}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      <LoadMore query={query} />
    </div>
  )
}

function FollowersTab({ username }: { username: string }) {
  const query = useInfiniteQuery(followersOptions(username))
  return (
    <PeopleList
      query={query}
      people={query.data?.pages.flatMap((p) => p.data) ?? []}
      empty="No followers yet."
    />
  )
}

function FollowingTab({ username }: { username: string }) {
  const query = useInfiniteQuery(followingOptions(username))
  return (
    <PeopleList
      query={query}
      people={query.data?.pages.flatMap((p) => p.data) ?? []}
      empty="Not following anyone yet."
    />
  )
}

export function ProfilePage({ username }: { username: string }) {
  const { data: profile } = useSuspenseQuery(profileOptions(username))
  const returnTo = useRouterState({ select: (s) => s.location.pathname })

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <header className="flex flex-wrap items-start gap-4">
        <AuthorAvatar author={profile} className="size-20 text-xl" />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h1 className="text-2xl font-bold tracking-tight" data-testid="name">
            {profile.display_name}
          </h1>
          <p className="text-muted-foreground" data-testid="username">
            @{profile.username}
          </p>
          {profile.bio && (
            <p
              className="mt-2 whitespace-pre-wrap break-words"
              data-testid="bio"
            >
              {profile.bio}
            </p>
          )}
          {profile.joined_at && (
            <p className="text-sm text-muted-foreground">
              Joined {joinedFormat.format(new Date(profile.joined_at))}
            </p>
          )}
          {profile.is_suspended && (
            <p className="text-sm text-destructive">
              Suspended from commenting
            </p>
          )}
        </div>
        <FollowButton profile={profile} returnTo={returnTo} />
      </header>

      <dl className="flex gap-6 text-sm" data-testid="profile-counts">
        <div className="flex gap-1">
          <dd className="font-semibold tabular-nums">
            {profile.comment_count}
          </dd>
          <dt className="text-muted-foreground">comments</dt>
        </div>
        <div className="flex gap-1">
          <dd
            className="font-semibold tabular-nums"
            data-testid="follower-count"
          >
            {profile.follower_count}
          </dd>
          <dt className="text-muted-foreground">followers</dt>
        </div>
        <div className="flex gap-1">
          <dd className="font-semibold tabular-nums">
            {profile.following_count}
          </dd>
          <dt className="text-muted-foreground">following</dt>
        </div>
      </dl>

      <Tabs defaultValue="comments">
        <TabsList>
          <TabsTrigger value="comments">Comments</TabsTrigger>
          <TabsTrigger value="followers">Followers</TabsTrigger>
          <TabsTrigger value="following">Following</TabsTrigger>
        </TabsList>
        <TabsContent value="comments">
          <CommentsTab username={profile.username} />
        </TabsContent>
        <TabsContent value="followers">
          <FollowersTab username={profile.username} />
        </TabsContent>
        <TabsContent value="following">
          <FollowingTab username={profile.username} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
