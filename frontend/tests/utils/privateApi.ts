// Note: the `PrivateService` is only available when generating the client
// for local environments
import { PrivateService } from "../../src/client"
import { client } from "../../src/client/client.gen"
import { firstSuperuser, firstSuperuserPassword } from "../config.ts"

client.setConfig({
  baseURL: `${process.env.VITE_API_URL}`,
})

export const createUser = async ({
  email,
  password,
}: {
  email: string
  password: string
}) => {
  const response = await PrivateService.createUser({
    body: {
      email,
      password,
      is_verified: true,
      full_name: "Test User",
    },
  })
  return response.data
}

/** Creates a user with a given role through the public admin API, as the first superuser. */
export const createUserWithRole = async ({
  email,
  password,
  role,
  isSuperuser = false,
}: {
  email: string
  password: string
  role: "member" | "editor" | "moderator" | "admin"
  isSuperuser?: boolean
}) => {
  const base = `${process.env.VITE_API_URL}/api/v1`
  const login = await fetch(`${base}/login/access-token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      username: firstSuperuser,
      password: firstSuperuserPassword,
    }),
  })
  const { access_token } = await login.json()
  const res = await fetch(`${base}/users/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${access_token}`,
    },
    body: JSON.stringify({
      email,
      password,
      role,
      is_superuser: isSuperuser,
      is_active: true,
      full_name: "Test User",
    }),
  })
  if (!res.ok) {
    throw new Error(`createUserWithRole failed: ${res.status}`)
  }
  return res.json()
}
