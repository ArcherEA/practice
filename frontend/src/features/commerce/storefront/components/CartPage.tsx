import { useQueries } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { AxiosError } from "axios"
import { Trash2 } from "lucide-react"
import { useMemo } from "react"

import type { ProductDetail } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { absoluteUrl } from "../../api"
import { formatSlotStart } from "../../time"
import { shopProductOptions } from "../api"
import {
  acceptPrice,
  type CartItem,
  lineKey,
  MAX_QUANTITY,
  removeFromCart,
  setQuantity,
  useCart,
} from "../cart"
import {
  cartTotal,
  type LineStatus,
  lineStatus,
  type ProductResult,
} from "../cartStatus"
import { useCurrency } from "../currency"
import { formatLocalTime } from "../offers"

function useCartProducts(items: CartItem[], currency: string | undefined) {
  // One request per product, however many lines it has.
  const slugs = useMemo(() => [...new Set(items.map((i) => i.slug))], [items])
  const queries = useQueries({
    queries: slugs.map((slug) => ({
      ...shopProductOptions(slug, currency ?? ""),
      enabled: !!currency,
      // The cart re-checks prices and availability every time it opens.
      staleTime: 0,
      refetchOnMount: "always" as const,
    })),
  })
  const results: Record<string, ProductResult> = {}
  slugs.forEach((slug, i) => {
    const q = queries[i]
    if (q.data) results[slug] = { state: "found", product: q.data }
    else if (q.error instanceof AxiosError && q.error.response?.status === 404)
      results[slug] = { state: "missing" }
    else if (q.isError) results[slug] = { state: "error" }
    else results[slug] = { state: "loading" }
  })
  return results
}

function optionsText(product: ProductDetail, variantId: string): string {
  const variant = product.variants.find((v) => v.id === variantId)
  return variant ? Object.values(variant.option_values).join(" / ") : ""
}

function Line({
  item,
  result,
  status,
  currency,
  timezone,
  format,
}: {
  item: CartItem
  result: ProductResult
  status: LineStatus
  currency: string
  timezone: string
  format: (amount: number) => string
}) {
  const key = lineKey(item)
  const product = result.state === "found" ? result.product : undefined
  const slot = product?.slots.find((s) => s.id === item.slotId)
  const options = product ? optionsText(product, item.variantId) : ""
  const image = product?.image_urls[0]

  return (
    <li
      className="flex flex-col gap-3 py-4 sm:flex-row sm:items-start"
      data-testid="cart-line"
      data-status={status.kind}
    >
      <div className="size-20 shrink-0 overflow-hidden rounded-md border bg-muted">
        {image && (
          <img
            src={absoluteUrl(image)}
            alt=""
            className="size-full object-cover"
          />
        )}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p className="font-medium">
          <Link
            to="/shop/$slug"
            params={{ slug: item.slug }}
            className="hover:underline"
          >
            {product?.title ?? item.slug}
          </Link>
        </p>
        {options && <p className="text-sm text-muted-foreground">{options}</p>}
        {slot && (
          <p className="text-sm text-muted-foreground">
            {formatSlotStart(slot.starts_at, timezone)} (store time) &middot;{" "}
            {formatLocalTime(slot.starts_at)} (your time)
          </p>
        )}
        {status.kind === "unavailable" && (
          <p role="alert" className="text-sm text-destructive">
            <Badge variant="destructive" className="mr-2">
              Unavailable
            </Badge>
            {status.reason} Remove it to continue.
          </p>
        )}
        {status.kind === "limited" && (
          <p role="alert" className="text-sm text-destructive">
            <Badge variant="destructive" className="mr-2">
              Changed
            </Badge>
            Only {status.max} available. Reduce the quantity.
          </p>
        )}
        {status.kind === "ok" && status.changedFrom !== null && (
          <p
            role="status"
            className="flex flex-wrap items-center gap-2 text-sm"
          >
            <Badge variant="secondary">Price changed</Badge>
            <span>
              Was {format(status.changedFrom)}, now {format(status.unitPrice)}.
            </span>
            <Button
              type="button"
              variant="link"
              size="sm"
              className="h-auto p-0"
              onClick={() => acceptPrice(key, status.unitPrice, currency)}
            >
              Accept new price
            </Button>
          </p>
        )}
      </div>
      <div className="flex items-center gap-3 sm:flex-col sm:items-end">
        <label className="sr-only" htmlFor={`qty-${key}`}>
          Quantity of {product?.title ?? item.slug}
        </label>
        <Input
          id={`qty-${key}`}
          type="number"
          inputMode="numeric"
          min={1}
          max={MAX_QUANTITY}
          value={item.quantity}
          onChange={(e) => setQuantity(key, Number(e.target.value))}
          className="w-20"
        />
        <p className="min-w-24 text-right text-sm" data-testid="line-total">
          {status.kind === "ok"
            ? format(status.unitPrice * item.quantity)
            : "—"}
        </p>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={`Remove ${product?.title ?? item.slug}`}
          onClick={() => removeFromCart(key)}
        >
          <Trash2 className="size-4" aria-hidden="true" />
        </Button>
      </div>
    </li>
  )
}

export function CartPage() {
  const items = useCart()
  const { currency, timezone, format } = useCurrency()
  const results = useCartProducts(items, currency)

  const statuses: Record<string, LineStatus> = {}
  for (const item of items) {
    statuses[lineKey(item)] = lineStatus(
      item,
      results[item.slug] ?? { state: "loading" },
      currency ?? "",
    )
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-muted-foreground" data-testid="cart-empty">
          Your cart is empty.
        </p>
        <Button asChild>
          <Link to="/shop">Continue shopping</Link>
        </Button>
      </div>
    )
  }

  const blocked = items.filter((i) => {
    const kind = statuses[lineKey(i)]?.kind
    return kind === "unavailable" || kind === "limited"
  }).length
  const total = cartTotal(items, statuses, lineKey)

  return (
    <div className="flex flex-col gap-4">
      <ul className="divide-y border-y" data-testid="cart-lines">
        {items.map((item) => (
          <Line
            key={lineKey(item)}
            item={item}
            result={results[item.slug] ?? { state: "loading" }}
            status={statuses[lineKey(item)] ?? { kind: "loading" }}
            currency={currency ?? ""}
            timezone={timezone}
            format={format}
          />
        ))}
      </ul>
      <div className="flex flex-col items-end gap-2">
        <p className="text-lg font-semibold" data-testid="cart-total">
          Total {format(total)}
        </p>
        {blocked > 0 && (
          <p className="text-sm text-muted-foreground">
            {blocked === 1 ? "1 item is" : `${blocked} items are`} not included
            in the total.
          </p>
        )}
        <Button type="button" disabled>
          Checkout coming soon
        </Button>
      </div>
    </div>
  )
}
