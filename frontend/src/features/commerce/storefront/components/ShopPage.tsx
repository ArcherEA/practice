import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"

import type { ProductListItem } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { absoluteUrl } from "../../api"
import {
  SHOP_PAGE_SIZE,
  shopCategoriesOptions,
  shopProductsOptions,
} from "../api"
import { useCurrency } from "../currency"

const chip = (active: boolean) =>
  `rounded-full border px-3 py-1 text-sm hover:bg-accent ${active ? "bg-accent font-medium" : ""}`

function ProductCard({
  product,
  format,
}: {
  product: ProductListItem
  format: (amount: number) => string
}) {
  return (
    <li>
      <Link
        to="/shop/$slug"
        params={{ slug: product.slug }}
        className="group flex h-full flex-col gap-3"
        data-testid="product-card"
      >
        <div className="aspect-square overflow-hidden rounded-lg border bg-muted">
          {product.image_url ? (
            <img
              src={absoluteUrl(product.image_url)}
              alt=""
              loading="lazy"
              className="size-full object-cover transition-transform group-hover:scale-105"
            />
          ) : (
            <div
              className="flex size-full items-center justify-center text-sm text-muted-foreground"
              aria-hidden="true"
            >
              No image
            </div>
          )}
        </div>
        <div className="flex flex-col gap-1">
          <h2 className="font-medium leading-snug group-hover:underline">
            {product.title}
          </h2>
          {product.available && product.from_price !== null ? (
            <p className="text-sm text-muted-foreground">
              From {format(product.from_price)}
            </p>
          ) : (
            <p>
              <Badge variant="secondary">Currently unavailable</Badge>
            </p>
          )}
        </div>
      </Link>
    </li>
  )
}

/** The product grid with the category filter, shared by `/shop` and `/shop/category/<slug>`. */
export function ShopPage({
  page,
  category,
}: {
  page: number
  category?: string
}) {
  const { currency, format } = useCurrency()
  const categories = useQuery(shopCategoriesOptions)
  const products = useQuery({
    ...shopProductsOptions({ page, category, currency: currency ?? "" }),
    enabled: !!currency,
    placeholderData: keepPreviousData,
  })
  const pages = Math.max(
    1,
    Math.ceil((products.data?.count ?? 0) / SHOP_PAGE_SIZE),
  )
  const pageLink = (target: number) => (
    <Link to="." search={{ page: target }} params={(p) => p} resetScroll>
      {target < page ? "Previous" : "Next"}
    </Link>
  )

  return (
    <div className="flex flex-col gap-6">
      {(categories.data?.data.length ?? 0) > 0 && (
        <nav
          aria-label="Categories"
          className="flex flex-wrap items-center gap-2"
        >
          <Link to="/shop" className={chip(!category)}>
            All
          </Link>
          {categories.data?.data.map((c) => (
            <Link
              key={c.id}
              to="/shop/category/$slug"
              params={{ slug: c.slug }}
              className={chip(c.slug === category)}
            >
              {c.name}
            </Link>
          ))}
        </nav>
      )}

      {products.isError ? (
        <p role="alert" className="text-destructive">
          The products could not be loaded. Please try again.
        </p>
      ) : products.data && products.data.data.length === 0 ? (
        <p className="text-muted-foreground">No products here yet.</p>
      ) : (
        <ul
          className="grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-3 lg:grid-cols-4"
          aria-busy={products.isFetching}
        >
          {products.data?.data.map((product) => (
            <ProductCard key={product.id} product={product} format={format} />
          ))}
        </ul>
      )}

      {pages > 1 && (
        <nav
          aria-label="Pagination"
          className="flex items-center justify-between gap-4"
        >
          <Button variant="outline" asChild disabled={page <= 1}>
            {page > 1 ? pageLink(page - 1) : <span>Previous</span>}
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} of {pages}
          </span>
          <Button variant="outline" asChild disabled={page >= pages}>
            {page < pages ? pageLink(page + 1) : <span>Next</span>}
          </Button>
        </nav>
      )}
    </div>
  )
}
