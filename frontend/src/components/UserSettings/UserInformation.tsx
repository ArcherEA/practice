import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { UsersService, type UserUpdateMe } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import { Textarea } from "@/components/ui/textarea"
import { useModules } from "@/features/modules/useModules"
import useAuth from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { cn } from "@/lib/utils"
import { handleError } from "@/utils"

const formSchema = z.object({
  full_name: z.string().max(30).optional(),
  email: z.email({ message: "Invalid email address" }),
  username: z
    .string()
    .regex(/^[a-z0-9_]{3,30}$/, {
      message: "3-30 characters: lowercase letters, numbers and underscores",
    })
    .optional(),
  bio: z.string().max(500).optional(),
})

const USERNAME_INTERVAL_DAYS = 30

type FormData = z.infer<typeof formSchema>

const UserInformation = () => {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [editMode, setEditMode] = useState(false)
  const { user: currentUser } = useAuth()
  const { isEnabled } = useModules()
  const community = isEnabled("community")
  const nextUsernameChange = (() => {
    if (!currentUser?.username_changed_at) return null
    const next = new Date(currentUser.username_changed_at)
    next.setDate(next.getDate() + USERNAME_INTERVAL_DAYS)
    return next > new Date() ? next.toLocaleDateString() : null
  })()

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      full_name: currentUser?.full_name ?? undefined,
      email: currentUser?.email,
      username: currentUser?.username,
      bio: currentUser?.bio ?? "",
    },
  })

  const toggleEditMode = () => {
    setEditMode(!editMode)
  }

  const mutation = useMutation({
    mutationFn: (data: UserUpdateMe) =>
      UsersService.updateUserMe({ body: data }),
    onSuccess: () => {
      showSuccessToast("User updated successfully")
      toggleEditMode()
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries()
    },
  })

  const onSubmit = (data: FormData) => {
    const updateData: UserUpdateMe = {}

    // only include fields that have changed
    if (data.full_name !== currentUser?.full_name) {
      updateData.full_name = data.full_name
    }
    if (data.email !== currentUser?.email) {
      updateData.email = data.email
    }

    if (community) {
      if (data.username && data.username !== currentUser?.username) {
        updateData.username = data.username
      }
      if ((data.bio ?? "") !== (currentUser?.bio ?? "")) {
        updateData.bio = data.bio ?? ""
      }
    }

    mutation.mutate(updateData)
  }

  const onCancel = () => {
    form.reset()
    toggleEditMode()
  }

  return (
    <div className="max-w-md">
      <h3 className="text-lg font-semibold py-4">User Information</h3>
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="flex flex-col gap-4"
        >
          <FormField
            control={form.control}
            name="full_name"
            render={({ field }) =>
              editMode ? (
                <FormItem>
                  <FormLabel>Full name</FormLabel>
                  <FormControl>
                    <Input type="text" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              ) : (
                <FormItem>
                  <FormLabel>Full name</FormLabel>
                  <p
                    className={cn(
                      "py-2 truncate max-w-sm",
                      !field.value && "text-muted-foreground",
                    )}
                  >
                    {field.value || "N/A"}
                  </p>
                </FormItem>
              )
            }
          />

          <FormField
            control={form.control}
            name="email"
            render={({ field }) =>
              editMode ? (
                <FormItem>
                  <FormLabel>Email</FormLabel>
                  <FormControl>
                    <Input type="email" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              ) : (
                <FormItem>
                  <FormLabel>Email</FormLabel>
                  <p className="py-2 truncate max-w-sm">{field.value}</p>
                </FormItem>
              )
            }
          />

          {community && (
            <>
              <FormField
                control={form.control}
                name="username"
                render={({ field }) =>
                  editMode ? (
                    <FormItem>
                      <FormLabel>Username</FormLabel>
                      <FormControl>
                        <Input
                          type="text"
                          autoCapitalize="none"
                          {...field}
                          onChange={(e) =>
                            field.onChange(e.target.value.toLowerCase())
                          }
                        />
                      </FormControl>
                      <p className="text-xs text-muted-foreground">
                        Your public profile address. It can be changed once
                        every {USERNAME_INTERVAL_DAYS} days
                        {nextUsernameChange
                          ? `; you can change it again on ${nextUsernameChange}`
                          : ""}
                        .
                      </p>
                      <FormMessage />
                    </FormItem>
                  ) : (
                    <FormItem>
                      <FormLabel>Username</FormLabel>
                      <p className="py-2 truncate max-w-sm">
                        @{field.value}{" "}
                        <Link
                          to="/u/$username"
                          params={{ username: currentUser?.username ?? "" }}
                          className="text-sm text-muted-foreground underline underline-offset-4"
                        >
                          View profile
                        </Link>
                      </p>
                    </FormItem>
                  )
                }
              />
              <FormField
                control={form.control}
                name="bio"
                render={({ field }) =>
                  editMode ? (
                    <FormItem>
                      <FormLabel>Bio</FormLabel>
                      <FormControl>
                        <Textarea rows={3} maxLength={500} {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  ) : (
                    <FormItem>
                      <FormLabel>Bio</FormLabel>
                      <p
                        className={cn(
                          "py-2 max-w-sm whitespace-pre-wrap break-words",
                          !field.value && "text-muted-foreground",
                        )}
                      >
                        {field.value || "N/A"}
                      </p>
                    </FormItem>
                  )
                }
              />
            </>
          )}

          <div className="flex gap-3">
            {editMode ? (
              <>
                <LoadingButton
                  type="submit"
                  loading={mutation.isPending}
                  disabled={!form.formState.isDirty}
                >
                  Save
                </LoadingButton>
                <Button
                  type="button"
                  variant="outline"
                  onClick={onCancel}
                  disabled={mutation.isPending}
                >
                  Cancel
                </Button>
              </>
            ) : (
              <Button type="button" onClick={toggleEditMode}>
                Edit
              </Button>
            )}
          </div>
        </form>
      </Form>
    </div>
  )
}

export default UserInformation
