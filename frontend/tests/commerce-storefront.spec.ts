import { expect, type Page, test } from "@playwright/test"
import { formatMoney } from "../src/features/commerce/money"
import { createUserWithRole } from "./utils/privateApi.ts"
import { randomEmail, randomPassword } from "./utils/random"

// The storefront is public: no login.
test.use({ storageState: { cookies: [], origins: [] } })

interface StoreConfig {
  currencies: { code: string; exponent: number }[]
  default_currency: string
  timezone: string
}

interface Created {
  id: string
  slug: string
}

const base = () => `${process.env.VITE_API_URL}/api/v1`
const unique = () => Math.random().toString(36).substring(2, 9)

async function storeConfig(): Promise<StoreConfig> {
  const res = await fetch(`${base()}/commerce/config`)
  expect(res.ok, "the commerce module must be enabled (MODULES)").toBe(true)
  return (await res.json()) as StoreConfig
}

/** Two currencies of the store: its default and another one (CI uses usd,eur). */
async function twoCurrencies() {
  const config = await storeConfig()
  const first = config.currencies.find(
    (c) => c.code === config.default_currency,
  )
  const second = config.currencies.find(
    (c) => c.code !== config.default_currency,
  )
  if (!first || !second) {
    throw new Error("Set STORE_CURRENCIES to at least two codes, e.g. usd,eur")
  }
  return { config, first, second }
}

const cleanups: (() => Promise<unknown>)[] = []

test.afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) {
    await cleanup().catch(() => undefined)
  }
})

