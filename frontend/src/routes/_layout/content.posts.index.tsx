import { createFileRoute } from "@tanstack/react-router"

import ContentListPage from "@/features/content/components/ContentListPage"

export const Route = createFileRoute("/_layout/content/posts/")({
  component: () => <ContentListPage kind="post" />,
  head: () => ({ meta: [{ title: "Posts - Content" }] }),
})
