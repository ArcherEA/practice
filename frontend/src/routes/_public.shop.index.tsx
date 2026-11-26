import { createFileRoute } from "@tanstack/react-router"

import {
  shopIndexMeta,
  shopProductsOptions,
  toHead,
} from "@/features/commerce/storefront/api"
import { ShopPage } from "@/features/commerce/storefront/components/ShopPage"
import { currentCurrency } from "@/features/commerce/storefront/currency"
import { parsePage } from "@/features/content/public/search"
import { configQueryOptions, requireModule } from "@/features/modules/api"

export const Route = createFileRoute("/_public/shop/")({
  beforeLoad: ({ context }) => requireModule(context.queryClient, "commerce"),
  validateSearch: parsePage,
  loaderDeps: ({ search }) => ({ page: search.page ?? 1 }),
  loader: async ({ context, deps }) => {
    const config = await context.queryClient.ensureQueryData(configQueryOptions)
    const currency = await currentCurrency(context.queryClient)
    await context.queryClient.ensureQueryData(
      shopProductsOptions({ page: deps.page, currency }),
    )
    return { siteName: config.project_name }
  },
  head: ({ loaderData }) => toHead(shopIndexMeta(loaderData?.siteName ?? "")),
  component: Shop,
})

function Shop() {
  const { page } = Route.useSearch()
  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-3xl font-bold">Shop</h1>
      <ShopPage page={page ?? 1} />
    </section>
  )
}
