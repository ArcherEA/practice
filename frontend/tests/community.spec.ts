import { expect, type Page, test } from "@playwright/test"
import { createUserApi } from "./utils/community"
import { createEditorApi, textBody } from "./utils/content"
import { logInUser } from "./utils/user"

const unique = () => Math.random().toString(36).substring(2, 9)

// Everything here starts logged out; tests log in as the users they create.
test.use({ storageState: { cookies: [], origins: [] } })

/** Logs out (drops the token) and logs in as someone else. */
async function switchTo(page: Page, user: { email: string; password: string }) {
  await page.goto("/login")
  await page.evaluate(() => localStorage.clear())
  await logInUser(page, user.email, user.password)
}

const commentBox = (page: Page) =>
  page.getByLabel("Add a comment", { exact: true })
const commentWith = (page: Page, text: string) =>
  page.getByTestId("comment").filter({ hasText: text })

async function newPost() {
  const api = await createEditorApi()
  const id = unique()
  const post = await api.post({
    title: `Community post ${id}`,
    body: textBody("Heading", `Body ${id}`),
  })
  return { api, id, post }
}

test.describe("Comments on a post", () => {
  test("A member comments, replies, likes, edits and deletes", async ({
    page,
  }) => {
    const { post, id } = await newPost()
    const member = await createUserApi()
    await logInUser(page, member.email, member.password)
    await page.goto(`/blog/${post.slug}`)

    // Comment text is shown as plain text, never as HTML.
    const text = `<b>first</b> ${id}\nsecond line`
    await commentBox(page).fill(text)
    await expect(page.getByTestId("char-counter")).toContainText("/ 5000")
    await page
      .getByRole("button", { name: "Post comment", exact: true })
      .click()
    const comment = commentWith(page, `first`)
    await expect(comment.getByTestId("comment-body")).toHaveText(text)
    await expect(comment.locator("b")).toHaveCount(0)
    await expect(commentBox(page)).toHaveValue("")

    // Like the comment and the post.
    await comment
      .getByRole("button", { name: "Like comment", exact: true })
      .click()
    await expect(
      comment.getByRole("button", { name: "Unlike comment", exact: true }),
    ).toContainText("1")
    const likePost = page.getByRole("button", {
      name: "Like post",
      exact: true,
    })
    await likePost.click()
    await expect(
      page.getByRole("button", { name: "Unlike post", exact: true }),
    ).toContainText("1")
    await page.reload()
    await expect(
      page.getByRole("button", { name: "Unlike post", exact: true }),
    ).toBeVisible()

    // Reply (one level, indented).
    await comment.getByRole("button", { name: "Reply", exact: true }).click()
    await page.getByLabel("Write a reply", { exact: true }).fill(`reply ${id}`)
    await page.getByRole("button", { name: "Send reply", exact: true }).click()
    const reply = commentWith(page, `reply ${id}`)
    await expect(reply).toBeVisible()
    // Replies cannot be replied to.
    await expect(
      reply.getByRole("button", { name: "Reply", exact: true }),
    ).toHaveCount(0)

    // Edit own comment (inline), then it is marked as edited.
    await comment
      .getByRole("button", { name: "Comment actions", exact: true })
      .click()
    await page.getByRole("menuitem", { name: "Edit", exact: true }).click()
    await page.getByLabel("Edit comment", { exact: true }).fill(`edited ${id}`)
    await page.getByRole("button", { name: "Save", exact: true }).click()
    await expect(commentWith(page, `edited ${id}`)).toContainText("(edited)")

    // Delete the reply: the confirm dialog, then it is gone.
    await reply
      .getByRole("button", { name: "Comment actions", exact: true })
      .click()
    await page.getByRole("menuitem", { name: "Delete", exact: true }).click()
    await page.getByRole("button", { name: "Delete", exact: true }).click()
    await expect(commentWith(page, `reply ${id}`)).toHaveCount(0)

    // Delete the comment: no replies left, so the row disappears.
    await commentWith(page, `edited ${id}`)
      .getByRole("button", { name: "Comment actions", exact: true })
      .click()
    await page.getByRole("menuitem", { name: "Delete", exact: true }).click()
    await page.getByRole("button", { name: "Delete", exact: true }).click()
    await expect(commentWith(page, `edited ${id}`)).toHaveCount(0)
    await expect(page.getByText("No comments yet")).toBeVisible()
  })

  test("Deleting a comment that has replies leaves a placeholder", async ({
    page,
  }) => {
    const { post, id } = await newPost()
    const member = await createUserApi()
    const other = await createUserApi()
    const parent = await member.comment(post.id, `parent ${id}`)
    await other.comment(post.id, `answer ${id}`, parent.id)

    await logInUser(page, member.email, member.password)
    await page.goto(`/blog/${post.slug}`)
    await commentWith(page, `parent ${id}`)
      .getByRole("button", { name: "Comment actions", exact: true })
      .click()
    await page.getByRole("menuitem", { name: "Delete", exact: true }).click()
    await page.getByRole("button", { name: "Delete", exact: true }).click()
    await expect(page.getByText("This comment was deleted.")).toBeVisible()
    await expect(commentWith(page, `answer ${id}`)).toBeVisible()
  })

  test("Other members' comments offer Report, not Edit or Delete; sorting works", async ({
    page,
  }) => {
    const { post, id } = await newPost()
    const author = await createUserApi()
    const reader = await createUserApi()
    await author.comment(post.id, `older ${id}`)
    await author.comment(post.id, `newer ${id}`)

    await logInUser(page, reader.email, reader.password)
    await page.goto(`/blog/${post.slug}`)
    const texts = page.getByTestId("comment-body")
    await expect(texts.first()).toHaveText(`newer ${id}`)
    await page.getByRole("button", { name: "Oldest", exact: true }).click()
    await expect(texts.first()).toHaveText(`older ${id}`)

    await commentWith(page, `older ${id}`)
      .getByRole("button", { name: "Comment actions", exact: true })
      .click()
    await expect(page.getByRole("menuitem", { name: "Report" })).toBeVisible()
    await expect(page.getByRole("menuitem", { name: "Edit" })).toHaveCount(0)
    await expect(page.getByRole("menuitem", { name: "Delete" })).toHaveCount(0)
  })

  test("A member comments on a page; pages have no post like button", async ({
    page,
  }) => {
    const api = await createEditorApi()
    const id = unique()
    const staticPage = await api.page({
      title: `Community page ${id}`,
      body: textBody("About", `About ${id}`),
    })
    const member = await createUserApi()
    await logInUser(page, member.email, member.password)
    await page.goto(`/p/${staticPage.slug}`)
    await commentBox(page).fill(`page comment ${id}`)
    await page
      .getByRole("button", { name: "Post comment", exact: true })
      .click()
    await expect(commentWith(page, `page comment ${id}`)).toBeVisible()
    await expect(
      page.getByRole("button", { name: "Like post", exact: true }),
    ).toHaveCount(0)
  })
})

