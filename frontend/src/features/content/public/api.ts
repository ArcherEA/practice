import { queryOptions } from "@tanstack/react-query"
import { notFound } from "@tanstack/react-router"
import { AxiosError } from "axios"

import { ContentService } from "@/client"
import { API_BASE } from "../body"

export const POSTS_PER_PAGE = 10

export interface PostFilters {
  page: number
  category?: string
  tag?: string
}

export const publicKeys = {
  posts: (f: PostFilters) => ["public", "posts", f] as const,
  post: (slug: string) => ["public", "post", slug] as const,
  page: (slug: string) => ["public", "page", slug] as const,
  categories: ["public", "categories"] as const,
  tags: ["public", "tags"] as const,
}

export const publishedPostsOptions = (f: PostFilters) =>
  queryOptions({
    queryKey: publicKeys.posts(f),
    queryFn: async () =>
      (
        await ContentService.readPublishedPosts({
          query: {
            skip: (f.page - 1) * POSTS_PER_PAGE,
            limit: POSTS_PER_PAGE,
            category: f.category,
            tag: f.tag,
          },
        })
      ).data,
  })

export const publishedPostOptions = (slug: string) =>
  queryOptions({
    queryKey: publicKeys.post(slug),
    retry: false, // an unknown slug is a 404, not a flaky request
    queryFn: async () =>
      (await ContentService.readPublishedPost({ path: { slug } })).data,
  })

export const publishedPageOptions = (slug: string) =>
  queryOptions({
    queryKey: publicKeys.page(slug),
    retry: false,
    queryFn: async () =>
      (await ContentService.readPublishedPage({ path: { slug } })).data,
  })

export const categoriesOptions = queryOptions({
  queryKey: publicKeys.categories,
  queryFn: async () => (await ContentService.readCategories()).data,
})

export const tagsOptions = queryOptions({
  queryKey: publicKeys.tags,
  queryFn: async () => (await ContentService.readTags()).data,
})

/** Runs a loader fetch; an API 404 becomes the router's not-found state. */
export async function orNotFound<T>(request: () => Promise<T>): Promise<T> {
  try {
    return await request()
  } catch (error) {
    if (error instanceof AxiosError && error.response?.status === 404) {
      throw notFound()
    }
    throw error
  }
}

/** API image URLs are relative; prefix them with the API base (dev runs on another origin). */
export const apiUrl = (url: string): string =>
  url.startsWith("/") && !url.startsWith("//") ? `${API_BASE}${url}` : url

/** The meta values below mirror backend/app/modules/content/seo.py. */
const first = (...values: (string | null | undefined)[]): string =>
  values.find((v) => v?.trim())?.trim() ?? ""

export const postMeta = (post: {
  title: string
  excerpt?: string | null
  seo_title?: string | null
  seo_description?: string | null
}) => ({
  title: first(post.seo_title, post.title),
  description: first(post.seo_description, post.excerpt, post.title),
})

export const pageMeta = (page: {
  title: string
  seo_title?: string | null
  seo_description?: string | null
}) => ({
  title: first(page.seo_title, page.title),
  description: first(page.seo_description, page.title),
})

export const categoryMeta = (c: {
  name: string
  description?: string | null
}) => ({
  title: c.name,
  description: first(c.description, `Posts in ${c.name}.`),
})

export const tagMeta = (t: { name: string }) => ({
  title: `Posts tagged ${t.name}`,
  description: `Posts tagged ${t.name}.`,
})

export const blogIndexMeta = (siteName: string) => ({
  title: `Blog - ${siteName}`,
  description: `Latest articles from ${siteName}.`,
})

export const toHead = (meta: { title: string; description: string }) => ({
  meta: [
    { title: meta.title },
    { name: "description", content: meta.description },
  ],
})

export const formatDate = (iso: string | null | undefined): string =>
  iso
    ? new Date(iso).toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : ""
