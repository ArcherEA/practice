import { createFileRoute, redirect } from "@tanstack/react-router"

import { UsersService } from "@/client"
import ModerationPage from "@/features/community/moderation/ModerationPage"
import { canModerate } from "@/features/community/permissions"
import { requireModule } from "@/features/modules/api"

// Module guard + role guard (moderator, admin, superuser; the API enforces the
// same). Editors are redirected to the dashboard.
export const Route = createFileRoute("/_layout/moderation")({
  beforeLoad: async ({ context }) => {
    await requireModule(context.queryClient, "community")
    const user = await context.queryClient.ensureQueryData({
      queryKey: ["currentUser"],
      queryFn: async () => (await UsersService.readUserMe()).data,
    })
    if (!canModerate(user)) {
      throw redirect({ to: "/" })
    }
  },
  component: ModerationPage,
  head: () => ({ meta: [{ title: "Moderation" }] }),
})
