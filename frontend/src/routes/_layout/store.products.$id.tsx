import { createFileRoute } from "@tanstack/react-router"

import ProductEditorPage from "@/features/commerce/components/ProductEditorPage"

export const Route = createFileRoute("/_layout/store/products/$id")({
  component: ProductEditor,
  head: () => ({ meta: [{ title: "Edit product - Store" }] }),
})

function ProductEditor() {
  const { id } = Route.useParams()
  return <ProductEditorPage id={id} />
}
