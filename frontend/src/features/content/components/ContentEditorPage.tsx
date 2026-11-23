import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useBlocker, useNavigate } from "@tanstack/react-router"
import type { JSONContent } from "@tiptap/react"
import { ArrowLeft, Eye, Pencil, Trash2 } from "lucide-react"
import { useRef, useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import {
  ContentService,
  type ContentStatus,
  type PagePublic,
  type PostPublic,
} from "@/client"
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
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"
import {
  type ContentKind,
  contentKeys,
  fetchCategories,
  fetchPage,
  fetchPost,
} from "../api"
import { EMPTY_BODY, slugify, toEditorContent } from "../body"
import { ContentRenderer } from "./ContentRenderer"
import { CharCounter, CoverImageField, TagPicker } from "./fields"
import { RichTextEditor } from "./RichTextEditor"
import { ConfirmDeleteDialog, StatusBadge } from "./shared"

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
  excerpt: z
    .string()
    .max(500, { message: "Excerpt is too long (500 characters at most)" }),
  categoryId: z.string(),
  tagIds: z.array(z.string()).max(30, { message: "At most 30 tags" }),
  coverFileId: z.string().nullable(),
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

interface Editable {
  id: string | null
  status: ContentStatus
  values: FormValues
  body: JSONContent
}

const emptyValues: FormValues = {
  title: "",
  slug: "",
  excerpt: "",
  categoryId: "",
  tagIds: [],
  coverFileId: null,
  seoTitle: "",
  seoDescription: "",
}

function fromPost(post: PostPublic): Editable {
  return {
    id: post.id,
    status: post.status,
    body: toEditorContent(post.body),
    values: {
      title: post.title,
      slug: post.slug,
      excerpt: post.excerpt ?? "",
      categoryId: post.category?.id ?? "",
      tagIds: post.tags.map((t) => t.id),
      coverFileId: post.cover_file_id ?? null,
      seoTitle: post.seo_title ?? "",
      seoDescription: post.seo_description ?? "",
    },
  }
}

function fromPage(page: PagePublic): Editable {
  return {
    id: page.id,
    status: page.status,
    body: toEditorContent(page.body),
    values: {
      ...emptyValues,
      title: page.title,
      slug: page.slug,
      seoTitle: page.seo_title ?? "",
      seoDescription: page.seo_description ?? "",
    },
  }
}

const blank: Editable = {
  id: null,
  status: "draft",
  values: emptyValues,
  body: EMPTY_BODY,
}

type Action = "save" | "publish" | "unpublish"

/** Create or update, then optionally publish/unpublish. Returns the final server state. */
async function persist(
  kind: ContentKind,
  current: Editable,
  values: FormValues,
  body: JSONContent,
  action: Action,
): Promise<Editable> {
  const seo = {
    seo_title: values.seoTitle.trim() || null,
    seo_description: values.seoDescription.trim() || null,
  }
  // Optional fields are sent as explicit nulls so clearing them in the form
  // clears them on the server (PostUpdate is a partial update).
  const slug = values.slug.trim() || undefined

  if (kind === "post") {
    const payload = {
      title: values.title.trim(),
      slug,
      excerpt: values.excerpt.trim() || null,
      body,
      cover_file_id: values.coverFileId,
      category_id: values.categoryId || null,
      tag_ids: values.tagIds,
      ...seo,
    }
    let post = current.id
      ? (
          await ContentService.updateManagePost({
            path: { post_id: current.id },
            body: payload,
          })
        ).data
      : (await ContentService.createManagePost({ body: payload })).data
    if (action === "publish") {
      post = (
        await ContentService.publishManagePost({ path: { post_id: post.id } })
      ).data
    } else if (action === "unpublish") {
      post = (
        await ContentService.unpublishManagePost({ path: { post_id: post.id } })
      ).data
    }
    return fromPost(post)
  }

  const payload = { title: values.title.trim(), slug, body, ...seo }
  let page = current.id
    ? (
        await ContentService.updateManagePage({
          path: { page_id: current.id },
          body: payload,
        })
      ).data
    : (await ContentService.createManagePage({ body: payload })).data
  if (action === "publish") {
    page = (
      await ContentService.publishManagePage({ path: { page_id: page.id } })
    ).data
  } else if (action === "unpublish") {
    page = (
      await ContentService.unpublishManagePage({ path: { page_id: page.id } })
    ).data
  }
  return fromPage(page)
}

interface EditorFormProps {
  kind: ContentKind
  initial: Editable
}

function EditorForm({ kind, initial }: EditorFormProps) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const [current, setCurrent] = useState<Editable>(initial)
  const [body, setBody] = useState<JSONContent>(initial.body)
  const [bodyDirty, setBodyDirty] = useState(false)
  const [preview, setPreview] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  // Existing items keep their slug when the title changes; new ones follow it.
  const slugTouched = useRef(initial.id !== null)
  const justSaved = useRef(false)

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    defaultValues: initial.values,
  })
  const { data: categoriesData } = useQuery({
    queryKey: contentKeys.categories,
    queryFn: fetchCategories,
    enabled: kind === "post",
  })

  const dirty = form.formState.isDirty || bodyDirty
  const dirtyRef = useRef(dirty)
  dirtyRef.current = dirty

  useBlocker({
    shouldBlockFn: () =>
      dirtyRef.current && !justSaved.current
        ? !window.confirm("You have unsaved changes. Leave without saving?")
        : false,
    enableBeforeUnload: () => dirtyRef.current,
  })

  const listTo = kind === "post" ? "/content/posts" : "/content/pages"
  const noun = kind === "post" ? "Post" : "Page"
  const isPublished = current.status === "published"

  const save = useMutation({
    mutationFn: ({ values, action }: { values: FormValues; action: Action }) =>
      persist(kind, current, values, body, action),
    onSuccess: (saved, { action }) => {
      showSuccessToast(
        action === "publish"
          ? `${noun} published`
          : action === "unpublish"
            ? `${noun} unpublished`
            : `${noun} saved`,
      )
      const wasNew = current.id === null
      setCurrent(saved)
      form.reset(saved.values)
      setBodyDirty(false)
      dirtyRef.current = false
      if (wasNew) {
        justSaved.current = true
        if (kind === "post") {
          navigate({
            to: "/content/posts/$id",
            params: { id: saved.id as string },
            replace: true,
          })
        } else {
          navigate({
            to: "/content/pages/$id",
            params: { id: saved.id as string },
            replace: true,
          })
        }
      }
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["content"] })
    },
  })

  const remove = useMutation({
    mutationFn: async () => {
      if (!current.id) return
      if (kind === "post") {
        await ContentService.deleteManagePost({ path: { post_id: current.id } })
      } else {
        await ContentService.deleteManagePage({ path: { page_id: current.id } })
      }
    },
    onSuccess: () => {
      showSuccessToast(`${noun} deleted`)
      justSaved.current = true
      dirtyRef.current = false
      navigate({ to: listTo })
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["content"] })
    },
  })

  const submit = (action: Action) =>
    form.handleSubmit((values) => save.mutate({ values, action }))

  const categories = categoriesData?.data ?? []
  const seoTitle = form.watch("seoTitle")
  const seoDescription = form.watch("seoDescription")
  const excerpt = form.watch("excerpt")
  const busy = save.isPending || remove.isPending

  return (
    <Form {...form}>
      <form
        className="flex flex-col gap-6"
        onSubmit={(e) => {
          e.preventDefault()
          submit("save")(e)
        }}
        noValidate
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Button asChild variant="ghost" size="sm">
              <Link to={listTo}>
                <ArrowLeft />
                {kind === "post" ? "Posts" : "Pages"}
              </Link>
            </Button>
            <h1 className="text-2xl font-bold tracking-tight">
              {current.id
                ? `Edit ${noun.toLowerCase()}`
                : `New ${noun.toLowerCase()}`}
            </h1>
            {current.id && <StatusBadge status={current.status} />}
            {dirty && (
              <span className="text-sm text-muted-foreground">
                Unsaved changes
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="outline"
              aria-pressed={preview}
              onClick={() => setPreview((p) => !p)}
            >
              {preview ? <Pencil /> : <Eye />}
              {preview ? "Edit" : "Preview"}
            </Button>
            {current.id && (
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => setConfirmDelete(true)}
              >
                <Trash2 />
                Delete
              </Button>
            )}
            {isPublished ? (
              <>
                <LoadingButton
                  type="button"
                  variant="outline"
                  loading={
                    save.isPending && save.variables?.action === "unpublish"
                  }
                  disabled={busy}
                  onClick={submit("unpublish")}
                >
                  Unpublish
                </LoadingButton>
                <LoadingButton
                  type="submit"
                  loading={save.isPending && save.variables?.action === "save"}
                  disabled={busy}
                >
                  Save changes
                </LoadingButton>
              </>
            ) : (
              <>
                <LoadingButton
                  type="submit"
                  variant="outline"
                  loading={save.isPending && save.variables?.action === "save"}
                  disabled={busy}
                >
                  Save draft
                </LoadingButton>
                <LoadingButton
                  type="button"
                  loading={
                    save.isPending && save.variables?.action === "publish"
                  }
                  disabled={busy}
                  onClick={submit("publish")}
                >
                  Publish
                </LoadingButton>
              </>
            )}
          </div>
        </div>

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
                    The URL part. Leave empty to generate it from the title.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex flex-col gap-2">
              <span className="text-sm font-medium">Body</span>
              <div hidden={preview}>
                <RichTextEditor
                  initialContent={initial.body}
                  onChange={(doc) => {
                    setBody(doc)
                    setBodyDirty(true)
                  }}
                />
              </div>
              {preview && (
                <div
                  className="min-h-[320px] rounded-md border px-4 py-3"
                  data-testid="body-preview"
                >
                  <ContentRenderer body={body} />
                </div>
              )}
            </div>
          </div>

          <aside className="flex flex-col gap-4">
            {kind === "post" && (
              <>
                <FormField
                  control={form.control}
                  name="excerpt"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Excerpt</FormLabel>
                      <FormControl>
                        <Textarea
                          {...field}
                          rows={3}
                          placeholder="A short summary for lists"
                        />
                      </FormControl>
                      <CharCounter value={excerpt} recommended={500} />
                      <FormMessage />
                    </FormItem>
                  )}
                />
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
                          <SelectItem value={NO_CATEGORY}>
                            No category
                          </SelectItem>
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
                <FormField
                  control={form.control}
                  name="tagIds"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Tags</FormLabel>
                      <TagPicker
                        value={field.value}
                        onChange={(ids) =>
                          form.setValue("tagIds", ids, { shouldDirty: true })
                        }
                      />
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="coverFileId"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Cover image</FormLabel>
                      <CoverImageField
                        value={field.value}
                        onChange={(id) =>
                          form.setValue("coverFileId", id, {
                            shouldDirty: true,
                          })
                        }
                      />
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </>
            )}
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
          title={`Delete ${noun.toLowerCase()}`}
          description={`This ${noun.toLowerCase()} will be permanently deleted. You will not be able to undo this action.`}
          pending={remove.isPending}
          onConfirm={() => remove.mutate()}
        />
      </form>
    </Form>
  )
}

interface ContentEditorPageProps {
  kind: ContentKind
  /** A UUID, or "new" to start a blank item. */
  id: string
}

export default function ContentEditorPage({
  kind,
  id,
}: ContentEditorPageProps) {
  const isNew = id === "new"
  const { data, isLoading, isError } = useQuery({
    queryKey: kind === "post" ? contentKeys.post(id) : contentKeys.page(id),
    queryFn: async () =>
      kind === "post"
        ? fromPost(await fetchPost(id))
        : fromPage(await fetchPage(id)),
    enabled: !isNew,
    // Always load fresh when opening an item: the editor copies it into form state.
    staleTime: 0,
    gcTime: 0,
  })

  if (isNew) return <EditorForm key="new" kind={kind} initial={blank} />
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
          Could not load this {kind}. It may have been deleted.
        </p>
        <Button asChild variant="outline">
          <Link to={kind === "post" ? "/content/posts" : "/content/pages"}>
            Back to the list
          </Link>
        </Button>
      </div>
    )
  }
  return <EditorForm key={id} kind={kind} initial={data} />
}
