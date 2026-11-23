import { ContentService, type ContentStatus } from "@/client"

export type ContentKind = "post" | "page"

export const contentKeys = {
  all: ["content"] as const,
  posts: (filters: ListFilters) => ["content", "posts", filters] as const,
  pages: (filters: ListFilters) => ["content", "pages", filters] as const,
  post: (id: string) => ["content", "post", id] as const,
  page: (id: string) => ["content", "page", id] as const,
  categories: ["content", "categories"] as const,
  tags: ["content", "tags"] as const,
}

export interface ListFilters {
  status: ContentStatus | "all"
  q: string
  skip: number
  limit: number
}

export const PAGE_SIZE = 20

export const fetchPosts = async (f: ListFilters) =>
  (
    await ContentService.readManagePosts({
      query: {
        status: f.status === "all" ? undefined : f.status,
        q: f.q || undefined,
        skip: f.skip,
        limit: f.limit,
      },
    })
  ).data

export const fetchPages = async (f: ListFilters) =>
  (
    await ContentService.readManagePages({
      query: {
        status: f.status === "all" ? undefined : f.status,
        q: f.q || undefined,
        skip: f.skip,
        limit: f.limit,
      },
    })
  ).data

export const fetchPost = async (id: string) =>
  (await ContentService.readManagePost({ path: { post_id: id } })).data

export const fetchPage = async (id: string) =>
  (await ContentService.readManagePage({ path: { page_id: id } })).data

export const fetchCategories = async () =>
  (await ContentService.readCategories()).data

export const fetchTags = async () => (await ContentService.readTags()).data

/** Where each kind lives in the admin UI. */
export const listPath = (kind: ContentKind) =>
  kind === "post" ? "/content/posts" : "/content/pages"
