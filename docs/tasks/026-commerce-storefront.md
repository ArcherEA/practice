# 026 — Commerce: storefront, currency switcher and cart

**Status:** approved 2026-11-23 · **Agent:** frontend-engineer (+ small backend part) · **Branch:** `feat/026-commerce-storefront` · **Needs:** 024 merged (025 helps with test data but isn't required)

## Scope
- **Public pages** in the public layout (011): `/shop` (grid, category filter, paging), `/shop/category/<slug>`,
  `/shop/<slug>` (image gallery, description, option pickers that resolve to a variant, price, availability, a slot
  picker for services showing the store time and the visitor's local time, quantity, "Add to cart"). A "Shop" link
  in the public header when the module is on.
- **Currency switcher** in the public header: currencies from the API config; default from the browser locale when it
  maps to an allowed currency, else the store default; remembered in `localStorage`. Prices always come from the API
  in that currency (no conversion in the browser).
- **Cart** in `localStorage` (variant id, quantity, slot id), so guests have one too; cart drawer/page with line
  totals. Whenever it opens, re-fetch prices and availability for the chosen currency and flag lines that changed or
  are unavailable (027 checks everything again at checkout). The Checkout button stays disabled until 027/028.
- **SEO (backend part):** `commerce` gets a `public_router` (like content) that injects meta tags for `/shop` and
  `/shop/<slug>` (title, description, first image as `og:image`, `og:type=product`); published products are added to
  `sitemap.xml` when the module is on (D16 pattern, with pytest tests).
- Playwright `tests/commerce-storefront.spec.ts`: browse, pick a variant, switch currency (the price changes), add to
  cart, the cart survives a reload, an unavailable variant can't be added.

## Out of scope
Checkout and payment (027/028), order pages (028).

## New dependencies
None.
