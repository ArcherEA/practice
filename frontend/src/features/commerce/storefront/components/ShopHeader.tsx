import { Link } from "@tanstack/react-router"
import { ShoppingCart } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cartCount, useCart } from "../cart"
import { useCurrency } from "../currency"

/** Currency choice; hidden while the store sells in a single currency. */
export function CurrencySwitcher() {
  const { currency, currencies, setCurrency } = useCurrency()
  if (!currency || currencies.length < 2) return null
  return (
    <Select value={currency} onValueChange={setCurrency}>
      <SelectTrigger
        size="sm"
        aria-label="Currency"
        data-testid="currency-switcher"
        className="w-[5.5rem]"
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {currencies.map((c) => (
          <SelectItem key={c.code} value={c.code}>
            {c.code.toUpperCase()}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function CartLink() {
  const count = cartCount(useCart())
  return (
    <Button variant="ghost" size="sm" asChild>
      <Link
        to="/shop/cart"
        data-testid="cart-link"
        aria-label={count > 0 ? `Cart, ${count} items` : "Cart"}
      >
        <ShoppingCart className="size-4" aria-hidden="true" />
        <span data-testid="cart-count" aria-hidden="true">
          {count}
        </span>
      </Link>
    </Button>
  )
}

/** Shop link, currency switcher and cart for the public header (commerce module on). */
export function ShopHeader() {
  return (
    <>
      <Button variant="ghost" size="sm" asChild>
        <Link to="/shop" activeOptions={{ exact: false }}>
          Shop
        </Link>
      </Button>
      <CurrencySwitcher />
      <CartLink />
    </>
  )
}
