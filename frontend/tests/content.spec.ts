import { expect, type Page, test } from "@playwright/test"
import { createUserWithRole } from "./utils/privateApi.ts"
import { randomEmail, randomPassword } from "./utils/random"
import { logInUser } from "./utils/user"

// A valid 1x1 PNG, generated here so no binary fixture is committed.
const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC",
  "base64",
)

// Mirrors the backend allow-list (docs/ARCHITECTURE.md, content module).
const ALLOWED_NODES = new Set([
  "doc",
  "paragraph",
  "heading",
  "bulletList",
  "orderedList",
  "listItem",
  "blockquote",
  "codeBlock",
  "horizontalRule",
  "hardBreak",
  "image",
  "text",
])
const ALLOWED_MARKS = new Set(["bold", "italic", "strike", "code", "link"])

interface DocNode {
  type: string
  attrs?: Record<string, unknown>
  marks?: { type: string; attrs?: Record<string, unknown> }[]
  content?: DocNode[]
}

const randomTitle = () => `Post ${Math.random().toString(36).substring(2, 9)}`

async function loginAsEditor(page: Page, role: "editor" | "member" = "editor") {
  const email = randomEmail()
  const password = randomPassword()
  await createUserWithRole({ email, password, role })
  await logInUser(page, email, password)
}

// "Title" alone would also match the "SEO title" field.
const titleInput = (page: Page) => page.getByRole("textbox", { name: /^Title/ })
const bodyEditor = (page: Page) => page.getByRole("textbox", { name: "Body" })
const tool = (page: Page, name: string) =>
  page.getByRole("button", { name, exact: true })

