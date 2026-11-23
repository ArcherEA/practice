import { useQuery } from "@tanstack/react-query"
import { Link, useRouterState } from "@tanstack/react-router"
import { ChevronRight } from "lucide-react"
import { useState } from "react"

import type { ArchiveEntry } from "@/client"
import { cn } from "@/lib/utils"
import { menuPagesOptions, postsArchiveOptions } from "../api"

interface MonthGroup {
  key: string
  label: string
  posts: ArchiveEntry[]
}

interface YearGroup {
  year: number
  months: MonthGroup[]
}

/** Groups posts (already newest first) by year, then month. */
function groupArchive(entries: ArchiveEntry[]): YearGroup[] {
  const years: YearGroup[] = []
  for (const entry of entries) {
    const date = new Date(entry.published_at)
    const year = date.getFullYear()
    const key = `${year}-${String(date.getMonth() + 1).padStart(2, "0")}`
    let yearGroup = years.find((y) => y.year === year)
    if (!yearGroup) {
      yearGroup = { year, months: [] }
      years.push(yearGroup)
    }
    let month = yearGroup.months.find((m) => m.key === key)
    if (!month) {
      month = {
        key,
        label: date.toLocaleDateString("en-US", {
          month: "long",
          year: "numeric",
        }),
        posts: [],
      }
      yearGroup.months.push(month)
    }
    month.posts.push(entry)
  }
  return years
}

const linkClass = (current: boolean) =>
  cn(
    "block rounded-md px-2 py-1 text-sm hover:bg-accent hover:text-accent-foreground",
    current ? "bg-accent font-medium text-accent-foreground" : "",
  )

function Timeline({
  entries,
  currentSlug,
}: {
  entries: ArchiveEntry[]
  currentSlug: string | null
}) {
  const years = groupArchive(entries)
  const months = years.flatMap((y) => y.months)
  const currentMonth = currentSlug
    ? months.find((m) => m.posts.some((p) => p.slug === currentSlug))
    : undefined
  const defaultOpen = (currentMonth ?? months[0])?.key
  // Months the visitor toggled by hand win over the default.
  const [toggled, setToggled] = useState<Record<string, boolean>>({})
  const isOpen = (key: string) => toggled[key] ?? key === defaultOpen

  return (
    <div className="flex flex-col gap-3">
      {years.map((y) => (
        <div key={y.year} className="flex flex-col gap-1">
          <h3 className="px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {y.year}
          </h3>
          {y.months.map((m) => {
            const open = isOpen(m.key)
            const panelId = `timeline-${m.key}`
            return (
              <div key={m.key}>
                <button
                  type="button"
                  aria-expanded={open}
                  aria-controls={panelId}
                  onClick={() =>
                    setToggled((prev) => ({ ...prev, [m.key]: !open }))
                  }
                  className="flex w-full items-center gap-1 rounded-md px-2 py-1 text-left text-sm font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <ChevronRight
                    aria-hidden="true"
                    className={cn(
                      "size-4 shrink-0 transition-transform",
                      open ? "rotate-90" : "",
                    )}
                  />
                  <span className="flex-1">{m.label}</span>
                  <span className="text-xs text-muted-foreground">
                    {m.posts.length}
                  </span>
                </button>
                {open && (
                  <ul id={panelId} className="ml-4 border-l pl-2">
                    {m.posts.map((p) => (
                      <li key={p.slug}>
                        <Link
                          to="/blog/$slug"
                          params={{ slug: p.slug }}
                          aria-current={
                            p.slug === currentSlug ? "page" : undefined
                          }
                          className={linkClass(p.slug === currentSlug)}
                        >
                          {p.title}
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}

/** Timeline of posts and the published pages, shown beside (or below) the content. */
export function PublicSidebar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const postSlug = /^\/blog\/([^/]+)\/?$/.exec(pathname)?.[1]
  const pageSlug = /^\/p\/([^/]+)\/?$/.exec(pathname)?.[1]
  // /blog/category/x and /blog/tag/x have two segments, so they never match.
  const currentPost = postSlug ? decodeURIComponent(postSlug) : null
  const currentPage = pageSlug ? decodeURIComponent(pageSlug) : null

  // A failed request just hides the matching section.
  const { data: archive } = useQuery(postsArchiveOptions)
  const { data: menuPages } = useQuery(menuPagesOptions)
  const entries = archive?.data ?? []
  const pages = menuPages?.data ?? []

  if (entries.length === 0 && pages.length === 0) return null

  return (
    <aside
      aria-label="Sidebar"
      className="flex min-w-0 flex-col gap-8 border-t pt-8 lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:self-start lg:overflow-y-auto lg:border-t-0 lg:pt-0"
    >
      {entries.length > 0 && (
        <nav aria-label="Timeline">
          <h2 className="mb-2 px-2 text-base font-semibold">Timeline</h2>
          <Timeline entries={entries} currentSlug={currentPost} />
        </nav>
      )}
      {pages.length > 0 && (
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
      )}
    </aside>
  )
}
