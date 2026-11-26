import type { ProductDetail, SlotPublic, VariantOffer } from "@/client"
import { MAX_QUANTITY } from "./cart"

export type Selection = Record<string, string>

const matches = (variant: VariantOffer, selection: Selection): boolean =>
  Object.entries(variant.option_values).every(
    ([name, value]) => selection[name] === value,
  )

/** The variant that has exactly the chosen value for every option (the only one when there are no options). */
export function findVariant(
  product: Pick<ProductDetail, "options" | "variants">,
  selection: Selection,
): VariantOffer | undefined {
  if (product.options.length === 0) return product.variants[0]
  if (product.options.some((o) => selection[o.name] === undefined)) {
    return undefined
  }
  return product.variants.find((v) => matches(v, selection))
}

/** Start on the first variant that can be bought, else on the first one. */
export function initialSelection(
  product: Pick<ProductDetail, "variants">,
): Selection {
  const variant =
    product.variants.find((v) => v.available) ?? product.variants[0]
  return variant ? { ...variant.option_values } : {}
}

/** Why a variant cannot be bought, or null when it can. */
export function unavailableReason(
  product: Pick<ProductDetail, "type" | "currency">,
  variant: VariantOffer | undefined,
): string | null {
  if (!variant) return "This combination is not available."
  if (variant.price === null) {
    return `Not sold in ${product.currency.toUpperCase()}.`
  }
  if (!variant.in_stock) {
    return product.type === "service"
      ? "No upcoming time slots."
      : "Out of stock."
  }
  return variant.available ? null : "Currently unavailable."
}

/** The most units one order line may have for this variant and slot. */
export function maxQuantity(
  product: Pick<ProductDetail, "type">,
  variant: VariantOffer,
  slot: SlotPublic | undefined,
): number {
  let max = MAX_QUANTITY
  if (product.type === "physical" && variant.stock !== null) {
    max = Math.min(max, variant.stock)
  }
  if (product.type === "service" && slot) max = Math.min(max, slot.remaining)
  return max
}

/** `Mon 24 Nov 2026, 10:00` in the visitor's own timezone. */
export function formatLocalTime(iso: string): string {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso))
}

/** The visitor's timezone name, e.g. `Europe/London`. */
export const localTimeZone = (): string =>
  Intl.DateTimeFormat().resolvedOptions().timeZone
