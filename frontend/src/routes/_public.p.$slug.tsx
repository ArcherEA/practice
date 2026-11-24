import { createFileRoute } from "@tanstack/react-router"

import {
  orNotFound,
  pageMeta,
  publishedPageOptions,
  toHead,
} from "@/features/content/public/api"
import { PageView } from "@/features/content/public/components/PostView"

export const Route = createFileRoute("/_public/p/$slug")({
  loader: ({ context, params }) =>
    orNotFound(() =>
      context.queryClient.ensureQueryData(publishedPageOptions(params.slug)),
    ),
  head: ({ loaderData }) => (loaderData ? toHead(pageMeta(loaderData)) : {}),
  component: PublicPage,
})

function PublicPage() {
  const page = Route.useLoaderData()
  return <PageView id={page.id} title={page.title} body={page.body} />
}
