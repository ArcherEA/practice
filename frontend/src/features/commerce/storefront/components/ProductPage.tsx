import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { useMemo, useState } from "react"

import type { ProductDetail, SlotPublic, VariantOffer } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { resolveBodyImages, toEditorContent } from "@/features/content/body"
import { ContentRenderer } from "@/features/content/components/ContentRenderer"
import { absoluteUrl } from "../../api"
import { formatSlotStart } from "../../time"
import { shopProductOptions } from "../api"
import { addToCart } from "../cart"
import { useCurrency } from "../currency"
import {
  findVariant,
  formatLocalTime,
  initialSelection,
  localTimeZone,
  maxQuantity,
  type Selection,
  unavailableReason,
} from "../offers"

const choiceClass =
  "flex cursor-pointer items-center rounded-md border px-3 py-1.5 text-sm hover:bg-accent has-[:checked]:border-primary has-[:checked]:bg-accent has-[:checked]:font-medium has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring"

function Gallery({ title, urls }: { title: string; urls: string[] }) {
  const [index, setIndex] = useState(0)
  const current = urls[Math.min(index, urls.length - 1)]
  if (urls.length === 0) {
    return (
      <div className="flex aspect-square items-center justify-center rounded-lg border bg-muted text-sm text-muted-foreground">
        No image
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-3">
      <img
        src={absoluteUrl(current)}
        alt={title}
        data-testid="product-image"
        className="aspect-square w-full rounded-lg border object-cover"
      />
      {urls.length > 1 && (
        <ul className="flex flex-wrap gap-2" aria-label="Product images">
          {urls.map((url, i) => (
            <li key={url}>
              <button
                type="button"
                onClick={() => setIndex(i)}
                aria-label={`Show image ${i + 1} of ${urls.length}`}
                aria-current={i === index}
                className={`size-16 overflow-hidden rounded-md border ${i === index ? "ring-2 ring-primary" : ""}`}
              >
                <img
                  src={absoluteUrl(url)}
                  alt=""
                  className="size-full object-cover"
                />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function SlotPicker({
  slots,
  timezone,
  value,
  onChange,
}: {
  slots: SlotPublic[]
  timezone: string
  value: string | null
  onChange: (id: string) => void
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-sm font-medium">Choose a time</legend>
      <p className="text-xs text-muted-foreground">
        Store time is {timezone}; your time is {localTimeZone()}.
      </p>
      <div className="flex flex-col gap-2" data-testid="slot-list">
        {slots.map((slot) => (
          <label
            key={slot.id}
            className={`${choiceClass} justify-between gap-3`}
          >
            <input
              type="radio"
              name="slot"
              value={slot.id}
              checked={value === slot.id}
              onChange={() => onChange(slot.id)}
              className="sr-only"
            />
            <span className="flex flex-col">
              <span>
                {formatSlotStart(slot.starts_at, timezone)}{" "}
                <span className="text-muted-foreground">(store time)</span>
              </span>
              <span className="text-muted-foreground">
                {formatLocalTime(slot.starts_at)} (your time)
              </span>
            </span>
            <span className="text-xs text-muted-foreground">
              {slot.remaining} {slot.remaining === 1 ? "place" : "places"}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}

function Availability({
  product,
  variant,
}: {
  product: ProductDetail
  variant: VariantOffer | undefined
}) {
  const reason = unavailableReason(product, variant)
  if (reason) {
    return (
      <p data-testid="availability">
        <Badge variant="secondary">{reason}</Badge>
      </p>
    )
  }
  const low =
    product.type === "physical" &&
    variant?.stock != null &&
    variant.stock > 0 &&
    variant.stock <= 5
  return (
    <p data-testid="availability" className="text-sm">
      {low ? `Only ${variant?.stock} left` : "In stock"}
    </p>
  )
}

function Purchase({ product }: { product: ProductDetail }) {
  const { format, timezone } = useCurrency()
  const [selection, setSelection] = useState<Selection>(() =>
    initialSelection(product),
  )
  const [slotId, setSlotId] = useState<string | null>(null)
  const [quantityText, setQuantityText] = useState("1")
  const [added, setAdded] = useState<string | null>(null)

  const variant = findVariant(product, selection)
  const slot = product.slots.find((s) => s.id === slotId)
  const isService = product.type === "service"
  const reason = unavailableReason(product, variant)
  const max = variant ? maxQuantity(product, variant, slot) : 1
  const quantity = Math.min(
    Math.max(1, Math.floor(Number(quantityText)) || 1),
    max,
  )
  const canAdd = !reason && !!variant && (!isService || !!slot) && max >= 1

  const choose = (name: string, value: string) => {
    setSelection((s) => ({ ...s, [name]: value }))
    setAdded(null)
  }

  const add = () => {
    if (!variant || !canAdd || variant.price === null) return
    addToCart({
      slug: product.slug,
      variantId: variant.id,
      slotId: isService ? slotId : null,
      quantity,
      price: variant.price,
      currency: product.currency,
    })
    setQuantityText("1")
    setAdded(product.title)
  }

  return (
    <div className="flex flex-col gap-5">
      {product.options.map((option) => (
        <fieldset key={option.name} className="flex flex-col gap-2">
          <legend className="mb-1 text-sm font-medium">{option.name}</legend>
          <div className="flex flex-wrap gap-2">
            {option.values.map((value) => (
              <label key={value} className={choiceClass}>
                <input
                  type="radio"
                  name={`option-${option.name}`}
                  value={value}
                  checked={selection[option.name] === value}
                  onChange={() => choose(option.name, value)}
                  className="sr-only"
                />
                {value}
              </label>
            ))}
          </div>
        </fieldset>
      ))}

      <div className="flex flex-col gap-1">
        <p className="text-2xl font-semibold" data-testid="product-price">
          {variant?.price != null
            ? format(variant.price, product.currency)
            : "—"}
        </p>
        <Availability product={product} variant={variant} />
      </div>

      {isService && product.slots.length > 0 && (
        <SlotPicker
          slots={product.slots}
          timezone={timezone}
          value={slotId}
          onChange={(id) => {
            setSlotId(id)
            setAdded(null)
          }}
        />
      )}

      <div className="flex items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="quantity">Quantity</Label>
          <Input
            id="quantity"
            type="number"
            inputMode="numeric"
            min={1}
            max={max}
            value={quantityText}
            onChange={(e) => setQuantityText(e.target.value)}
            onBlur={() => setQuantityText(String(quantity))}
            className="w-24"
          />
        </div>
        <Button type="button" onClick={add} disabled={!canAdd}>
          Add to cart
        </Button>
      </div>
      {isService && !slot && !reason && (
        <p className="text-sm text-muted-foreground">
          Choose a time to add this to your cart.
        </p>
      )}

      {added && (
        <p
          role="status"
          data-testid="added-to-cart"
          className="rounded-md border bg-muted px-3 py-2 text-sm"
        >
          Added to your cart.{" "}
          <Link to="/shop/cart" className="font-medium underline">
            View cart
          </Link>
        </p>
      )}
    </div>
  )
}

export function ProductPage({ slug }: { slug: string }) {
  const { currency } = useCurrency()
  const query = useQuery({
    ...shopProductOptions(slug, currency ?? ""),
    enabled: !!currency,
    placeholderData: keepPreviousData,
  })
  const product = query.data
  const description = useMemo(
    () =>
      product ? resolveBodyImages(toEditorContent(product.description)) : null,
    [product],
  )

  if (query.isError) {
    return (
      <p role="alert" className="text-destructive">
        This product could not be loaded.
      </p>
    )
  }
  if (!product) return null

  return (
    <article className="flex flex-col gap-8">
      <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground">
        <Link to="/shop" className="hover:underline">
          Shop
        </Link>
        {product.category && (
          <>
            {" / "}
            <Link
              to="/shop/category/$slug"
              params={{ slug: product.category.slug }}
              className="hover:underline"
            >
              {product.category.name}
            </Link>
          </>
        )}
      </nav>
      <div className="grid gap-8 md:grid-cols-2">
        <Gallery title={product.title} urls={product.image_urls} />
        <div className="flex flex-col gap-5">
          <h1 className="text-3xl font-bold leading-tight">{product.title}</h1>
          {/* Key: another product starts with fresh choices; a currency change keeps them. */}
          <Purchase key={product.id} product={product} />
        </div>
      </div>
      {description && (
        <section aria-label="Description" className="max-w-[42rem]">
          <ContentRenderer body={description} />
        </section>
      )}
    </article>
  )
}
