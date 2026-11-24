import { expect, type Page, test } from "@playwright/test"
import {
  formatMoney,
  moneyExample,
  parseMoney,
} from "../src/features/commerce/money"
import { createUserWithRole } from "./utils/privateApi.ts"
import { randomEmail, randomPassword } from "./utils/random"
import { logInUser } from "./utils/user"

interface StoreConfig {
  currencies: { code: string; exponent: number }[]
  default_currency: string
  timezone: string
}

const api = () => `${process.env.VITE_API_URL}/api/v1`

async function storeConfig(): Promise<StoreConfig> {
  const res = await fetch(`${api()}/commerce/config`)
  expect(res.ok, "the commerce module must be enabled (MODULES)").toBe(true)
  return (await res.json()) as StoreConfig
}

const randomName = (prefix: string) =>
  `${prefix} ${Math.random().toString(36).substring(2, 8)}`

/** Opens the "New product" dialog, picks the type and creates the product; lands on its editor. */
async function createProduct(
  page: Page,
  type: "physical" | "digital" | "service",
  title: string,
) {
  await page.goto("/store/products")
  await page.getByRole("button", { name: "New product" }).click()
  await page.getByTestId(`product-type-${type}`).click()
  await page.getByRole("textbox", { name: "Title" }).fill(title)
  await page.getByRole("button", { name: "Create product" }).click()
  await expect(page).toHaveURL(/\/store\/products\/[0-9a-f-]{36}$/)
  await expect(
    page.getByRole("heading", { name: "Edit product" }),
  ).toBeVisible()
}

/** Types a normal price (`12.50`, or `1500` for zero-decimal currencies) for each currency. */
async function fillPrices(
  page: Page,
  variant: string,
  currencies: StoreConfig["currencies"],
) {
  for (const c of currencies) {
    await page
      .getByLabel(`Price ${c.code.toUpperCase()} of ${variant}`, {
        exact: true,
      })
      .fill(moneyExample(c.exponent))
  }
}

const gridRows = (page: Page) =>
  page.getByTestId("variant-grid").locator("tbody tr")

test.describe("Money conversion", () => {
  // Same rules as backend money.py: the exponent comes from the store config.
  test("typed amounts become minor units exactly", () => {
    expect(parseMoney("12.50", 2)).toEqual({ ok: true, amount: 1250 })
    expect(parseMoney("12,5", 2)).toEqual({ ok: true, amount: 1250 })
    expect(parseMoney("0.10", 2)).toEqual({ ok: true, amount: 10 })
    expect(parseMoney("1.005", 3)).toEqual({ ok: true, amount: 1005 })
    expect(parseMoney("1500", 0)).toEqual({ ok: true, amount: 1500 })
    expect(parseMoney("19", 2)).toEqual({ ok: true, amount: 1900 })
  })

  test("invalid amounts are refused, never rounded", () => {
    expect(parseMoney("12.555", 2).ok).toBe(false)
    expect(parseMoney("12.5", 0).ok).toBe(false)
    expect(parseMoney("1500.00", 0).ok).toBe(false)
    expect(parseMoney("abc", 2).ok).toBe(false)
    expect(parseMoney("0", 2).ok).toBe(false)
    expect(parseMoney("-5", 2).ok).toBe(false)
    expect(parseMoney("1000000", 2).ok).toBe(false) // above 99,999,999 minor units
    expect(parseMoney("99999999", 0)).toEqual({ ok: true, amount: 99999999 })
  })

  test("minor units are shown as normal money", () => {
    expect(formatMoney(1250, 2)).toBe("12.50")
    expect(formatMoney(5, 2)).toBe("0.05")
    expect(formatMoney(1500, 0)).toBe("1500")
    expect(formatMoney(1005, 3)).toBe("1.005")
    expect(formatMoney(7, 3)).toBe("0.007")
  })
})

