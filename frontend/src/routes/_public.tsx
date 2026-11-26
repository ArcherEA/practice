import { createFileRoute } from "@tanstack/react-router"

import {
  PublicLayout,
  PublicNotFound,
} from "@/features/content/public/components/PublicLayout"
import { requireAnyModule } from "@/features/modules/api"

// Public site (blog, pages, shop): no login, so it must not live under /_layout.
// Each page checks its own module; the layout is shown when any public module is on.
export const Route = createFileRoute("/_public")({
  beforeLoad: ({ context }) =>
    requireAnyModule(context.queryClient, ["content", "commerce"]),
  component: PublicLayout,
  notFoundComponent: PublicNotFound,
})
