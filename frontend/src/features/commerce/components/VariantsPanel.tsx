import { useMutation } from "@tanstack/react-query"
import { Trash2 } from "lucide-react"
import { useEffect, useMemo, useState } from "react"

import {
  CommerceService,
  type CurrencyInfo,
  type ProductAdmin,
  type StoreConfig,
  type VariantAdmin,
} from "@/client"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import { ConfirmDeleteDialog } from "@/features/content/components/shared"
import { FileUpload } from "@/features/files/FileUpload"
import useCustomToast from "@/hooks/useCustomToast"
import { formatBytes } from "../api"
import { errorText, parseApiError } from "../errors"
import { moneyExample, parseMoney } from "../money"
import { useProductFileUpload } from "../useProductFileUpload"
import {
  draftFromVariant,
  draftsEqual,
  MAX_GENERATED,
  missingCombinations,
  priceOf,
  type RowErrors,
  suggestSku,
  type VariantDraft,
  validateDraft,
  variantSignature,
} from "../variants"
import { OptionsEditor } from "./OptionsEditor"
import { FieldError } from "./shared"

interface Props {
  product: ProductAdmin
  config: StoreConfig
  /** Reloads the product and resolves with the fresh copy. */
  refresh: () => Promise<ProductAdmin>
  onDirtyChange: (dirty: boolean) => void
}

interface Edit {
  /** Signature of the saved variant this edit started from; a different one means the edit is stale. */
  base: string
  draft: VariantDraft
}

const label = (variant: VariantAdmin, product: ProductAdmin): string => {
  const parts = product.options
    .map((o) => variant.option_values[o.name])
    .filter(Boolean)
  return parts.length > 0 ? parts.join(" / ") : "Default"
}

/** Digital product: the private file of one variant (name and size, replace). */
function VariantFileCell({
  variant,
  refresh,
}: {
  variant: VariantAdmin
  refresh: () => Promise<unknown>
}) {
  const { upload, isUploading, progress, error } = useProductFileUpload()
  const [problem, setProblem] = useState<string | null>(null)
  const file = variant.file

  return (
    <div className="flex min-w-48 flex-col gap-1">
      {file ? (
        <span
          className="text-sm"
          data-testid={`variant-file-name-${variant.sku}`}
        >
          {file.filename}{" "}
          <span className="text-muted-foreground">
            ({formatBytes(file.size)})
          </span>
        </span>
      ) : (
        <span className="text-sm text-muted-foreground">No file yet</span>
      )}
      <FileUpload
        label={file ? "Replace file" : "Upload file"}
        isUploading={isUploading}
        progress={progress}
        error={error ?? problem}
        testId={`variant-file-${variant.sku}`}
        onSelect={async (selected) => {
          setProblem(null)
          const uploaded = await upload(selected)
          if (!uploaded) return
          try {
            await CommerceService.adminUpdateVariant({
              path: { variant_id: variant.id },
              body: { file_id: uploaded.id },
            })
            await refresh()
          } catch (err) {
            setProblem(errorText(err))
          }
        }}
      />
    </div>
  )
}

