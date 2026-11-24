/**
 * Money helpers. Amounts are integer minor units (cents; yen for jpy).
 *
 * The number of decimals comes from the store config (`exponent`, sent by
 * `GET /commerce/config`, computed by backend `money.exponent`): 0 for zero-decimal
 * currencies such as jpy, 3 for kwd/bhd/..., else 2. The conversion works on text
 * only (no floating point), so `0.10` or `1.005` never pick up rounding errors.
 */

/** Stripe's upper limit for one amount in minor units (backend `MAX_AMOUNT`). */
export const MAX_AMOUNT = 99_999_999

export type MoneyParse =
  | { ok: true; amount: number }
  | { ok: false; error: string }

/** Minor units to the text shown in an input: `1250` + 2 -> `12.50`, `1500` + 0 -> `1500`. */
export function formatMoney(amount: number, exponent: number): string {
  const digits = String(Math.abs(Math.trunc(amount))).padStart(
    exponent + 1,
    "0",
  )
  const sign = amount < 0 ? "-" : ""
  if (exponent === 0) return `${sign}${digits}`
  return `${sign}${digits.slice(0, -exponent)}.${digits.slice(-exponent)}`
}

/** Same, with the currency code: `12.50 USD`. */
export function formatMoneyWithCode(
  amount: number,
  currency: string,
  exponent: number,
): string {
  return `${formatMoney(amount, exponent)} ${currency.toUpperCase()}`
}

/** Hint under a price input, e.g. `12.50` or `1500` for zero-decimal currencies. */
export function moneyExample(exponent: number): string {
  return exponent === 0 ? "1500" : `12.${"5".padEnd(exponent, "0")}`
}

/**
 * Text typed by an admin (`12.50`, `12,5`, `1500`) to minor units. Never rounds:
 * more decimals than the currency allows is an error, not a silent cut.
 */
export function parseMoney(text: string, exponent: number): MoneyParse {
  const value = text.trim()
  const pattern = exponent === 0 ? /^\d+$/ : /^(\d+)(?:[.,](\d+))?$/
  const match = pattern.exec(value)
  if (!match) {
    return {
      ok: false,
      error:
        exponent === 0
          ? "Enter a whole number, for example 1500 (this currency has no decimals)."
          : `Enter an amount like ${moneyExample(exponent)}.`,
    }
  }
  const whole = exponent === 0 ? value : match[1]
  const fraction = exponent === 0 ? "" : (match[2] ?? "")
  if (fraction.length > exponent) {
    return {
      ok: false,
      error: `At most ${exponent} decimal places for this currency.`,
    }
  }
  const amount = Number(`${whole}${fraction.padEnd(exponent, "0")}`)
  if (!Number.isSafeInteger(amount) || amount > MAX_AMOUNT) {
    return {
      ok: false,
      error: `The price is too high (at most ${formatMoney(MAX_AMOUNT, exponent)}).`,
    }
  }
  if (amount <= 0) {
    return { ok: false, error: "The price must be greater than 0." }
  }
  return { ok: true, amount }
}
