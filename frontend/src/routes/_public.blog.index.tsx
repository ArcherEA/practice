import { createFileRoute } from "@tanstack/react-router"
import { Suspense } from "react"
import {
  blogIndexMeta,
  publishedPostsOptions,
  toHead,
} from "@/features/content/public/api"
import { PostList } from "@/features/content/public/components/PostList"
import { parsePage } from "@/features/content/public/search"
import { configQueryOptions, requireModule } from "@/features/modules/api"

export const Route = createFileRoute("/_public/blog/")({
  beforeLoad: ({ context }) => requireModule(context.queryClient, "content"),
  validateSearch: parsePage,
  loaderDeps: ({ search }) => ({ page: search.page ?? 1 }),
  loader: async ({ context, deps }) => {
    const config = await context.queryClient.ensureQueryData(configQueryOptions)
    await context.queryClient.ensureQueryData(
      publishedPostsOptions({ page: deps.page }),
    )
    return { siteName: config.project_name }
  },
  head: ({ loaderData }) => toHead(blogIndexMeta(loaderData?.siteName ?? "")),
  component: BlogIndex,
})

function BlogIndex() {
  const { page } = Route.useSearch()
  return (
    <section className="mx-auto w-full max-w-3xl">
      <h1 className="mb-8 text-3xl font-bold">Blog</h1>
      <Suspense fallback={null}>
        <PostList filters={{ page: page ?? 1 }} />
      </Suspense>
    </section>
  )
}
