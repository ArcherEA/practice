import { createUserWithRole } from "./privateApi.ts"
import { randomEmail, randomPassword } from "./random"

const base = () => `${process.env.VITE_API_URL}/api/v1`

/** A Tiptap body with a heading and one paragraph. */
export const textBody = (heading: string, text: string) => ({
  type: "doc",
  content: [
    {
      type: "heading",
      attrs: { level: 2 },
      content: [{ type: "text", text: heading }],
    },
    { type: "paragraph", content: [{ type: "text", text }] },
  ],
})

/** Creates an editor user and returns an API client acting as that user. */
export async function createEditorApi() {
  const email = randomEmail()
  const password = randomPassword()
  await createUserWithRole({ email, password, role: "editor" })
  const login = await fetch(`${base()}/login/access-token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: email, password }),
  })
  const { access_token } = await login.json()

  const call = async <T>(method: string, path: string, body?: unknown) => {
    const res = await fetch(`${base()}${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${access_token}`,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`${method} ${path} failed: ${res.status}`)
    return (await res.json()) as T
  }

  return {
    category: (name: string) =>
      call<{ id: string; slug: string }>("POST", "/content/manage/categories", {
        name,
      }),
    tag: (name: string) =>
      call<{ id: string; slug: string }>("POST", "/content/manage/tags", {
        name,
      }),
    /** Creates a post and publishes it unless `draft` is set. */
    async post(
      data: Record<string, unknown> & { title: string },
      { draft = false }: { draft?: boolean } = {},
    ) {
      const post = await call<{ id: string; slug: string }>(
        "POST",
        "/content/manage/posts",
        data,
      )
      if (!draft) await call("POST", `/content/manage/posts/${post.id}/publish`)
      return post
    },
    async page(
      data: Record<string, unknown> & { title: string },
      { draft = false }: { draft?: boolean } = {},
    ) {
      const page = await call<{ id: string; slug: string }>(
        "POST",
        "/content/manage/pages",
        data,
      )
      if (!draft) await call("POST", `/content/manage/pages/${page.id}/publish`)
      return page
    },
  }
}
