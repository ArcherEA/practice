import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useBlocker, useNavigate } from "@tanstack/react-router"
import type { JSONContent } from "@tiptap/react"
import { ArrowLeft, Trash2 } from "lucide-react"
import { useRef, useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { CommerceService, type ProductAdmin } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import { slugify, toEditorContent } from "@/features/content/body"
import { CharCounter } from "@/features/content/components/fields"
import { RichTextEditor } from "@/features/content/components/RichTextEditor"
import { ConfirmDeleteDialog } from "@/features/content/components/shared"
import useCustomToast from "@/hooks/useCustomToast"
import {
  commerceKeys,
  fetchCategories,
  fetchProduct,
  TYPE_LABEL,
  useStoreConfig,
} from "../api"
import { type ParsedApiError, parseApiError } from "../errors"
import { ProductImagesField } from "./ProductImagesField"
import { SlotsPanel } from "./SlotsPanel"
import { FieldError, StatusBadge } from "./shared"
import { VariantsPanel } from "./VariantsPanel"

const formSchema = z.object({
  title: z
    .string()
    .trim()
    .min(1, { message: "Title is required" })
    .max(255, { message: "Title is too long (255 characters at most)" }),
  slug: z
    .string()
    .trim()
    .max(80, { message: "Slug is too long (80 characters at most)" }),
  categoryId: z.string(),
  seoTitle: z
    .string()
    .max(255, { message: "SEO title is too long (255 characters at most)" }),
  seoDescription: z.string().max(500, {
    message: "SEO description is too long (500 characters at most)",
  }),
})

type FormValues = z.infer<typeof formSchema>

const SEO_TITLE_RECOMMENDED = 60
const SEO_DESCRIPTION_RECOMMENDED = 160
const NO_CATEGORY = "none"

/** API field name -> form field. `description` and `image_file_ids` are not inputs of the form. */
const FORM_FIELDS: Record<string, keyof FormValues> = {
  title: "title",
  slug: "slug",
  category_id: "categoryId",
  seo_title: "seoTitle",
  seo_description: "seoDescription",
}

const toValues = (p: ProductAdmin): FormValues => ({
  title: p.title,
  slug: p.slug,
  categoryId: p.category_id ?? "",
  seoTitle: p.seo_title ?? "",
  seoDescription: p.seo_description ?? "",
})

type Action = "save" | "publish"

interface EditorFormProps {
  product: ProductAdmin
}

function EditorForm({ product }: EditorFormProps) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const { data: config } = useStoreConfig()
  const { data: categoriesData } = useQuery({
    queryKey: commerceKeys.categories,
    queryFn: fetchCategories,
  })
  const categories = categoriesData?.data ?? []

  // The form starts from the product as it was when the page opened; the live
  // `product` prop keeps status, options and variants current.
  const [initial] = useState(() => ({
    values: toValues(product),
    body: toEditorContent(product.description),
    images: product.image_file_ids,
  }))
  const [saved, setSaved] = useState(initial)
  const [body, setBody] = useState<JSONContent>(initial.body)
  const [bodyDirty, setBodyDirty] = useState(false)
  const [images, setImages] = useState<string[]>(initial.images)
  const [variantsDirty, setVariantsDirty] = useState(false)
  const [bodyError, setBodyError] = useState<string | null>(null)
  const [imagesError, setImagesError] = useState<string | null>(null)
  const [problem, setProblem] = useState<ParsedApiError | null>(null)
  const [publishIssues, setPublishIssues] = useState<string[]>([])
  const [confirmDelete, setConfirmDelete] = useState(false)
  const slugTouched = useRef(true)
  const justLeft = useRef(false)

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    defaultValues: initial.values,
  })

  const imagesDirty = images.join(",") !== saved.images.join(",")
  const dirty = form.formState.isDirty || bodyDirty || imagesDirty
  const anyDirty = dirty || variantsDirty
  const dirtyRef = useRef(anyDirty)
  dirtyRef.current = anyDirty

  useBlocker({
    shouldBlockFn: () =>
      dirtyRef.current && !justLeft.current
        ? !window.confirm("You have unsaved changes. Leave without saving?")
        : false,
    enableBeforeUnload: () => dirtyRef.current,
  })

  const refresh = async () =>
    queryClient.fetchQuery({
      queryKey: commerceKeys.product(product.id),
      queryFn: () => fetchProduct(product.id),
      staleTime: 0,
    })

  const showApiError = (err: unknown) => {
    const parsed = parseApiError(err)
    let leftover = parsed.message
    for (const [field, message] of Object.entries(parsed.fields)) {
      const formField = FORM_FIELDS[field]
      if (formField) form.setError(formField, { message })
      else if (field === "description") setBodyError(message)
      else if (field === "image_file_ids") setImagesError(message)
      else leftover = `${leftover ?? ""} ${field}: ${message}`.trim()
    }
    setProblem(leftover ? { fields: {}, message: leftover } : null)
    if (Object.keys(parsed.fields).length === 0 && parsed.message) {
      showErrorToast(parsed.message)
    }
  }

  const persist = async (values: FormValues): Promise<ProductAdmin> => {
    const updated = (
      await CommerceService.adminUpdateProduct({
        path: { product_id: product.id },
        body: {
          title: values.title.trim(),
          slug: values.slug.trim() || undefined,
          description: body,
          category_id: values.categoryId || null,
          image_file_ids: images,
          seo_title: values.seoTitle.trim() || null,
          seo_description: values.seoDescription.trim() || null,
        },
      })
    ).data
    queryClient.setQueryData(commerceKeys.product(product.id), updated)
    const next = {
      values: toValues(updated),
      body,
      images: updated.image_file_ids,
    }
    setSaved(next)
    form.reset(next.values)
    setBodyDirty(false)
    return updated
  }

  const save = useMutation({
    mutationFn: async ({
      values,
      action,
    }: {
      values: FormValues
      action: Action
    }) => {
      setProblem(null)
      setPublishIssues([])
      setBodyError(null)
      setImagesError(null)
      if (dirty || action === "save") await persist(values)
      if (action === "publish") {
        try {
          await CommerceService.adminPublishProduct({
            path: { product_id: product.id },
          })
        } catch (err) {
          const parsed = parseApiError(err)
          if (parsed.message) {
            setPublishIssues(parsed.message.split("; "))
          } else {
            showApiError(err)
          }
          await refresh()
          return false
        }
      }
      return true
    },
    onSuccess: async (ok, { action }) => {
      await refresh()
      if (ok)
        showSuccessToast(
          action === "publish" ? "Product published" : "Product saved",
        )
      else if (action === "publish")
        showErrorToast("The product cannot be published yet")
    },
    onError: showApiError,
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["commerce", "products"] })
    },
  })

  const changeStatus = useMutation({
    mutationFn: async (action: "unpublish" | "archive") => {
      setProblem(null)
      setPublishIssues([])
      return action === "unpublish"
        ? CommerceService.adminUnpublishProduct({
            path: { product_id: product.id },
          })
        : CommerceService.adminArchiveProduct({
            path: { product_id: product.id },
          })
    },
    onSuccess: async (_data, action) => {
      await refresh()
      showSuccessToast(
        action === "archive"
          ? "Product archived"
          : product.status === "archived"
            ? "Product restored to draft"
            : "Product unpublished",
      )
    },
    onError: showApiError,
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["commerce", "products"] })
    },
  })

  const remove = useMutation({
    mutationFn: async () =>
      CommerceService.adminDeleteProduct({ path: { product_id: product.id } }),
    onSuccess: () => {
      showSuccessToast("Product deleted")
      justLeft.current = true
      dirtyRef.current = false
      navigate({ to: "/store/products" })
    },
    onError: (err) => {
      setConfirmDelete(false)
      showApiError(err)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["commerce", "products"] })
    },
  })

  const submit = (action: Action) =>
    form.handleSubmit((values) => save.mutate({ values, action }))

  const status = product.status
  const isPublished = status === "published"
  const busy = save.isPending || changeStatus.isPending || remove.isPending
  const seoTitle = form.watch("seoTitle")
  const seoDescription = form.watch("seoDescription")

  return (
    <Form {...form}>
      <form
        className="flex flex-col gap-6"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          submit("save")(e)
        }}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <Button asChild variant="ghost" size="sm">
              <Link to="/store/products">
                <ArrowLeft />
                Products
              </Link>
            </Button>
            <h1 className="text-2xl font-bold tracking-tight">Edit product</h1>
            <Badge variant="outline">{TYPE_LABEL[product.type]}</Badge>
            <StatusBadge status={status} />
            {anyDirty && (
              <span className="text-sm text-muted-foreground">
                Unsaved changes
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={busy || isPublished}
              title={
                isPublished ? "Unpublish the product to delete it" : undefined
              }
              onClick={() => setConfirmDelete(true)}
            >
              <Trash2 />
              Delete
            </Button>
            {status !== "archived" && (
              <LoadingButton
                type="button"
                variant="outline"
                loading={
                  changeStatus.isPending && changeStatus.variables === "archive"
                }
                disabled={busy}
                onClick={() => changeStatus.mutate("archive")}
              >
                Archive
              </LoadingButton>
            )}
            {isPublished && (
              <LoadingButton
                type="button"
                variant="outline"
                loading={
                  changeStatus.isPending &&
                  changeStatus.variables === "unpublish"
                }
                disabled={busy}
                onClick={() => changeStatus.mutate("unpublish")}
              >
                Unpublish
              </LoadingButton>
            )}
            {status === "archived" && (
              <LoadingButton
                type="button"
                variant="outline"
                loading={changeStatus.isPending}
                disabled={busy}
                onClick={() => changeStatus.mutate("unpublish")}
              >
                Restore to draft
              </LoadingButton>
            )}
            <LoadingButton
              type="submit"
              variant={isPublished ? "default" : "outline"}
              loading={save.isPending && save.variables?.action === "save"}
              disabled={busy}
            >
              {isPublished ? "Save changes" : "Save draft"}
            </LoadingButton>
            {status === "draft" && (
              <LoadingButton
                type="button"
                loading={save.isPending && save.variables?.action === "publish"}
                disabled={busy || variantsDirty}
                title={variantsDirty ? "Save the variants first" : undefined}
                onClick={submit("publish")}
              >
                Publish
              </LoadingButton>
            )}
          </div>
        </div>

        {publishIssues.length > 0 && (
          <div
            role="alert"
            data-testid="publish-issues"
            className="rounded-md border border-destructive/50 p-4 text-sm"
          >
            <p className="font-medium text-destructive">
              The product cannot be published yet:
            </p>
            <ul className="mt-1 list-disc pl-5">
              {publishIssues.map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          </div>
        )}
        {problem?.message && <FieldError message={problem.message} />}

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="flex min-w-0 flex-col gap-4">
            <FormField
              control={form.control}
              name="title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    Title <span className="text-destructive">*</span>
                  </FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      placeholder="Title"
                      onChange={(e) => {
                        field.onChange(e)
                        if (!slugTouched.current) {
                          form.setValue("slug", slugify(e.target.value), {
                            shouldDirty: true,
                          })
                        }
                      }}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="slug"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Slug</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      placeholder="generated-from-the-title"
                      onChange={(e) => {
                        slugTouched.current = true
                        field.onChange(e)
                      }}
                    />
                  </FormControl>
                  <FormDescription>
                    The URL part of the product page.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="flex flex-col gap-2">
              <span className="text-sm font-medium">Description</span>
              <RichTextEditor
                initialContent={initial.body}
                onChange={(doc) => {
                  setBody(doc)
                  setBodyDirty(true)
                  setBodyError(null)
                }}
              />
              <FieldError message={bodyError} />
            </div>
          </div>

          <aside className="flex flex-col gap-4">
            <FormField
              control={form.control}
              name="categoryId"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Category</FormLabel>
                  <Select
                    value={field.value || NO_CATEGORY}
                    onValueChange={(v) =>
                      field.onChange(v === NO_CATEGORY ? "" : v)
                    }
                  >
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value={NO_CATEGORY}>No category</SelectItem>
                      {categories.map((c) => (
                        <SelectItem key={c.id} value={c.id}>
                          {c.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="flex flex-col gap-2">
              <span className="text-sm font-medium">Images</span>
              <ProductImagesField
                value={images}
                onChange={(ids) => {
                  setImages(ids)
                  setImagesError(null)
                }}
              />
              <FieldError message={imagesError} />
            </div>
            <FormField
              control={form.control}
              name="seoTitle"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>SEO title</FormLabel>
                  <FormControl>
                    <Input {...field} placeholder="Defaults to the title" />
                  </FormControl>
                  <CharCounter
                    value={seoTitle}
                    recommended={SEO_TITLE_RECOMMENDED}
                  />
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="seoDescription"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>SEO description</FormLabel>
                  <FormControl>
                    <Textarea
                      {...field}
                      rows={3}
                      placeholder="Shown in search results"
                    />
                  </FormControl>
                  <CharCounter
                    value={seoDescription}
                    recommended={SEO_DESCRIPTION_RECOMMENDED}
                  />
                  <FormMessage />
                </FormItem>
              )}
            />
          </aside>
        </div>

        <ConfirmDeleteDialog
          open={confirmDelete}
          onOpenChange={setConfirmDelete}
          title="Delete product"
          description="This product, its variants, prices, files and slots will be permanently deleted. You will not be able to undo this action."
          pending={remove.isPending}
          onConfirm={() => remove.mutate()}
        />
      </form>

      {config ? (
        <div className="flex flex-col gap-6">
          <section
            aria-labelledby="sellable-heading"
            className="flex flex-col gap-4 rounded-lg border p-4"
          >
            <h2 id="sellable-heading" className="text-lg font-semibold">
              Options, variants and prices
            </h2>
            <VariantsPanel
              product={product}
              config={config}
              refresh={refresh}
              onDirtyChange={setVariantsDirty}
            />
          </section>
          {product.type === "service" && (
            <section
              aria-labelledby="slots-section"
              className="flex flex-col gap-4 rounded-lg border p-4"
            >
              <h2 id="slots-section" className="text-lg font-semibold">
                Bookings
              </h2>
              <SlotsPanel productId={product.id} timezone={config.timezone} />
            </section>
          )}
        </div>
      ) : (
        <Skeleton className="h-40 w-full" />
      )}
    </Form>
  )
}

export default function ProductEditorPage({ id }: { id: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: commerceKeys.product(id),
    queryFn: () => fetchProduct(id),
    // Always load fresh when opening a product: the editor copies it into form state.
    staleTime: 0,
    gcTime: 0,
  })

  if (isLoading) {
    return (
      <div className="flex flex-col gap-4" aria-busy="true">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-80 w-full" />
      </div>
    )
  }
  if (isError || !data) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p role="alert" className="text-destructive">
          Could not load this product. It may have been deleted.
        </p>
        <Button asChild variant="outline">
          <Link to="/store/products">Back to the list</Link>
        </Button>
      </div>
    )
  }
  return <EditorForm key={id} product={data} />
}
