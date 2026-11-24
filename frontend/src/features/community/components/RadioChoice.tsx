import { useId } from "react"

import { Label } from "@/components/ui/label"

export type Choice<T extends string | number> = { value: T; label: string }

/** A small native radio group (the template has no shadcn radio component). */
export function RadioChoice<T extends string | number>({
  legend,
  name,
  choices,
  value,
  onChange,
}: {
  legend: string
  name: string
  choices: Choice<T>[]
  value: T
  onChange: (value: T) => void
}) {
  const prefix = useId()
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-sm font-medium">{legend}</legend>
      {choices.map((choice) => {
        const id = `${prefix}-${choice.value}`
        return (
          <div key={choice.value} className="flex items-center gap-2">
            <input
              type="radio"
              id={id}
              name={name}
              className="size-4 accent-primary"
              checked={value === choice.value}
              onChange={() => onChange(choice.value)}
            />
            <Label htmlFor={id} className="font-normal">
              {choice.label}
            </Label>
          </div>
        )
      })}
    </fieldset>
  )
}