/** Reads the saved post through the API, as the logged-in browser user. */
async function fetchSavedPost(page: Page) {
  const id = page.url().split("/").pop()
  return page.evaluate(
    async ({ id, base }) => {
      const token = localStorage.getItem("access_token")
      const res = await fetch(`${base}/api/v1/content/manage/posts/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      return { status: res.status, post: await res.json() }
    },
    { id, base: process.env.VITE_API_URL ?? "" },
  )
}

function collect(node: DocNode, nodes: Set<string>, marks: Set<string>) {
  nodes.add(node.type)
  for (const mark of node.marks ?? []) marks.add(mark.type)
  for (const child of node.content ?? []) collect(child, nodes, marks)
}

test.describe("Content editor", () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test("Editor writes a post with heading, list, link and image, publishes it", async ({
    page,
  }) => {
    await loginAsEditor(page)
    await page.getByRole("link", { name: "Content", exact: true }).click()
    await expect(page).toHaveURL(/\/content\/posts$/)
    await expect(page.getByRole("heading", { name: "Posts" })).toBeVisible()

    await page.getByRole("link", { name: "New post" }).click()
    const title = randomTitle()
    await titleInput(page).fill(title)
    // The slug follows the title until it is edited.
    await expect(page.getByRole("textbox", { name: "Slug" })).toHaveValue(
      title.toLowerCase().replace(/\s+/g, "-"),
    )
    await page.getByLabel("Excerpt").fill("A short excerpt")

    await bodyEditor(page).click()
    await tool(page, "Heading 2").click()
    await page.keyboard.type("A heading")
    await page.keyboard.press("Enter")
    await tool(page, "Bullet list").click()
    await page.keyboard.type("first point")
    await page.keyboard.press("Enter")
    await page.keyboard.type("second point")
    // Enter on an empty item leaves the list.
    await page.keyboard.press("Enter")
    await page.keyboard.press("Enter")
    await page.keyboard.type("a link")
    await page.keyboard.press("Shift+Home")
    // Wait until the text is really selected before opening the link bar (CI is slower).
    await expect
      .poll(() => page.evaluate(() => window.getSelection()?.toString()))
      .toBe("a link")
    await tool(page, "Link").click()
    await page.getByLabel("Link URL").fill("https://example.com")
    await page.getByRole("button", { name: "Apply link" }).click()
    await page.keyboard.press("End")
    await page.keyboard.press("Enter")
    await page.getByTestId("editor-image-input").setInputFiles({
      name: "pic.png",
      mimeType: "image/png",
      buffer: TINY_PNG,
    })
    await expect(
      page.getByTestId("rich-text-editor").locator("img"),
    ).toBeVisible({ timeout: 15000 })

    // Preview renders the same body read-only.
    await page.getByRole("button", { name: "Preview" }).click()
    const preview = page.getByTestId("body-preview")
    await expect(preview.locator("h2")).toHaveText("A heading")
    await expect(preview.locator("li")).toHaveCount(2)
    await expect(preview.locator("a[href='https://example.com']")).toHaveText(
      "a link",
    )
    await expect(preview.locator("img")).toBeVisible()
    await page.getByRole("button", { name: "Edit", exact: true }).click()

    await page.getByRole("button", { name: "Publish" }).click()
    await expect(page.getByText("Post published")).toBeVisible()
    await expect(page).toHaveURL(/\/content\/posts\/[0-9a-f-]{36}$/)
    await expect(page.getByRole("button", { name: "Unpublish" })).toBeVisible()

    // Saved body: accepted by the backend, image carries the file id.
    const { status, post } = await fetchSavedPost(page)
    expect(status).toBe(200)
    expect(post.status).toBe("published")
    const nodes = new Set<string>()
    const marks = new Set<string>()
    collect(post.body, nodes, marks)
    for (const type of ["heading", "bulletList", "listItem", "image"]) {
      expect(nodes).toContain(type)
    }
    expect(marks).toContain("link")
    const image = (function find(n: DocNode): DocNode | undefined {
      return n.type === "image"
        ? n
        : n.content?.map(find).find((x) => x !== undefined)
    })(post.body)
    expect(image?.attrs?.fileId).toBeTruthy()

    // Reload: formatting is still there.
    await page.reload()
    const editor = page.getByTestId("rich-text-editor")
    await expect(editor.locator("h2")).toHaveText("A heading")
    await expect(editor.locator("ul li")).toHaveCount(2)
    await expect(editor.locator("a[href='https://example.com']")).toBeVisible()
    await expect(editor.locator("img")).toBeVisible()
    await expect(titleInput(page)).toHaveValue(title)

    // The list shows it as Published.
    await page.goto("/content/posts")
    const row = page.getByRole("row").filter({ hasText: title })
    await expect(row.getByText("Published")).toBeVisible()
    await page.getByLabel("Filter by status").click()
    await page.getByRole("option", { name: "Draft" }).click()
    await expect(page.getByRole("row").filter({ hasText: title })).toHaveCount(
      0,
    )
  })

  test("Every toolbar action round-trips and the backend accepts it", async ({
    page,
  }) => {
    await loginAsEditor(page)
    await page.goto("/content/posts/new")
    await titleInput(page).fill(randomTitle())
    await bodyEditor(page).click()
    const type = (text: string) => page.keyboard.type(text)
    const enter = () => page.keyboard.press("Enter")

    await tool(page, "Heading 1").click()
    await type("H1")
    await enter()
    await tool(page, "Heading 2").click()
    await type("H2")
    await enter()
    await tool(page, "Heading 3").click()
    await type("H3")
    await enter()

    for (const name of ["Bold", "Italic", "Strikethrough", "Inline code"]) {
      await tool(page, name).click()
      await type(name.toLowerCase())
      await tool(page, name).click()
      await type(" ")
    }
    await tool(page, "Line break").click()
    await type("after break")
    await enter()

    // An empty line (Enter twice) leaves a list or quote; three Enters leave a code block.
    await tool(page, "Numbered list").click()
    await type("one")
    await enter()
    await type("two")
    await enter()
    await enter()
    await tool(page, "Bullet list").click()
    await type("bullet")
    await enter()
    await enter()
    await tool(page, "Quote").click()
    await type("quoted")
    await enter()
    await enter()
    await tool(page, "Code block").click()
    await type("const a = 1")
    await enter()
    await enter()
    await enter()
    await tool(page, "Horizontal rule").click()
    await type("linked")
    await page.keyboard.press("Shift+Home")
    // Wait until the text is really selected before opening the link bar (CI is slower).
    await expect
      .poll(() => page.evaluate(() => window.getSelection()?.toString()))
      .toBe("linked")
    await tool(page, "Link").click()
    await page.getByLabel("Link URL").fill("/about")
    await page.getByRole("button", { name: "Apply link" }).click()
    await page.keyboard.press("End")
    await enter()
    await page.getByTestId("editor-image-input").setInputFiles({
      name: "all.png",
      mimeType: "image/png",
      buffer: TINY_PNG,
    })
    await expect(
      page.getByTestId("rich-text-editor").locator("img"),
    ).toBeVisible({ timeout: 15000 })

    await page.getByRole("button", { name: "Save draft" }).click()
    await expect(page.getByText("Post saved")).toBeVisible()
    await expect(page).toHaveURL(/\/content\/posts\/[0-9a-f-]{36}$/)

    const { status, post } = await fetchSavedPost(page)
    expect(status).toBe(200)
    const nodes = new Set<string>()
    const marks = new Set<string>()
    collect(post.body, nodes, marks)
    // Everything the toolbar produced is inside the allow-list ...
    for (const n of nodes) expect(ALLOWED_NODES).toContain(n)
    for (const m of marks) expect(ALLOWED_MARKS).toContain(m)
    // ... and every action actually produced its node or mark.
    for (const n of ALLOWED_NODES) expect(nodes).toContain(n)
    for (const m of ALLOWED_MARKS) expect(marks).toContain(m)
    const levels = new Set<number>()
    ;(function walk(n: DocNode) {
      if (n.type === "heading") levels.add(n.attrs?.level as number)
      n.content?.forEach(walk)
    })(post.body)
    expect([...levels].sort()).toEqual([1, 2, 3])

    // Reload: the same structure comes back in the editor.
    await page.reload()
    const editor = page.getByTestId("rich-text-editor")
    for (const selector of [
      "h1",
      "h2",
      "h3",
      "strong",
      "em",
      "s",
      "p code",
      "br",
      "ol li",
      "blockquote",
      "pre code",
      "hr",
      "a[href='/about']",
      "img",
    ]) {
      await expect(editor.locator(selector).first(), selector).toBeAttached()
    }
  })

  test("Rejects a link with a disallowed address", async ({ page }) => {
    await loginAsEditor(page)
    await page.goto("/content/posts/new")
    await bodyEditor(page).click()
    await page.keyboard.type("bad link")
    await page.keyboard.press("Shift+Home")
    // Wait until the text is really selected before opening the link bar (CI is slower).
    await expect
      .poll(() => page.evaluate(() => window.getSelection()?.toString()))
      .toBe("bad link")
    await tool(page, "Link").click()
    await page.getByLabel("Link URL").fill("javascript:alert(1)")
    await page.getByRole("button", { name: "Apply link" }).click()
    await expect(page.getByRole("alert")).toContainText("http://")
    await expect(page.getByTestId("rich-text-editor").locator("a")).toHaveCount(
      0,
    )
  })

  test("Delete asks for confirmation; unsaved changes warn on leaving", async ({
    page,
  }) => {
    await loginAsEditor(page)
    await page.goto("/content/posts/new")
    const title = randomTitle()
    await titleInput(page).fill(title)
    await page.getByRole("button", { name: "Save draft" }).click()
    await expect(page.getByText("Post saved")).toBeVisible()
    await expect(page.getByRole("button", { name: "Publish" })).toBeVisible()

    // Unsaved edit -> leaving asks; dismissing keeps us here.
    await titleInput(page).fill(`${title} changed`)
    const messages: string[] = []
    page.once("dialog", async (dialog) => {
      messages.push(dialog.message())
      await dialog.dismiss()
    })
    await page.getByRole("link", { name: "Posts" }).first().click()
    await expect.poll(() => messages.length).toBe(1)
    await expect(page).toHaveURL(/\/content\/posts\/[0-9a-f-]{36}$/)

    await page.getByRole("button", { name: "Delete" }).click()
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Cancel" })
      .click()
    await expect(titleInput(page)).toBeVisible()
    await page.getByRole("button", { name: "Delete" }).click()
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Delete" })
      .click()
    await expect(page.getByText("Post deleted")).toBeVisible()
    await expect(page).toHaveURL(/\/content\/posts$/)
  })

  test("Editor manages categories and tags, and writes a page", async ({
    page,
  }) => {
    await loginAsEditor(page)
    await page.goto("/content/taxonomy")
    const categoryName = `Cat ${Math.random().toString(36).substring(2, 8)}`
    await page.getByLabel("New category name").fill(categoryName)
    await page.getByRole("button", { name: "Add category" }).click()
    await expect(page.getByText("Category created")).toBeVisible()
    await expect(
      page.getByRole("cell", { name: categoryName, exact: true }),
    ).toBeVisible()

    // A post can use the category and a tag created on the fly.
    await page.goto("/content/posts/new")
    await titleInput(page).fill(randomTitle())
    await page.getByRole("combobox", { name: "Category" }).click()
    await page.getByRole("option", { name: categoryName }).click()
    const tagName = `tag-${Math.random().toString(36).substring(2, 8)}`
    await page.getByLabel("Add tag").fill(tagName)
    await page.getByLabel("Add tag").press("Enter")
    await expect(
      page.getByRole("button", { name: `Remove tag ${tagName}` }),
    ).toBeVisible()
    await page.getByLabel("SEO title").fill("x".repeat(10))
    await expect(page.getByText("10 / 60")).toBeVisible()
    await page.getByRole("button", { name: "Save draft" }).click()
    await expect(page.getByText("Post saved")).toBeVisible()
    await page.goto("/content/posts")
    await expect(
      page.getByRole("row").filter({ hasText: categoryName }),
    ).toBeVisible()

    // Pages use the same editor without post-only fields.
    await page.goto("/content/pages/new")
    const pageTitle = `Page ${Math.random().toString(36).substring(2, 8)}`
    await titleInput(page).fill(pageTitle)
    await expect(page.getByLabel("Excerpt")).toHaveCount(0)
    await bodyEditor(page).click()
    await page.keyboard.type("About us")
    await page.getByRole("button", { name: "Publish" }).click()
    await expect(page.getByText("Page published")).toBeVisible()
    await page.goto("/content/pages")
    // Search instead of relying on page 1: the list is sorted by title and paginated.
    await page.getByPlaceholder("Search by title").fill(pageTitle)
    await expect(
      page
        .getByRole("row")
        .filter({ hasText: pageTitle })
        .getByText("Published"),
    ).toBeVisible()
  })

  test("Member does not see Content and cannot open /content/posts", async ({
    page,
  }) => {
    await loginAsEditor(page, "member")
    await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible()
    await expect(
      page.getByRole("link", { name: "Content", exact: true }),
    ).toHaveCount(0)
    await page.goto("/content/posts")
    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByRole("heading", { name: "Posts" })).toHaveCount(0)
  })
})

test.describe("Content module disabled", () => {
  test("Content is hidden and /content/posts is not found", async ({
    page,
  }) => {
    await page.route("**/api/v1/utils/config", (route) =>
      route.fulfill({ json: { project_name: "Test", modules: [] } }),
    )
    await page.goto("/")
    await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible()
    await expect(
      page.getByRole("link", { name: "Content", exact: true }),
    ).toHaveCount(0)
    await page.goto("/content/posts")
    await expect(page.getByText("404")).toBeVisible()
  })
})

test.describe("Public links in the editor", () => {
  test.use({
    storageState: { cookies: [], origins: [] },
    permissions: ["clipboard-read", "clipboard-write"],
  })

  test("Published post: View on site, Copy link, list icon; draft: hint", async ({
    page,
  }) => {
    await loginAsEditor(page)
    await page.goto("/content/posts/new")
    const title = randomTitle()
    await titleInput(page).fill(title)
    await bodyEditor(page).click()
    await page.keyboard.type("Visible on the public site")
    const slug = title.toLowerCase().replace(/\s+/g, "-")

    await page.getByRole("button", { name: "Save draft" }).click()
    await expect(page.getByText("Post saved")).toBeVisible()
    await expect(page.getByText("Not published yet")).toBeVisible()
    await expect(page.getByRole("link", { name: "View on site" })).toHaveCount(
      0,
    )

    await page.getByRole("button", { name: "Publish" }).click()
    await expect(page.getByText("Post published")).toBeVisible()
    const view = page.getByRole("link", { name: "View on site", exact: true })
    await expect(view).toHaveAttribute("href", `/blog/${slug}`)
    await expect(view).toHaveAttribute("target", "_blank")
    await expect(view).toHaveAttribute("rel", /noopener/)

    // An unsaved slug edit keeps the saved link and shows a hint.
    await page.getByRole("textbox", { name: "Slug" }).fill(`${slug}-new`)
    await expect(page.getByText("Save to update the link")).toBeVisible()
    await expect(view).toHaveAttribute("href", `/blog/${slug}`)
    await page.getByRole("textbox", { name: "Slug" }).fill(slug)

    await page.getByRole("button", { name: "Copy link", exact: true }).click()
    await expect(page.getByText("Link copied")).toBeVisible()
    const origin = new URL(page.url()).origin
    // The Clipboard API only exists on secure pages (https or localhost). In CI the app
    // runs at http://backend:8000, where the app uses its execCommand fallback and the
    // test can't read the clipboard back, so only the toast is checked there.
    const secure = await page.evaluate(
      () => window.isSecureContext && Boolean(navigator.clipboard),
    )
    if (secure) {
      expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
        `${origin}/blog/${slug}`,
      )
    }

    const [popup] = await Promise.all([
      page.waitForEvent("popup"),
      view.click(),
    ])
    await expect(popup).toHaveURL(`${origin}/blog/${slug}`)
    await expect(
      popup.getByRole("heading", { name: title, level: 1 }),
    ).toBeVisible()
    await popup.close()

    // The list has an icon link for the published row.
    await page.goto("/content/posts")
    const icon = page.getByRole("link", {
      name: `View ${title} on site`,
      exact: true,
    })
    await expect(icon).toHaveAttribute("href", `/blog/${slug}`)
    await expect(icon).toHaveAttribute("target", "_blank")
  })

  test("Published page links to /p/<slug>; drafts have no list icon", async ({
    page,
  }) => {
    await loginAsEditor(page)
    await page.goto("/content/pages/new")
    const title = `Page ${Math.random().toString(36).substring(2, 8)}`
    await titleInput(page).fill(title)
    await page.getByRole("button", { name: "Save draft" }).click()
    await expect(page.getByText("Page saved")).toBeVisible()
    await page.goto("/content/pages")
    await page.getByPlaceholder("Search by title").fill(title)
    await expect(
      page.getByRole("link", { name: title, exact: true }),
    ).toBeVisible()
    await expect(
      page.getByRole("link", { name: `View ${title} on site`, exact: true }),
    ).toHaveCount(0)

    await page.getByRole("link", { name: title, exact: true }).click()
    await page.getByRole("button", { name: "Publish" }).click()
    await expect(page.getByText("Page published")).toBeVisible()
    const slug = title.toLowerCase().replace(/\s+/g, "-")
    await expect(
      page.getByRole("link", { name: "View on site", exact: true }),
    ).toHaveAttribute("href", `/p/${slug}`)
  })

  test("View blog opens /blog from the sidebar and the content header", async ({
    page,
  }) => {
    await loginAsEditor(page)
    await page
      .getByRole("link", { name: "View blog", exact: true })
      .first()
      .click()
    await expect(page).toHaveURL(/\/blog$/)

    await page.goto("/content/posts")
    await page.getByTestId("content-view-blog").click()
    await expect(page).toHaveURL(/\/blog$/)
  })

  test("Members also get the View blog link", async ({ page }) => {
    await loginAsEditor(page, "member")
    await page.getByRole("link", { name: "View blog", exact: true }).click()
    await expect(page).toHaveURL(/\/blog$/)
  })
})
