import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"

import { UsersService } from "@/client"
import { canManageStore } from "@/features/commerce/api"
import { requireModule } from "@/features/modules/api"

// Guards every /store/* page: the commerce module must be enabled and the user
// must be an admin or superuser (the API enforces the same on its side).
export const Route = createFileRoute("/_layout/store")({
  beforeLoad: async ({ context }) => {
    await requireModule(context.queryClient, "commerce")
    const user = await context.queryClient.ensureQueryData({
      queryKey: ["currentUser"],
      queryFn: async () => (await UsersService.readUserMe()).data,
    })
    if (!canManageStore(user)) {
      throw redirect({ to: "/" })
    }
  },
  component: () => <Outlet />,
})
