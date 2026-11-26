import { createFileRoute } from "@tanstack/react-router"

import {
  orNotFound,
  postMeta,
  publishedPostOptions,
  toHead,
} from "@/features/content/public/api"
import { PostView } from "@/features/content/public/components/PostView"
import { requireModule } from "@/features/modules/api"

export const Route = createFileRoute("/_public/blog/$slug")({
  beforeLoad: ({ context }) => requireModule(context.queryClient, "content"),
  loader: ({ context, params }) =>
    orNotFound(() =>
      context.queryClient.ensureQueryData(publishedPostOptions(params.slug)),
    ),
  head: ({ loaderData }) => (loaderData ? toHead(postMeta(loaderData)) : {}),
  component: Post,
})

function Post() {
  const { slug } = Route.useParams()
  return <PostView slug={slug} />
}
