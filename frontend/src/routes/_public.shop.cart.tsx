import { createFileRoute } from "@tanstack/react-router"

import { CartPage } from "@/features/commerce/storefront/components/CartPage"
import { requireModule } from "@/features/modules/api"

export const Route = createFileRoute("/_public/shop/cart")({
  beforeLoad: ({ context }) => requireModule(context.queryClient, "commerce"),
  head: () => ({ meta: [{ title: "Cart" }] }),
  component: Cart,
})

function Cart() {
  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-3xl font-bold">Cart</h1>
      <CartPage />
    </section>
  )
}
