import { expect, test } from "@playwright/test"
import { firstSuperuser, firstSuperuserPassword } from "./config.ts"
import { createUser, createUserWithRole } from "./utils/privateApi"
import { randomEmail, randomPassword } from "./utils/random"
import { logInUser } from "./utils/user"

test("Admin page is accessible and shows correct title", async ({ page }) => {
  await page.goto("/admin")
  await expect(page.getByRole("heading", { name: "Users" })).toBeVisible()
  await expect(
    page.getByText("Manage user accounts and permissions"),
  ).toBeVisible()
})

test("Add User button is visible", async ({ page }) => {
  await page.goto("/admin")
  await expect(page.getByRole("button", { name: "Add User" })).toBeVisible()
})

test.describe("Admin user management", () => {
  test("Create a new user successfully", async ({ page }) => {
    await page.goto("/admin")

    const email = randomEmail()
    const password = randomPassword()
    const fullName = "Test User Admin"

    await page.getByRole("button", { name: "Add User" }).click()

    await page.getByPlaceholder("Email").fill(email)
    await page.getByPlaceholder("Full name").fill(fullName)
    await page.getByPlaceholder("Password").first().fill(password)
    await page.getByPlaceholder("Password").last().fill(password)

    await page.getByRole("button", { name: "Save" }).click()

    await expect(page.getByText("User created successfully")).toBeVisible()

    await expect(page.getByRole("dialog")).not.toBeVisible()

    const userRow = page.getByRole("row").filter({ hasText: email })
    await expect(userRow).toBeVisible()
  })

  test("Create a superuser", async ({ page }) => {
    await page.goto("/admin")

    const email = randomEmail()
    const password = randomPassword()

    await page.getByRole("button", { name: "Add User" }).click()

    await page.getByPlaceholder("Email").fill(email)
    await page.getByPlaceholder("Password").first().fill(password)
    await page.getByPlaceholder("Password").last().fill(password)
    await page.getByLabel("Is superuser?").check()
    await page.getByLabel("Is active?").check()

    await page.getByRole("button", { name: "Save" }).click()

    await expect(page.getByText("User created successfully")).toBeVisible()

    await expect(page.getByRole("dialog")).not.toBeVisible()

    const userRow = page.getByRole("row").filter({ hasText: email })
    await expect(userRow.getByText("Superuser")).toBeVisible()
  })

  test("Edit a user successfully", async ({ page }) => {
    await page.goto("/admin")

    const email = randomEmail()
    const password = randomPassword()
    const originalName = "Original Name"
    const updatedName = "Updated Name"

    await page.getByRole("button", { name: "Add User" }).click()
    await page.getByPlaceholder("Email").fill(email)
    await page.getByPlaceholder("Full name").fill(originalName)
    await page.getByPlaceholder("Password").first().fill(password)
    await page.getByPlaceholder("Password").last().fill(password)
    await page.getByRole("button", { name: "Save" }).click()

    await expect(page.getByText("User created successfully")).toBeVisible()
    await expect(page.getByRole("dialog")).not.toBeVisible()

    const userRow = page.getByRole("row").filter({ hasText: email })
    await userRow.getByRole("button").click()

    await page.getByRole("menuitem", { name: "Edit User" }).click()

    await page.getByPlaceholder("Full name").fill(updatedName)
    await page.getByRole("button", { name: "Save" }).click()

    await expect(page.getByText("User updated successfully")).toBeVisible()
    await expect(page.getByText(updatedName)).toBeVisible()
  })

  test("Delete a user successfully", async ({ page }) => {
    await page.goto("/admin")

    const email = randomEmail()
    const password = randomPassword()

    await page.getByRole("button", { name: "Add User" }).click()
    await page.getByPlaceholder("Email").fill(email)
    await page.getByPlaceholder("Password").first().fill(password)
    await page.getByPlaceholder("Password").last().fill(password)
    await page.getByRole("button", { name: "Save" }).click()

    await expect(page.getByText("User created successfully")).toBeVisible()

    await expect(page.getByRole("dialog")).not.toBeVisible()

    const userRow = page.getByRole("row").filter({ hasText: email })
    await userRow.getByRole("button").click()

    await page.getByRole("menuitem", { name: "Delete User" }).click()

    await page.getByRole("button", { name: "Delete" }).click()

    await expect(
      page.getByText("The user was deleted successfully"),
    ).toBeVisible()

    await expect(
      page.getByRole("row").filter({ hasText: email }),
    ).not.toBeVisible()
  })

  test("Cancel user creation", async ({ page }) => {
    await page.goto("/admin")

    await page.getByRole("button", { name: "Add User" }).click()
    await page.getByPlaceholder("Email").fill("test@example.com")

    await page.getByRole("button", { name: "Cancel" }).click()

    await expect(page.getByRole("dialog")).not.toBeVisible()
  })

  test("Email is required and must be valid", async ({ page }) => {
    await page.goto("/admin")

    await page.getByRole("button", { name: "Add User" }).click()

    await page.getByPlaceholder("Email").fill("invalid-email")
    await page.getByPlaceholder("Email").blur()

    await expect(page.getByText("Invalid email address")).toBeVisible()
  })

  test("Password must be at least 8 characters", async ({ page }) => {
    await page.goto("/admin")

    await page.getByRole("button", { name: "Add User" }).click()

    await page.getByPlaceholder("Email").fill(randomEmail())
    await page.getByPlaceholder("Password").first().fill("short")
    await page.getByPlaceholder("Password").last().fill("short")
    await page.getByRole("button", { name: "Save" }).click()

    await expect(
      page.getByText("Password must be at least 8 characters"),
    ).toBeVisible()
  })

  test("Passwords must match", async ({ page }) => {
    await page.goto("/admin")

    await page.getByRole("button", { name: "Add User" }).click()

    await page.getByPlaceholder("Email").fill(randomEmail())
    await page.getByPlaceholder("Password").first().fill(randomPassword())
    await page.getByPlaceholder("Password").last().fill("different12345")
    await page.getByPlaceholder("Password").last().blur()

    await expect(page.getByText("The passwords don't match")).toBeVisible()
  })
})

