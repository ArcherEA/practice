import type { CurrencyInfo, OptionPublic, VariantAdmin } from "@/client"
import { formatMoney, parseMoney } from "./money"

/** Backend limit per product (`MAX_OPTIONS`) and a sanity cap for one "generate" click. */
export const MAX_OPTIONS = 3
export const MAX_GENERATED = 200

export type OptionValues = Record<string, string>

const canonical = (values: OptionValues): string =>
  JSON.stringify(
    Object.keys(values)
      .sort()
      .map((k) => [k, values[k]]),
  )

/** Every combination of the options' values, in option and value order. One empty combination when there are no options. */
export function combinations(
  options: Pick<OptionPublic, "name" | "values">[],
): OptionValues[] {
  let result: OptionValues[] = [{}]
  for (const option of options) {
    result = result.flatMap((partial) =>
      option.values.map((value) => ({ ...partial, [option.name]: value })),
    )
  }
  return result
}

/** Combinations that do not have a variant yet. */
export function missingCombinations(
  options: Pick<OptionPublic, "name" | "values">[],
  variants: Pick<VariantAdmin, "option_values">[],
): OptionValues[] {
  const existing = new Set(variants.map((v) => canonical(v.option_values)))
  return combinations(options).filter((c) => !existing.has(canonical(c)))
}

const SKU_MAX = 64

const skuPart = (text: string): string =>
  text
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")

/** Suggested SKU, e.g. `TEE-M-RED` for slug `tee` and values M / Red. Matches the backend pattern. */
export function suggestSku(
  slug: string,
  values: OptionValues,
  options: Pick<OptionPublic, "name">[],
  index: number,
): string {
  const parts = [
    skuPart(slug) || "ITEM",
    ...options.map((o, i) => skuPart(values[o.name] ?? "") || String(i + 1)),
  ]
  const sku = parts.join("-").slice(0, SKU_MAX).replace(/-+$/g, "")
  return sku || `ITEM-${index + 1}`
}

/** What the grid edits for one variant: texts, as typed. */
export interface VariantDraft {
  sku: string
  stock: string
  active: boolean
  /** Price text by currency code; empty = no price. */
  prices: Record<string, string>
}

export const priceOf = (
  variant: Pick<VariantAdmin, "prices">,
  currency: string,
): number | undefined =>
  variant.prices.find((p) => p.currency.toLowerCase() === currency)?.amount

export function draftFromVariant(
  variant: VariantAdmin,
  currencies: CurrencyInfo[],
): VariantDraft {
  const prices: Record<string, string> = {}
  for (const c of currencies) {
    const amount = priceOf(variant, c.code)
    prices[c.code] = amount === undefined ? "" : formatMoney(amount, c.exponent)
  }
  return {
    sku: variant.sku,
    stock: variant.stock === null ? "" : String(variant.stock),
    active: variant.is_active,
    prices,
  }
}

/** Changes whenever the saved variant's editable fields change (file changes do not count). */
export const variantSignature = (variant: VariantAdmin): string =>
  JSON.stringify([
    variant.sku,
    variant.stock,
    variant.is_active,
    [...variant.prices]
      .sort((a, b) => a.currency.localeCompare(b.currency))
      .map((p) => [p.currency, p.amount]),
  ])

export const draftsEqual = (a: VariantDraft, b: VariantDraft): boolean =>
  a.sku === b.sku &&
  a.stock === b.stock &&
  a.active === b.active &&
  Object.keys({ ...a.prices, ...b.prices }).every(
    (c) => (a.prices[c] ?? "") === (b.prices[c] ?? ""),
  )

export type RowErrors = Record<string, string>

/** Local checks before saving a row. Returns field -> message (`sku`, `stock`, `price:usd`). */
export function validateDraft(
  draft: VariantDraft,
  currencies: CurrencyInfo[],
): RowErrors {
  const errors: RowErrors = {}
  if (!draft.sku.trim()) errors.sku = "SKU is required"
  else if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(draft.sku.trim())) {
    errors.sku = "Letters, digits, '.', '_' and '-' only"
  } else if (draft.sku.trim().length > SKU_MAX) {
    errors.sku = `At most ${SKU_MAX} characters`
  }
  const stock = draft.stock.trim()
  if (stock && !/^\d{1,9}$/.test(stock)) {
    errors.stock = "A whole number, 0 or more"
  }
  for (const c of currencies) {
    const text = draft.prices[c.code]?.trim() ?? ""
    if (!text) continue
    const parsed = parseMoney(text, c.exponent)
    if (!parsed.ok) errors[`price:${c.code}`] = parsed.error
  }
  return errors
}
