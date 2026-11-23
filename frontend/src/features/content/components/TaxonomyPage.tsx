import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Pencil, Plus, Trash2 } from "lucide-react"
import { useState } from "react"

import { ContentService } from "@/client"
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
import { Textarea } from "@/components/ui/textarea"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"
import { contentKeys, fetchCategories, fetchTags } from "../api"
import { ConfirmDeleteDialog, ContentTabs } from "./shared"

interface TermRow {
  id: string
  name: string
  slug: string
  description?: string | null
}

interface EditDialogProps {
  noun: "category" | "tag"
  term: TermRow | null
  onClose: () => void
  onSave: (values: { name: string; slug: string; description: string }) => void
  pending: boolean
}

function EditDialog({ noun, term, onClose, onSave, pending }: EditDialogProps) {
  const [name, setName] = useState(term?.name ?? "")
  const [slug, setSlug] = useState(term?.slug ?? "")
  const [description, setDescription] = useState(term?.description ?? "")
  const valid = name.trim().length > 0

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (valid)
              onSave({ name: name.trim(), slug: slug.trim(), description })
          }}
        >
          <DialogHeader>
            <DialogTitle>Edit {noun}</DialogTitle>
            <DialogDescription>
              Changing the slug changes the {noun}'s public address.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="term-name">Name</Label>
              <Input
                id="term-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={100}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="term-slug">Slug</Label>
              <Input
                id="term-slug"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                maxLength={80}
              />
            </div>
            {noun === "category" && (
              <div className="grid gap-2">
                <Label htmlFor="term-description">Description</Label>
                <Textarea
                  id="term-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={500}
                />
              </div>
            )}
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline" disabled={pending}>
                Cancel
              </Button>
            </DialogClose>
            <LoadingButton type="submit" loading={pending} disabled={!valid}>
              Save
            </LoadingButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

interface SectionProps {
  noun: "category" | "tag"
  title: string
  rows: TermRow[]
  isLoading: boolean
  onCreate: (name: string) => Promise<unknown>
  creating: boolean
  onUpdate: (
    id: string,
    values: { name: string; slug: string; description: string },
  ) => Promise<unknown>
  updating: boolean
  onDelete: (id: string) => Promise<unknown>
  deleting: boolean
}

function TaxonomySection({
  noun,
  title,
  rows,
  isLoading,
  onCreate,
  creating,
  onUpdate,
  updating,
  onDelete,
  deleting,
}: SectionProps) {
  const [name, setName] = useState("")
  const [editing, setEditing] = useState<TermRow | null>(null)
  const [removing, setRemoving] = useState<TermRow | null>(null)

  return (
    <section
      className="flex flex-col gap-3"
      aria-labelledby={`${noun}-heading`}
    >
      <h2 id={`${noun}-heading`} className="text-lg font-semibold">
        {title}
      </h2>
      <form
        className="flex gap-2"
        onSubmit={async (e) => {
          e.preventDefault()
          const value = name.trim()
          if (!value) return
          try {
            await onCreate(value)
            setName("")
          } catch {
            // The mutation's onError shows the message; keep the typed name.
          }
        }}
      >
        <Input
          aria-label={`New ${noun} name`}
          placeholder={`New ${noun} name`}
          value={name}
          maxLength={100}
          onChange={(e) => setName(e.target.value)}
        />
        <LoadingButton type="submit" loading={creating} disabled={!name.trim()}>
          <Plus />
          Add {noun}
        </LoadingButton>
      </form>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Slug</TableHead>
            <TableHead className="w-24 text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.id}>
              <TableCell className="font-medium">{row.name}</TableCell>
              <TableCell className="text-muted-foreground">
                {row.slug}
              </TableCell>
              <TableCell className="text-right">
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Edit ${noun} ${row.name}`}
                  onClick={() => setEditing(row)}
                >
                  <Pencil />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Delete ${noun} ${row.name}`}
                  onClick={() => setRemoving(row)}
                >
                  <Trash2 />
                </Button>
              </TableCell>
            </TableRow>
          ))}
          {!isLoading && rows.length === 0 && (
            <TableRow>
              <TableCell
                colSpan={3}
                className="py-8 text-center text-muted-foreground"
              >
                No {noun === "category" ? "categories" : "tags"} yet
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      {editing && (
        <EditDialog
          key={editing.id}
          noun={noun}
          term={editing}
          pending={updating}
          onClose={() => setEditing(null)}
          onSave={async (values) => {
            try {
              await onUpdate(editing.id, values)
              setEditing(null)
            } catch {
              // Error toast comes from the mutation.
            }
          }}
        />
      )}
      <ConfirmDeleteDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={`Delete ${noun}`}
        description={
          noun === "category"
            ? `"${removing?.name}" will be deleted. Posts in it stay, but lose their category.`
            : `"${removing?.name}" will be deleted and removed from all posts.`
        }
        pending={deleting}
        onConfirm={async () => {
          if (!removing) return
          try {
            await onDelete(removing.id)
            setRemoving(null)
          } catch {
            // Error toast comes from the mutation.
          }
        }}
      />
    </section>
  )
}

