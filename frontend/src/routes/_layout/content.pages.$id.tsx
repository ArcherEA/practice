import { createFileRoute } from "@tanstack/react-router"

import ContentEditorPage from "@/features/content/components/ContentEditorPage"

export const Route = createFileRoute("/_layout/content/pages/$id")({
  component: PageEditor,
  head: () => ({ meta: [{ title: "Edit page - Content" }] }),
})

function PageEditor() {
  const { id } = Route.useParams()
  return <ContentEditorPage kind="page" id={id} />
}
