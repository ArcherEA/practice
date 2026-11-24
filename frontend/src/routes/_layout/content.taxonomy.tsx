import { createFileRoute } from "@tanstack/react-router"

import TaxonomyPage from "@/features/content/components/TaxonomyPage"

export const Route = createFileRoute("/_layout/content/taxonomy")({
  component: TaxonomyPage,
  head: () => ({ meta: [{ title: "Categories & tags - Content" }] }),
})