export default function TaxonomyPage() {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const categories = useQuery({
    queryKey: contentKeys.categories,
    queryFn: fetchCategories,
  })
  const tags = useQuery({ queryKey: contentKeys.tags, queryFn: fetchTags })

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["content"] })
  const onError = handleError.bind(showErrorToast)

  const createCategory = useMutation({
    mutationFn: async (name: string) =>
      ContentService.createManageCategory({ body: { name } }),
    onSuccess: () => showSuccessToast("Category created"),
    onError,
    onSettled: refresh,
  })
  const updateCategory = useMutation({
    mutationFn: async (v: {
      id: string
      name: string
      slug: string
      description: string
    }) =>
      ContentService.updateManageCategory({
        path: { category_id: v.id },
        body: {
          name: v.name,
          slug: v.slug || undefined,
          description: v.description.trim() || null,
        },
      }),
    onSuccess: () => showSuccessToast("Category updated"),
    onError,
    onSettled: refresh,
  })
  const deleteCategory = useMutation({
    mutationFn: async (id: string) =>
      ContentService.deleteManageCategory({ path: { category_id: id } }),
    onSuccess: () => showSuccessToast("Category deleted"),
    onError,
    onSettled: refresh,
  })

  const createTag = useMutation({
    mutationFn: async (name: string) =>
      ContentService.createManageTag({ body: { name } }),
    onSuccess: () => showSuccessToast("Tag created"),
    onError,
    onSettled: refresh,
  })
  const updateTag = useMutation({
    mutationFn: async (v: { id: string; name: string; slug: string }) =>
      ContentService.updateManageTag({
        path: { tag_id: v.id },
        body: { name: v.name, slug: v.slug || undefined },
      }),
    onSuccess: () => showSuccessToast("Tag updated"),
    onError,
    onSettled: refresh,
  })
  const deleteTag = useMutation({
    mutationFn: async (id: string) =>
      ContentService.deleteManageTag({ path: { tag_id: id } }),
    onSuccess: () => showSuccessToast("Tag deleted"),
    onError,
    onSettled: refresh,
  })

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Categories & tags</h1>
        <p className="text-muted-foreground">
          Organize posts. A post has one category and any number of tags.
        </p>
      </div>
      <ContentTabs />
      <div className="grid gap-8 lg:grid-cols-2">
        <TaxonomySection
          noun="category"
          title="Categories"
          rows={categories.data?.data ?? []}
          isLoading={categories.isLoading}
          onCreate={(name) => createCategory.mutateAsync(name)}
          creating={createCategory.isPending}
          onUpdate={(id, v) => updateCategory.mutateAsync({ id, ...v })}
          updating={updateCategory.isPending}
          onDelete={(id) => deleteCategory.mutateAsync(id)}
          deleting={deleteCategory.isPending}
        />
        <TaxonomySection
          noun="tag"
          title="Tags"
          rows={tags.data?.data ?? []}
          isLoading={tags.isLoading}
          onCreate={(name) => createTag.mutateAsync(name)}
          creating={createTag.isPending}
          onUpdate={(id, v) =>
            updateTag.mutateAsync({ id, name: v.name, slug: v.slug })
          }
          updating={updateTag.isPending}
          onDelete={(id) => deleteTag.mutateAsync(id)}
          deleting={deleteTag.isPending}
        />
      </div>
    </div>
  )
}
