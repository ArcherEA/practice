import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Trash2 } from "lucide-react"
import { useId, useState } from "react"

import { CommerceService, type SlotAdmin } from "@/client"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"
import { ConfirmDeleteDialog } from "@/features/content/components/shared"
import useCustomToast from "@/hooks/useCustomToast"
import { commerceKeys, fetchSlots } from "../api"
import { errorText, parseApiError } from "../errors"
import {
  buildWindow,
  formatClock,
  formatSlotStart,
  parseClock,
  parseDate,
  repeatDates,
  type SlotWindow,
  todayIn,
  WEEKDAYS,
} from "../time"
import { FieldError } from "./shared"

const MAX_REPEAT_SLOTS = 200
const MAX_WEEKS = 52

type Mode = "single" | "repeat"

interface AddSlotsFormProps {
  productId: string
  timezone: string
  onCreated: () => void
}

/** Add one slot, or a weekly repeat. Times are typed in the store timezone and sent as UTC. */
function AddSlotsForm({ productId, timezone, onCreated }: AddSlotsFormProps) {
  const { showSuccessToast } = useCustomToast()
  const ids = {
    date: useId(),
    start: useId(),
    end: useId(),
    capacity: useId(),
    weeks: useId(),
  }
  const [mode, setMode] = useState<Mode>("single")
  const [date, setDate] = useState(() => todayIn(timezone))
  const [start, setStart] = useState("10:00")
  const [end, setEnd] = useState("11:00")
  const [capacity, setCapacity] = useState("1")
  const [weeks, setWeeks] = useState("4")
  const [weekdays, setWeekdays] = useState<number[]>([1, 2, 3, 4, 5])
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [result, setResult] = useState<string | null>(null)
  const [progress, setProgress] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: async () => {
      setResult(null)
      const found: Record<string, string> = {}
      const day = parseDate(date)
      const from = parseClock(start)
      const to = parseClock(end)
      const seats = /^\d+$/.test(capacity) ? Number(capacity) : 0
      const count = /^\d+$/.test(weeks) ? Number(weeks) : 0
      if (!day) found.date = "Choose a date"
      if (!from) found.start = "Choose a start time"
      if (!to) found.end = "Choose an end time"
      if (
        from &&
        to &&
        to.hour * 60 + to.minute <= from.hour * 60 + from.minute
      ) {
        found.end = "The end must be after the start"
      }
      if (seats < 1 || seats > 100_000) {
        found.capacity = "Capacity must be 1 or more"
      }
      if (mode === "repeat") {
        if (count < 1 || count > MAX_WEEKS) {
          found.weeks = `Use 1 to ${MAX_WEEKS} weeks`
        }
        if (weekdays.length === 0) found.weekdays = "Choose at least one day"
      }
      if (Object.keys(found).length > 0 || !day || !from || !to) {
        setErrors(found)
        return false
      }

      const dates =
        mode === "single" ? [day] : repeatDates(day, weekdays, count)
      if (dates.length > MAX_REPEAT_SLOTS) {
        setErrors({
          weeks: `That would create ${dates.length} slots (at most ${MAX_REPEAT_SLOTS} at once).`,
        })
        return false
      }
      const windows: SlotWindow[] = []
      const skippedClock: string[] = []
      for (const d of dates) {
        const w = buildWindow(d, from, to, timezone)
        if (w) windows.push(w)
        else skippedClock.push(`${d.year}-${d.month}-${d.day}`)
      }
      if (windows.length === 0) {
        setErrors({
          start: `That time does not exist in ${timezone} on that day (clock change).`,
        })
        return false
      }
      setErrors({})

      let created = 0
      const skipped: string[] = []
      const failed: string[] = []
      for (const [index, w] of windows.entries()) {
        setProgress(`Creating slot ${index + 1} of ${windows.length}...`)
        try {
          await CommerceService.adminCreateSlot({
            path: { product_id: productId },
            body: {
              starts_at: w.starts_at,
              ends_at: w.ends_at,
              capacity: seats,
            },
          })
          created++
        } catch (err) {
          const parsed = parseApiError(err)
          if (mode === "single") {
            // One slot: show the error on the right field.
            const fieldErrors: Record<string, string> = {}
            if (parsed.fields.capacity)
              fieldErrors.capacity = parsed.fields.capacity
            if (parsed.fields.starts_at)
              fieldErrors.start = parsed.fields.starts_at
            if (parsed.fields.ends_at) fieldErrors.end = parsed.fields.ends_at
            if (parsed.message) {
              fieldErrors[
                /same start and end/i.test(parsed.message) ? "start" : "general"
              ] = parsed.message
            }
            setErrors(fieldErrors)
            setProgress(null)
            return false
          }
          if (parsed.message && /already exists/i.test(parsed.message)) {
            skipped.push(w.label)
          } else {
            failed.push(`${w.label}: ${errorText(err)}`)
          }
        }
      }
      setProgress(null)
      const parts = [`${created} slot${created === 1 ? "" : "s"} created`]
      if (skipped.length > 0) {
        parts.push(`${skipped.length} skipped (already exist)`)
      }
      if (skippedClock.length > 0) {
        parts.push(
          `${skippedClock.length} skipped (time does not exist: clock change)`,
        )
      }
      if (failed.length > 0) parts.push(`${failed.length} failed`)
      if (failed.length > 0) {
        setErrors({ general: failed.join(" ") })
      }
      setResult(parts.join(", "))
      if (created > 0) showSuccessToast(parts[0])
      return true
    },
    onSettled: () => {
      setProgress(null)
      onCreated()
    },
    onError: (err) => setErrors({ general: errorText(err) }),
  })

  const toggleDay = (value: number, on: boolean) =>
    setWeekdays((list) =>
      on ? [...list, value] : list.filter((d) => d !== value),
    )

  return (
    <form
      noValidate
      className="flex flex-col gap-3 rounded-md border p-4"
      aria-label="Add slots"
      onSubmit={(e) => {
        e.preventDefault()
        create.mutate()
      }}
    >
      <fieldset className="inline-flex w-fit rounded-md border p-0.5">
        <legend className="sr-only">Slot type</legend>
        {(
          [
            ["single", "One slot"],
            ["repeat", "Weekly repeat"],
          ] as const
        ).map(([value, text]) => (
          <button
            key={value}
            type="button"
            aria-pressed={mode === value}
            onClick={() => setMode(value)}
            className={`rounded px-3 py-1 text-sm ${
              mode === value
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {text}
          </button>
        ))}
      </fieldset>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="grid gap-1.5">
          <Label htmlFor={ids.date}>
            {mode === "single" ? "Date" : "First date"}
          </Label>
          <Input
            id={ids.date}
            type="date"
            value={date}
            aria-invalid={!!errors.date}
            onChange={(e) => setDate(e.target.value)}
          />
          <FieldError message={errors.date} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor={ids.start}>Start ({timezone})</Label>
          <Input
            id={ids.start}
            type="time"
            value={start}
            aria-invalid={!!errors.start}
            onChange={(e) => setStart(e.target.value)}
          />
          <FieldError message={errors.start} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor={ids.end}>End ({timezone})</Label>
          <Input
            id={ids.end}
            type="time"
            value={end}
            aria-invalid={!!errors.end}
            onChange={(e) => setEnd(e.target.value)}
          />
          <FieldError message={errors.end} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor={ids.capacity}>Capacity</Label>
          <Input
            id={ids.capacity}
            inputMode="numeric"
            value={capacity}
            aria-invalid={!!errors.capacity}
            onChange={(e) => setCapacity(e.target.value)}
          />
          <FieldError message={errors.capacity} />
        </div>
      </div>

      {mode === "repeat" && (
        <div className="grid gap-3 sm:grid-cols-[auto_160px] sm:items-start">
          <fieldset className="grid gap-1.5">
            <legend className="mb-1 text-sm font-medium">Repeat on</legend>
            <div className="flex flex-wrap gap-3">
              {WEEKDAYS.map((d) => (
                <label
                  key={d.value}
                  htmlFor={`${ids.date}-day-${d.value}`}
                  className="flex items-center gap-1.5 text-sm"
                >
                  <Checkbox
                    id={`${ids.date}-day-${d.value}`}
                    checked={weekdays.includes(d.value)}
                    onCheckedChange={(c) => toggleDay(d.value, c === true)}
                  />
                  {d.label}
                </label>
              ))}
            </div>
            <FieldError message={errors.weekdays} />
          </fieldset>
          <div className="grid gap-1.5">
            <Label htmlFor={ids.weeks}>For how many weeks</Label>
            <Input
              id={ids.weeks}
              inputMode="numeric"
              value={weeks}
              aria-invalid={!!errors.weeks}
              onChange={(e) => setWeeks(e.target.value)}
            />
            <FieldError message={errors.weeks} />
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <LoadingButton type="submit" loading={create.isPending}>
          {mode === "single" ? "Add slot" : "Add slots"}
        </LoadingButton>
        {progress && (
          <span role="status" className="text-sm text-muted-foreground">
            {progress}
          </span>
        )}
        {result && !progress && (
          <span role="status" className="text-sm" data-testid="slots-result">
            {result}
          </span>
        )}
      </div>
      <FieldError message={errors.general} />
    </form>
  )
}

function SlotRow({
  slot,
  timezone,
  onChanged,
}: {
  slot: SlotAdmin
  timezone: string
  onChanged: () => void
}) {
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [capacity, setCapacity] = useState(String(slot.capacity))
  const [error, setError] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const update = useMutation({
    mutationFn: async (body: { capacity?: number; is_active?: boolean }) =>
      CommerceService.adminUpdateSlot({
        path: { slot_id: slot.id },
        body,
      }),
    onSuccess: () => setError(null),
    onError: (err) => {
      const parsed = parseApiError(err)
      setError(parsed.fields.capacity ?? parsed.message ?? errorText(err))
    },
    onSettled: onChanged,
  })
  const remove = useMutation({
    mutationFn: async () =>
      CommerceService.adminDeleteSlot({ path: { slot_id: slot.id } }),
    onSuccess: () => showSuccessToast("Slot deleted"),
    onError: (err) => showErrorToast(errorText(err)),
    onSettled: () => {
      setConfirmDelete(false)
      onChanged()
    },
  })

  const seats = /^\d+$/.test(capacity) ? Number(capacity) : null
  const capacityChanged = capacity !== String(slot.capacity)
  const when = `${formatSlotStart(slot.starts_at, timezone)} - ${formatClock(slot.ends_at, timezone)}`

  return (
    <li
      className="flex flex-wrap items-start gap-3 py-3"
      data-testid="slot-row"
    >
      <div className="min-w-56 flex-1">
        <p className="font-medium">{when}</p>
        {!slot.is_active && (
          <p className="text-sm text-muted-foreground">Deactivated</p>
        )}
      </div>
      <div className="grid gap-1">
        <div className="flex items-center gap-2">
          <Input
            aria-label={`Capacity of the slot on ${when}`}
            value={capacity}
            inputMode="numeric"
            className="w-20"
            aria-invalid={!!error}
            onChange={(e) => setCapacity(e.target.value)}
          />
          {capacityChanged && (
            <LoadingButton
              type="button"
              size="sm"
              variant="outline"
              loading={update.isPending}
              onClick={() => {
                if (seats === null || seats < 1) {
                  setError("Capacity must be 1 or more")
                  return
                }
                update.mutate({ capacity: seats })
              }}
            >
              Save
            </LoadingButton>
          )}
        </div>
        <FieldError message={error} />
      </div>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={update.isPending}
        onClick={() => update.mutate({ is_active: !slot.is_active })}
      >
        {slot.is_active ? "Deactivate" : "Activate"}
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        aria-label={`Delete the slot on ${when}`}
        onClick={() => setConfirmDelete(true)}
      >
        <Trash2 />
      </Button>
      <ConfirmDeleteDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete slot"
        description={`The slot on ${when} will be deleted.`}
        pending={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </li>
  )
}

interface SlotsPanelProps {
  productId: string
  timezone: string
}

export function SlotsPanel({ productId, timezone }: SlotsPanelProps) {
  const queryClient = useQueryClient()
  const [showPast, setShowPast] = useState(false)
  const { data, isLoading, isError } = useQuery({
    queryKey: commerceKeys.slots(productId),
    queryFn: () => fetchSlots(productId),
  })
  const reload = () =>
    queryClient.invalidateQueries({ queryKey: commerceKeys.slots(productId) })

  const nowMs = Date.now()
  const all = data?.data ?? []
  const upcoming = all.filter((s) => new Date(s.starts_at).getTime() > nowMs)
  const past = all.length - upcoming.length
  const shown = showPast ? all : upcoming

  return (
    <section aria-labelledby="slots-heading" className="flex flex-col gap-4">
      <div>
        <h3 id="slots-heading" className="font-semibold">
          Time slots
        </h3>
        <p className="text-sm text-muted-foreground">
          Bookable times with a capacity. All times are in the store timezone,{" "}
          <span className="font-medium" data-testid="store-timezone">
            {timezone}
          </span>
          .
        </p>
      </div>
      <AddSlotsForm
        productId={productId}
        timezone={timezone}
        onCreated={reload}
      />
      {isError ? (
        <FieldError message="Could not load the slots." />
      ) : (
        <>
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-sm font-medium">
              {showPast ? "All slots" : "Upcoming slots"} ({shown.length})
            </h4>
            {past > 0 && (
              <label
                htmlFor={`${productId}-show-past`}
                className="flex items-center gap-2 text-sm"
              >
                <Checkbox
                  id={`${productId}-show-past`}
                  checked={showPast}
                  onCheckedChange={(c) => setShowPast(c === true)}
                />
                Show {past} past slot{past === 1 ? "" : "s"}
              </label>
            )}
          </div>
          {shown.length === 0 && !isLoading ? (
            <p className="rounded-md border border-dashed py-6 text-center text-sm text-muted-foreground">
              No upcoming slots.
            </p>
          ) : (
            <ul
              className="divide-y rounded-md border px-4"
              data-testid="slot-list"
            >
              {shown.map((slot) => (
                <SlotRow
                  key={`${slot.id}:${slot.capacity}:${slot.is_active}`}
                  slot={slot}
                  timezone={timezone}
                  onChanged={reload}
                />
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}
