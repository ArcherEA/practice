import { createFileRoute } from "@tanstack/react-router"

import ProductsListPage from "@/features/commerce/components/ProductsListPage"

export const Route = createFileRoute("/_layout/store/products/")({
  component: ProductsListPage,
  head: () => ({ meta: [{ title: "Products - Store" }] }),
})
