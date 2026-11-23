import type { Control, FieldValues, Path } from "react-hook-form"

import type { UserRole } from "@/client"
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ROLE_OPTIONS } from "@/features/auth/permissions"

interface RoleFieldProps<T extends FieldValues & { role?: UserRole }> {
  control: Control<T>
  /** Only superusers may assign the admin role. */
  canAssignAdmin: boolean
  disabled?: boolean
  hint?: string
}

export function RoleField<T extends FieldValues & { role?: UserRole }>({
  control,
  canAssignAdmin,
  disabled,
  hint,
}: RoleFieldProps<T>) {
  return (
    <FormField
      control={control}
      name={"role" as Path<T>}
      render={({ field }) => (
        <FormItem>
          <FormLabel>Role</FormLabel>
          <Select
            value={field.value}
            onValueChange={field.onChange}
            disabled={disabled}
          >
            <FormControl>
              <SelectTrigger className="w-full" aria-label="Role">
                <SelectValue placeholder="Select a role" />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              {ROLE_OPTIONS.filter(
                (o) =>
                  o.value !== "admin" ||
                  canAssignAdmin ||
                  field.value === "admin",
              ).map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {hint && <FormDescription>{hint}</FormDescription>}
          <FormMessage />
        </FormItem>
      )}
    />
  )
}