test.describe("Admin page access control", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("Non-superuser cannot access admin page", async ({ page }) => {
    const email = randomEmail()
    const password = randomPassword()

    await createUser({ email, password })
    await logInUser(page, email, password)

    await page.goto("/admin")

    await expect(page.getByRole("heading", { name: "Users" })).not.toBeVisible()
    await expect(page).not.toHaveURL(/\/admin/)
  })

  test("Superuser can access admin page", async ({ page }) => {
    await logInUser(page, firstSuperuser, firstSuperuserPassword)

    await page.goto("/admin")

    await expect(page.getByRole("heading", { name: "Users" })).toBeVisible()
  })
})

test.describe("Roles", () => {
  const addUserViaUi = async (
    page: import("@playwright/test").Page,
    email: string,
    password: string,
  ) => {
    await page.getByRole("button", { name: "Add User" }).click()
    await page.getByPlaceholder("Email").fill(email)
    await page.getByPlaceholder("Password").first().fill(password)
    await page.getByPlaceholder("Password").last().fill(password)
  }

  test("Superuser sees the admin option and the superuser checkbox", async ({
    page,
  }) => {
    await page.goto("/admin")
    await page.getByRole("button", { name: "Add User" }).click()
    await expect(page.getByLabel("Is superuser?")).toBeVisible()
    await page.getByRole("combobox", { name: "Role" }).click()
    await expect(page.getByRole("option", { name: "Admin" })).toBeVisible()
    await expect(page.getByRole("option", { name: "Editor" })).toBeVisible()
  })

  test("Superuser sets a user's role to editor and the table shows it", async ({
    page,
  }) => {
    await page.goto("/admin")
    const email = randomEmail()
    await addUserViaUi(page, email, randomPassword())
    await page.getByRole("button", { name: "Save" }).click()
    await expect(page.getByText("User created successfully")).toBeVisible()
    await expect(page.getByRole("dialog")).not.toBeVisible()

    const userRow = page.getByRole("row").filter({ hasText: email })
    await expect(userRow.getByText("Member")).toBeVisible()
    await userRow.getByRole("button").click()
    await page.getByRole("menuitem", { name: "Edit User" }).click()
    await page.getByRole("combobox", { name: "Role" }).click()
    await page.getByRole("option", { name: "Editor" }).click()
    await page.getByRole("button", { name: "Save" }).click()

    await expect(page.getByText("User updated successfully")).toBeVisible()
    await expect(userRow.getByText("Editor")).toBeVisible()
  })

  test("Role is disabled when a superuser edits themselves", async ({
    page,
  }) => {
    await page.goto("/admin")
    const row = page.getByRole("row").filter({ hasText: firstSuperuser })
    await row.getByRole("button").click()
    await page.getByRole("menuitem", { name: "Edit User" }).click()
    await expect(page.getByRole("combobox", { name: "Role" })).toBeDisabled()
    await expect(
      page.getByText("You cannot change your own role."),
    ).toBeVisible()
  })

  test.describe("as a non-superuser admin", () => {
    test.use({ storageState: { cookies: [], origins: [] } })

    test("sees Admin, no admin option, and cannot edit admins or superusers", async ({
      page,
    }) => {
      const adminEmail = randomEmail()
      const otherAdminEmail = randomEmail()
      const superEmail = randomEmail()
      const memberEmail = randomEmail()
      const password = randomPassword()
      await createUserWithRole({ email: adminEmail, password, role: "admin" })
      await createUserWithRole({
        email: otherAdminEmail,
        password,
        role: "admin",
      })
      await createUserWithRole({
        email: superEmail,
        password,
        role: "member",
        isSuperuser: true,
      })
      await createUserWithRole({ email: memberEmail, password, role: "member" })

      await logInUser(page, adminEmail, password)
      await expect(page.getByRole("link", { name: "Admin" })).toBeVisible()
      await page.getByRole("link", { name: "Admin" }).click()
      await expect(page.getByRole("heading", { name: "Users" })).toBeVisible()

      const rowOf = (email: string) =>
        page.getByRole("row").filter({ hasText: email })
      await expect(rowOf(memberEmail)).toBeVisible()
      await expect(rowOf(memberEmail).getByRole("button")).toBeVisible()
      await expect(rowOf(otherAdminEmail)).toBeVisible()
      await expect(rowOf(otherAdminEmail).getByRole("button")).toHaveCount(0)
      await expect(rowOf(superEmail)).toBeVisible()
      await expect(rowOf(superEmail).getByRole("button")).toHaveCount(0)
      await expect(rowOf(adminEmail).getByRole("button")).toHaveCount(0)

      await page.getByRole("button", { name: "Add User" }).click()
      await expect(page.getByLabel("Is superuser?")).toHaveCount(0)
      await page.getByRole("combobox", { name: "Role" }).click()
      await expect(page.getByRole("option", { name: "Editor" })).toBeVisible()
      await expect(page.getByRole("option", { name: "Admin" })).toHaveCount(0)
    })

    test("a member does not see Admin in the sidebar", async ({ page }) => {
      const email = randomEmail()
      const password = randomPassword()
      await createUserWithRole({ email, password, role: "member" })
      await logInUser(page, email, password)
      await expect(page.getByRole("link", { name: "Admin" })).toHaveCount(0)
    })
  })
})
