import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { ExternalLink, Plus, Search } from "lucide-react"
import { useEffect, useState } from "react"

import type { ContentStatus, PageSummary, PostSummary } from "@/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  type ContentKind,
  contentKeys,
  fetchPages,
  fetchPosts,
  type ListFilters,
  PAGE_SIZE,
  publicPath,
} from "../api"
import { ContentTabs, formatDate, StatusBadge } from "./shared"

const copy = {
  post: {
    title: "Posts",
    subtitle: "Write and publish blog posts",
    newLabel: "New post",
    empty: "No posts found",
  },
  page: {
    title: "Pages",
    subtitle: "Static pages such as About or Contact",
    newLabel: "New page",
    empty: "No pages found",
  },
} as const

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return debounced
}

function TitleLink({
  kind,
  id,
  title,
}: {
  kind: ContentKind
  id: string
  title: string
}) {
  return kind === "post" ? (
    <Link
      to="/content/posts/$id"
      params={{ id }}
      className="font-medium hover:underline"
    >
      {title}
    </Link>
  ) : (
    <Link
      to="/content/pages/$id"
      params={{ id }}
      className="font-medium hover:underline"
    >
      {title}
    </Link>
  )
}

export default function ContentListPage({ kind }: { kind: ContentKind }) {
  const text = copy[kind]
  const [status, setStatus] = useState<ContentStatus | "all">("all")
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(0)
  const q = useDebounced(search.trim(), 250)

  const filters: ListFilters = {
    status,
    q,
    skip: page * PAGE_SIZE,
    limit: PAGE_SIZE,
  }
  const { data, isLoading, isError } = useQuery({
    queryKey:
      kind === "post" ? contentKeys.posts(filters) : contentKeys.pages(filters),
    queryFn: () =>
      kind === "post" ? fetchPosts(filters) : fetchPages(filters),
    placeholderData: keepPreviousData,
  })

  const rows: (PostSummary | PageSummary)[] = data?.data ?? []
  const count = data?.count ?? 0
  const lastPage = Math.max(0, Math.ceil(count / PAGE_SIZE) - 1)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{text.title}</h1>
          <p className="text-muted-foreground">{text.subtitle}</p>
        </div>
        {kind === "post" ? (
          <Button asChild>
            <Link to="/content/posts/$id" params={{ id: "new" }}>
              <Plus />
              {text.newLabel}
            </Link>
          </Button>
        ) : (
          <Button asChild>
            <Link to="/content/pages/$id" params={{ id: "new" }}>
              <Plus />
              {text.newLabel}
            </Link>
          </Button>
        )}
      </div>

      <ContentTabs />

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
          <Input
            aria-label="Search by title"
            placeholder="Search by title"
            className="pl-8"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(0)
            }}
          />
        </div>
        <Select
          value={status}
          onValueChange={(v) => {
            setStatus(v as ContentStatus | "all")
            setPage(0)
          }}
        >
          <SelectTrigger aria-label="Filter by status" className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="draft">Draft</SelectItem>
            <SelectItem value="published">Published</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isError ? (
        <p role="alert" className="text-destructive">
          Could not load the list.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Status</TableHead>
              {kind === "post" && <TableHead>Category</TableHead>}
              <TableHead>Updated</TableHead>
              <TableHead className="w-12">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id}>
                <TableCell>
                  <TitleLink kind={kind} id={row.id} title={row.title} />
                </TableCell>
                <TableCell>
                  <StatusBadge status={row.status} />
                </TableCell>
                {kind === "post" && (
                  <TableCell className="text-muted-foreground">
                    {"category" in row ? (row.category?.name ?? "-") : "-"}
                  </TableCell>
                )}
                <TableCell className="text-muted-foreground">
                  {formatDate(row.updated_at)}
                </TableCell>
                <TableCell>
                  {row.status === "published" && (
                    <Button asChild variant="ghost" size="icon">
                      <a
                        href={publicPath(kind, row.slug)}
                        target="_blank"
                        rel="noopener"
                        aria-label={`View ${row.title} on site`}
                        title="View on site"
                      >
                        <ExternalLink />
                      </a>
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {!isLoading && rows.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={kind === "post" ? 5 : 4}
                  className="py-10 text-center text-muted-foreground"
                >
                  {text.empty}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}

      {count > PAGE_SIZE && (
        <div className="flex items-center justify-end gap-2">
          <span className="text-sm text-muted-foreground">
            Page {page + 1} of {lastPage + 1}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= lastPage}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  )
}