test.describe("Anonymous visitors", () => {
  test("see comments but no form, and come back after logging in", async ({
    page,
  }) => {
    const { post, id } = await newPost()
    const member = await createUserApi()
    await member.comment(post.id, `visible to all ${id}`)

    await page.goto(`/blog/${post.slug}`)
    await expect(commentWith(page, `visible to all ${id}`)).toBeVisible()
    await expect(commentBox(page)).toHaveCount(0)
    await expect(
      page.getByRole("button", { name: "Post comment", exact: true }),
    ).toHaveCount(0)

    await page
      .getByRole("link", { name: "Log in to comment", exact: true })
      .click()
    await expect(page).toHaveURL(/\/login\?redirect=/)
    await page.getByTestId("email-input").fill(member.email)
    await page.getByTestId("password-input").fill(member.password)
    await page.getByRole("button", { name: "Log In" }).click()
    await expect(page).toHaveURL(`/blog/${post.slug}`)
    await expect(commentBox(page)).toBeVisible()
  })

  test("a login redirect to another site is ignored", async ({ page }) => {
    const member = await createUserApi()
    await page.goto("/login?redirect=//evil.example/x")
    await page.getByTestId("email-input").fill(member.email)
    await page.getByTestId("password-input").fill(member.password)
    await page.getByRole("button", { name: "Log In" }).click()
    await expect(page).toHaveURL("/")
  })
})