export function VariantsPanel({
  product,
  config,
  refresh,
  onDirtyChange,
}: Props) {
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const currencies: CurrencyInfo[] = config.currencies
  const isPhysical = product.type === "physical"
  const isDigital = product.type === "digital"
  const variants = product.variants
  const [edits, setEdits] = useState<Record<string, Edit>>({})
  const [rowErrors, setRowErrors] = useState<Record<string, RowErrors>>({})
  const [removing, setRemoving] = useState<VariantAdmin | null>(null)
  const [removingAll, setRemovingAll] = useState(false)
  const [generateMessage, setGenerateMessage] = useState<string | null>(null)

  // A stored edit counts only while the saved variant is still the one it started from.
  const draftOf = (v: VariantAdmin): VariantDraft => {
    const edit = edits[v.id]
    return edit && edit.base === variantSignature(v)
      ? edit.draft
      : draftFromVariant(v, currencies)
  }
  const isDirty = (v: VariantAdmin) =>
    !draftsEqual(draftOf(v), draftFromVariant(v, currencies))
  const dirtyVariants = variants.filter(isDirty)

  useEffect(() => {
    onDirtyChange(dirtyVariants.length > 0)
  })

  const setDraft = (v: VariantAdmin, patch: Partial<VariantDraft>) => {
    const next = { ...draftOf(v), ...patch }
    setEdits((all) => ({
      ...all,
      [v.id]: { base: variantSignature(v), draft: next },
    }))
  }
  const setPrice = (v: VariantAdmin, currency: string, text: string) =>
    setDraft(v, { prices: { ...draftOf(v).prices, [currency]: text } })

  const missing = useMemo(
    () => missingCombinations(product.options, variants),
    [product.options, variants],
  )

  const generate = useMutation({
    mutationFn: async () => {
      setGenerateMessage(null)
      if (missing.length > MAX_GENERATED) {
        setGenerateMessage(
          `That would create ${missing.length} variants (at most ${MAX_GENERATED} at once). Use fewer option values.`,
        )
        return
      }
      const taken = new Set(variants.map((v) => v.sku))
      const failures: string[] = []
      let created = 0
      for (const [index, values] of missing.entries()) {
        let sku = suggestSku(product.slug, values, product.options, index)
        for (let n = 2; taken.has(sku); n++) sku = `${sku.slice(0, 58)}-${n}`
        taken.add(sku)
        try {
          await CommerceService.adminCreateVariant({
            path: { product_id: product.id },
            body: { sku, option_values: values },
          })
          created++
        } catch (err) {
          failures.push(`${sku}: ${errorText(err)}`)
        }
      }
      if (failures.length > 0) {
        setGenerateMessage(
          `Created ${created}, failed ${failures.length}. ${failures.join(" ")}`,
        )
      } else {
        showSuccessToast(
          created === 1 ? "Variant created" : `${created} variants created`,
        )
      }
    },
    onSettled: () => refresh(),
  })

  const saveAll = useMutation({
    mutationFn: async () => {
      // Check every changed row first; nothing is sent while a field is invalid.
      const problems: Record<string, RowErrors> = {}
      for (const v of dirtyVariants) {
        const found = validateDraft(draftOf(v), currencies)
        if (Object.keys(found).length > 0) problems[v.id] = found
      }
      setRowErrors(problems)
      if (Object.keys(problems).length > 0) return { saved: 0, failed: -1 }

      const failed: Record<string, RowErrors> = {}
      const submitted = new Map<string, VariantDraft>()
      let saved = 0
      for (const v of dirtyVariants) {
        const draft = draftOf(v)
        const errors: RowErrors = {}
        const fail = (err: unknown, priceCurrency?: string) => {
          const parsed = parseApiError(err)
          for (const [field, message] of Object.entries(parsed.fields)) {
            const key =
              field === "amount" && priceCurrency
                ? `price:${priceCurrency}`
                : field === "is_active"
                  ? "general"
                  : field
            errors[key] = message
          }
          if (parsed.message) {
            const key =
              !priceCurrency && /\bsku\b/i.test(parsed.message)
                ? "sku"
                : priceCurrency
                  ? `price:${priceCurrency}`
                  : "general"
            errors[key] = parsed.message
          }
        }
        for (const c of currencies) {
          const text = draft.prices[c.code]?.trim() ?? ""
          const parsed = text ? parseMoney(text, c.exponent) : null
          const current = priceOf(v, c.code)
          if (parsed?.ok && parsed.amount !== current) {
            try {
              await CommerceService.adminSetPrice({
                path: { variant_id: v.id, currency: c.code },
                body: { amount: parsed.amount },
              })
            } catch (err) {
              fail(err, c.code)
            }
          }
        }
        const body: {
          sku?: string
          stock?: number | null
          is_active?: boolean
        } = {}
        if (draft.sku.trim().toUpperCase() !== v.sku) {
          body.sku = draft.sku.trim()
        }
        const stock = draft.stock.trim() === "" ? null : Number(draft.stock)
        if (stock !== v.stock) body.stock = stock
        if (draft.active !== v.is_active) body.is_active = draft.active
        if (Object.keys(body).length > 0) {
          try {
            await CommerceService.adminUpdateVariant({
              path: { variant_id: v.id },
              body,
            })
          } catch (err) {
            fail(err)
          }
        }
        // Removing a price last: a published product rejects a variant without one.
        for (const c of currencies) {
          const text = draft.prices[c.code]?.trim() ?? ""
          if (!text && priceOf(v, c.code) !== undefined) {
            try {
              await CommerceService.adminDeletePrice({
                path: { variant_id: v.id, currency: c.code },
              })
            } catch (err) {
              fail(err, c.code)
            }
          }
        }
        if (Object.keys(errors).length > 0) {
          failed[v.id] = errors
          submitted.set(v.id, draft)
        } else {
          saved++
        }
      }
      const fresh = await refresh()
      // Keep what the admin typed in rows that failed, based on the fresh saved copy.
      setEdits(() => {
        const kept: Record<string, Edit> = {}
        for (const v of fresh.variants) {
          const draft = submitted.get(v.id)
          if (draft) kept[v.id] = { base: variantSignature(v), draft }
        }
        return kept
      })
      setRowErrors(failed)
      return { saved, failed: Object.keys(failed).length }
    },
    onSuccess: ({ saved, failed }) => {
      if (failed === -1) {
        showErrorToast("Fix the highlighted fields first")
      } else if (failed > 0) {
        showErrorToast(
          `${failed} variant${failed === 1 ? "" : "s"} could not be saved`,
        )
      } else if (saved > 0) {
        showSuccessToast("Variants saved")
      }
    },
    onError: (err) => showErrorToast(errorText(err)),
  })

  const removeOne = useMutation({
    mutationFn: async (variant: VariantAdmin) =>
      CommerceService.adminDeleteVariant({ path: { variant_id: variant.id } }),
    onSuccess: () => {
      showSuccessToast("Variant deleted")
      setRemoving(null)
    },
    onError: (err) => {
      showErrorToast(errorText(err))
      setRemoving(null)
    },
    onSettled: () => refresh(),
  })

  const removeAll = useMutation({
    mutationFn: async () => {
      for (const v of variants) {
        await CommerceService.adminDeleteVariant({ path: { variant_id: v.id } })
      }
    },
    onSuccess: () => {
      showSuccessToast("Variants deleted")
      setRemovingAll(false)
    },
    onError: (err) => {
      showErrorToast(errorText(err))
      setRemovingAll(false)
    },
    onSettled: () => refresh(),
  })

  const optionSignature = JSON.stringify(
    product.options.map((o) => [o.id, o.name, o.values]),
  )
  const hasOptions = product.options.length > 0
  const generateLabel = hasOptions
    ? missing.length === 0
      ? "All combinations exist"
      : `Generate ${missing.length} variant${missing.length === 1 ? "" : "s"}`
    : "Add the default variant"

  return (
    <div className="flex flex-col gap-6">
      <OptionsEditor
        key={optionSignature}
        productId={product.id}
        options={product.options}
        locked={variants.length > 0}
        onSaved={refresh}
      />

      <section
        aria-labelledby="variants-heading"
        className="flex flex-col gap-3"
      >
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 id="variants-heading" className="font-semibold">
              Variants
            </h3>
            <p className="text-sm text-muted-foreground">
              One row per combination. Prices are normal amounts such as{" "}
              {moneyExample(currencies[0]?.exponent ?? 2)}, one per currency; an
              empty price means the variant is not sold in that currency.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <LoadingButton
              type="button"
              variant="outline"
              size="sm"
              loading={generate.isPending}
              disabled={missing.length === 0}
              onClick={() => generate.mutate()}
            >
              {generateLabel}
            </LoadingButton>
            {variants.length > 0 && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setRemovingAll(true)}
              >
                Delete all variants
              </Button>
            )}
          </div>
        </div>
        {generateMessage && <FieldError message={generateMessage} />}

        {variants.length === 0 ? (
          <p className="rounded-md border border-dashed py-8 text-center text-sm text-muted-foreground">
            No variants yet.{" "}
            {hasOptions
              ? "Save the options, then generate the variants."
              : "Add the default variant, or define options first."}
          </p>
        ) : (
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-sm" data-testid="variant-grid">
              <thead className="bg-muted/50 text-left">
                <tr>
                  <th className="px-3 py-2 font-medium">Variant</th>
                  <th className="px-3 py-2 font-medium">SKU</th>
                  {isPhysical && (
                    <th className="px-3 py-2 font-medium">Stock</th>
                  )}
                  <th className="px-3 py-2 font-medium">Active</th>
                  {currencies.map((c) => (
                    <th key={c.code} className="px-3 py-2 font-medium">
                      Price {c.code.toUpperCase()}
                    </th>
                  ))}
                  {isDigital && <th className="px-3 py-2 font-medium">File</th>}
                  <th className="px-3 py-2">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {variants.map((v) => {
                  const draft = draftOf(v)
                  const errors = rowErrors[v.id] ?? {}
                  return (
                    <tr
                      key={v.id}
                      className="border-t align-top"
                      data-testid={`variant-row-${v.sku}`}
                    >
                      <td className="px-3 py-2 font-medium whitespace-nowrap">
                        {label(v, product)}
                        <FieldError message={errors.general} />
                      </td>
                      <td className="px-3 py-2">
                        <Input
                          aria-label={`SKU of ${label(v, product)}`}
                          value={draft.sku}
                          maxLength={64}
                          className="w-40"
                          aria-invalid={!!errors.sku}
                          onChange={(e) => setDraft(v, { sku: e.target.value })}
                        />
                        <FieldError message={errors.sku} />
                      </td>
                      {isPhysical && (
                        <td className="px-3 py-2">
                          <Input
                            aria-label={`Stock of ${label(v, product)}`}
                            value={draft.stock}
                            inputMode="numeric"
                            className="w-24"
                            aria-invalid={!!errors.stock}
                            onChange={(e) =>
                              setDraft(v, { stock: e.target.value })
                            }
                          />
                          <FieldError message={errors.stock} />
                        </td>
                      )}
                      <td className="px-3 py-2">
                        <Checkbox
                          aria-label={`Active: ${label(v, product)}`}
                          checked={draft.active}
                          onCheckedChange={(checked) =>
                            setDraft(v, { active: checked === true })
                          }
                        />
                      </td>
                      {currencies.map((c) => {
                        const error = errors[`price:${c.code}`]
                        return (
                          <td key={c.code} className="px-3 py-2">
                            <Input
                              aria-label={`Price ${c.code.toUpperCase()} of ${label(v, product)}`}
                              value={draft.prices[c.code] ?? ""}
                              inputMode="decimal"
                              placeholder={moneyExample(c.exponent)}
                              className="w-28"
                              aria-invalid={!!error}
                              onChange={(e) =>
                                setPrice(v, c.code, e.target.value)
                              }
                            />
                            <FieldError message={error} />
                          </td>
                        )
                      })}
                      {isDigital && (
                        <td className="px-3 py-2">
                          <VariantFileCell variant={v} refresh={refresh} />
                        </td>
                      )}
                      <td className="px-3 py-2">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          aria-label={`Delete variant ${label(v, product)}`}
                          onClick={() => setRemoving(v)}
                        >
                          <Trash2 />
                        </Button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {variants.length > 0 && (
          <div className="flex flex-wrap items-center gap-3">
            <LoadingButton
              type="button"
              loading={saveAll.isPending}
              disabled={dirtyVariants.length === 0}
              onClick={() => saveAll.mutate()}
            >
              Save variants
            </LoadingButton>
            {dirtyVariants.length > 0 && (
              <span className="text-sm text-muted-foreground">
                {dirtyVariants.length} variant
                {dirtyVariants.length === 1 ? "" : "s"} with unsaved changes
              </span>
            )}
          </div>
        )}
      </section>

      <ConfirmDeleteDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title="Delete variant"
        description={`The variant ${removing ? label(removing, product) : ""} (${removing?.sku ?? ""}) and its prices${removing?.file ? " and file" : ""} will be deleted.`}
        pending={removeOne.isPending}
        onConfirm={() => removing && removeOne.mutate(removing)}
      />
      <ConfirmDeleteDialog
        open={removingAll}
        onOpenChange={setRemovingAll}
        title="Delete all variants"
        description="Every variant with its prices and files will be deleted, so that the options can be changed."
        pending={removeAll.isPending}
        onConfirm={() => removeAll.mutate()}
      />
    </div>
  )
}
