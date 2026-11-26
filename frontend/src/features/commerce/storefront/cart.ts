import { createPersistedStore, usePersistedStore } from "./persisted"

export const CART_KEY = "shop.cart"
export const MAX_QUANTITY = 99
const MAX_LINES = 50

/**
 * One cart line. Only identifiers and the quantity are stored; names, prices and
 * availability are always fetched again when the cart opens. `price` and `currency`
 * remember what the visitor saw when adding (or last accepted), so the cart can flag
 * a changed price.
 */
export interface CartItem {
  slug: string
  variantId: string
  slotId: string | null
  quantity: number
  price: number | null
  currency: string | null
}

const isString = (v: unknown): v is string => typeof v === "string" && v !== ""

const clampQuantity = (n: unknown): number =>
  Math.min(MAX_QUANTITY, Math.max(1, Math.floor(Number(n)) || 1))

/** Reads whatever is in storage, dropping anything that is not a valid line. */
export function parseCart(raw: unknown): CartItem[] {
  if (!Array.isArray(raw)) return []
  const items: CartItem[] = []
  for (const entry of raw.slice(0, MAX_LINES)) {
    if (typeof entry !== "object" || entry === null) continue
    const e = entry as Record<string, unknown>
    if (!isString(e.slug) || !isString(e.variantId)) continue
    items.push({
      slug: e.slug,
      variantId: e.variantId,
      slotId: isString(e.slotId) ? e.slotId : null,
      quantity: clampQuantity(e.quantity),
      price:
        typeof e.price === "number" && Number.isSafeInteger(e.price)
          ? e.price
          : null,
      currency: isString(e.currency) ? e.currency : null,
    })
  }
  return items
}

const store = createPersistedStore<CartItem[]>(CART_KEY, parseCart, [])

export const lineKey = (item: Pick<CartItem, "variantId" | "slotId">): string =>
  `${item.variantId}:${item.slotId ?? ""}`

const sameLine = (a: CartItem, b: CartItem): boolean =>
  lineKey(a) === lineKey(b)

export function addToCart(item: CartItem): void {
  const items = store.get()
  const existing = items.find((i) => sameLine(i, item))
  if (existing) {
    store.set(
      items.map((i) =>
        i === existing
          ? {
              ...i,
              ...item,
              quantity: clampQuantity(i.quantity + item.quantity),
            }
          : i,
      ),
    )
  } else if (items.length < MAX_LINES) {
    store.set([...items, { ...item, quantity: clampQuantity(item.quantity) }])
  }
}

export function setQuantity(key: string, quantity: number): void {
  store.set(
    store
      .get()
      .map((i) =>
        lineKey(i) === key ? { ...i, quantity: clampQuantity(quantity) } : i,
      ),
  )
}

export function removeFromCart(key: string): void {
  store.set(store.get().filter((i) => lineKey(i) !== key))
}

/** The visitor accepted the current price of a line. */
export function acceptPrice(
  key: string,
  price: number,
  currency: string,
): void {
  store.set(
    store
      .get()
      .map((i) => (lineKey(i) === key ? { ...i, price, currency } : i)),
  )
}

export const useCart = (): CartItem[] => usePersistedStore(store)

export const cartCount = (items: CartItem[]): number =>
  items.reduce((sum, i) => sum + i.quantity, 0)
