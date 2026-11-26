import type { ProductDetail, SlotPublic, VariantOffer } from "@/client"
import type { CartItem } from "./cart"
import { maxQuantity, unavailableReason } from "./offers"

/**
 * What the freshly fetched product says about one cart line.
 *
 * - `loading`: the product has not been fetched yet.
 * - `unavailable`: cannot be bought as it is (product gone, option gone, out of stock,
 *   slot gone, not sold in this currency). Not counted in the total.
 * - `limited`: fewer units are available than in the cart. Not counted in the total.
 * - `ok`: can be bought; `changedFrom` is set when the price differs from what the
 *   visitor saw (only comparable within one currency).
 */
export type LineStatus =
  | { kind: "loading" }
  | { kind: "unavailable"; reason: string }
  | { kind: "limited"; max: number; variant: VariantOffer; slot?: SlotPublic }
  | {
      kind: "ok"
      variant: VariantOffer
      unitPrice: number
      changedFrom: number | null
      slot?: SlotPublic
    }

export type ProductResult =
  | { state: "loading" }
  | { state: "missing" }
  | { state: "error" }
  | { state: "found"; product: ProductDetail }

export function lineStatus(
  item: CartItem,
  result: ProductResult,
  currency: string,
): LineStatus {
  if (result.state === "loading") return { kind: "loading" }
  if (result.state === "error") {
    return {
      kind: "unavailable",
      reason: "This item could not be checked right now.",
    }
  }
  if (result.state === "missing") {
    return {
      kind: "unavailable",
      reason: "This product is no longer available.",
    }
  }
  const { product } = result
  const variant = product.variants.find((v) => v.id === item.variantId)
  if (!variant) {
    return {
      kind: "unavailable",
      reason: "This option is no longer available.",
    }
  }
  const reason = unavailableReason(product, variant)
  if (reason) return { kind: "unavailable", reason }

  let slot: SlotPublic | undefined
  if (product.type === "service") {
    slot = product.slots.find((s) => s.id === item.slotId)
    if (!slot) {
      return {
        kind: "unavailable",
        reason: "This time slot is no longer available.",
      }
    }
  }
  const max = maxQuantity(product, variant, slot)
  if (item.quantity > max) return { kind: "limited", max, variant, slot }

  const unitPrice = variant.price as number // unavailableReason ruled out null
  const changedFrom =
    item.currency === currency &&
    item.price !== null &&
    item.price !== unitPrice
      ? item.price
      : null
  return { kind: "ok", variant, unitPrice, changedFrom, slot }
}

/** Sum of the lines that can be bought, in minor units of the cart currency. */
export function cartTotal(
  items: CartItem[],
  statuses: Record<string, LineStatus>,
  key: (item: CartItem) => string,
): number {
  return items.reduce((sum, item) => {
    const status = statuses[key(item)]
    return status?.kind === "ok" ? sum + status.unitPrice * item.quantity : sum
  }, 0)
}
