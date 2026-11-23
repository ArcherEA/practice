import { createFileRoute } from "@tanstack/react-router"

import FollowingPage from "@/features/community/profile/FollowingPage"
import { requireModule } from "@/features/modules/api"

export const Route = createFileRoute("/_layout/following")({
  beforeLoad: ({ context }) => requireModule(context.queryClient, "community"),
  component: FollowingPage,
  head: () => ({ meta: [{ title: "Following" }] }),
})
