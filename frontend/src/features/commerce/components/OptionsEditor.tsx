import { useMutation } from "@tanstack/react-query"
import { Plus, Trash2 } from "lucide-react"
import { useState } from "react"

import { CommerceService, type OptionPublic } from "@/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import { type ParsedApiError, parseApiError } from "../errors"
import { MAX_OPTIONS } from "../variants"
import { FieldError } from "./shared"

interface OptionDraft {
  key: string
  id: string | null
  name: string
  valuesText: string
}

const toDraft = (o: OptionPublic): OptionDraft => ({
  key: o.id,
  id: o.id,
  name: o.name,
  valuesText: o.values.join(", "),
})

/** `S, M, L` -> `["S", "M", "L"]`. Empty entries are dropped. */
export const splitValues = (text: string): string[] =>
  text
    .split(/[,\n]/)
    .map((v) => v.trim())
    .filter(Boolean)

interface OptionsEditorProps {
  productId: string
  options: OptionPublic[]
  /** Names cannot change and options cannot be added or removed while variants exist (API rule). */
  locked: boolean
  onSaved: () => Promise<unknown>
}

type RowErrors = Record<
  string,
  { name?: string; values?: string; general?: string }
>

let counter = 0
const nextKey = () => `new-${++counter}`

/** Up to 3 options with their values. Saved with one button; the variant grid is built from them. */
export function OptionsEditor({
  productId,
  options,
  locked,
  onSaved,
}: OptionsEditorProps) {
  const { showSuccessToast } = useCustomToast()
  const [drafts, setDrafts] = useState<OptionDraft[]>(() =>
    options.map(toDraft),
  )
  const [errors, setErrors] = useState<RowErrors>({})
  const [general, setGeneral] = useState<ParsedApiError | null>(null)

  const dirty =
    drafts.length !== options.length ||
    drafts.some((d) => {
      const saved = options.find((o) => o.id === d.id)
      return (
        !saved ||
        saved.name !== d.name.trim() ||
        saved.values.join("\u0000") !== splitValues(d.valuesText).join("\u0000")
      )
    })

  const save = useMutation({
    mutationFn: async () => {
      const found: RowErrors = {}
      for (const d of drafts) {
        if (!d.name.trim()) found[d.key] = { name: "Name is required" }
        else if (splitValues(d.valuesText).length === 0) {
          found[d.key] = { values: "Add at least one value" }
        }
      }
      const names = drafts.map((d) => d.name.trim().toLowerCase())
      for (const [i, d] of drafts.entries()) {
        if (d.name.trim() && names.indexOf(names[i]) !== i) {
          found[d.key] = { name: "Option names must be different" }
        }
      }
      if (Object.keys(found).length > 0) {
        setErrors(found)
        return false
      }
      setErrors({})
      setGeneral(null)
      const keep = new Set(drafts.map((d) => d.id))
      let failed = false
      // Removed options first, then edits, then new ones: keeps the position order.
      for (const o of options) {
        if (!keep.has(o.id)) {
          try {
            await CommerceService.adminDeleteOption({
              path: { option_id: o.id },
            })
          } catch (err) {
            setGeneral(parseApiError(err))
            return false
          }
        }
      }
      for (const [position, d] of drafts.entries()) {
        const body = { name: d.name.trim(), values: splitValues(d.valuesText) }
        try {
          if (d.id) {
            const saved = options.find((o) => o.id === d.id)
            const changed =
              saved?.name !== body.name ||
              saved.values.join("\u0000") !== body.values.join("\u0000")
            if (changed) {
              await CommerceService.adminUpdateOption({
                path: { option_id: d.id },
                body: { ...body, position },
              })
            }
          } else {
            await CommerceService.adminCreateOption({
              path: { product_id: productId },
              body,
            })
          }
        } catch (err) {
          const parsed = parseApiError(err)
          found[d.key] = {
            name: parsed.fields.name,
            values: parsed.fields.values,
            general: parsed.message ?? undefined,
          }
          failed = true
        }
      }
      setErrors(found)
      return !failed
    },
    onSuccess: async (ok) => {
      if (ok) showSuccessToast("Options saved")
      // Reload even after a partial failure so the form matches the server.
      await onSaved()
    },
    onError: (err) => setGeneral(parseApiError(err)),
  })

  const update = (key: string, patch: Partial<OptionDraft>) =>
    setDrafts((list) =>
      list.map((d) => (d.key === key ? { ...d, ...patch } : d)),
    )

  return (
    <section aria-labelledby="options-heading" className="flex flex-col gap-3">
      <div>
        <h3 id="options-heading" className="font-semibold">
          Options
        </h3>
        <p className="text-sm text-muted-foreground">
          Up to {MAX_OPTIONS} options such as Size or Color; separate the values
          with commas.{" "}
          {locked &&
            "Delete the variants to rename, add or remove options. You can still add values."}
        </p>
      </div>
      {drafts.map((d, i) => (
        <div
          key={d.key}
          className="grid gap-2 sm:grid-cols-[180px_minmax(0,1fr)_auto] sm:items-start"
        >
          <div className="grid gap-1">
            <Input
              aria-label={`Option ${i + 1} name`}
              placeholder="Name, e.g. Size"
              value={d.name}
              maxLength={50}
              disabled={locked && d.id !== null}
              aria-invalid={!!errors[d.key]?.name}
              onChange={(e) => update(d.key, { name: e.target.value })}
            />
            <FieldError message={errors[d.key]?.name} />
          </div>
          <div className="grid gap-1">
            <Input
              aria-label={`Option ${i + 1} values`}
              placeholder="Values, e.g. S, M, L"
              value={d.valuesText}
              aria-invalid={!!errors[d.key]?.values}
              onChange={(e) => update(d.key, { valuesText: e.target.value })}
            />
            <FieldError message={errors[d.key]?.values} />
            <FieldError message={errors[d.key]?.general} />
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={`Remove option ${i + 1}`}
            disabled={locked}
            onClick={() =>
              setDrafts((list) => list.filter((x) => x.key !== d.key))
            }
          >
            <Trash2 />
          </Button>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={locked || drafts.length >= MAX_OPTIONS}
          onClick={() =>
            setDrafts((list) => [
              ...list,
              { key: nextKey(), id: null, name: "", valuesText: "" },
            ])
          }
        >
          <Plus />
          Add option
        </Button>
        <LoadingButton
          type="button"
          size="sm"
          loading={save.isPending}
          disabled={!dirty}
          onClick={() => save.mutate()}
        >
          Save options
        </LoadingButton>
        {dirty && (
          <span className="text-sm text-muted-foreground">
            Unsaved option changes
          </span>
        )}
      </div>
      {general && (
        <FieldError
          message={
            general.message ??
            Object.values(general.fields).join(" ") ??
            "Could not save the options"
          }
        />
      )}
    </section>
  )
}
