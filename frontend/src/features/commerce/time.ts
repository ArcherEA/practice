/**
 * Time helpers for service slots. The API stores UTC instants; admins think in the
 * store's timezone (`STORE_TIMEZONE`, from `GET /commerce/config`), which can differ
 * from their browser's. Only `Intl` is used (no date library).
 */

export interface WallTime {
  year: number
  month: number // 1-12
  day: number
  hour: number
  minute: number
}

export interface CalendarDate {
  year: number
  month: number // 1-12
  day: number
}

const partsCache = new Map<string, Intl.DateTimeFormat>()

function formatter(timeZone: string): Intl.DateTimeFormat {
  let f = partsCache.get(timeZone)
  if (!f) {
    f = new Intl.DateTimeFormat("en-GB", {
      timeZone,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    })
    partsCache.set(timeZone, f)
  }
  return f
}

/** Wall-clock fields of an instant in `timeZone`. */
export function wallTimeIn(instant: Date | number, timeZone: string): WallTime {
  const parts = formatter(timeZone).formatToParts(instant)
  const get = (type: string) =>
    Number(parts.find((p) => p.type === type)?.value ?? "0")
  return {
    year: get("year"),
    month: get("month"),
    day: get("day"),
    hour: get("hour") % 24,
    minute: get("minute"),
  }
}

const asUtcMs = (w: WallTime): number =>
  Date.UTC(w.year, w.month - 1, w.day, w.hour, w.minute)

/**
 * The instant at which the clocks in `timeZone` show `wall`. Returns null for a time
 * that does not exist there (skipped by a clock change). For a time that happens
 * twice (clocks go back) the earlier one is used.
 */
export function zonedTimeToUtc(wall: WallTime, timeZone: string): Date | null {
  const target = asUtcMs(wall)
  const offsetAt = (ms: number) => asUtcMs(wallTimeIn(ms, timeZone)) - ms
  let guess = target - offsetAt(target)
  guess = target - offsetAt(guess)
  // Check the round trip: it fails exactly for times inside a clock-change gap.
  if (asUtcMs(wallTimeIn(guess, timeZone)) !== target) return null
  // Earlier of two candidates when the hour repeats.
  const earlier = guess - 3_600_000
  if (asUtcMs(wallTimeIn(earlier, timeZone)) === target)
    return new Date(earlier)
  return new Date(guess)
}

const dayFormat = new Map<string, Intl.DateTimeFormat>()

/** `Mon 24 Nov 2026, 10:00` in the store timezone. */
export function formatSlotStart(iso: string, timeZone: string): string {
  let f = dayFormat.get(timeZone)
  if (!f) {
    f = new Intl.DateTimeFormat("en-GB", {
      timeZone,
      hourCycle: "h23",
      weekday: "short",
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
    dayFormat.set(timeZone, f)
  }
  return f.format(new Date(iso))
}

/** `10:30` in the store timezone. */
export function formatClock(iso: string, timeZone: string): string {
  const w = wallTimeIn(new Date(iso), timeZone)
  return `${String(w.hour).padStart(2, "0")}:${String(w.minute).padStart(2, "0")}`
}

/** `2026-11-24` -> parts. Null when the text is not a real calendar date. */
export function parseDate(text: string): CalendarDate | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text)
  if (!m) return null
  const date = { year: Number(m[1]), month: Number(m[2]), day: Number(m[3]) }
  const check = new Date(Date.UTC(date.year, date.month - 1, date.day))
  if (
    check.getUTCFullYear() !== date.year ||
    check.getUTCMonth() !== date.month - 1 ||
    check.getUTCDate() !== date.day
  ) {
    return null
  }
  return date
}

/** `10:30` -> minutes since midnight. Null when invalid. */
export function parseClock(
  text: string,
): { hour: number; minute: number } | null {
  const m = /^(\d{2}):(\d{2})$/.exec(text)
  if (!m) return null
  const hour = Number(m[1])
  const minute = Number(m[2])
  return hour < 24 && minute < 60 ? { hour, minute } : null
}

/** Weekday of a calendar date: 0 = Sunday ... 6 = Saturday. */
export const weekdayOf = (d: CalendarDate): number =>
  new Date(Date.UTC(d.year, d.month - 1, d.day)).getUTCDay()

export function addDays(d: CalendarDate, days: number): CalendarDate {
  const next = new Date(Date.UTC(d.year, d.month - 1, d.day + days))
  return {
    year: next.getUTCFullYear(),
    month: next.getUTCMonth() + 1,
    day: next.getUTCDate(),
  }
}

/** Today's calendar date in `timeZone`, as `YYYY-MM-DD`. */
export function todayIn(timeZone: string): string {
  const w = wallTimeIn(new Date(), timeZone)
  return `${w.year}-${String(w.month).padStart(2, "0")}-${String(w.day).padStart(2, "0")}`
}

export const WEEKDAYS = [
  { value: 1, label: "Mon" },
  { value: 2, label: "Tue" },
  { value: 3, label: "Wed" },
  { value: 4, label: "Thu" },
  { value: 5, label: "Fri" },
  { value: 6, label: "Sat" },
  { value: 0, label: "Sun" },
] as const

export interface SlotWindow {
  starts_at: string
  ends_at: string
  /** Store-timezone label, for messages. */
  label: string
}

/**
 * Dates on which a repeat falls: every selected weekday from `start` for `weeks` weeks
 * (the first 7 * weeks days beginning with the start date).
 */
export function repeatDates(
  start: CalendarDate,
  weekdays: number[],
  weeks: number,
): CalendarDate[] {
  const out: CalendarDate[] = []
  for (let i = 0; i < weeks * 7; i++) {
    const day = addDays(start, i)
    if (weekdays.includes(weekdayOf(day))) out.push(day)
  }
  return out
}

/** UTC start/end of a slot on `date` (store wall times). Null when a time does not exist that day. */
export function buildWindow(
  date: CalendarDate,
  start: { hour: number; minute: number },
  end: { hour: number; minute: number },
  timeZone: string,
): SlotWindow | null {
  const s = zonedTimeToUtc({ ...date, ...start }, timeZone)
  const e = zonedTimeToUtc({ ...date, ...end }, timeZone)
  if (!s || !e) return null
  return {
    starts_at: s.toISOString(),
    ends_at: e.toISOString(),
    label: `${date.year}-${String(date.month).padStart(2, "0")}-${String(date.day).padStart(2, "0")}`,
  }
}
