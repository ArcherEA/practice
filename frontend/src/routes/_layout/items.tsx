import { createFileRoute } from "@tanstack/react-router"

import ItemsPage from "@/features/items/components/ItemsPage"
import { requireModule } from "@/features/modules/api"

export const Route = createFileRoute("/_layout/items")({
  beforeLoad: ({ context }) => requireModule(context.queryClient, "items"),
  component: ItemsPage,
  head: () => ({
    meta: [
      {
        title: "Items - FastAPI Template",
      },
    ],
  }),
})
