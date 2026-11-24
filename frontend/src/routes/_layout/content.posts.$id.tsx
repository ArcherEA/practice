import { createFileRoute } from "@tanstack/react-router"

import ContentEditorPage from "@/features/content/components/ContentEditorPage"

export const Route = createFileRoute("/_layout/content/posts/$id")({
  component: PostEditor,
  head: () => ({ meta: [{ title: "Edit post - Content" }] }),
})

function PostEditor() {
  const { id } = Route.useParams()
  return <ContentEditorPage kind="post" id={id} />
}
