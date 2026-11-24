import { useQuery } from "@tanstack/react-query"

import {
  CommerceService,
  type ProductStatus,
  type ProductType,
  type StoreConfig,
} from "@/client"
import { hasRole } from "@/features/auth/permissions"
import { API_BASE } from "@/features/content/body"

export const PAGE_SIZE = 20

export interface ProductFilters {
  q: string
  type: ProductType | "all"
  status: ProductStatus | "all"
  categoryId: string
  skip: number
  limit: number
}

export const commerceKeys = {
  all: ["commerce"] as const,
  config: ["commerce", "config"] as const,
  products: (filters: ProductFilters) =>
    ["commerce", "products", filters] as const,
  product: (id: string) => ["commerce", "product", id] as const,
  slots: (productId: string) => ["commerce", "slots", productId] as const,
  categories: ["commerce", "categories"] as const,
}

export const TYPE_LABEL: Record<ProductType, string> = {
  physical: "Physical",
  digital: "Digital",
  service: "Service",
}

export const TYPE_HINT: Record<ProductType, string> = {
  physical: "Shipped goods with stock, such as a T-shirt.",
  digital: "A downloadable file delivered after payment.",
  service: "A booking with fixed time slots and capacity.",
}

export const STATUS_LABEL: Record<ProductStatus, string> = {
  draft: "Draft",
  published: "Published",
  archived: "Archived",
}

/** Who may use the store admin: admin and superuser (mirrors the backend `RequireAdmin`). */
export const canManageStore = (
  user: Parameters<typeof hasRole>[0] | null | undefined,
): boolean => hasRole(user, "admin")

export const fetchStoreConfig = async (): Promise<StoreConfig> =>
  (await CommerceService.readStoreConfig()).data

/** Currencies, default currency and timezone of the store. Rarely changes, so cached for the session. */
export function useStoreConfig() {
  return useQuery({
    queryKey: commerceKeys.config,
    queryFn: fetchStoreConfig,
    staleTime: Number.POSITIVE_INFINITY,
  })
}

export const fetchProducts = async (f: ProductFilters) =>
  (
    await CommerceService.adminReadProducts({
      query: {
        q: f.q || undefined,
        type: f.type === "all" ? undefined : f.type,
        status: f.status === "all" ? undefined : f.status,
        category_id: f.categoryId || undefined,
        skip: f.skip,
        limit: f.limit,
      },
    })
  ).data

export const fetchProduct = async (id: string) =>
  (await CommerceService.adminReadProduct({ path: { product_id: id } })).data

export const fetchCategories = async () =>
  (await CommerceService.adminReadCategories()).data

export const fetchSlots = async (productId: string) =>
  (await CommerceService.adminReadSlots({ path: { product_id: productId } }))
    .data

/** API paths such as `/api/v1/files/{id}/content` need the API origin when the app runs elsewhere (dev). */
export const absoluteUrl = (url: string): string =>
  url.startsWith("/") && !url.startsWith("//") ? `${API_BASE}${url}` : url

/** Image URL for a public file id (same endpoint the content editor uses). */
export const imageUrl = (fileId: string): string =>
  `${API_BASE}/api/v1/files/${fileId}/content`

/** `1234567` -> `1.2 MB`. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ["KB", "MB", "GB"]
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit++
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`
}
