import { createFileRoute } from "@tanstack/react-router"

import ContentListPage from "@/features/content/components/ContentListPage"

export const Route = createFileRoute("/_layout/content/pages/")({
  component: () => <ContentListPage kind="page" />,
  head: () => ({ meta: [{ title: "Pages - Content" }] }),
})
