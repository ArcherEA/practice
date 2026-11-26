import { createFileRoute } from "@tanstack/react-router"

import {
  productMeta,
  shopProductOptions,
  toHead,
} from "@/features/commerce/storefront/api"
import { ProductPage } from "@/features/commerce/storefront/components/ProductPage"
import { currentCurrency } from "@/features/commerce/storefront/currency"
import { orNotFound } from "@/features/content/public/api"
import { requireModule } from "@/features/modules/api"

export const Route = createFileRoute("/_public/shop/$slug")({
  beforeLoad: ({ context }) => requireModule(context.queryClient, "commerce"),
  loader: async ({ context, params }) => {
    const currency = await currentCurrency(context.queryClient)
    return orNotFound(() =>
      context.queryClient.ensureQueryData(
        shopProductOptions(params.slug, currency),
      ),
    )
  },
  head: ({ loaderData }) => (loaderData ? toHead(productMeta(loaderData)) : {}),
  component: Product,
})

function Product() {
  const { slug } = Route.useParams()
  return <ProductPage slug={slug} />
}
