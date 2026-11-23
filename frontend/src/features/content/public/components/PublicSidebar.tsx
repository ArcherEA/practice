import { useQuery } from "@tanstack/react-query"
import { Link, useRouterState } from "@tanstack/react-router"

import { cn } from "@/lib/utils"
import { menuPagesOptions } from "../api"

const linkClass = (current: boolean) =>
  cn(
    "block rounded-md px-2 py-1 text-sm hover:bg-accent hover:text-accent-foreground",
    current ? "bg-accent font-medium text-accent-foreground" : "",
  )

/** Published pages, shown beside (desktop) or below (phones) the content. */
export function PublicSidebar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const pageSlug = /^\/p\/([^/]+)\/?$/.exec(pathname)?.[1]
  const currentPage = pageSlug ? decodeURIComponent(pageSlug) : null

  // A failed or empty request just hides the sidebar.
  const { data: menuPages } = useQuery(menuPagesOptions)
  const pages = menuPages?.data ?? []
  if (pages.length === 0) return null

  return (
    <aside
      aria-label="Sidebar"
      className="flex min-w-0 flex-col gap-8 border-t pt-8 lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:self-start lg:overflow-y-auto lg:border-t-0 lg:pt-0"
    >
      <nav aria-label="Pages">
        <h2 className="mb-2 px-2 text-base font-semibold">Pages</h2>
        <ul>
          {pages.map((p) => (
            <li key={p.id}>
              <Link
                to="/p/$slug"
                params={{ slug: p.slug }}
                aria-current={p.slug === currentPage ? "page" : undefined}
                className={linkClass(p.slug === currentPage)}
              >
                {p.title}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  )
}
