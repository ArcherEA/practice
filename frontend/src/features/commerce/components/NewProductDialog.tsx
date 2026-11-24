import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { useId, useState } from "react"

import { CommerceService, type ProductType } from "@/client"
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
import { cn } from "@/lib/utils"
import { TYPE_HINT, TYPE_LABEL } from "../api"
import { type ParsedApiError, parseApiError } from "../errors"
import { FieldError } from "./shared"

const TYPES: ProductType[] = ["physical", "digital", "service"]

/** Step 1 of creating a product: the type first (it cannot change later), then a title. */
export function NewProductDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [type, setType] = useState<ProductType | null>(null)
  const [title, setTitle] = useState("")
  const [error, setError] = useState<ParsedApiError | null>(null)
  const [typeError, setTypeError] = useState(false)
  const [titleError, setTitleError] = useState<string | null>(null)
  const titleId = useId()
  const titleErrorId = useId()

  const create = useMutation({
    mutationFn: async () =>
      (
        await CommerceService.adminCreateProduct({
          body: { type: type as ProductType, title: title.trim() },
        })
      ).data,
    onSuccess: (product) => {
      queryClient.invalidateQueries({ queryKey: ["commerce", "products"] })
      onClose()
      navigate({ to: "/store/products/$id", params: { id: product.id } })
    },
    onError: (err) => setError(parseApiError(err)),
  })

  const submit = () => {
    setError(null)
    setTypeError(!type)
    const empty = !title.trim()
    setTitleError(empty ? "Title is required" : null)
    if (!type || empty) return
    create.mutate()
  }

  const serverTitleError = error?.fields.title ?? null

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <form
          noValidate
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
        >
          <DialogHeader>
            <DialogTitle>New product</DialogTitle>
            <DialogDescription>
              Choose what you sell. The type cannot be changed afterwards.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <fieldset className="grid gap-2">
              <legend className="mb-1 text-sm font-medium">Type</legend>
              <div className="grid gap-2 sm:grid-cols-3">
                {TYPES.map((t) => (
                  <button
                    key={t}
                    type="button"
                    aria-pressed={type === t}
                    data-testid={`product-type-${t}`}
                    onClick={() => {
                      setType(t)
                      setTypeError(false)
                    }}
                    className={cn(
                      "rounded-md border p-3 text-left text-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
                      type === t
                        ? "border-primary bg-accent"
                        : "hover:bg-accent/50",
                    )}
                  >
                    <span className="block font-medium">{TYPE_LABEL[t]}</span>
                    <span className="mt-1 block text-xs text-muted-foreground">
                      {TYPE_HINT[t]}
                    </span>
                  </button>
                ))}
              </div>
              {typeError && <FieldError message="Choose a product type" />}
            </fieldset>
            <div className="grid gap-2">
              <Label htmlFor={titleId}>Title</Label>
              <Input
                id={titleId}
                value={title}
                maxLength={255}
                aria-invalid={!!(titleError || serverTitleError)}
                aria-describedby={
                  titleError || serverTitleError ? titleErrorId : undefined
                }
                onChange={(e) => setTitle(e.target.value)}
              />
              <FieldError
                id={titleErrorId}
                message={titleError ?? serverTitleError}
              />
            </div>
            {error?.message && <FieldError message={error.message} />}
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button
                type="button"
                variant="outline"
                disabled={create.isPending}
              >
                Cancel
              </Button>
            </DialogClose>
            <LoadingButton type="submit" loading={create.isPending}>
              Create product
            </LoadingButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
