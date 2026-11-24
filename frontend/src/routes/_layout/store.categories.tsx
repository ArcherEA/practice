import { createFileRoute } from "@tanstack/react-router"

import CategoriesPage from "@/features/commerce/components/CategoriesPage"

export const Route = createFileRoute("/_layout/store/categories")({
  component: CategoriesPage,
  head: () => ({ meta: [{ title: "Categories - Store" }] }),
})