test.describe("Store admin", () => {
  test("Physical product: Size x Color variants, two currencies, published", async ({
    page,
  }) => {
    const config = await storeConfig()
    expect(
      config.currencies.length,
      "set STORE_CURRENCIES to at least two currencies",
    ).toBeGreaterThanOrEqual(2)
    const currencies = config.currencies.slice(0, 2)
    const title = randomName("Tee")

    await page.goto("/")
    await expect(page.getByRole("link", { name: "Store" })).toBeVisible()
    await createProduct(page, "physical", title)

    // An API validation error (422) shows on the right field.
    await page.getByRole("button", { name: "Add option" }).click()
    await page.getByLabel("Option 1 name").fill("Size")
    await page.getByLabel("Option 1 values").fill("S, s")
    await page.getByRole("button", { name: "Save options" }).click()
    await expect(page.getByText("values must be unique")).toBeVisible()

    await page.getByLabel("Option 1 values").fill("S, M")
    await page.getByRole("button", { name: "Add option" }).click()
    await page.getByLabel("Option 2 name").fill("Color")
    await page.getByLabel("Option 2 values").fill("Red, Blue")
    await page.getByRole("button", { name: "Save options" }).click()
    await expect(page.getByText("Options saved")).toBeVisible()

    await page.getByRole("button", { name: "Generate 4 variants" }).click()
    await expect(gridRows(page)).toHaveCount(4)
    for (const label of ["S / Red", "S / Blue", "M / Red", "M / Blue"]) {
      await expect(page.getByLabel(`SKU of ${label}`)).toBeVisible()
    }

    // Not sellable yet: the reasons are listed.
    await page.getByRole("button", { name: "Publish" }).click()
    await expect(page.getByTestId("publish-issues")).toContainText(
      "has no price",
    )

    // A wrong price is shown at its field and nothing is saved.
    await fillPrices(page, "S / Red", currencies)
    await page
      .getByLabel(`Price ${currencies[0].code.toUpperCase()} of S / Red`, {
        exact: true,
      })
      .fill("12.555")
    await page.getByRole("button", { name: "Save variants" }).click()
    await expect(page.getByText("At most 2 decimal places")).toBeVisible()
    await page
      .getByLabel(`Price ${currencies[0].code.toUpperCase()} of S / Red`, {
        exact: true,
      })
      .fill(moneyExample(currencies[0].exponent))

    for (const label of ["S / Red", "S / Blue", "M / Red", "M / Blue"]) {
      await fillPrices(page, label, currencies)
      await page.getByLabel(`Stock of ${label}`).fill("5")
    }
    await page.getByRole("button", { name: "Save variants" }).click()
    await expect(page.getByText("Variants saved")).toBeVisible()

    // Prices came back as normal money, per currency.
    await page.reload()
    await expect(gridRows(page)).toHaveCount(4)
    for (const c of currencies) {
      await expect(
        page.getByLabel(`Price ${c.code.toUpperCase()} of M / Blue`, {
          exact: true,
        }),
      ).toHaveValue(moneyExample(c.exponent))
    }

    await page.getByRole("button", { name: "Publish" }).click()
    await expect(page.getByText("Product published")).toBeVisible()
    await expect(page.getByRole("button", { name: "Unpublish" })).toBeVisible()

    // The list shows it as published.
    await page.goto("/store/products")
    await page.getByLabel("Search by title").fill(title)
    const row = page.getByRole("row").filter({ hasText: title })
    await expect(row).toContainText("Published")
    await expect(row).toContainText("Physical")
  })

  test("Digital product: private file per variant, replaced, published", async ({
    page,
  }) => {
    const config = await storeConfig()
    const currencies = config.currencies.slice(0, 1)
    const title = randomName("Guide")
    await createProduct(page, "digital", title)

    await page.getByRole("button", { name: "Add the default variant" }).click()
    await expect(gridRows(page)).toHaveCount(1)
    await fillPrices(page, "Default", currencies)

    // Not sellable without a file.
    await page.getByRole("button", { name: "Save variants" }).click()
    await expect(page.getByText("Variants saved")).toBeVisible()
    await page.getByRole("button", { name: "Publish" }).click()
    await expect(page.getByTestId("publish-issues")).toContainText(
      "has no file",
    )

    const first = `guide-${Math.random().toString(36).substring(2, 8)}.pdf`
    const fileInput = page
      .getByTestId("variant-grid")
      .locator('input[type="file"]')
    await fileInput.setInputFiles({
      name: first,
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4 ".repeat(100)),
    })
    const fileName = page.getByTestId(/^variant-file-name-/)
    await expect(fileName).toContainText(first)
    await expect(fileName).toContainText("(900 B)")

    // Replace it.
    const second = `guide-v2-${Math.random().toString(36).substring(2, 8)}.pdf`
    await fileInput.setInputFiles({
      name: second,
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4 ".repeat(300)),
    })
    await expect(fileName).toContainText(second)
    await expect(fileName).toContainText("(2.6 KB)")

    await page.getByRole("button", { name: "Publish" }).click()
    await expect(page.getByText("Product published")).toBeVisible()
  })

  test("Service product: slots in the store timezone, weekly repeat, deactivate", async ({
    page,
  }) => {
    const config = await storeConfig()
    const title = randomName("Consult")
    await createProduct(page, "service", title)

    await page.getByRole("button", { name: "Add the default variant" }).click()
    await expect(gridRows(page)).toHaveCount(1)
    await fillPrices(page, "Default", config.currencies.slice(0, 1))
    await page.getByRole("button", { name: "Save variants" }).click()
    await expect(page.getByText("Variants saved")).toBeVisible()

    await expect(page.getByTestId("store-timezone")).toHaveText(config.timezone)

    // Three days from now, counted in the store's calendar.
    const todayInStore = new Intl.DateTimeFormat("en-CA", {
      timeZone: config.timezone,
    }).format(new Date())
    const [y, m, d] = todayInStore.split("-").map(Number)
    const plusDays = (n: number) =>
      new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10)

    await page.getByLabel("Date", { exact: true }).fill(plusDays(3))
    await page.getByLabel(/^Start/).fill("10:00")
    await page.getByLabel(/^End/).fill("11:00")
    await page.getByLabel("Capacity", { exact: true }).fill("4")
    await page.getByRole("button", { name: "Add slot" }).click()
    const slots = page.getByTestId("slot-row")
    await expect(slots).toHaveCount(1)
    // Shown as typed (store wall time), whatever the browser's timezone is.
    await expect(slots.first()).toContainText("10:00 - 11:00")

    // An end before the start is refused at the field.
    await page.getByLabel(/^End/).fill("09:00")
    await page.getByRole("button", { name: "Add slot" }).click()
    await expect(
      page.getByText("The end must be after the start"),
    ).toBeVisible()
    await page.getByLabel(/^End/).fill("11:00")

    // Every weekday at 10:00 for 2 weeks: 14 consecutive days hold exactly 10 weekdays.
    await page.getByRole("button", { name: "Weekly repeat" }).click()
    await page.getByLabel("First date").fill(plusDays(4))
    await page.getByLabel("For how many weeks").fill("2")
    await page.getByRole("button", { name: "Add slots" }).click()
    await expect(page.getByTestId("slots-result")).toContainText(
      "10 slots created",
    )
    await expect(slots).toHaveCount(11)

    // Running the same repeat again skips the existing slots.
    await page.getByRole("button", { name: "Add slots" }).click()
    await expect(page.getByTestId("slots-result")).toContainText(
      "0 slots created, 10 skipped (already exist)",
    )
    await expect(slots).toHaveCount(11)

    await slots.first().getByRole("button", { name: "Deactivate" }).click()
    await expect(slots.first()).toContainText("Deactivated")
    await expect(
      slots.first().getByRole("button", { name: "Activate" }),
    ).toBeVisible()

    await page.getByRole("button", { name: "Publish" }).click()
    await expect(page.getByText("Product published")).toBeVisible()
  })

  test("Categories: create, edit, order, delete", async ({ page }) => {
    const first = randomName("Shirts")
    const second = randomName("Mugs")
    await page.goto("/store/categories")
    await expect(page.getByRole("heading", { name: "Store" })).toBeVisible()

    for (const name of [first, second]) {
      await page.getByRole("button", { name: "New category" }).click()
      await page.getByRole("textbox", { name: "Name" }).fill(name)
      await page.getByRole("button", { name: "Save" }).click()
      await expect(page.getByRole("cell", { name, exact: true })).toBeVisible()
    }

    // A wrong value is reported at its field.
    await page.getByRole("button", { name: "New category" }).click()
    await page.getByRole("textbox", { name: "Name" }).fill("Position test")
    await page.getByRole("textbox", { name: "Position" }).fill("abc")
    await page.getByRole("button", { name: "Save" }).click()
    await expect(page.getByText("Use a whole number")).toBeVisible()
    await page.getByRole("button", { name: "Cancel" }).click()

    // Edit.
    const renamed = `${first} 2`
    await page.getByRole("button", { name: `Edit ${first}` }).click()
    await page.getByRole("textbox", { name: "Name" }).fill(renamed)
    await page.getByRole("button", { name: "Save" }).click()
    await expect(
      page.getByRole("cell", { name: renamed, exact: true }),
    ).toBeVisible()

    // Order: move the second one up above the first.
    const names = () =>
      page.getByRole("row").filter({ has: page.getByRole("cell") })
    const before = await names().allInnerTexts()
    const iRenamed = before.findIndex((t) => t.includes(renamed))
    const iSecond = before.findIndex((t) => t.includes(second))
    expect(iSecond).toBeGreaterThan(iRenamed)
    await page.getByRole("button", { name: `Move ${second} up` }).click()
    await expect
      .poll(async () => {
        const after = await names().allInnerTexts()
        return (
          after.findIndex((t) => t.includes(second)) <
          after.findIndex((t) => t.includes(renamed))
        )
      })
      .toBe(true)

    // Delete both.
    for (const name of [renamed, second]) {
      await page.getByRole("button", { name: `Delete ${name}` }).click()
      await page.getByRole("button", { name: "Delete", exact: true }).click()
      await expect(page.getByRole("cell", { name, exact: true })).toHaveCount(0)
    }
  })
})

test.describe("Store admin access", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("A member sees no Store link and cannot open the store admin", async ({
    page,
  }) => {
    const email = randomEmail()
    const password = randomPassword()
    await createUserWithRole({ email, password, role: "member" })
    await logInUser(page, email, password)

    await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible()
    await expect(page.getByRole("link", { name: "Store" })).toHaveCount(0)

    for (const path of [
      "/store/products",
      "/store/categories",
      "/store/products/new",
    ]) {
      await page.goto(path)
      await expect(page).toHaveURL("/")
      await expect(page.getByRole("heading", { name: "Store" })).toHaveCount(0)
    }

    // The API refuses too.
    const token = await page.evaluate(() =>
      localStorage.getItem("access_token"),
    )
    const res = await page.request.get(`${api()}/commerce/admin/products`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(res.status()).toBe(403)
  })
})
