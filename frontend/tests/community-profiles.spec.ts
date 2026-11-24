import { expect, test } from "@playwright/test"
import { createUserApi } from "./utils/community"
import { createEditorApi, textBody } from "./utils/content"
import { logInUser } from "./utils/user"

const unique = () => Math.random().toString(36).substring(2, 9)

// Everything here starts logged out; tests log in as the users they create.
test.use({ storageState: { cookies: [], origins: [] } })

async function newPost() {
  const api = await createEditorApi()
  const id = unique()
  const post = await api.post({
    title: `Profile post ${id}`,
    body: textBody("Heading", `Body ${id}`),
  })
  return { id, post }
}

test.describe("Profiles", () => {
  test("Username and bio set in settings show on the public profile", async ({
    page,
  }) => {
    const member = await createUserApi()
    const username = `ada_${unique()}`
    const bio = `Hello, I write things ${unique()}`
    await logInUser(page, member.email, member.password)

    await page.goto("/settings")
    await page.getByRole("button", { name: "Edit", exact: true }).click()
    // The 30-day rule is shown next to the field.
    await expect(page.getByText("once every 30 days")).toBeVisible()
    await page.getByRole("textbox", { name: "Username" }).fill(username)
    await page.getByRole("textbox", { name: "Bio" }).fill(bio)
    await page.getByRole("button", { name: "Save", exact: true }).click()
    await expect(page.getByText("User updated successfully")).toBeVisible()

    await page.getByRole("link", { name: "View profile" }).click()
    await expect(page).toHaveURL(`/u/${username}`)
    await expect(page.getByTestId("username")).toHaveText(`@${username}`)
    await expect(page.getByTestId("bio")).toHaveText(bio)
    // Your own profile has no follow button.
    await expect(page.getByRole("button", { name: "Follow" })).toHaveCount(0)

    // Changing it again right away is refused by the API (once every 30 days).
    await page.goto("/settings")
    await page.getByRole("button", { name: "Edit", exact: true }).click()
    await page.getByRole("textbox", { name: "Username" }).fill(`${username}_2`)
    await page.getByRole("button", { name: "Save", exact: true }).click()
    await expect(page.getByText(/once every 30 days/).last()).toBeVisible()
  })

  test("Unknown profiles show the not-found page", async ({ page }) => {
    await page.goto("/u/nobody_here_at_all")
    await expect(page.getByTestId("not-found")).toBeVisible()
  })

  test("Comment authors link to profiles and a member can follow and unfollow", async ({
    page,
  }) => {
    const { post, id } = await newPost()
    const author = await createUserApi()
    await author.comment(post.id, `Profile comment ${id}`)
    const viewer = await createUserApi()
    await logInUser(page, viewer.email, viewer.password)

    await page.goto(`/blog/${post.slug}`)
    await page
      .getByTestId("comment")
      .filter({ hasText: `Profile comment ${id}` })
      .getByRole("link")
      .first()
      .click()
    await expect(page).toHaveURL(`/u/${author.username}`)
    await expect(page.getByTestId("username")).toHaveText(`@${author.username}`)
    // The profile lists the comment, linking to the post.
    const listed = page
      .getByTestId("user-comment")
      .filter({ hasText: `Profile comment ${id}` })
    await expect(listed).toBeVisible()
    await expect(listed.getByRole("link", { name: post.title })).toBeVisible()

    await page.getByRole("button", { name: "Follow", exact: true }).click()
    await expect(
      page.getByRole("button", { name: "Unfollow", exact: true }),
    ).toBeVisible()
    await expect(page.getByTestId("follower-count")).toHaveText("1")
    await page.reload()
    await expect(
      page.getByRole("button", { name: "Unfollow", exact: true }),
    ).toBeVisible()

    // Followed people's comments show up on the Following page.
    await page.goto("/following")
    await expect(
      page
        .getByTestId("user-comment")
        .filter({ hasText: `Profile comment ${id}` }),
    ).toBeVisible()

    await page.goto(`/u/${author.username}`)
    await page.getByRole("tab", { name: "Followers" }).click()
    await expect(page.getByTestId("person")).toHaveCount(1)
    await page.getByRole("button", { name: "Unfollow", exact: true }).click()
    await expect(
      page.getByRole("button", { name: "Follow", exact: true }),
    ).toBeVisible()
    await expect(page.getByTestId("follower-count")).toHaveText("0")
  })

  test("Visitors see a login link instead of a follow button", async ({
    page,
  }) => {
    const member = await createUserApi()
    await page.goto(`/u/${member.username}`)
    await expect(page.getByTestId("username")).toBeVisible()
    await expect(
      page.getByRole("link", { name: "Log in to follow" }),
    ).toBeVisible()
    await expect(page.getByTestId("notification-bell")).toHaveCount(0)
  })
})

test.describe("Notifications", () => {
  test("Replies, likes and follows notify, and Mark all read clears the badge", async ({
    page,
  }) => {
    const { post, id } = await newPost()
    const owner = await createUserApi()
    const comment = await owner.comment(post.id, `Owner comment ${id}`)

    const other = await createUserApi()
    await other.comment(post.id, `Reply ${id}`, comment.id)
    await other.likeComment(comment.id)
    await other.follow(owner.username)

    await logInUser(page, owner.email, owner.password)
    await page.goto(`/blog/${post.slug}`)

    const bell = page.getByTestId("notification-bell")
    await expect(page.getByTestId("unread-badge")).toHaveText("3")

    await bell.click()
    const items = page.getByTestId("notification-item")
    await expect(items).toHaveCount(3)
    await expect(
      items.filter({ hasText: "replied to your comment" }),
    ).toHaveCount(1)
    await expect(items.filter({ hasText: "liked your comment" })).toHaveCount(1)
    await expect(
      items.filter({ hasText: "started following you" }),
    ).toHaveCount(1)

    await page.getByRole("button", { name: "Mark all read" }).click()
    await expect(page.getByTestId("unread-badge")).toHaveCount(0)
    await page.keyboard.press("Escape")

    // The full page lists them, each linking to its target.
    await page.goto("/notifications")
    await expect(page.getByTestId("notification-row")).toHaveCount(3)
    await expect(page.getByText("You are all caught up")).toBeVisible()
    await page
      .getByTestId("notification-row")
      .filter({ hasText: "started following you" })
      .getByRole("link")
      .click()
    await expect(page).toHaveURL(`/u/${other.username}`)

    // After a reload the badge is still gone (the server remembers).
    await page.reload()
    await expect(page.getByTestId("unread-badge")).toHaveCount(0)
  })

  test("A notification link scrolls to the reply, beyond the first page, and highlights it", async ({
    page,
  }) => {
    const { post, id } = await newPost()
    const owner = await createUserApi()
    const comment = await owner.comment(post.id, `Owner comment ${id}`)
    const other = await createUserApi()
    const reply = await other.comment(post.id, `Linked reply ${id}`, comment.id)
    // 21 newer comments push the owner's thread onto the second page ("Newest" first).
    for (let n = 0; n < 21; n++) {
      await other.comment(post.id, `Filler ${n} ${id}`)
    }

    await logInUser(page, owner.email, owner.password)
    await page.goto("/notifications")
    await page
      .getByTestId("notification-row")
      .filter({ hasText: "replied to your comment" })
      .getByRole("link")
      .click()
    await expect(page).toHaveURL(`/blog/${post.slug}#comment-${reply.id}`)

    const target = page.locator(`#comment-${reply.id}`)
    await expect(target).toContainText(`Linked reply ${id}`)
    await expect(target).toHaveAttribute("data-highlight", "true")
    await expect(target).toBeInViewport()
  })
})
