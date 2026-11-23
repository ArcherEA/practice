import { Briefcase, FileText, type LucideIcon } from "lucide-react"

import type { UserPublic, UserRole } from "@/client"
import { hasRole } from "@/features/auth/permissions"

export type ModuleNavItem = {
  /** Module name, as in the backend MODULES setting. */
  module: string
  title: string
  icon: LucideIcon
  path: string
  /** Only users with this role (or a role that includes it, or a superuser) see the entry. */
  requiredRole?: UserRole
}

/** One entry per module with a sidebar link; add new modules here. */
export const moduleNavItems: ModuleNavItem[] = [
  { module: "items", title: "Items", icon: Briefcase, path: "/items" },
  {
    module: "content",
    title: "Content",
    icon: FileText,
    path: "/content",
    requiredRole: "editor",
  },
]

/** Whether the nav entry may be shown to this user (module enablement is checked separately). */
export const isNavItemVisible = (
  item: ModuleNavItem,
  user: Parameters<typeof hasRole>[0] | UserPublic | null | undefined,
): boolean => !item.requiredRole || hasRole(user, item.requiredRole)
