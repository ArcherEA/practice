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
    await page.getByRole("link", { name: title }).click()

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

    await page.getByRole("link", { name: `Tag ${id}` }).click()
    await expect(page).toHaveURL(`/blog/tag/${tag.slug}`)
    await expect(page.getByRole("link", { name: title })).toBeVisible()
    await expect.poll(() => page.title()).toBe(`Posts tagged Tag ${id}`)

    await page.goBack()
    await page.getByRole("link", { name: `Cat ${id}`, exact: true }).click()
    await expect(page).toHaveURL(`/blog/category/${category.slug}`)
    await expect(page.getByRole("link", { name: title })).toBeVisible()
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
      page.getByRole("link", { name: `Live post ${id}` }),
    ).toBeVisible()
    await expect(page.getByRole("link", { name: title })).toHaveCount(0)

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
})
