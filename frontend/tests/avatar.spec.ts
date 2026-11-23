import { expect, test } from "@playwright/test"
import { createUser } from "./utils/privateApi.ts"
import { randomEmail, randomPassword } from "./utils/random"
import { logInUser } from "./utils/user"

// A valid 1x1 PNG (69 bytes), generated here so no binary fixture is committed.
const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC",
  "base64",
)

test.describe("Profile picture", () => {
  test.use({ storageState: { cookies: [], origins: [] } })
  let email: string
  let password: string

  test.beforeEach(async ({ page }) => {
    // A fresh user per test, so tests do not affect each other.
    email = randomEmail()
    password = randomPassword()
    await createUser({ email, password })
    await logInUser(page, email, password)
    await page.goto("/settings")
    await expect(page.getByTestId("avatar-section")).toBeVisible()
  })

  test("Upload, reload and remove an avatar", async ({ page }) => {
    const settingsImage = page.getByTestId("settings-avatar-image")
    const sidebarImage = page.getByTestId("sidebar-avatar-image")
    await expect(settingsImage).toHaveCount(0)
    await expect(sidebarImage).toHaveCount(0)

    await page.getByTestId("avatar-upload-input").setInputFiles({
      name: "avatar.png",
      mimeType: "image/png",
      buffer: TINY_PNG,
    })

    await expect(page.getByText("Profile picture updated")).toBeVisible()
    await expect(settingsImage).toBeVisible()
    await expect(sidebarImage).toBeVisible()

    await page.reload()
    await expect(settingsImage).toBeVisible()
    await expect(sidebarImage).toBeVisible()

    await page.getByRole("button", { name: "Remove" }).click()
    await expect(page.getByText("Profile picture removed")).toBeVisible()
    await expect(settingsImage).toHaveCount(0)
    await expect(sidebarImage).toHaveCount(0)
    await expect(page.getByRole("button", { name: "Remove" })).toHaveCount(0)
  })

  test("Rejects a non-image file as avatar", async ({ page }) => {
    let apiCalled = false
    page.on("request", (req) => {
      if (req.url().includes("/api/v1/files")) apiCalled = true
    })

    await page.getByTestId("avatar-upload-input").setInputFiles({
      name: "notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("hello"),
    })

    await expect(
      page.getByText("Please choose a JPEG, PNG, WebP or GIF image."),
    ).toBeVisible()
    await expect(page.getByTestId("settings-avatar-image")).toHaveCount(0)
    expect(apiCalled).toBe(false)
  })

  test("Rejects a file larger than 10 MB", async ({ page }) => {
    let apiCalled = false
    page.on("request", (req) => {
      if (req.url().includes("/api/v1/files")) apiCalled = true
    })

    await page.getByTestId("avatar-upload-input").setInputFiles({
      name: "huge.png",
      mimeType: "image/png",
      buffer: Buffer.alloc(10 * 1024 * 1024 + 1),
    })

    await expect(
      page.getByText("This file is too large. The maximum size is 10 MB."),
    ).toBeVisible()
    expect(apiCalled).toBe(false)
  })
})
