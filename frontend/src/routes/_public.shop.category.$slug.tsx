import { createFileRoute, notFound } from "@tanstack/react-router"

import {
  shopCategoriesOptions,
  shopCategoryMeta,
  shopProductsOptions,
  toHead,
} from "@/features/commerce/storefront/api"
import { ShopPage } from "@/features/commerce/storefront/components/ShopPage"
import { currentCurrency } from "@/features/commerce/storefront/currency"
import { parsePage } from "@/features/content/public/search"
import { requireModule } from "@/features/modules/api"

export const Route = createFileRoute("/_public/shop/category/$slug")({
  beforeLoad: ({ context }) => requireModule(context.queryClient, "commerce"),
  validateSearch: parsePage,
  loaderDeps: ({ search }) => ({ page: search.page ?? 1 }),
  loader: async ({ context, params, deps }) => {
    const categories = await context.queryClient.ensureQueryData(
      shopCategoriesOptions,
    )
    const category = categories.data.find((c) => c.slug === params.slug)
    if (!category) throw notFound()
    const currency = await currentCurrency(context.queryClient)
    await context.queryClient.ensureQueryData(
      shopProductsOptions({ page: deps.page, category: params.slug, currency }),
    )
    return category
  },
  head: ({ loaderData }) =>
    loaderData ? toHead(shopCategoryMeta(loaderData.name)) : {},
  component: ShopCategory,
})

function ShopCategory() {
  const { slug } = Route.useParams()
  const { page } = Route.useSearch()
  const category = Route.useLoaderData()
  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-3xl font-bold">{category.name}</h1>
      <ShopPage page={page ?? 1} category={slug} />
    </section>
  )
}
