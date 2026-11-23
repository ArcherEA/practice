import { useSuspenseQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { useMemo } from "react"

import { CommentSection } from "@/features/community/components/CommentSection"
import { resolveBodyImages } from "@/features/content/body"
import { ContentRenderer } from "@/features/content/components/ContentRenderer"
import { apiUrl, formatDate, publishedPostOptions } from "../api"

/** Long text stays at a readable line length (about 65-75 characters). */
const READABLE = "mx-auto w-full max-w-[42rem]"

export function PostView({ slug }: { slug: string }) {
  const { data: post } = useSuspenseQuery(publishedPostOptions(slug))
  const body = useMemo(() => resolveBodyImages(post.body), [post.body])

  return (
    <>
      <article className={READABLE}>
        <header className="mb-8 flex flex-col gap-3">
          <h1 className="text-3xl font-bold leading-tight sm:text-4xl">
            {post.title}
          </h1>
          <p className="flex flex-wrap items-center gap-x-2 text-sm text-muted-foreground">
            {post.author_name && <span>{post.author_name}</span>}
            {post.published_at && (
              <>
                {post.author_name && <span aria-hidden="true">&middot;</span>}
                <time dateTime={post.published_at}>
                  {formatDate(post.published_at)}
                </time>
              </>
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
          {post.cover_url && (
            <img
              src={apiUrl(post.cover_url)}
              alt=""
              className="mt-2 aspect-video w-full rounded-lg object-cover"
            />
          )}
        </header>
        <ContentRenderer body={body} />
        {post.tags.length > 0 && (
          <footer className="mt-10 flex flex-wrap items-center gap-2 border-t pt-4 text-sm">
            <span className="text-muted-foreground">Tags:</span>
            {post.tags.map((tag) => (
              <Link
                key={tag.id}
                to="/blog/tag/$slug"
                params={{ slug: tag.slug }}
                className="rounded-full border px-3 py-1 hover:bg-accent"
              >
                {tag.name}
              </Link>
            ))}
          </footer>
        )}
      </article>
      <CommentSection target={{ type: "post", id: post.id }} />
    </>
  )
}

export function PageView({
  id,
  title,
  body,
}: {
  id: string
  title: string
  body: { [key: string]: unknown }
}) {
  const resolved = useMemo(() => resolveBodyImages(body), [body])
  return (
    <>
      <article className={READABLE}>
        <h1 className="mb-8 text-3xl font-bold leading-tight sm:text-4xl">
          {title}
        </h1>
        <ContentRenderer body={resolved} />
      </article>
      <CommentSection target={{ type: "page", id }} />
    </>
  )
}
