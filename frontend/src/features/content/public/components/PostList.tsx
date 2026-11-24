import { useSuspenseQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"

import { Button } from "@/components/ui/button"
import {
  apiUrl,
  formatDate,
  POSTS_PER_PAGE,
  type PostFilters,
  publishedPostsOptions,
} from "../api"

export function PostList({ filters }: { filters: PostFilters }) {
  const { data } = useSuspenseQuery(publishedPostsOptions(filters))
  const pages = Math.max(1, Math.ceil(data.count / POSTS_PER_PAGE))
  // Same route, other page: Link keeps the path params and only swaps `page`.
  const pageLink = (page: number) => (
    <Link to="." search={{ page }} params={(p) => p} resetScroll>
      {page < filters.page ? "Previous" : "Next"}
    </Link>
  )

  if (data.data.length === 0) {
    return <p className="text-muted-foreground">No posts yet.</p>
  }

  return (
    <div className="flex flex-col gap-8">
      <ul className="flex flex-col gap-8">
        {data.data.map((post) => (
          <li key={post.id}>
            <article className="flex flex-col gap-4 sm:flex-row">
              {post.cover_url && (
                <Link
                  to="/blog/$slug"
                  params={{ slug: post.slug }}
                  tabIndex={-1}
                  aria-hidden="true"
                  className="shrink-0 sm:w-56"
                >
                  <img
                    src={apiUrl(post.cover_url)}
                    alt=""
                    loading="lazy"
                    className="aspect-video w-full rounded-lg object-cover"
                  />
                </Link>
              )}
              <div className="flex min-w-0 flex-col gap-2">
                <h2 className="text-xl font-semibold leading-snug">
                  <Link
                    to="/blog/$slug"
                    params={{ slug: post.slug }}
                    className="hover:underline"
                  >
                    {post.title}
                  </Link>
                </h2>
                <p className="flex flex-wrap items-center gap-x-2 text-sm text-muted-foreground">
                  {post.published_at && (
                    <time dateTime={post.published_at}>
                      {formatDate(post.published_at)}
                    </time>
                  )}
                  {post.category && (
                    <>
                      <span aria-hidden="true">&middot;</span>
                      <Link
                        to="/blog/category/$slug"
                        params={{ slug: post.category.slug }}
                        className="hover:underline"
                      >
                        {post.category.name}
                      </Link>
                    </>
                  )}
                </p>
                {post.excerpt && (
                  <p className="text-muted-foreground">{post.excerpt}</p>
                )}
              </div>
            </article>
          </li>
        ))}
      </ul>

      {pages > 1 && (
        <nav
          aria-label="Pagination"
          className="flex items-center justify-between gap-4"
        >
          <Button variant="outline" asChild disabled={filters.page <= 1}>
            {filters.page > 1 ? (
              pageLink(filters.page - 1)
            ) : (
              <span>Previous</span>
            )}
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {filters.page} of {pages}
          </span>
          <Button variant="outline" asChild disabled={filters.page >= pages}>
            {filters.page < pages ? (
              pageLink(filters.page + 1)
            ) : (
              <span>Next</span>
            )}
          </Button>
        </nav>
      )}
    </div>
  )
}
