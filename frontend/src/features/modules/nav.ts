import { Briefcase, type LucideIcon } from "lucide-react"

export type ModuleNavItem = {
  /** Module name, as in the backend MODULES setting. */
  module: string
  title: string
  icon: LucideIcon
  path: string
}

/** One entry per module with a sidebar link; add new modules here. */
export const moduleNavItems: ModuleNavItem[] = [
  { module: "items", title: "Items", icon: Briefcase, path: "/items" },
]
