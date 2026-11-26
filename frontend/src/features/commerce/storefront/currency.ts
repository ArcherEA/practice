import type { QueryClient } from "@tanstack/react-query"
import { useCallback } from "react"

import type { StoreConfig } from "@/client"
import { commerceKeys, fetchStoreConfig, useStoreConfig } from "../api"
import { formatMoney } from "../money"
import { createPersistedStore, usePersistedStore } from "./persisted"

export const CURRENCY_KEY = "shop.currency"

const storedCurrency = createPersistedStore<string | null>(
  CURRENCY_KEY,
  (raw) => (typeof raw === "string" ? raw : null),
  null,
)

/**
 * Country (from the browser language, e.g. `de-DE` -> `DE`) to its usual currency.
 * There is no browser API for this, so it is a short table of common regions; a
 * region that is missing, or whose currency the store does not sell in, simply falls
 * back to the store's default currency.
 */
const EUR = [
  "AT",
  "BE",
  "CY",
  "DE",
  "EE",
  "ES",
  "FI",
  "FR",
  "GR",
  "HR",
  "IE",
  "IT",
  "LT",
  "LU",
  "LV",
  "MT",
  "NL",
  "PT",
  "SI",
  "SK",
]
const REGION_CURRENCY: Record<string, string> = {
  ...Object.fromEntries(EUR.map((r) => [r, "eur"])),
  US: "usd",
  GB: "gbp",
  JP: "jpy",
  CA: "cad",
  AU: "aud",
  NZ: "nzd",
  CH: "chf",
  SE: "sek",
  NO: "nok",
  DK: "dkk",
  PL: "pln",
  CZ: "czk",
  HU: "huf",
  RO: "ron",
  BG: "bgn",
  CN: "cny",
  HK: "hkd",
  SG: "sgd",
  KR: "krw",
  IN: "inr",
  BR: "brl",
  MX: "mxn",
  ZA: "zar",
  TR: "try",
  AE: "aed",
  IL: "ils",
}

/** Region of a BCP 47 tag; `en` alone is completed to its likely region (`US`). */
function regionOf(locale: string): string | undefined {
  try {
    const parsed = new Intl.Locale(locale)
    return parsed.region ?? parsed.maximize().region
  } catch {
    return undefined
  }
}

/** The allowed currency for the visitor's languages, if any. */
export function currencyForLocales(
  locales: readonly string[],
  allowed: readonly string[],
): string | undefined {
  for (const locale of locales) {
    const region = regionOf(locale)
    const code = region ? REGION_CURRENCY[region] : undefined
    if (code && allowed.includes(code)) return code
  }
  return undefined
}

const browserLocales = (): readonly string[] =>
  typeof navigator === "undefined"
    ? []
    : navigator.languages?.length
      ? navigator.languages
      : [navigator.language]

/** Remembered choice, else the browser locale's currency, else the store default. */
export function resolveCurrency(
  config: StoreConfig,
  stored: string | null,
  locales: readonly string[] = browserLocales(),
): string {
  const allowed = config.currencies.map((c) => c.code)
  if (stored && allowed.includes(stored)) return stored
  return currencyForLocales(locales, allowed) ?? config.default_currency
}

/** For route loaders (no hooks): the currency the page will use. */
export async function currentCurrency(
  queryClient: QueryClient,
): Promise<string> {
  const config = await queryClient.ensureQueryData({
    queryKey: commerceKeys.config,
    queryFn: fetchStoreConfig,
    staleTime: Number.POSITIVE_INFINITY,
  })
  return resolveCurrency(config, storedCurrency.get())
}

export interface CurrencyState {
  /** Undefined until the store config has loaded. */
  currency: string | undefined
  currencies: StoreConfig["currencies"]
  timezone: string
  setCurrency: (code: string) => void
  /** Minor units to text, using the current currency's exponent: `12.50 USD`. */
  format: (amount: number, currency?: string) => string
  isLoading: boolean
}

export function useCurrency(): CurrencyState {
  const { data: config, isLoading } = useStoreConfig()
  const stored = usePersistedStore(storedCurrency)
  const currency = config ? resolveCurrency(config, stored) : undefined
  const exponents = config?.currencies

  const format = useCallback(
    (amount: number, code?: string) => {
      const target = code ?? currency ?? ""
      const exponent = exponents?.find((c) => c.code === target)?.exponent ?? 2
      return `${formatMoney(amount, exponent)} ${target.toUpperCase()}`
    },
    [currency, exponents],
  )

  return {
    currency,
    currencies: exponents ?? [],
    timezone: config?.timezone ?? "UTC",
    setCurrency: storedCurrency.set,
    format,
    isLoading,
  }
}