/** Creates an admin user (own data, no shared state) and returns an API caller. */
async function createAdminApi() {
  const email = randomEmail()
  const password = randomPassword()
  await createUserWithRole({ email, password, role: "admin" })
  const login = await fetch(`${base()}/login/access-token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: email, password }),
  })
  const { access_token } = await login.json()

  const call = async <T>(method: string, path: string, body?: unknown) => {
    const res = await fetch(`${base()}/commerce/admin${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${access_token}`,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    if (!res.ok) {
      throw new Error(
        `${method} ${path} failed: ${res.status} ${await res.text()}`,
      )
    }
    return (await res.json()) as T
  }

  return {
    async category(name: string) {
      const category = await call<Created>("POST", "/categories", { name })
      // Categories are shared admin data: remove ours so the store admin specs
      // (which renumber the whole category list) do not slow down over time.
      cleanups.push(() => call("DELETE", `/categories/${category.id}`))
      return category
    },
    product: (body: Record<string, unknown>) =>
      call<Created>("POST", "/products", body),
    option: (productId: string, name: string, values: string[]) =>
      call<{ id: string }>("POST", `/products/${productId}/options`, {
        name,
        values,
      }),
    variant: (productId: string, body: Record<string, unknown>) =>
      call<Created>("POST", `/products/${productId}/variants`, body),
    updateVariant: (variantId: string, body: Record<string, unknown>) =>
      call("PATCH", `/variants/${variantId}`, body),
    setPrice: (variantId: string, currency: string, amount: number) =>
      call("PUT", `/variants/${variantId}/prices/${currency}`, { amount }),
    slot: (productId: string, startsAt: Date, capacity: number) =>
      call<Created>("POST", `/products/${productId}/slots`, {
        starts_at: startsAt.toISOString(),
        ends_at: new Date(startsAt.getTime() + 3_600_000).toISOString(),
        capacity,
      }),
    publish: (productId: string) =>
      call("POST", `/products/${productId}/publish`),
    unpublish: (productId: string) =>
      call("POST", `/products/${productId}/unpublish`),
  }
}

type AdminApi = Awaited<ReturnType<typeof createAdminApi>>

const money = (amount: number, c: { code: string; exponent: number }) =>
  `${formatMoney(amount, c.exponent)} ${c.code.toUpperCase()}`

/** A published T-shirt: S (5 in stock), M (5) and XL (sold out), a price in two currencies each. */
async function createShirt(
  api: AdminApi,
  title: string,
  currencies: { first: { code: string }; second: { code: string } },
  categoryId?: string,
) {
  const { first, second } = currencies
  const product = await api.product({
    type: "physical",
    title,
    category_id: categoryId,
  })
  await api.option(product.id, "Size", ["S", "M", "XL"])
  const sku = unique().toUpperCase()
  const prices = (usd: number, other: number) => ({
    [first.code]: usd,
    [second.code]: other,
  })
  const s = await api.variant(product.id, {
    sku: `S-${sku}`,
    option_values: { Size: "S" },
    stock: 20,
    prices: prices(1999, 1799),
  })
  const m = await api.variant(product.id, {
    sku: `M-${sku}`,
    option_values: { Size: "M" },
    stock: 20,
    prices: prices(2499, 2299),
  })
  const xl = await api.variant(product.id, {
    sku: `XL-${sku}`,
    option_values: { Size: "XL" },
    stock: 0,
    prices: prices(2999, 2799),
  })
  await api.publish(product.id)
  return { product, s, m, xl }
}

/** Picks an option value or a time slot (visually hidden radio inside a label). */
const choose = (page: Page, text: string | RegExp) =>
  page
    .locator("label")
    .filter({
      hasText: typeof text === "string" ? new RegExp(`^${text}$`) : text,
    })
    .click()

const priceText = (page: Page) => page.getByTestId("product-price")

test.describe("Storefront", () => {
  test("browse by category, pick a variant, switch currency, add to cart", async ({
    page,
  }) => {
    const currencies = await twoCurrencies()
    const { first, second } = currencies
    const api = await createAdminApi()
    const id = unique()
    const categoryName = `Shirts ${id}`
    const category = await api.category(categoryName)
    const title = `Shirt ${id}`
    await createShirt(api, title, currencies, category.id)
    const other = await api.product({
      type: "physical",
      title: `Other ${id}`,
    })
    const otherVariant = await api.variant(other.id, {
      sku: `O-${id.toUpperCase()}`,
      stock: 3,
      prices: { [first.code]: 500 },
    })
    expect(otherVariant.id).toBeTruthy()
    await api.publish(other.id)

    // The shop lists the product; the category page only the category's products.
    await page.goto("/shop")
    await expect(page.getByRole("heading", { name: "Shop" })).toBeVisible()
    await expect(
      page.getByRole("link", { name: "Shop", exact: true }),
    ).toBeVisible()
    await page
      .getByRole("navigation", { name: "Categories" })
      .getByRole("link", { name: categoryName })
      .click()
    await expect(page).toHaveURL(new RegExp(`/shop/category/${category.slug}$`))
    await expect(page.getByTestId("product-card")).toHaveCount(1)
    await expect(page.getByTestId("product-card")).toContainText(title)
    await expect(page.getByTestId("product-card")).toContainText(
      `From ${money(1999, first)}`,
    )

    // Product page: the first buyable variant (S) is selected.
    await page.getByTestId("product-card").click()
    await expect(
      page.getByRole("heading", { level: 1, name: title }),
    ).toBeVisible()
    await expect(priceText(page)).toHaveText(money(1999, first))
    await expect(page.getByTestId("availability")).toHaveText("In stock")

    // Another size resolves to another variant and price.
    await choose(page, "M")
    await expect(priceText(page)).toHaveText(money(2499, first))

    // A sold-out size shows why and cannot be added.
    await choose(page, "XL")
    await expect(page.getByTestId("availability")).toHaveText("Out of stock.")
    await expect(
      page.getByRole("button", { name: "Add to cart" }),
    ).toBeDisabled()

    // The currency switcher changes the price (the API sends it; no browser conversion).
    await choose(page, "M")
    await page.getByTestId("currency-switcher").click()
    await page.getByRole("option", { name: second.code.toUpperCase() }).click()
    await expect(priceText(page)).toHaveText(money(2299, second))
    await expect(page.getByTestId("currency-switcher")).toContainText(
      second.code.toUpperCase(),
    )

    // Add two to the cart.
    await page.getByLabel("Quantity").fill("2")
    await page.getByRole("button", { name: "Add to cart" }).click()
    await expect(page.getByTestId("added-to-cart")).toBeVisible()
    await expect(page.getByTestId("cart-count")).toHaveText("2")
  })

  test("the cart survives a reload and shows line totals", async ({ page }) => {
    const currencies = await twoCurrencies()
    const { first } = currencies
    const api = await createAdminApi()
    const title = `Cart shirt ${unique()}`
    const { product } = await createShirt(api, title, currencies)

    await page.goto(`/shop/${product.slug}`)
    await expect(priceText(page)).toHaveText(money(1999, first))
    await page.getByLabel("Quantity").fill("3")
    await page.getByRole("button", { name: "Add to cart" }).click()
    await expect(page.getByTestId("cart-count")).toHaveText("3")

    // Adding the same variant again merges the lines.
    await page.getByLabel("Quantity").fill("1")
    await page.getByRole("button", { name: "Add to cart" }).click()
    await expect(page.getByTestId("cart-count")).toHaveText("4")

    await page.reload()
    await expect(page.getByTestId("cart-count")).toHaveText("4")
    await page.getByTestId("cart-link").click()
    await expect(page).toHaveURL(/\/shop\/cart$/)

    const line = page.getByTestId("cart-line")
    await expect(line).toHaveCount(1)
    await expect(line).toContainText(title)
    await expect(line.getByTestId("line-total")).toHaveText(
      money(1999 * 4, first),
    )
    await expect(page.getByTestId("cart-total")).toHaveText(
      `Total ${money(1999 * 4, first)}`,
    )
    await expect(
      page.getByRole("button", { name: "Checkout coming soon" }),
    ).toBeDisabled()

    // Change the quantity and remove the line.
    await line.getByRole("spinbutton").fill("2")
    await expect(line.getByTestId("line-total")).toHaveText(
      money(1999 * 2, first),
    )
    await page.reload()
    await expect(page.getByTestId("cart-count")).toHaveText("2")
    await page.getByRole("button", { name: `Remove ${title}` }).click()
    await expect(page.getByTestId("cart-empty")).toBeVisible()
    await expect(page.getByTestId("cart-count")).toHaveText("0")
  })

  test("the cart flags a changed price, a sold-out variant and a removed product", async ({
    page,
  }) => {
    const currencies = await twoCurrencies()
    const { first } = currencies
    const api = await createAdminApi()
    const title = `Flag shirt ${unique()}`
    const { product, s } = await createShirt(api, title, currencies)

    await page.goto(`/shop/${product.slug}`)
    await page.getByRole("button", { name: "Add to cart" }).click()
    await expect(page.getByTestId("cart-count")).toHaveText("1")

    // Price goes up after the visitor added the item.
    await api.setPrice(s.id, first.code, 2099)
    await page.goto("/shop/cart")
    const line = page.getByTestId("cart-line")
    await expect(line).toContainText("Price changed")
    await expect(line).toContainText(
      `Was ${money(1999, first)}, now ${money(2099, first)}`,
    )
    await expect(page.getByTestId("cart-total")).toHaveText(
      `Total ${money(2099, first)}`,
    )
    await page.getByRole("button", { name: "Accept new price" }).click()
    await expect(line).not.toContainText("Price changed")

    // The variant sells out.
    await api.updateVariant(s.id, { stock: 0 })
    await page.reload()
    await expect(line).toContainText("Unavailable")
    await expect(line).toContainText("Out of stock.")
    await expect(page.getByTestId("cart-total")).toHaveText(
      `Total ${money(0, first)}`,
    )

    // The product is taken off the shop.
    await api.unpublish(product.id)
    await page.reload()
    await expect(line).toContainText("This product is no longer available.")
  })

  test("quantity above the stock is flagged in the cart", async ({ page }) => {
    const currencies = await twoCurrencies()
    const api = await createAdminApi()
    const { product, s } = await createShirt(
      api,
      `Limited ${unique()}`,
      currencies,
    )
    await page.goto(`/shop/${product.slug}`)
    await page.getByLabel("Quantity").fill("4")
    await page.getByRole("button", { name: "Add to cart" }).click()
    await expect(page.getByTestId("cart-count")).toHaveText("4")

    await api.updateVariant(s.id, { stock: 2 })
    await page.goto("/shop/cart")
    await expect(page.getByTestId("cart-line")).toContainText(
      "Only 2 available",
    )
  })

  test("a service shows slots in store time and local time", async ({
    page,
  }) => {
    const currencies = await twoCurrencies()
    const { first, config } = currencies
    const api = await createAdminApi()
    const title = `Lesson ${unique()}`
    const product = await api.product({ type: "service", title })
    await api.variant(product.id, {
      sku: `SVC-${unique().toUpperCase()}`,
      prices: { [first.code]: 4500 },
    })
    const start = new Date(Date.now() + 72 * 3_600_000)
    start.setUTCMinutes(0, 0, 0)
    await api.slot(product.id, start, 4)
    await api.publish(product.id)

    await page.goto(`/shop/${product.slug}`)
    await expect(priceText(page)).toHaveText(money(4500, first))
    const slots = page.getByTestId("slot-list")
    await expect(slots).toContainText("(store time)")
    await expect(slots).toContainText("(your time)")
    await expect(
      page.getByText(`Store time is ${config.timezone}`),
    ).toBeVisible()
    await expect(slots).toContainText("4 places")

    // A time must be chosen first.
    await expect(
      page.getByRole("button", { name: "Add to cart" }),
    ).toBeDisabled()
    await choose(page, /\(store time\)/)
    await page.getByRole("button", { name: "Add to cart" }).click()
    await expect(page.getByTestId("cart-count")).toHaveText("1")

    await page.goto("/shop/cart")
    const line = page.getByTestId("cart-line")
    await expect(line).toContainText(title)
    await expect(line).toContainText("(store time)")
    await expect(line).toContainText("(your time)")
    await expect(line.getByTestId("line-total")).toHaveText(money(4500, first))
  })

  test("a long category is paged", async ({ page }) => {
    const currencies = await twoCurrencies()
    const { first } = currencies
    const api = await createAdminApi()
    const category = await api.category(`Paged ${unique()}`)
    await Promise.all(
      Array.from({ length: 13 }, async (_, i) => {
        const product = await api.product({
          type: "physical",
          title: `Paged item ${i} ${unique()}`,
          category_id: category.id,
        })
        await api.variant(product.id, {
          sku: `PG-${unique().toUpperCase()}`,
          stock: 1,
          prices: { [first.code]: 100 + i },
        })
        await api.publish(product.id)
      }),
    )

    await page.goto(`/shop/category/${category.slug}`)
    await expect(page.getByTestId("product-card")).toHaveCount(12)
    await expect(page.getByText("Page 1 of 2")).toBeVisible()
    await page.getByRole("link", { name: "Next" }).click()
    await expect(page).toHaveURL(/page=2/)
    await expect(page.getByText("Page 2 of 2")).toBeVisible()
    await expect(page.getByTestId("product-card")).toHaveCount(1)
  })

  test("an unknown product shows the not found page", async ({ page }) => {
    await page.goto(`/shop/does-not-exist-${unique()}`)
    await expect(page.getByTestId("not-found")).toBeVisible()
  })

  test("the shop works when localStorage is blocked", async ({ page }) => {
    const currencies = await twoCurrencies()
    const { first } = currencies
    const api = await createAdminApi()
    const title = `Blocked ${unique()}`
    const { product } = await createShirt(api, title, currencies)
    // The shop's own keys fail like a blocked storage; the rest of the app is untouched.
    await page.addInitScript(() => {
      for (const method of ["getItem", "setItem"] as const) {
        const original = Storage.prototype[method]
        Storage.prototype[method] = function (
          this: Storage,
          key: string,
          value: string,
        ) {
          if (key.startsWith("shop.")) {
            throw new DOMException("blocked", "SecurityError")
          }
          return original.call(this, key, value)
        } as typeof original
      }
    })
    await page.goto(`/shop/${product.slug}`)
    await expect(priceText(page)).toHaveText(money(1999, first))
    await page.getByRole("button", { name: "Add to cart" }).click()
    // Kept in memory for this page view.
    await expect(page.getByTestId("cart-count")).toHaveText("1")
  })
})

test.describe("Currency from the browser language", () => {
  test.use({ locale: "de-DE" })

  test("a German browser starts in EUR and the choice is remembered", async ({
    page,
  }) => {
    const currencies = await twoCurrencies()
    const eur = [currencies.first, currencies.second].find(
      (c) => c.code === "eur",
    )
    const other = [currencies.first, currencies.second].find(
      (c) => c.code !== "eur",
    )
    test.skip(!eur || !other, "needs eur and one other store currency")
    if (!eur || !other) return

    const api = await createAdminApi()
    const { product } = await createShirt(api, `Locale ${unique()}`, currencies)
    const priceIn = (c: { code: string }) =>
      c.code === currencies.first.code ? 1999 : 1799

    await page.goto(`/shop/${product.slug}`)
    await expect(page.getByTestId("currency-switcher")).toContainText("EUR")
    await expect(priceText(page)).toHaveText(money(priceIn(eur), eur))

    await page.getByTestId("currency-switcher").click()
    await page.getByRole("option", { name: other.code.toUpperCase() }).click()
    await expect(priceText(page)).toHaveText(money(priceIn(other), other))

    await page.reload()
    await expect(page.getByTestId("currency-switcher")).toContainText(
      other.code.toUpperCase(),
    )
    await expect(priceText(page)).toHaveText(money(priceIn(other), other))
  })
})

test.describe("Modules", () => {
  const stubModules = (page: Page, modules: string[]) =>
    page.route("**/api/v1/utils/config", (route) =>
      route.fulfill({ json: { project_name: "Test", modules } }),
    )

  test("the shop works without the content module (no Blog link)", async ({
    page,
  }) => {
    await stubModules(page, ["commerce"])
    await page.goto("/shop")
    const nav = page.getByRole("navigation", { name: "Main" })
    await expect(page.getByRole("heading", { name: "Shop" })).toBeVisible()
    await expect(nav.getByRole("link", { name: "Shop" })).toBeVisible()
    await expect(nav.getByRole("link", { name: "Blog" })).toHaveCount(0)
    await page.goto("/blog")
    await expect(page.getByTestId("not-found")).toBeVisible()
  })

  test("with the commerce module off there is no shop and no Shop link", async ({
    page,
  }) => {
    await stubModules(page, ["content"])
    await page.goto("/blog")
    const nav = page.getByRole("navigation", { name: "Main" })
    await expect(nav.getByRole("link", { name: "Blog" })).toBeVisible()
    await expect(nav.getByRole("link", { name: "Shop" })).toHaveCount(0)
    await expect(page.getByTestId("cart-link")).toHaveCount(0)
    await page.goto("/shop")
    await expect(page.getByTestId("not-found")).toBeVisible()
  })
})
