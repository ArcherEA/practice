import { queryOptions } from "@tanstack/react-query"

import { CommerceService, type ProductDetail } from "@/client"
import { toHead } from "@/features/content/public/api"

export const SHOP_PAGE_SIZE = 12

export interface ShopFilters {
  page: number
  category?: string
  currency: string
}

export const shopKeys = {
  categories: ["shop", "categories"] as const,
  products: (f: ShopFilters) => ["shop", "products", f] as const,
  product: (slug: string, currency: string) =>
    ["shop", "product", slug, currency] as const,
}

export const shopCategoriesOptions = queryOptions({
  queryKey: shopKeys.categories,
  queryFn: async () => (await CommerceService.readCategories()).data,
})

export const shopProductsOptions = (f: ShopFilters) =>
  queryOptions({
    queryKey: shopKeys.products(f),
    queryFn: async () =>
      (
        await CommerceService.readPublishedProducts({
          query: {
            skip: (f.page - 1) * SHOP_PAGE_SIZE,
            limit: SHOP_PAGE_SIZE,
            category: f.category,
            currency: f.currency,
          },
        })
      ).data,
  })

export const shopProductOptions = (slug: string, currency: string) =>
  queryOptions({
    queryKey: shopKeys.product(slug, currency),
    retry: false, // an unknown or unpublished slug is a 404, not a flaky request
    queryFn: async () =>
      (
        await CommerceService.readPublishedProduct({
          path: { slug },
          query: { currency },
        })
      ).data,
  })

export { toHead }

/** The meta values below mirror backend/app/modules/commerce/seo.py. */
export const shopIndexMeta = (siteName: string) => ({
  title: `Shop - ${siteName}`,
  description: `Products from ${siteName}.`,
})

export const shopCategoryMeta = (name: string) => ({
  title: name,
  description: `Products in ${name}.`,
})

const first = (...values: (string | null | undefined)[]): string =>
  values.find((v) => v?.trim())?.trim() ?? ""

/** Text of a Tiptap JSON tree, blocks separated by spaces. */
function plainText(node: unknown): string {
  if (typeof node !== "object" || node === null) return ""
  const n = node as { type?: unknown; text?: unknown; content?: unknown }
  if (n.type === "text") return typeof n.text === "string" ? n.text : ""
  if (!Array.isArray(n.content)) return ""
  return n.content.map(plainText).filter(Boolean).join(" ")
}

export const productMeta = (product: ProductDetail) => {
  const text = plainText(product.description).replace(/\s+/g, " ").trim()
  return {
    title: first(product.seo_title, product.title),
    description: first(
      product.seo_description,
      text.length > 300 ? `${text.slice(0, 299).trimEnd()}…` : text,
      product.title,
    ),
  }
}
