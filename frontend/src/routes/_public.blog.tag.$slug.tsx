import { createFileRoute, notFound } from "@tanstack/react-router"

import {
  publishedPostsOptions,
  tagMeta,
  tagsOptions,
  toHead,
} from "@/features/content/public/api"
import { PostList } from "@/features/content/public/components/PostList"
import { parsePage } from "@/features/content/public/search"
import { requireModule } from "@/features/modules/api"

export const Route = createFileRoute("/_public/blog/tag/$slug")({
  beforeLoad: ({ context }) => requireModule(context.queryClient, "content"),
  validateSearch: parsePage,
  loaderDeps: ({ search }) => ({ page: search.page ?? 1 }),
  loader: async ({ context, params, deps }) => {
    const tags = await context.queryClient.ensureQueryData(tagsOptions)
    const tag = tags.data.find((t) => t.slug === params.slug)
    if (!tag) throw notFound()
    await context.queryClient.ensureQueryData(
      publishedPostsOptions({ page: deps.page, tag: params.slug }),
    )
    return tag
  },
  head: ({ loaderData }) => (loaderData ? toHead(tagMeta(loaderData)) : {}),
  component: TagPosts,
})

function TagPosts() {
  const { slug } = Route.useParams()
  const { page } = Route.useSearch()
  const tag = Route.useLoaderData()
  return (
    <section className="mx-auto w-full max-w-3xl">
      <h1 className="mb-8 text-3xl font-bold">Posts tagged {tag.name}</h1>
      <PostList filters={{ page: page ?? 1, tag: slug }} />
    </section>
  )
}
