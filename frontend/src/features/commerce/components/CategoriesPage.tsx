import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowDown, ArrowUp, Pencil, Plus, Trash2 } from "lucide-react"
import { useId, useState } from "react"

import { CommerceService, type ProductCategoryPublic } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ConfirmDeleteDialog } from "@/features/content/components/shared"
import useCustomToast from "@/hooks/useCustomToast"
import { commerceKeys, fetchCategories } from "../api"
import { errorText, type ParsedApiError, parseApiError } from "../errors"
import { FieldError, StoreTabs } from "./shared"

interface CategoryDialogProps {
  /** Null = create. */
  category: ProductCategoryPublic | null
  nextPosition: number
  onClose: () => void
}

function CategoryDialog({
  category,
  nextPosition,
  onClose,
}: CategoryDialogProps) {
  const queryClient = useQueryClient()
  const { showSuccessToast } = useCustomToast()
  const [name, setName] = useState(category?.name ?? "")
  const [slug, setSlug] = useState(category?.slug ?? "")
  const [position, setPosition] = useState(
    String(category?.position ?? nextPosition),
  )
  const [local, setLocal] = useState<Record<string, string>>({})
  const [error, setError] = useState<ParsedApiError | null>(null)
  const ids = { name: useId(), slug: useId(), position: useId() }

  const save = useMutation({
    mutationFn: async () => {
      const pos = Number(position)
      if (category) {
        return CommerceService.adminUpdateCategory({
          path: { category_id: category.id },
          body: {
            name: name.trim(),
            slug: slug.trim() || undefined,
            position: pos,
          },
        })
      }
      return CommerceService.adminCreateCategory({
        body: {
          name: name.trim(),
          slug: slug.trim() || undefined,
          position: pos,
        },
      })
    },
    onSuccess: () => {
      showSuccessToast(category ? "Category saved" : "Category created")
      queryClient.invalidateQueries({ queryKey: commerceKeys.categories })
      onClose()
    },
    onError: (err) => setError(parseApiError(err)),
  })

  const submit = () => {
    setError(null)
    const problems: Record<string, string> = {}
    if (!name.trim()) problems.name = "Name is required"
    if (!/^\d+$/.test(position.trim()) || Number(position) > 100_000) {
      problems.position = "Use a whole number from 0 to 100000"
    }
    setLocal(problems)
    if (Object.keys(problems).length > 0) return
    save.mutate()
  }

  const message = (field: "name" | "slug" | "position") =>
    local[field] ?? error?.fields[field] ?? null

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <form
          noValidate
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
        >
          <DialogHeader>
            <DialogTitle>
              {category ? "Edit category" : "New category"}
            </DialogTitle>
            <DialogDescription>
              Categories group products in the store. Lower positions come
              first.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            {(
              [
                ["name", "Name", name, setName, 100],
                ["slug", "Slug", slug, setSlug, 80],
                ["position", "Position", position, setPosition, 6],
              ] as const
            ).map(([field, label, value, set, max]) => (
              <div className="grid gap-2" key={field}>
                <Label htmlFor={ids[field]}>{label}</Label>
                <Input
                  id={ids[field]}
                  value={value}
                  maxLength={max}
                  inputMode={field === "position" ? "numeric" : undefined}
                  placeholder={
                    field === "slug" ? "Generated from the name" : undefined
                  }
                  aria-invalid={!!message(field)}
                  aria-describedby={
                    message(field) ? `${ids[field]}-error` : undefined
                  }
                  onChange={(e) => set(e.target.value)}
                />
                <FieldError
                  id={`${ids[field]}-error`}
                  message={message(field)}
                />
              </div>
            ))}
            {error?.message && <FieldError message={error.message} />}
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline" disabled={save.isPending}>
                Cancel
              </Button>
            </DialogClose>
            <LoadingButton type="submit" loading={save.isPending}>
              Save
            </LoadingButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export default function CategoriesPage() {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [editing, setEditing] = useState<ProductCategoryPublic | "new" | null>(
    null,
  )
  const [removing, setRemoving] = useState<ProductCategoryPublic | null>(null)
  const { data, isLoading, isError } = useQuery({
    queryKey: commerceKeys.categories,
    queryFn: fetchCategories,
  })
  const rows = data?.data ?? []

  const remove = useMutation({
    mutationFn: async (id: string) =>
      CommerceService.adminDeleteCategory({ path: { category_id: id } }),
    onSuccess: () => {
      showSuccessToast("Category deleted")
      setRemoving(null)
    },
    onError: (err) => showErrorToast(errorText(err)),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: commerceKeys.categories })
      queryClient.invalidateQueries({ queryKey: ["commerce", "products"] })
    },
  })

  // Moving renumbers the whole list (positions may be equal or have gaps), then
  // saves only the rows whose position changed.
  const reorder = useMutation({
    mutationFn: async ({ from, to }: { from: number; to: number }) => {
      const next = [...rows]
      const [moved] = next.splice(from, 1)
      next.splice(to, 0, moved)
      for (const [index, category] of next.entries()) {
        if (category.position !== index) {
          await CommerceService.adminUpdateCategory({
            path: { category_id: category.id },
            body: { position: index },
          })
        }
      }
    },
    onError: (err) => showErrorToast(errorText(err)),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: commerceKeys.categories }),
  })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Store</h1>
          <p className="text-muted-foreground">Product categories</p>
        </div>
        <Button onClick={() => setEditing("new")}>
          <Plus />
          New category
        </Button>
      </div>

      <StoreTabs />

      {isError ? (
        <p role="alert" className="text-destructive">
          Could not load the categories.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Slug</TableHead>
              <TableHead className="w-24">Position</TableHead>
              <TableHead className="w-40">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, index) => (
              <TableRow key={row.id}>
                <TableCell className="font-medium">{row.name}</TableCell>
                <TableCell className="text-muted-foreground">
                  {row.slug}
                </TableCell>
                <TableCell>{row.position}</TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Move ${row.name} up`}
                      disabled={index === 0 || reorder.isPending}
                      onClick={() =>
                        reorder.mutate({ from: index, to: index - 1 })
                      }
                    >
                      <ArrowUp />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Move ${row.name} down`}
                      disabled={index === rows.length - 1 || reorder.isPending}
                      onClick={() =>
                        reorder.mutate({ from: index, to: index + 1 })
                      }
                    >
                      <ArrowDown />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Edit ${row.name}`}
                      onClick={() => setEditing(row)}
                    >
                      <Pencil />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Delete ${row.name}`}
                      onClick={() => setRemoving(row)}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {!isLoading && rows.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={4}
                  className="py-10 text-center text-muted-foreground"
                >
                  No categories yet
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}

      {editing && (
        <CategoryDialog
          key={editing === "new" ? "new" : editing.id}
          category={editing === "new" ? null : editing}
          nextPosition={rows.length}
          onClose={() => setEditing(null)}
        />
      )}
      <ConfirmDeleteDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title="Delete category"
        description={`"${removing?.name ?? ""}" will be deleted. Its products stay in the store without a category.`}
        pending={remove.isPending}
        onConfirm={() => removing && remove.mutate(removing.id)}
      />
    </div>
  )
}
