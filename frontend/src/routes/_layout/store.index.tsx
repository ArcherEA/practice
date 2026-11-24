import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/store/")({
  beforeLoad: () => {
    throw redirect({ to: "/store/products", replace: true })
  },
})
