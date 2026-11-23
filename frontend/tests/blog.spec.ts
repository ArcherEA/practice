import { expect, test } from "@playwright/test"
import { createEditorApi, textBody } from "./utils/content"

const unique = () => Math.random().toString(36).substring(2, 9)

// Public pages need no login.
test.use({ storageState: { cookies: [], origins: [] } })

test.describe("Public blog", () => {
  test("Anonymous visitor reads a post, follows category and tag, opens a page", async ({
    page,
  }) => {
    const id = unique()
    const api = await createEditorApi()
    const category = await api.category(`Cat ${id}`)
    const tag = await api.tag(`Tag ${id}`)
    const title = `Public post ${id}`
    const seoTitle = `SEO title ${id}`
    const bodyText = `Body text of ${id}`
    const post = await api.post({
      title,
      excerpt: `Excerpt ${id}`,
      body: textBody("A heading", bodyText),
      category_id: category.id,
      tag_ids: [tag.id],
      seo_title: seoTitle,
      seo_description: `Description ${id}`,
    })
    const pageTitle = `Public page ${id}`
    const staticPage = await api.page({
      title: pageTitle,
      body: textBody("About", `About text ${id}`),
    })

    await page.goto("/blog")
    await expect(page.getByRole("heading", { name: "Blog" })).toBeVisible()
    await expect(page.getByRole("link", { name: "Log in" })).toBeVisible()
    await page.getByRole("main").getByRole("link", { name: title }).click()

    // Client-side navigation: the title matches what the server injects.
    await expect(page).toHaveURL(`/blog/${post.slug}`)
    await expect(
      page.getByRole("heading", { name: title, level: 1 }),
    ).toBeVisible()
    await expect(page.getByTestId("content-renderer")).toContainText(bodyText)
    await expect.poll(() => page.title()).toBe(seoTitle)
    await expect(page.locator('meta[name="description"]')).toHaveAttribute(
      "content",
      `Description ${id}`,
    )

    await page
      .getByRole("main")
      .getByRole("link", { name: `Tag ${id}` })
      .click()
    await expect(page).toHaveURL(`/blog/tag/${tag.slug}`)
    await expect(
      page.getByRole("main").getByRole("link", { name: title }),
    ).toBeVisible()
    await expect.poll(() => page.title()).toBe(`Posts tagged Tag ${id}`)

    await page.goBack()
    await page
      .getByRole("main")
      .getByRole("link", { name: `Cat ${id}`, exact: true })
      .click()
    await expect(page).toHaveURL(`/blog/category/${category.slug}`)
    await expect(
      page.getByRole("main").getByRole("link", { name: title }),
    ).toBeVisible()
    await expect.poll(() => page.title()).toBe(`Cat ${id}`)

    await page.goto(`/p/${staticPage.slug}`)
    await expect(
      page.getByRole("heading", { name: pageTitle, level: 1 }),
    ).toBeVisible()
    await expect(page.getByTestId("content-renderer")).toContainText(
      `About text ${id}`,
    )
  })

  test("A draft is not listed and its URL shows not-found", async ({
    page,
  }) => {
    const id = unique()
    const api = await createEditorApi()
    const title = `Draft post ${id}`
    const draft = await api.post({ title }, { draft: true })
    const draftPage = await api.page(
      { title: `Draft page ${id}` },
      { draft: true },
    )
    const published = await api.post({ title: `Live post ${id}` })

    await page.goto("/blog")
    await expect(
      page.getByRole("main").getByRole("link", { name: `Live post ${id}` }),
    ).toBeVisible()
    await expect(
      page.getByRole("main").getByRole("link", { name: title }),
    ).toHaveCount(0)

    await page.goto(`/blog/${draft.slug}`)
    await expect(page.getByTestId("not-found")).toBeVisible()
    await page.goto(`/p/${draftPage.slug}`)
    await expect(page.getByTestId("not-found")).toBeVisible()
    await page.goto(`/blog/does-not-exist-${id}`)
    await expect(page.getByTestId("not-found")).toBeVisible()
    await page.goto(`/blog/tag/does-not-exist-${id}`)
    await expect(page.getByTestId("not-found")).toBeVisible()

    await page.goto(`/blog/${published.slug}`)
    await expect(
      page.getByRole("heading", { name: `Live post ${id}` }),
    ).toBeVisible()
  })

  test("Header and footer have no page links; the sidebar lists published pages only", async ({
    page,
  }) => {
    const id = unique()
    const api = await createEditorApi()
    // The sidebar lists the first pages by title, so sort ahead of other tests' pages.
    const live = await api.page({ title: `AAA Menu ${id}` })
    const draft = await api.page({ title: `AAA Draft ${id}` }, { draft: true })
    try {
      await page.goto("/blog")
      const sidebar = page.getByRole("complementary", {
        name: "Sidebar",
        exact: true,
      })
      const pages = sidebar.getByRole("navigation", {
        name: "Pages",
        exact: true,
      })
      await expect(
        pages.getByRole("link", { name: `AAA Menu ${id}`, exact: true }),
      ).toBeVisible()
      await expect(
        pages.getByRole("link", { name: `AAA Draft ${id}`, exact: true }),
      ).toHaveCount(0)

      // No page links in the header or footer, and no "More" menu.
      await expect(
        page.getByRole("banner").getByRole("link", { name: `AAA Menu ${id}` }),
      ).toHaveCount(0)
      await expect(
        page.locator("footer", { hasText: "©" }).getByRole("link"),
      ).toHaveCount(0)
      await expect(
        page.getByRole("button", { name: "More", exact: true }),
      ).toHaveCount(0)
      await expect(page.locator("footer", { hasText: "©" })).toBeVisible()

      await pages
        .getByRole("link", { name: `AAA Menu ${id}`, exact: true })
        .click()
      await expect(page).toHaveURL(`/p/${live.slug}`)
      await expect(
        page.getByRole("heading", { name: `AAA Menu ${id}`, level: 1 }),
      ).toBeVisible()
      // The current page is marked in the sidebar.
      await expect(
        sidebar.getByRole("link", { name: `AAA Menu ${id}`, exact: true }),
      ).toHaveAttribute("aria-current", "page")
    } finally {
      await api.deletePage(live.id)
      await api.deletePage(draft.id)
    }
  })

  test("The timeline lists a new post under its month and marks the current one", async ({
    page,
  }) => {
    const id = unique()
    const api = await createEditorApi()
    const title = `Timeline post ${id}`
    const post = await api.post({ title })
    const month = new Date().toLocaleDateString("en-US", {
      month: "long",
      year: "numeric",
    })

    await page.goto("/blog")
    const timeline = page.getByRole("navigation", {
      name: "Timeline",
      exact: true,
    })
    const toggle = timeline.getByRole("button", { name: month })
    await expect(toggle).toHaveAttribute("aria-expanded", "true")
    await timeline.getByRole("link", { name: title, exact: true }).click()
    await expect(page).toHaveURL(`/blog/${post.slug}`)
    await expect(
      timeline.getByRole("link", { name: title, exact: true }),
    ).toHaveAttribute("aria-current", "page")

    // Months collapse and expand with the button.
    await toggle.click()
    await expect(toggle).toHaveAttribute("aria-expanded", "false")
    await expect(
      timeline.getByRole("link", { name: title, exact: true }),
    ).toHaveCount(0)
    await toggle.click()
    await expect(
      timeline.getByRole("link", { name: title, exact: true }),
    ).toBeVisible()
  })

  test("On a narrow screen the sidebar sits below the content without overflow", async ({
    page,
  }) => {
    const api = await createEditorApi()
    await api.post({ title: `Narrow post ${unique()}` })
    await page.setViewportSize({ width: 375, height: 800 })
    await page.goto("/blog")
    const sidebar = page.getByRole("complementary", {
      name: "Sidebar",
      exact: true,
    })
    await expect(sidebar).toBeVisible()
    const main = await page.getByRole("main").boundingBox()
    const side = await sidebar.boundingBox()
    expect(main && side && side.y >= main.y + main.height - 1).toBe(true)
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth,
    )
    expect(overflow).toBe(false)
  })

  test("On a wide screen the sidebar sits beside the content", async ({
    page,
  }) => {
    const api = await createEditorApi()
    await api.post({ title: `Wide post ${unique()}` })
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.goto("/blog")
    const sidebar = page.getByRole("complementary", {
      name: "Sidebar",
      exact: true,
    })
    await expect(sidebar).toBeVisible()
    const main = await page.getByRole("main").boundingBox()
    const side = await sidebar.boundingBox()
    expect(main && side && side.x >= main.x + main.width - 1).toBe(true)
    expect(main && side && Math.abs(side.y - main.y) < 8).toBe(true)
  })
})
