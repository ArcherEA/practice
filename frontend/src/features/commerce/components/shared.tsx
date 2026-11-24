import { Link, useRouterState } from "@tanstack/react-router"

import type { ProductStatus } from "@/client"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { STATUS_LABEL } from "../api"

export function StatusBadge({ status }: { status: ProductStatus }) {
  if (status === "published") return <Badge>{STATUS_LABEL[status]}</Badge>
  return (
    <Badge variant={status === "archived" ? "outline" : "secondary"}>
      {STATUS_LABEL[status]}
    </Badge>
  )
}

/** Error text tied to a field through `id` (use it in `aria-describedby`). */
export function FieldError({
  id,
  message,
}: {
  id?: string
  message?: string | null
}) {
  if (!message) return null
  return (
    <p id={id} role="alert" className="text-sm text-destructive">
      {message}
    </p>
  )
}

const tabs = [
  { to: "/store/products", label: "Products" },
  { to: "/store/categories", label: "Categories" },
] as const

/** Section navigation shown on the store list screens. */
export function StoreTabs() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  return (
    <nav aria-label="Store sections" className="flex gap-1 border-b">
      {tabs.map((tab) => {
        const active = pathname.startsWith(tab.to)
        return (
          <Link
            key={tab.to}
            to={tab.to}
            aria-current={active ? "page" : undefined}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium",
              active
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.label}
          </Link>
        )
      })}
    </nav>
  )
}
