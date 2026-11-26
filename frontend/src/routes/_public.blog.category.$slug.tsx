import { createFileRoute, notFound } from "@tanstack/react-router"

import {
  categoriesOptions,
  categoryMeta,
  publishedPostsOptions,
  toHead,
} from "@/features/content/public/api"
import { PostList } from "@/features/content/public/components/PostList"
import { parsePage } from "@/features/content/public/search"
import { requireModule } from "@/features/modules/api"

export const Route = createFileRoute("/_public/blog/category/$slug")({
  beforeLoad: ({ context }) => requireModule(context.queryClient, "content"),
  validateSearch: parsePage,
  loaderDeps: ({ search }) => ({ page: search.page ?? 1 }),
  loader: async ({ context, params, deps }) => {
    const categories =
      await context.queryClient.ensureQueryData(categoriesOptions)
    const category = categories.data.find((c) => c.slug === params.slug)
    if (!category) throw notFound()
    await context.queryClient.ensureQueryData(
      publishedPostsOptions({ page: deps.page, category: params.slug }),
    )
    return category
  },
  head: ({ loaderData }) =>
    loaderData ? toHead(categoryMeta(loaderData)) : {},
  component: CategoryPosts,
})

function CategoryPosts() {
  const { slug } = Route.useParams()
  const { page } = Route.useSearch()
  const category = Route.useLoaderData()
  return (
    <section className="mx-auto w-full max-w-3xl">
      <h1 className="mb-2 text-3xl font-bold">{category.name}</h1>
      {category.description && (
        <p className="mb-8 text-muted-foreground">{category.description}</p>
      )}
      <PostList filters={{ page: page ?? 1, category: slug }} />
    </section>
  )
}
