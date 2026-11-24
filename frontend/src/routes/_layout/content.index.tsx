import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/content/")({
  beforeLoad: () => {
    throw redirect({ to: "/content/posts", replace: true })
  },
})