test.describe("Reports and moderation", () => {
  test("A member reports; a moderator hides and restores the comment", async ({
    page,
  }) => {
    const { post, id } = await newPost()
    const author = await createUserApi()
    const reporter = await createUserApi()
    const moderator = await createUserApi("moderator")
    await author.comment(post.id, `report me ${id}`)

    await logInUser(page, reporter.email, reporter.password)
    await page.goto(`/blog/${post.slug}`)
    await commentWith(page, `report me ${id}`)
      .getByRole("button", { name: "Comment actions", exact: true })
      .click()
    await page.getByRole("menuitem", { name: "Report", exact: true }).click()
    await page.getByLabel("Abuse or harassment", { exact: true }).check()
    await page.getByLabel("Note (optional)", { exact: true }).fill(`note ${id}`)
    await page.getByRole("button", { name: "Send report", exact: true }).click()
    await expect(
      page.getByText("Thanks, the moderators will take a look"),
    ).toBeVisible()

    // Reporting twice is rejected with the API's message.
    await commentWith(page, `report me ${id}`)
      .getByRole("button", { name: "Comment actions", exact: true })
      .click()
    await page.getByRole("menuitem", { name: "Report", exact: true }).click()
    await page.getByRole("button", { name: "Send report", exact: true }).click()
    await expect(page.getByText(/already reported/i)).toBeVisible()

    await switchTo(page, moderator)
    await expect(
      page.getByRole("link", { name: "Moderation", exact: true }),
    ).toBeVisible()
    await page.getByRole("link", { name: "Moderation", exact: true }).click()
    await expect(page).toHaveURL("/moderation")
    const item = page
      .getByTestId("queue-item")
      .filter({ hasText: `report me ${id}` })
    await expect(item).toContainText("abuse")
    await expect(item).toContainText(`note ${id}`)
    await expect(item).toContainText("1 report")
    await expect(
      item.getByRole("link", { name: `Community post ${id}`, exact: true }),
    ).toHaveAttribute("href", `/blog/${post.slug}`)

    await item.getByRole("button", { name: "Hide", exact: true }).click()
    await expect(
      item.getByRole("button", { name: "Restore", exact: true }),
    ).toBeVisible()
    await expect(item.getByText("Hidden", { exact: true })).toBeVisible()
    // Hidden for the public.
    await page.goto(`/blog/${post.slug}`)
    await expect(commentWith(page, `report me ${id}`)).toHaveCount(0)

    await page.goto("/moderation")
    await page.getByRole("tab", { name: "Hidden", exact: true }).click()
    const hidden = page
      .getByTestId("queue-item")
      .filter({ hasText: `report me ${id}` })
    await hidden.getByRole("button", { name: "Restore", exact: true }).click()
    await expect(hidden).toHaveCount(0)
    await page.goto(`/blog/${post.slug}`)
    await expect(commentWith(page, `report me ${id}`)).toBeVisible()

    // Resolving the reports empties the "Reported" tab for this comment.
    await page.goto("/moderation")
    const again = page
      .getByTestId("queue-item")
      .filter({ hasText: `report me ${id}` })
    await again
      .getByRole("button", { name: "Resolve reports", exact: true })
      .click()
    await expect(again).toHaveCount(0)
  })

  test("A moderator suspends a member, who sees a notice instead of the form", async ({
    page,
  }) => {
    const { post, id } = await newPost()
    const member = await createUserApi()
    const reporter = await createUserApi()
    const moderator = await createUserApi("moderator")
    const comment = await member.comment(post.id, `rude ${id}`)
    await reporter.report(comment.id, "abuse")

    await logInUser(page, moderator.email, moderator.password)
    await page.goto("/moderation")
    const item = page
      .getByTestId("queue-item")
      .filter({ hasText: `rude ${id}` })
    await item
      .getByRole("button", { name: "Suspend member", exact: true })
      .click()
    await page.getByLabel("30 days", { exact: true }).check()
    await page
      .getByLabel("Reason (optional)", { exact: true })
      .fill(`be nice ${id}`)
    await page.getByRole("button", { name: "Suspend", exact: true }).click()

    await page.getByRole("tab", { name: "Suspensions", exact: true }).click()
    const suspension = page
      .getByTestId("suspension")
      .filter({ hasText: `be nice ${id}` })
    await expect(suspension).toBeVisible()
    await expect(suspension).toContainText("Until")

    await switchTo(page, member)
    await page.goto(`/blog/${post.slug}`)
    await expect(page.getByText("You can't comment right now")).toBeVisible()
    await expect(page.getByText(`be nice ${id}`)).toBeVisible()
    await expect(commentBox(page)).toHaveCount(0)

    // Ending the suspension brings the form back.
    await switchTo(page, moderator)
    await page.goto("/moderation")
    await page.getByRole("tab", { name: "Suspensions", exact: true }).click()
    await page
      .getByTestId("suspension")
      .filter({ hasText: `be nice ${id}` })
      .getByRole("button", { name: "End suspension", exact: true })
      .click()
    await expect(
      page.getByTestId("suspension").filter({ hasText: `be nice ${id}` }),
    ).toHaveCount(0)
    await switchTo(page, member)
    await page.goto(`/blog/${post.slug}`)
    await expect(commentBox(page)).toBeVisible()
  })

  test("A moderator cannot act on an admin's comment and sees why", async ({
    page,
  }) => {
    const { post, id } = await newPost()
    const admin = await createUserApi("admin")
    const reporter = await createUserApi()
    const moderator = await createUserApi("moderator")
    const comment = await admin.comment(post.id, `admin says ${id}`)
    await reporter.report(comment.id, "spam")

    await logInUser(page, moderator.email, moderator.password)
    await page.goto("/moderation")
    const item = page
      .getByTestId("queue-item")
      .filter({ hasText: `admin says ${id}` })
    await item.getByRole("button", { name: "Hide", exact: true }).click()
    await expect(
      page.getByText("Only superusers can moderate admins and superusers"),
    ).toBeVisible()
  })

  test("An editor has no Moderation entry and is redirected from /moderation", async ({
    page,
  }) => {
    const editor = await createUserApi("editor")
    await logInUser(page, editor.email, editor.password)
    await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible()
    await expect(
      page.getByRole("link", { name: "Content", exact: true }),
    ).toBeVisible()
    await expect(
      page.getByRole("link", { name: "Moderation", exact: true }),
    ).toHaveCount(0)
    await page.goto("/moderation")
    await expect(page).toHaveURL("/")
  })

  test("A member has no Moderation entry either", async ({ page }) => {
    const member = await createUserApi()
    await logInUser(page, member.email, member.password)
    await expect(
      page.getByRole("link", { name: "Moderation", exact: true }),
    ).toHaveCount(0)
    await page.goto("/moderation")
    await expect(page).toHaveURL("/")
  })
})

test.describe("Community module disabled", () => {
  test("posts show no comment section and make no community requests", async ({
    page,
  }) => {
    const { post, id } = await newPost()
    await page.route("**/api/v1/utils/config", (route) =>
      route.fulfill({
        json: { project_name: "Test", modules: ["items", "content"] },
      }),
    )
    const communityRequests: string[] = []
    page.on("request", (req) => {
      if (req.url().includes("/api/v1/community/")) {
        communityRequests.push(req.url())
      }
    })

    await page.goto(`/blog/${post.slug}`)
    await expect(
      page.getByRole("heading", { name: `Community post ${id}`, level: 1 }),
    ).toBeVisible()
    await expect(page.getByTestId("comment-section")).toHaveCount(0)
    await expect(page.getByRole("heading", { name: /^Comments/ })).toHaveCount(
      0,
    )
    await expect(
      page.getByRole("button", { name: "Like post", exact: true }),
    ).toHaveCount(0)
    await expect(
      page.getByRole("link", { name: "Log in to comment" }),
    ).toHaveCount(0)
    expect(communityRequests).toEqual([])
  })
})
