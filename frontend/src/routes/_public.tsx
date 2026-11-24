import { createFileRoute } from "@tanstack/react-router"

import {
  PublicLayout,
  PublicNotFound,
} from "@/features/content/public/components/PublicLayout"
import { requireModule } from "@/features/modules/api"

// Public site (blog and pages): no login, so it must not live under /_layout.
export const Route = createFileRoute("/_public")({
  beforeLoad: ({ context }) => requireModule(context.queryClient, "content"),
  component: PublicLayout,
  notFoundComponent: PublicNotFound,
})
