import type { UserPublic, UserRole } from "@/client"

/** Roles in display order, lowest privilege first. */
export const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: "member", label: "Member" },
  { value: "editor", label: "Editor" },
  { value: "moderator", label: "Moderator" },
  { value: "admin", label: "Admin" },
]

export const roleLabel = (role: UserRole = "member"): string =>
  ROLE_OPTIONS.find((o) => o.value === role)?.label ?? role

// Mirrors backend ROLE_INCLUDES (app/core/roles.py): a role satisfies itself
// and the roles listed here. editor and moderator are siblings.
const ROLE_INCLUDES: Record<UserRole, UserRole[]> = {
  admin: ["admin", "editor", "moderator", "member"],
  editor: ["editor", "member"],
  moderator: ["moderator", "member"],
  member: ["member"],
}

// Generated types mark role/is_superuser optional (they have defaults); treat
// missing values as member / not superuser.
type Actor =
  | Partial<Pick<UserPublic, "id" | "role" | "is_superuser">>
  | null
  | undefined
type Target = Partial<Pick<UserPublic, "id" | "role" | "is_superuser">>

export const hasRole = (actor: Actor, required: UserRole): boolean =>
  !!actor &&
  (!!actor.is_superuser ||
    ROLE_INCLUDES[actor.role ?? "member"].includes(required))

export const canManageUsers = (actor: Actor): boolean =>
  !!actor && (!!actor.is_superuser || actor.role === "admin")

const isPrivilegedTarget = (target: Target): boolean =>
  !!target.is_superuser || target.role === "admin"

/** Admins manage everyone except admins and superusers; superusers manage all. */
export const canEditUser = (actor: Actor, target: Target) => {
  if (!actor || !canManageUsers(actor)) return false
  return !!actor.is_superuser || !isPrivilegedTarget(target)
}

export const canDeleteUser = (actor: Actor, target: Target) =>
  canEditUser(actor, target) && actor?.id !== target.id
