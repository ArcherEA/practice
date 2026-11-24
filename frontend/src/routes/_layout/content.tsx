import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"

import { UsersService } from "@/client"
import { canManageContent } from "@/features/content/permissions"
import { requireModule } from "@/features/modules/api"

// Guards every /content/* page: the module must be enabled and the user must
// be an editor, admin or superuser (the API enforces the same on its side).
export const Route = createFileRoute("/_layout/content")({
  beforeLoad: async ({ context }) => {
    await requireModule(context.queryClient, "content")
    const user = await context.queryClient.ensureQueryData({
      queryKey: ["currentUser"],
      queryFn: async () => (await UsersService.readUserMe()).data,
    })
    if (!canManageContent(user)) {
      throw redirect({ to: "/" })
    }
  },
  component: () => <Outlet />,
})
