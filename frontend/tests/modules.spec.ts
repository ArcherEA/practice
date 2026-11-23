import { expect, test } from "@playwright/test"

test("Items is in the sidebar and /items works with the default config", async ({
  page,
}) => {
  await page.goto("/")
  await expect(page.getByRole("link", { name: "Items" })).toBeVisible()
  await page.goto("/items")
  await expect(page.getByRole("heading", { name: "Items" })).toBeVisible()
})

test.describe("Items module disabled", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/v1/utils/config", (route) =>
      route.fulfill({
        json: { project_name: "Test", modules: [] },
      }),
    )
  })

  test("Items link is hidden in the sidebar", async ({ page }) => {
    await page.goto("/")
    await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible()
    await expect(page.getByRole("link", { name: "Items" })).toHaveCount(0)
  })

  test("/items shows the not found page", async ({ page }) => {
    await page.goto("/items")
    await expect(page.getByText("404")).toBeVisible()
    await expect(page.getByRole("heading", { name: "Items" })).toHaveCount(0)
  })
})
