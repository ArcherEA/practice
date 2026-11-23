import { createFileRoute } from "@tanstack/react-router"

import NotificationsPage from "@/features/community/notifications/NotificationsPage"
import { requireModule } from "@/features/modules/api"

export const Route = createFileRoute("/_layout/notifications")({
  beforeLoad: ({ context }) => requireModule(context.queryClient, "community"),
  component: NotificationsPage,
  head: () => ({ meta: [{ title: "Notifications" }] }),
})
