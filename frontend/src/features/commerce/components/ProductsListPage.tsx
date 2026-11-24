import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { Plus, Search } from "lucide-react"
import { useEffect, useState } from "react"

import type { ProductStatus, ProductType } from "@/client"
import { Badge } from "@/components/ui/badge"
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
  absoluteUrl,
  commerceKeys,
  fetchCategories,
  fetchProducts,
  PAGE_SIZE,
  type ProductFilters,
  TYPE_LABEL,
} from "../api"
import { NewProductDialog } from "./NewProductDialog"
import { StatusBadge, StoreTabs } from "./shared"

const ALL = "all"

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return debounced
}

const formatDate = (iso: string): string =>
  new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })

export default function ProductsListPage() {
  const [search, setSearch] = useState("")
  const [type, setType] = useState<ProductType | "all">(ALL)
  const [status, setStatus] = useState<ProductStatus | "all">(ALL)
  const [categoryId, setCategoryId] = useState("")
  const [page, setPage] = useState(0)
  const [creating, setCreating] = useState(false)
  const q = useDebounced(search.trim(), 250)

  const filters: ProductFilters = {
    q,
    type,
    status,
    categoryId,
    skip: page * PAGE_SIZE,
    limit: PAGE_SIZE,
  }
  const { data, isLoading, isError } = useQuery({
    queryKey: commerceKeys.products(filters),
    queryFn: () => fetchProducts(filters),
    placeholderData: keepPreviousData,
  })
  const { data: categoriesData } = useQuery({
    queryKey: commerceKeys.categories,
    queryFn: fetchCategories,
  })
  const categories = categoriesData?.data ?? []
  const categoryName = (id: string | null) =>
    id ? (categories.find((c) => c.id === id)?.name ?? "-") : "-"

  const rows = data?.data ?? []
  const count = data?.count ?? 0
  const lastPage = Math.max(0, Math.ceil(count / PAGE_SIZE) - 1)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Store</h1>
          <p className="text-muted-foreground">
            Products, prices, stock and bookings
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus />
          New product
        </Button>
      </div>

      <StoreTabs />

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
          value={type}
          onValueChange={(v) => {
            setType(v as ProductType | "all")
            setPage(0)
          }}
        >
          <SelectTrigger aria-label="Filter by type" className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All types</SelectItem>
            <SelectItem value="physical">Physical</SelectItem>
            <SelectItem value="digital">Digital</SelectItem>
            <SelectItem value="service">Service</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={status}
          onValueChange={(v) => {
            setStatus(v as ProductStatus | "all")
            setPage(0)
          }}
        >
          <SelectTrigger aria-label="Filter by status" className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All statuses</SelectItem>
            <SelectItem value="draft">Draft</SelectItem>
            <SelectItem value="published">Published</SelectItem>
            <SelectItem value="archived">Archived</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={categoryId || ALL}
          onValueChange={(v) => {
            setCategoryId(v === ALL ? "" : v)
            setPage(0)
          }}
        >
          <SelectTrigger aria-label="Filter by category" className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All categories</SelectItem>
            {categories.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isError ? (
        <p role="alert" className="text-destructive">
          Could not load the products.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-14">
                <span className="sr-only">Image</span>
              </TableHead>
              <TableHead>Title</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id}>
                <TableCell>
                  {row.image_url ? (
                    <img
                      src={absoluteUrl(row.image_url)}
                      alt=""
                      className="size-10 rounded object-cover"
                    />
                  ) : (
                    <div className="size-10 rounded bg-muted" aria-hidden />
                  )}
                </TableCell>
                <TableCell>
                  <Link
                    to="/store/products/$id"
                    params={{ id: row.id }}
                    className="font-medium hover:underline"
                  >
                    {row.title}
                  </Link>
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{TYPE_LABEL[row.type]}</Badge>
                </TableCell>
                <TableCell>
                  <StatusBadge status={row.status} />
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {categoryName(row.category_id)}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {formatDate(row.updated_at)}
                </TableCell>
              </TableRow>
            ))}
            {!isLoading && rows.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={6}
                  className="py-10 text-center text-muted-foreground"
                >
                  No products found
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

      {creating && <NewProductDialog onClose={() => setCreating(false)} />}
    </div>
  )
}
