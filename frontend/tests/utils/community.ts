import { createUserWithRole } from "./privateApi.ts"
import { randomEmail, randomPassword } from "./random"

const base = () => `${process.env.VITE_API_URL}/api/v1`

type Role = "member" | "editor" | "moderator" | "admin"

/** Creates a user with a role and returns an API client acting as that user. */
export async function createUserApi(role: Role = "member") {
  const email = randomEmail()
  const password = randomPassword()
  await createUserWithRole({ email, password, role })
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
    email,
    password,
    comment: (postId: string, body: string, parentId?: string) =>
      call<{ id: string }>("POST", `/community/posts/${postId}/comments`, {
        body,
        parent_id: parentId,
      }),
    report: (
      commentId: string,
      reason: "spam" | "abuse" | "other",
      note?: string,
    ) =>
      call("POST", `/community/comments/${commentId}/report`, { reason, note }),
  }
}
